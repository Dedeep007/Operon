"""Local run history and incremental events for the single-worker prototype."""

import json
import sqlite3
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from operon.agent import OperonAgent
from operon.environment.erp_system import default_erp

TERMINAL = {"completed", "failed", "partially_completed", "interrupted"}


class RunBusyError(ValueError):
    pass


class RunStore:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS runs (
                    id TEXT PRIMARY KEY, task TEXT NOT NULL, mode TEXT NOT NULL,
                    status TEXT NOT NULL, created_at TEXT NOT NULL,
                    packet TEXT, approval TEXT, error TEXT
                );
                CREATE TABLE IF NOT EXISTS events (
                    seq INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT NOT NULL, payload TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS events_by_run ON events(run_id, seq);
            """)

    def connect(self):
        return sqlite3.connect(self.path, timeout=10)

    def create(self, agent, task):
        with self.connect() as db:
            db.execute("INSERT INTO runs(id,task,mode,status,created_at) VALUES(?,?,?,?,?)",
                (agent.thread_id, task, agent.mode, "queued", datetime.now(timezone.utc).isoformat()))

    def update(self, run_id, status, *, packet=None, approval=None, error=None):
        with self.connect() as db:
            db.execute("UPDATE runs SET status=?, packet=COALESCE(?,packet), approval=?, error=? WHERE id=?",
                (status, json.dumps(packet) if packet else None, json.dumps(approval) if approval else None, error, run_id))

    def append(self, run_id, payload):
        with self.connect() as db:
            db.execute("INSERT INTO events(run_id,payload) VALUES(?,?)", (run_id, json.dumps(payload)))

    def finish(self, run_id, status, *, packet=None, error=None):
        # Publish completion and the terminal event together so subscribers cannot miss it.
        with self.connect() as db:
            db.execute("UPDATE runs SET status=?,packet=?,approval=NULL,error=? WHERE id=?",
                (status, json.dumps(packet) if packet else None, error, run_id))
            if error:
                db.execute("INSERT INTO events(run_id,payload) VALUES(?,?)",
                    (run_id, json.dumps({"event": "error", "message": error})))
            db.execute("INSERT INTO events(run_id,payload) VALUES(?,?)",
                (run_id, json.dumps({"event": "end", "status": status})))

    def get(self, run_id):
        with self.connect() as db:
            db.row_factory = sqlite3.Row
            row = db.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone()
        if not row:
            raise KeyError(run_id)
        result = dict(row)
        for key in ("packet", "approval"):
            result[key] = json.loads(result[key]) if result[key] else None
        return result

    def list(self, limit=30):
        with self.connect() as db:
            db.row_factory = sqlite3.Row
            return [dict(r) for r in db.execute(
                "SELECT id,task,mode,status,created_at,error FROM runs ORDER BY created_at DESC LIMIT ?", (limit,))]

    def events(self, run_id, after=0):
        with self.connect() as db:
            return [{"seq": seq, **json.loads(payload)} for seq, payload in db.execute(
                "SELECT seq,payload FROM events WHERE run_id=? AND seq>? ORDER BY seq LIMIT 100", (run_id, after))]

    def recover_interrupted(self):
        with self.connect() as db:
            ids = [r[0] for r in db.execute("SELECT id FROM runs WHERE status IN ('queued','running','waiting_approval')")]
        for run_id in ids:
            message = "The server restarted. This run cannot resume; review the ledger before starting a new task."
            self.finish(run_id, "interrupted", error=message)


def node_event(node, data):
    def dump(value):
        if hasattr(value, "model_dump"):
            return value.model_dump(mode="json")
        if isinstance(value, list):
            return [dump(v) for v in value]
        if isinstance(value, dict):
            return {k: dump(v) for k, v in value.items()}
        return value
    payload = {"event": "node_update", "node": node}
    for key in ("status", "current_step_index", "plan", "scratchpad", "errors", "policy_checks", "planner_backend"):
        if key in data:
            payload[key] = dump(data[key])
    if data.get("action_history"):
        payload["action"] = dump(data["action_history"][-1])
    for key, target in (("verification_result", "verification"), ("evidence_packet", "evidence_packet")):
        if data.get(key):
            payload[target] = dump(data[key])
    return payload


class RunManager:
    """One active task keeps shared ledger changes attributable to one run."""

    def __init__(self, path):
        self.store = RunStore(path)
        self.store.recover_interrupted()
        self._pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="operon-worker")
        self._lock = threading.RLock()
        self._active = None
        self._agent = None
        self._future = None

    def start(self, task, mode="execute"):
        with self._lock:
            if self._active:
                raise RunBusyError("A task is already active. Complete or decline its approval before starting another.")
            agent = OperonAgent(mode=mode)
            self.store.create(agent, task)
            self._active, self._agent = agent.thread_id, agent
            self._future = self._pool.submit(self._drive, agent, agent.stream(task), True)
            return self.store.get(agent.thread_id)

    def _drive(self, agent, events, initial=False):
        run_id = agent.thread_id
        try:
            self.store.update(run_id, "running")
            if initial:
                self.store.append(run_id, {"event": "start", "run_id": run_id, "mode": agent.mode})
            packet = None
            for event in events:
                if "__interrupt__" in event:
                    # Publish only after the graph generator exits and its checkpoint is readable.
                    continue
                for node, data in event.items():
                    payload = node_event(node, data)
                    self.store.append(run_id, payload)
                    if payload.get("evidence_packet"):
                        packet = payload["evidence_packet"]
            approval = agent.pending_approval
            if approval:
                self.store.update(run_id, "waiting_approval", approval=approval)
                self.store.append(run_id, {"event": "approval_required", "approval": approval})
                return
            if packet is None:
                raise RuntimeError("Execution ended without evidence.")
            self.store.finish(run_id, packet["status"], packet=packet)
        except Exception as exc:
            message = f"Execution stopped: {type(exc).__name__}: {exc}"
            self.store.finish(run_id, "failed", error=message)
        finally:
            with self._lock:
                if self.store.get(run_id)["status"] in TERMINAL:
                    self._active, self._agent = None, None

    def decide(self, run_id, approval_id, approved):
        with self._lock:
            run = self.store.get(run_id)
            if self._active != run_id or not self._agent or run["status"] != "waiting_approval":
                raise ValueError("This run has no pending approval in the current server session.")
            if run["approval"]["approval_id"] != approval_id:
                raise ValueError("This approval is stale or does not match the pending action.")
            self.store.update(run_id, "running")
            self.store.append(run_id, {"event": "approval_decision", "approved": approved})
            self._future = self._pool.submit(self._drive, self._agent, self._agent.resume_stream(approved))
            return self.store.get(run_id)

    def wait_segment(self):
        self._future.result(timeout=120)

    def reset_erp(self):
        with self._lock:
            if self._active:
                raise RunBusyError("Finish the active task before resetting the ERP.")
            default_erp.reset()
            return default_erp.get_state_snapshot()

    def close(self):
        self._pool.shutdown(wait=True)
