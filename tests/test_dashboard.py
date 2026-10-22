"""API contracts, saved-event replay, restart behavior, and worker isolation."""

import json
import re
import threading
import time
import pytest
from fastapi.testclient import TestClient
from operon.config import settings
from operon.environment.erp_system import default_erp
from operon.runs import RunManager, TERMINAL
from operon.tools.registry import registry
from ui.app import app

TASK = "Find the latest invoice from Company X, register it in ERP and verify."
HIGH = "Find the latest invoice from OmniCorp, register it in ERP and verify."


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "storage_dir", tmp_path)
    with TestClient(app) as client:
        yield client


def wait_run(client, run_id, wanted=None):
    for _ in range(200):
        result = client.get(f"/api/runs/{run_id}").json()
        if result["status"] in (wanted or TERMINAL):
            return result
        time.sleep(0.01)
    raise AssertionError("Run did not reach expected state")


def test_dashboard_and_preview_evidence_download(client):
    page = client.get("/")
    assert page.status_code == 200
    assert re.search(r"/static/app\.js\?v=[a-f0-9]{12}", page.text)
    assert re.search(r"/static/style\.css\?v=[a-f0-9]{12}", page.text)
    assert page.headers["cache-control"] == "no-cache"
    assert page.text.count("open data-always-open") == 4
    script = client.get(re.search(r'src="([^"]*app\.js\?v=[a-f0-9]{12})"', page.text).group(1))
    assert script.status_code == 200
    assert 'querySelectorAll("details[data-always-open]")' in script.text
    assert 'detail.open = true' in script.text
    before = client.get("/api/erp/state").json()
    created = client.post("/api/runs", json={"task": TASK, "mode": "preview"})
    assert created.status_code == 202
    run_id = created.json()["id"]
    run = wait_run(client, run_id)
    assert run["status"] == "completed"
    report = client.get(f"/api/runs/{run_id}/evidence")
    assert report.status_code == 200
    assert "attachment" in report.headers["content-disposition"]
    assert report.json()["mode"] == "preview"
    assert client.get("/api/erp/state").json() == before
    assert client.get("/api/runs").json()[0]["id"] == run_id


def test_approval_api_busy_reset_stale_and_decline(client):
    run_id = client.post("/api/runs", json={"task": HIGH}).json()["id"]
    run = wait_run(client, run_id, {"waiting_approval"})
    assert client.post("/api/runs", json={"task": TASK}).status_code == 409
    assert client.post("/api/erp/reset").status_code == 409
    assert client.delete("/api/runs").status_code == 409
    assert client.post(f"/api/runs/{run_id}/approval", json={"approval_id": "stale", "approved": True}).status_code == 409
    assert client.post(f"/api/runs/{run_id}/approval", json={"approval_id": run["approval"]["approval_id"], "approved": "yes"}).status_code == 422
    assert default_erp.get_invoice("INV-OMNI-2026-001") is None
    assert client.post(f"/api/runs/{run_id}/approval", json={"approval_id": run["approval"]["approval_id"], "approved": False}).status_code == 202
    result = wait_run(client, run_id)
    assert result["status"] == "failed"
    assert default_erp.get_invoice("INV-OMNI-2026-001") is None


def test_saved_sse_events_replay_and_cursor(client):
    run_id = client.post("/api/runs", json={"task": TASK}).json()["id"]
    wait_run(client, run_id)
    stream = client.get(f"/api/runs/{run_id}/events")
    records = [json.loads(line[6:]) for line in stream.text.splitlines() if line.startswith("data: ")]
    assert records[0]["event"] == "start"
    assert records[-1] == {"seq": records[-1]["seq"], "event": "end", "status": "completed"}
    cursor = records[-2]["seq"]
    tail = client.get(f"/api/runs/{run_id}/events", headers={"Last-Event-ID": str(cursor)})
    assert tail.text.count("data: ") == 1
    assert '"event": "end"' in tail.text
    assert client.get(f"/api/runs/{run_id}/events", headers={"Last-Event-ID":"invalid"}).status_code == 400


def test_event_is_saved_before_work_finishes(tmp_path, monkeypatch):
    started, release = threading.Event(), threading.Event()
    original = registry._tools["find_latest_invoice_file"]
    def delayed(**args):
        started.set()
        assert release.wait(5)
        return original(**args)
    monkeypatch.setitem(registry._tools, "find_latest_invoice_file", delayed)
    manager = RunManager(tmp_path / "runs.db")
    try:
        run = manager.start(TASK)
        assert started.wait(5)
        events = manager.store.events(run["id"])
        assert any(e.get("node") == "planner" for e in events)
        assert not any(e["event"] == "end" for e in events)
        assert manager.store.get(run["id"])["status"] == "running"
    finally:
        release.set()
        manager.close()


def test_server_restart_retains_history_and_marks_pending_interrupted(tmp_path):
    path = tmp_path / "runs.db"
    first = RunManager(path)
    run = first.start(HIGH)
    first.wait_segment()
    assert first.store.get(run["id"])["status"] == "waiting_approval"
    first.close()
    restarted = RunManager(path)
    try:
        stored = restarted.store.get(run["id"])
        assert stored["status"] == "interrupted"
        assert stored["approval"] is None
        assert "restarted" in stored["error"]
        assert default_erp.get_invoice("INV-OMNI-2026-001") is None
    finally:
        restarted.close()


@pytest.mark.parametrize("body", [{"task":" "},{"task":"x"*4001},{"task":TASK,"mode":"other"}])
def test_invalid_task_requests(client, body):
    assert client.post("/api/runs", json=body).status_code == 422


def test_missing_runs_return_404(client):
    assert client.get("/api/runs/missing").status_code == 404
    assert client.get("/api/runs/missing/evidence").status_code == 404


def test_saved_history_can_be_cleared_when_idle(client):
    run_id = client.post("/api/runs", json={"task": TASK}).json()["id"]
    wait_run(client, run_id)
    assert client.get("/api/runs").json()
    cleared = client.delete("/api/runs")
    assert cleared.status_code == 200
    assert cleared.json() == {"deleted_runs": 1}
    assert client.get("/api/runs").json() == []
    assert client.get(f"/api/runs/{run_id}").status_code == 404


def test_restricted_source_approval_is_explained_and_recorded(client):
    task = "Read the vendor profile for Apex and register them in ERP."
    run_id = client.post("/api/runs", json={"task": task}).json()["id"]
    first = wait_run(client, run_id, {"waiting_approval"})
    approval = first["approval"]
    assert approval["data_classification"] == "RESTRICTED"
    assert approval["approval_scope"] == "all_modes"
    assert approval["resource"].startswith("Vendor profile")
    client.post(
        f"/api/runs/{run_id}/approval",
        json={"approval_id": approval["approval_id"], "approved": True},
    )
    second = wait_run(client, run_id, {"waiting_approval"})
    assert second["approval"]["tool_name"] == "erp_register_vendor"
    assert "***" in second["approval"]["tool_args"]["tax_id"]
    client.post(
        f"/api/runs/{run_id}/approval",
        json={"approval_id": second["approval"]["approval_id"], "approved": True},
    )
    completed = wait_run(client, run_id)
    checks = completed["packet"]["policy_checks"]
    assert [check["decision"] for check in checks] == ["approved", "approved"]
    assert client.get(f"/api/runs/{run_id}/sources/0").status_code == 200
