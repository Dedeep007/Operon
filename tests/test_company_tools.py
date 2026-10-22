"""Real company-source retrieval, independent checks, and safe source access."""

import json
import shutil
import pytest
from fastapi.testclient import TestClient
from operon.agent import OperonAgent
from operon.config import settings
from operon.environment.erp_system import ERPSystem
from operon.llm import llm_provider
from operon.tools.company_tools import (
    AmbiguousResourceError, CompanySourceError, find_latest_signed_deal,
    read_deal_quotation, search_company_records,
)
from operon.tools.registry import registry
from ui.app import app

GOAL = "Get me the quotation for the latest deal signed."


@pytest.fixture
def company_sources(tmp_path, monkeypatch):
    root = tmp_path / "company"
    for name in ("deals", "quotations"):
        shutil.copytree(settings.sample_data_dir / name, root / name)
    monkeypatch.setattr(settings, "sample_data_dir", root)
    monkeypatch.setattr(settings, "storage_dir", tmp_path / "storage")
    return root


def test_latest_signed_deal_uses_source_dates_and_excludes_drafts(company_sources):
    result = find_latest_signed_deal()
    assert result["deal_record"]["deal_id"] == "DEAL-2026-105"
    assert result["eligible_count"] == 3
    assert len(result["selection_manifest"]) == 4
    assert find_latest_signed_deal("Globex")["deal_record"]["deal_id"] == "DEAL-2026-104"


def test_quotation_goal_really_reads_and_verifies_linked_sources(company_sources):
    erp = ERPSystem()
    before = erp.get_state_snapshot()
    packet = OperonAgent(erp=erp).run(GOAL)
    assert packet.status == "completed" and packet.issue is None
    assert [a.tool_name for a in packet.action_log] == ["find_latest_signed_deal", "read_deal_quotation"]
    assert "QT-2026-105" in packet.agent_message and "24,000.00" in packet.agent_message
    assert len(packet.source_documents) == 2
    assert "Re-read deal catalogue and verify latest signed date" in packet.verification.checks_performed
    assert erp.get_state_snapshot() == before


def test_missing_linked_quotation_stops_without_substituting(company_sources):
    packet = OperonAgent().run("Get the quotation for the latest signed deal with OmniCorp.")
    assert packet.status == "failed" and packet.issue.code == "resource_not_found"
    assert "QT-2026-103" in packet.agent_message and "wasn’t found" in packet.agent_message
    assert "Add the linked quotation" in packet.agent_message
    assert "QT-2026-105" not in packet.agent_message
    assert packet.total_actions_taken == 2
    assert not packet.verification.is_verified and not packet.created_records


@pytest.mark.parametrize("task", ["Get the quotation for Umbrella Labs.", "Get the quotation for the latest deal signed with Umbrella Labs."])
def test_unknown_customer_never_falls_back_to_another_deal(company_sources, task):
    packet = OperonAgent().run(task)
    assert packet.status == "failed"
    assert "Umbrella Labs" in packet.agent_message
    assert packet.issue.code == "resource_not_found"
    assert packet.total_actions_taken == 1


def test_specific_quotation_id_is_not_replaced_with_the_latest(company_sources):
    packet = OperonAgent().run("Get quotation QT-DOES-NOT-EXIST.")
    assert packet.status == "failed" and packet.total_actions_taken == 0
    assert packet.issue.code == "unsupported_task"
    assert "QT-2026-105" not in packet.agent_message


def test_same_signing_date_requires_clarification(company_sources):
    path = company_sources / "deals" / "globex_platform.json"
    deal = json.loads(path.read_text())
    deal["signed_at"] = "2026-10-20"
    path.write_text(json.dumps(deal))
    with pytest.raises(AmbiguousResourceError):
        find_latest_signed_deal()
    packet = OperonAgent().run(GOAL)
    assert packet.status == "failed" and packet.issue.code == "needs_clarification"
    assert "more than one" in packet.agent_message.casefold()


def test_malformed_deal_is_not_silently_ignored(company_sources):
    (company_sources / "deals" / "broken.json").write_text('{"status": "signed"}')
    with pytest.raises(CompanySourceError):
        find_latest_signed_deal()


@pytest.mark.parametrize("field,bad", [("deal_id", "WRONG"), ("amount", 1), ("customer", "Wrong Customer")])
def test_linked_quotation_must_match_signed_deal(company_sources, field, bad):
    path = company_sources / "quotations" / "acme_dispatch.json"
    quote = json.loads(path.read_text())
    quote[field] = bad
    path.write_text(json.dumps(quote))
    with pytest.raises(CompanySourceError):
        read_deal_quotation("DEAL-2026-105")


def test_link_cannot_escape_company_quotation_folder(company_sources):
    path = company_sources / "deals" / "acme_dispatch.json"
    deal = json.loads(path.read_text())
    deal["quotation_file"] = "../deals/acme_dispatch.json"
    path.write_text(json.dumps(deal))
    with pytest.raises(CompanySourceError):
        read_deal_quotation("DEAL-2026-105")


