"""Chat intent, grounded follow-ups, and the preview/approval boundary."""

import pytest
from fastapi.testclient import TestClient
from operon.config import settings
from operon.conversation import chat_reply
from operon.environment.erp_system import default_erp
from ui.app import app

TASK = "Find the latest invoice from Company X, enter it into ERP, and verify."
HIGH = "Find the latest invoice from OmniCorp, enter it into ERP, and verify."


@pytest.fixture
def chat_client(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "storage_dir", tmp_path)
    with TestClient(app) as client:
        yield client


def send(client, text, run_id=None, mode="execute"):
    response = client.post("/api/chat", json={"task": text, "context_run_id": run_id, "mode": mode})
    assert response.status_code == 200, response.text
    return response.json()


def complete(client, response):
    assert response["kind"] == "run"
    client.app.state.runs.wait_segment()
    return client.get("/api/runs/" + response["run"]["id"]).json()


@pytest.mark.parametrize("text", ["hi", "hello Operon", "thanks", "what can you do?", "okay"])
def test_social_messages_reply_without_starting_work(chat_client, text):
    response = send(chat_client, text)
    assert response["kind"] == "reply" and response["reply"]
    assert chat_client.get("/api/runs").json() == []


def test_goals_and_followups_share_the_recorded_result(chat_client):
    run = complete(chat_client, send(chat_client, TASK, mode="preview"))
    assert run["status"] == "completed"
    # The answer comes from the saved report, even if the current ledger changes.
    default_erp.reset()
    amount = send(chat_client, "How much was it?", run["id"])
    due = send(chat_client, "When is it due?", run["id"])
    checks = send(chat_client, "How did you verify it?", run["id"])
    assert "13,446.00" in amount["reply"]
    assert "2026-04-10" in due["reply"]
    assert "source document integrity" in checks["reply"]
    assert len(chat_client.get("/api/runs").json()) == 1


def test_explicit_followup_can_execute_a_verified_preview(chat_client):
    preview = complete(chat_client, send(chat_client, TASK, mode="preview"))
    assert default_erp.get_invoice("INV-X-2026-003") is None
    executed = complete(chat_client, send(chat_client, "Run it", preview["id"]))
    assert executed["mode"] == "execute" and executed["status"] == "completed"
    assert default_erp.get_invoice("INV-X-2026-003") is not None


def test_preview_button_never_commits_the_followup(chat_client):
    preview = complete(chat_client, send(chat_client, TASK, mode="preview"))
    repeated = complete(chat_client, send(chat_client, "Run it", preview["id"], mode="preview"))
    assert repeated["mode"] == "preview"
    assert default_erp.get_invoice("INV-X-2026-003") is None


@pytest.mark.parametrize("decision,expected", [("approve", "completed"), ("decline", "failed")])
def test_chat_decisions_use_the_existing_pending_approval(chat_client, decision, expected):
    run = complete(chat_client, send(chat_client, HIGH))
    assert run["status"] == "waiting_approval"
    assert default_erp.get_invoice("INV-OMNI-2026-001") is None
    result = complete(chat_client, send(chat_client, decision, run["id"]))
    assert result["status"] == expected
    assert (default_erp.get_invoice("INV-OMNI-2026-001") is not None) is (decision == "approve")


def test_preview_message_cannot_approve_a_real_pending_action(chat_client):
    run = complete(chat_client, send(chat_client, HIGH))
    response = send(chat_client, "approve", run["id"], mode="preview")
    assert response["kind"] == "reply"
    assert chat_client.get("/api/runs/" + run["id"]).json()["status"] == "waiting_approval"
    assert default_erp.get_invoice("INV-OMNI-2026-001") is None


def test_failed_report_answers_are_explicitly_unverified():
    previous = {"packet": {"verification": {"is_verified": False}, "action_log": [{"observation": {"invoice_number": "INV-1", "amount": 100, "due_date": "2026-12-01"}}]}}
    reply = chat_reply("What was the amount?", previous)
    assert "100.00" in reply["reply"] and "did not pass verification" in reply["reply"]


@pytest.mark.parametrize("question", ["When is it due?", "Which vendor was it?", "How much was it?"])
def test_incomplete_failed_observations_do_not_invent_details(question):
    previous = {"packet": {"verification": None, "action_log": [{"observation": {"invoice_number": "INV-1", "amount": "invalid"}}]}}
    reply = chat_reply(question, previous)
    assert reply["kind"] == "reply"
    assert "did not pass verification" in reply["reply"]


def test_missing_context_is_an_explanation_not_a_guessed_action(chat_client):
    assert send(chat_client, "How much was it?")["kind"] == "reply"
    assert send(chat_client, "Run it")["kind"] == "reply"
    assert chat_client.get("/api/runs").json() == []


def test_invalid_context_does_not_start_an_unrelated_task(chat_client):
    response = chat_client.post("/api/chat", json={"task": "How much was it?", "context_run_id": "missing"})
    assert response.status_code == 404
    assert chat_client.get("/api/runs").json() == []
