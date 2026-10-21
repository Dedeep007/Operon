"""High-level client with isolated previews and resumable approval checkpoints."""

import time
import uuid
from langgraph.types import Command
from operon.graph import create_operon_graph
from operon.environment.erp_system import default_erp
from operon.environment.context import use_erp


class ApprovalRequired(RuntimeError):
    def __init__(self, approval):
        self.approval = approval
        super().__init__(approval["prompt"])


class OperonAgent:
    def __init__(self, thread_id=None, *, mode="execute", erp=None):
        if mode not in {"execute", "preview"}:
            raise ValueError("Mode must be execute or preview.")
        self.thread_id = thread_id or f"run_{uuid.uuid4().hex}"
        self.mode = mode
        source = erp if erp is not None else default_erp
        self.erp = source.clone() if mode == "preview" else source
        self.config = {"configurable": {"thread_id": self.thread_id}, "recursion_limit": 150}
        self.app = create_operon_graph()

    def _initial_state(self, task):
        if not task.strip():
            raise ValueError("Please enter a task.")
        return {
            "task": task.strip(), "plan": [], "current_step_index": 0, "scratchpad": {},
            "action_history": [], "errors": [], "retry_count": {}, "verification_result": None,
            "evidence_packet": None, "requires_approval": False, "approval_prompt": None,
            "human_feedback": None, "status": "planning", "start_time": time.time(),
            "last_execution_result": None, "run_id": self.thread_id, "mode": self.mode,
            "baseline_snapshot": self.erp.get_state_snapshot(), "baseline_audit_count": len(self.erp.audit_log),
            "approved_action": None, "approval_rejected": False, "policy_checks": [],
        }

    @property
    def pending_approval(self):
        snapshot = self.app.get_state(self.config)
        for task in snapshot.tasks:
            if task.interrupts:
                return task.interrupts[0].value
        return None

    def _invoke(self, graph_input):
        with use_erp(self.erp):
            result = self.app.invoke(graph_input, config=self.config)
        if result.get("__interrupt__"):
            raise ApprovalRequired(result["__interrupt__"][0].value)
        return result.get("evidence_packet")

    def run(self, task):
        return self._invoke(self._initial_state(task))

    def resume(self, approved):
        if not isinstance(approved, bool) or not self.pending_approval:
            raise ValueError("A boolean decision and a pending approval are required.")
        return self._invoke(Command(resume=approved))

    def stream(self, task):
        with use_erp(self.erp):
            yield from self.app.stream(self._initial_state(task), config=self.config)

    def resume_stream(self, approved):
        if not isinstance(approved, bool) or not self.pending_approval:
            raise ValueError("A boolean decision and a pending approval are required.")
        with use_erp(self.erp):
            yield from self.app.stream(Command(resume=approved), config=self.config)