def test_independent_verifier_rejects_incorrect_tool_output(company_sources, monkeypatch):
    original = registry._tools["read_deal_quotation"]
    def corrupt(**args):
        result = original(**args)
        result["quotation_record"]["amount"] = 1
        return result
    monkeypatch.setitem(registry._tools, "read_deal_quotation", corrupt)
    packet = OperonAgent().run(GOAL)
    assert packet.status == "failed" and not packet.verification.is_verified
    assert any("differs from its source" in d for d in packet.verification.discrepancies)
    assert "I found quotation" not in packet.agent_message


def test_deal_catalogue_changes_invalidate_selection(company_sources, monkeypatch):
    original = registry._tools["read_deal_quotation"]
    def change_catalogue(**args):
        result = original(**args)
        path = company_sources / "deals" / "company_x_draft.json"
        data = json.loads(path.read_text())
        data["status"], data["signed_at"] = "signed", "2026-10-21"
        path.write_text(json.dumps(data))
        return result
    monkeypatch.setitem(registry._tools, "read_deal_quotation", change_catalogue)
    packet = OperonAgent().run(GOAL)
    assert packet.status == "failed"
    assert any("catalogue changed" in d for d in packet.verification.discrepancies)


def test_company_search_combines_sources_and_ledger_without_writes(company_sources):
    erp = ERPSystem()
    before = erp.get_state_snapshot()
    packet = OperonAgent(erp=erp).run("Search company records for Acme.")
    assert packet.status == "completed"
    result = packet.action_log[0].observation
    assert {m["kind"] for m in result["matches"]} == {"document", "invoice", "vendor"}
    assert result["total_matches"] >= 4
    assert erp.get_state_snapshot() == before
    assert packet.source_documents


def test_empty_company_search_is_not_success(company_sources):
    packet = OperonAgent().run("Search company records for neverexistingcustomer.")
    assert packet.status == "failed" and packet.issue.code == "resource_not_found"
    assert not packet.verification.is_verified
    assert "No changes were made" in packet.agent_message


def test_unreadable_file_means_search_is_incomplete(company_sources):
    (company_sources / "broken.txt").write_bytes(b"\xff\xfe\xff")
    packet = OperonAgent().run("Search company records for Acme.")
    assert packet.status == "failed" and packet.issue.title == "Search incomplete"
    assert "broken.txt" in packet.action_log[0].observation["skipped_files"]


def test_company_search_limit_is_explicit(company_sources):
    result = search_company_records("Acme", limit=1)
    assert len(result["matches"]) == 1 and result["truncated"]
    assert result["total_matches"] > 1


def test_new_read_tools_work_in_preview(company_sources):
    packet = OperonAgent(mode="preview").run(GOAL)
    assert packet.status == "completed" and packet.mode == "preview"
    assert packet.created_records == []


@pytest.mark.parametrize("mode", ["execute", "preview"])
def test_repair_missing_source_then_retry_same_goal_in_chat(company_sources, mode):
    task = "Get the quotation for the latest signed deal with OmniCorp."
    with TestClient(app) as client:
        first = client.post("/api/chat", json={"task": task, "mode": mode}).json()["run"]
        client.app.state.runs.wait_segment()
        failed = client.get(f"/api/runs/{first['id']}").json()
        assert failed["status"] == "failed"
        why = client.post("/api/chat", json={"task": "What went wrong?", "context_run_id": first["id"]}).json()
        assert why["kind"] == "reply" and "QT-2026-103" in why["reply"]
        assert len(client.get("/api/runs").json()) == 1
        source = json.loads((company_sources / "deals" / "omnicorp_missing_quote.json").read_text())
        quote = {key: source[key] for key in ("quotation_id", "deal_id", "customer", "amount", "currency")}
        quote["valid_until"] = "2026-12-01"
        (company_sources / "quotations" / source["quotation_file"]).write_text(json.dumps(quote))
        retry = client.post("/api/chat", json={"task": "Try again", "context_run_id": first["id"]}).json()["run"]
        client.app.state.runs.wait_segment()
        result = client.get(f"/api/runs/{retry['id']}").json()
        assert result["status"] == "completed" and result["mode"] == mode and result["task"] == task
        followup = client.post("/api/chat", json={"task": "How much was it?", "context_run_id": retry["id"]}).json()
        assert followup["kind"] == "reply" and "9,600.00" in followup["reply"]


def test_source_view_checks_scope_and_captured_hash(company_sources):
    with TestClient(app) as client:
        response = client.post("/api/chat", json={"task": GOAL})
        run_id = response.json()["run"]["id"]
        client.app.state.runs.wait_segment()
        packet = client.get(f"/api/runs/{run_id}").json()["packet"]
        index = next(i for i, d in enumerate(packet["source_documents"]) if "quotations" in d["file_path"])
        url = f"/api/runs/{run_id}/sources/{index}"
        opened = client.get(url)
        assert opened.status_code == 200 and '"QT-2026-105"' in opened.text
        assert opened.headers["x-content-type-options"] == "nosniff"
        path = company_sources / "quotations" / "acme_dispatch.json"
        path.write_text(path.read_text() + "\n")
        assert client.get(url).status_code == 409
        assert client.get(f"/api/runs/{run_id}/sources/-1").status_code == 404
        assert client.get(f"/api/runs/{run_id}/sources/99").status_code == 404
        packet["source_documents"][index]["file_path"] = str(company_sources.parent / "outside.txt")
        client.app.state.runs.store.update(run_id, "completed", packet=packet)
        assert client.get(url).status_code == 403
