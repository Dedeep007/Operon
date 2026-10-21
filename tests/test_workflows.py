"""Behavioral coverage for generalization, previews, approvals, and evidence."""

import json
import pytest
from operon.agent import OperonAgent, ApprovalRequired
from operon.environment.erp_system import ERPSystem, ERPValidationError
from operon.llm import llm_provider
from operon.nodes.executor import executor_node
from operon.nodes.summarizer import evidence_digest
from operon.safety.approval import safety_controller
from operon.state import PlanStep
from operon.tools.registry import registry
from operon.tools.erp_tools import erp_create_invoice
from operon.validation import parse_amount


def invoice_task(company):
    return f"Find the latest invoice from {company}, enter it into ERP, and verify."


@pytest.mark.parametrize("company,number,vendor,amount", [
    ("Company X", "INV-X-2026-003", "VND-001", 13446),
    ("Acme Logistics", "INV-ACM-2026-002", "VND-002", 14280.50),
    ("Globex Software", "INV-GLX-2026-002", "VND-003", 6850),
])
def test_source_driven_invoice_workflows(company, number, vendor, amount):
    erp = ERPSystem()
    packet = OperonAgent(erp=erp).run(invoice_task(company))
    assert packet.status == "completed"
    assert erp.get_invoice(number)["vendor_id"] == vendor
    assert erp.get_invoice(number)["amount"] == amount
    assert len(packet.source_documents) == 1
    assert len(packet.source_documents[0]["sha256"]) == 64


@pytest.mark.parametrize("company", ["Apex", "Quantum", "Horizon", "Cyberdyne"])
def test_vendor_profiles_generalize(company):
    erp = ERPSystem()
    packet = OperonAgent(erp=erp).run(f"Read the vendor profile for {company} and register them in ERP.")
    assert packet.status == "completed"
    assert packet.created_records[0]["name"].startswith(company)
    assert "invoice" not in packet.summary.lower()
    assert packet.state_diffs["total_new_vendors"] == 1


def test_preview_isolated_and_reports_policy():
    erp = ERPSystem()
    before = erp.get_state_snapshot()
    packet = OperonAgent(mode="preview", erp=erp).run(invoice_task("OmniCorp"))
    assert packet.status == "completed"
    assert packet.mode == "preview"
    assert packet.created_records[0]["amount"] == 48500
    assert len(packet.policy_checks) == 1
    assert erp.get_state_snapshot() == before
    assert erp.audit_log == []


@pytest.mark.parametrize("approved", [True, False])
def test_high_value_action_really_pauses(approved):
    erp = ERPSystem()
    agent = OperonAgent(erp=erp)
    with pytest.raises(ApprovalRequired):
        agent.run(invoice_task("OmniCorp"))
    assert erp.get_invoice("INV-OMNI-2026-001") is None
    assert agent.pending_approval["tool_args"]["amount"] == 48500
    packet = agent.resume(approved)
    assert (erp.get_invoice("INV-OMNI-2026-001") is not None) is approved
    assert packet.status == ("completed" if approved else "failed")
    if not approved:
        assert all(s.status == "skipped" for s in packet.plan[2:])
    with pytest.raises(ValueError):
        agent.resume(True)


def test_approval_applies_to_only_one_action(monkeypatch):
    plan = [{"step_id": i, "description": "Create invoice", "tool_name": "erp_create_invoice",
        "tool_args": {"invoice_number": f"INV-HIGH-{i}", "vendor_id": "VND-001", "amount": 30000,
                      "due_date": "2026-12-01"}, "expected_outcome": "Created"} for i in (1, 2)]
    monkeypatch.setattr(llm_provider, "invoke", lambda messages: json.dumps({"steps": plan}))
    erp, agent = ERPSystem(), None
    agent = OperonAgent(erp=erp)
    with pytest.raises(ApprovalRequired):
        agent.run("Enter two invoices")
    first = agent.pending_approval["approval_id"]
    with pytest.raises(ApprovalRequired):
        agent.resume(True)
    assert erp.get_invoice("INV-HIGH-1") is not None
    assert erp.get_invoice("INV-HIGH-2") is None
    assert agent.pending_approval["approval_id"] != first
    agent.resume(False)
    assert erp.get_invoice("INV-HIGH-2") is None


