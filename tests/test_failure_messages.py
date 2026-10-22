"""Failure replies must be useful, factual, and consistent with verification."""

import json
import pytest
from operon.agent import OperonAgent
from operon.config import settings
from operon.environment.erp_system import ERPSystem
from operon.llm import llm_provider
from operon.tools.registry import registry


def plan_step(number, tool, args):
    return {"step_id": number, "description": tool, "tool_name": tool,
            "tool_args": args, "expected_outcome": "Requested outcome"}


@pytest.mark.parametrize("tool,args", [("search_files", {"pattern": "*no_such_quotation_999*"}),
                                       ("search_company_records", {"query": "no_such_quotation_999"})])
def test_missing_document_stops_dependent_writes_and_explains_scope(monkeypatch, tool, args):
    plan = [plan_step(1, tool, args),
            plan_step(2, "read_document", {"file_path": "{{file_path}}"}),
            plan_step(3, "erp_register_vendor", {"name": "Should not be created", "tax_id": "NOT-REAL"})]
    monkeypatch.setattr(llm_provider, "invoke", lambda messages: json.dumps({"steps": plan}))
    erp = ERPSystem()
    before = erp.get_state_snapshot()
    packet = OperonAgent(erp=erp).run("Find a quotation document")
    assert packet.status == "failed" and not packet.verification.is_verified
    assert packet.total_actions_taken == 1
    assert packet.issue.code == "resource_not_found"
    assert "No changes were made" in packet.agent_message
    assert "customer, deal, or filename" in packet.agent_message
    assert "no supported independent verifier" not in packet.agent_message
    assert erp.get_state_snapshot() == before


def test_a_read_document_does_not_mask_a_later_tool_failure(monkeypatch):
    path = settings.sample_data_dir / "invoices" / "company_x_inv_2026_03_latest.txt"
    plan = [plan_step(1, "read_document", {"file_path": str(path)}),
            plan_step(2, "api_request", {"url": "https://sandbox.example.invalid"})]
    monkeypatch.setattr(llm_provider, "invoke", lambda messages: json.dumps({"steps": plan}))
    monkeypatch.setattr(settings, "max_retries", 0)
    def unavailable(**args):
        raise ConnectionError("Technical failure retained in evidence")
    monkeypatch.setitem(registry._tools, "api_request", unavailable)
    packet = OperonAgent().run("Read a source document and request the service")
    assert packet.source_documents and packet.status == "failed"
    assert packet.issue.code == "tool_failed"
    assert "I couldn’t complete the service request" in packet.agent_message
    assert "completed your task" not in packet.agent_message
    assert "Technical failure" not in packet.agent_message
    assert any("Technical failure" in e.message for e in packet.errors)


def test_an_explicit_alternate_search_can_recover(monkeypatch):
    plan = [plan_step(1, "search_files", {"pattern": "*missing_999*"}),
            plan_step(2, "search_files", {"pattern": "*company_x_inv_2026_03*"}),
            plan_step(3, "read_document", {"file_path": "{{file_path}}"})]
    monkeypatch.setattr(llm_provider, "invoke", lambda messages: json.dumps({"steps": plan}))
    packet = OperonAgent().run("Find the source document with an alternate search")
    assert packet.status == "completed" and packet.issue is None
    assert packet.total_actions_taken == 3


def test_partial_write_failure_is_disclosed(monkeypatch):
    original = registry._tools["erp_create_invoice"]
    monkeypatch.setitem(registry._tools, "erp_create_invoice", lambda **args: original(**{**args, "amount": 1}))
    packet = OperonAgent(erp=ERPSystem()).run("Process the latest invoice from Company X and verify.")
    assert packet.status == "partially_completed"
    assert packet.issue.code == "verification_failed"
    assert "not been rolled back" in packet.agent_message
    assert "No changes were made" not in packet.agent_message
    assert "can’t mark this task complete" in packet.agent_message
