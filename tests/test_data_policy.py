"""Sensitive-resource classification, approval scope, redaction, and path confinement."""

import pytest

from operon.agent import ApprovalRequired, OperonAgent
from operon.config import settings
from operon.safety.approval import safety_controller
from operon.safety.data_policy import classify_resource, redact_action_args
from operon.tools.file_tools import read_document, search_files


def test_vendor_profiles_are_explicitly_restricted():
    path = settings.sample_data_dir / "vendors" / "new_vendor_apex_tech.json"
    classification = classify_resource(path)
    assert classification.data_classification == "RESTRICTED"
    assert classification.requires_approval
    assert classification.approval_scope == "all_modes"
    assert "tax identifier" in classification.data_categories


def test_invoice_sources_are_known_confidential_but_readable_internally():
    path = settings.sample_data_dir / "invoices" / "company_x_inv_2026_03_latest.txt"
    classification = classify_resource(path)
    assert classification.data_classification == "CONFIDENTIAL"
    assert not classification.requires_approval


def test_source_evidence_carries_its_classification():
    packet = OperonAgent().run(
        "Find the latest invoice from Company X, enter it into ERP, and verify."
    )
    assert packet.source_documents[0]["data_classification"] == "CONFIDENTIAL"
    assert "financial record" in packet.source_documents[0]["data_categories"]


def test_restricted_read_requires_approval_even_in_preview():
    agent = OperonAgent(mode="preview")
    with pytest.raises(ApprovalRequired):
        agent.run("Read the vendor profile for Apex and register them in ERP.")
    approval = agent.pending_approval
    assert approval["data_classification"] == "RESTRICTED"
    assert approval["approval_scope"] == "all_modes"
    assert approval["one_time"] is True
    packet = agent.resume(True)
    assert packet.status == "completed" and packet.mode == "preview"
    decisions = {check["decision"] for check in packet.policy_checks}
    assert {"approved", "would_require_on_execution"} <= decisions


def test_vendor_registration_needs_a_second_exact_action_approval():
    agent = OperonAgent()
    with pytest.raises(ApprovalRequired):
        agent.run("Read the vendor profile for Apex and register them in ERP.")
    first_id = agent.pending_approval["approval_id"]
    with pytest.raises(ApprovalRequired):
        agent.resume(True)
    second = agent.pending_approval
    assert second["approval_id"] != first_id
    assert second["tool_name"] == "erp_register_vendor"
    assert second["tool_args"]["tax_id"].startswith("TX-")
    assert "***" in second["tool_args"]["tax_id"]
    packet = agent.resume(True)
    assert packet.status == "completed"
    assert [item["decision"] for item in packet.policy_checks] == ["approved", "approved"]


def test_secret_arguments_are_redacted_before_review():
    shown = redact_action_args({
        "headers": {"Authorization": "Bearer private", "X-Trace": "safe"},
        "content": "confidential body",
    })
    assert shown["headers"]["Authorization"] == "[REDACTED]"
    assert shown["headers"]["X-Trace"] == "safe"
    assert shown["content"] == "[content: 17 characters]"


def test_file_tools_reject_paths_outside_company_roots():
    outside = settings.base_dir / "README.md"
    with pytest.raises(PermissionError, match="ResourceScopeError"):
        read_document(file_path=str(outside))
    with pytest.raises(PermissionError, match="ResourceScopeError"):
        search_files(pattern="*", directory=str(settings.base_dir))


def test_external_mutations_and_secret_api_calls_are_gated():
    form = safety_controller.evaluate_step(
        "browser_fill_form", {"url": "https://portal.internal/vendors/onboard", "form_data": {"name": "Apex"}}
    )
    api = safety_controller.evaluate_step(
        "api_request", {"method": "GET", "url": "https://example.test", "headers": {"Authorization": "secret"}}
    )
    assert form.requires_approval and form.approval_scope == "execution"
    assert api.requires_approval and api.approval_scope == "all_modes"
    assert api.data_classification == "RESTRICTED"