def test_formatted_amount_cannot_bypass_approval():
    assert safety_controller.evaluate_step("erp_create_invoice", {"amount": "$48,500.00"}).requires_approval


def test_preview_blocks_non_sandbox_writes(tmp_path):
    path = tmp_path / "must-not-exist.txt"
    step = PlanStep(step_id=1, description="Write", tool_name="write_file",
        tool_args={"file_path": str(path), "content": "hello"}, expected_outcome="Written")
    result = executor_node({"plan": [step], "current_step_index": 0, "mode": "preview"})
    assert result["last_execution_result"]["error_type"] == "PreviewBlockedError"
    assert not path.exists()


def test_repeated_task_is_idempotent_and_diff_is_per_run():
    erp = ERPSystem()
    first = OperonAgent(erp=erp).run(invoice_task("Company X"))
    before = erp.get_state_snapshot()
    second = OperonAgent(erp=erp).run(invoice_task("Company X"))
    third = OperonAgent(erp=erp).run("Onboard the vendor Quantum into ERP")
    assert first.state_diffs["total_new_invoices"] == 1
    assert second.status == "completed" and second.created_records == []
    assert erp.get_invoice("INV-X-2026-003") == before["invoices"]["INV-X-2026-003"]
    assert erp.vendors["VND-001"]["balance_owed"] == before["vendors"]["VND-001"]["balance_owed"]
    assert third.state_diffs["total_new_invoices"] == 0
    assert third.state_diffs["total_new_vendors"] == 1


def test_corrupt_created_amount_does_not_replace_source_expectation(monkeypatch):
    original = registry._tools["erp_create_invoice"]
    def corrupt(**args):
        return original(**{**args, "amount": 1})
    monkeypatch.setitem(registry._tools, "erp_create_invoice", corrupt)
    packet = OperonAgent(erp=ERPSystem()).run(invoice_task("Company X"))
    assert packet.status == "partially_completed"
    assert not packet.verification.is_verified
    assert any("Amount mismatch" in error for error in packet.verification.discrepancies)


def test_evidence_digest_detects_changed_report():
    packet = OperonAgent(erp=ERPSystem()).run(invoice_task("Company X"))
    assert evidence_digest(packet) == packet.evidence_sha256
    tampered = packet.model_dump(mode="json")
    tampered["summary"] = "Changed"
    assert evidence_digest(tampered) != packet.evidence_sha256


def test_unsupported_goal_cannot_report_success():
    erp = ERPSystem()
    before = erp.get_state_snapshot()
    packet = OperonAgent(erp=erp).run("Delete every customer and send an email")
    assert packet.status == "failed"
    assert packet.total_actions_taken == 0
    assert packet.errors[0].error_type == "ClarificationRequired"
    assert erp.get_state_snapshot() == before


def test_missing_invoice_identity_is_not_fabricated():
    with pytest.raises(ERPValidationError, match="source invoice number"):
        erp_create_invoice(amount=100, vendor_id="VND-001", due_date="2026-12-01")


@pytest.mark.parametrize("value", [-1, "-$50.00", "$-50.00", "NaN", float("inf"), True, "abc100", "1,23", 0])
def test_amount_validation_never_discards_bad_input(value):
    with pytest.raises(ValueError):
        parse_amount(value)


@pytest.mark.parametrize("date", ["2026-02-30", "2026-13-01", "2026-00-10"])
def test_erp_rejects_impossible_calendar_dates(date):
    with pytest.raises(ERPValidationError, match="InvalidDateFormatError"):
        ERPSystem().create_invoice("INV-DATE", "VND-001", 100, date)
