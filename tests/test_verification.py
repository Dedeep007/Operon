"""Unit tests for the Independent Outcome Verifier node."""

import pytest
from operon.nodes.verifier import verifier_node
from operon.environment.erp_system import default_erp
from operon.memory.scratchpad import Scratchpad

def test_verifier_detects_successful_invoice_entry():
    # Setup ERP with matching record
    inv_num = "INV-VERIFY-PASS-01"
    default_erp.create_invoice(
        invoice_number=inv_num,
        vendor_id="VND-001",
        amount=13446.00,
        due_date="2026-04-10"
    )
    
    # State where scratchpad has matching details
    scratchpad = Scratchpad()
    scratchpad.record_entity("invoice_number", inv_num)
    scratchpad.record_entity("amount", 13446.00)
    scratchpad.record_entity("due_date", "2026-04-10")
    
    state = {
        "task": "Find latest invoice from Company X, enter into system and tell me when done",
        "plan": [],
        "current_step_index": 4,
        "scratchpad": scratchpad.to_dict(),
        "action_history": [],
        "errors": [],
        "retry_count": {},
        "verification_result": None,
        "evidence_packet": None,
        "requires_approval": False,
        "approval_prompt": None,
        "human_feedback": None,
        "status": "executing",
        "start_time": 0.0,
        "last_execution_result": None
    }
    
    result = verifier_node(state)
    verif = result["verification_result"]
    assert verif.is_verified is True
    assert verif.confidence_score == 1.0
    assert len(verif.discrepancies) == 0
    assert "Amount verified" in verif.evidence
    assert "Due date verified" in verif.evidence
    assert result["status"] == "completed"

def test_verifier_flags_missing_invoice_in_erp():
    scratchpad = Scratchpad()
    scratchpad.record_entity("invoice_number", "INV-NONEXISTENT-999")
    scratchpad.record_entity("amount", 500.0)
    scratchpad.record_entity("due_date", "2026-12-31")
    
    state = {
        "task": "Enter invoice into internal system",
        "plan": [],
        "current_step_index": 4,
        "scratchpad": scratchpad.to_dict(),
        "action_history": [],
        "errors": [],
        "retry_count": {},
        "verification_result": None,
        "evidence_packet": None,
        "requires_approval": False,
        "approval_prompt": None,
        "human_feedback": None,
        "status": "executing",
        "start_time": 0.0,
        "last_execution_result": None
    }
    
    result = verifier_node(state)
    verif = result["verification_result"]
    assert verif.is_verified is False
    assert any("NOT present" in d for d in verif.discrepancies)
    assert result["status"] == "failed"

def test_verifier_flags_amount_mismatch():
    inv_num = "INV-MISMATCH-01"
    default_erp.create_invoice(
        invoice_number=inv_num,
        vendor_id="VND-001",
        amount=1000.00,
        due_date="2026-04-10"
    )
    
    # Scratchpad expected $5,000.00 but ERP had $1,000.00
    scratchpad = Scratchpad()
    scratchpad.record_entity("invoice_number", inv_num)
    scratchpad.record_entity("amount", 5000.00)
    scratchpad.record_entity("due_date", "2026-04-10")
    
    state = {
        "task": "Enter invoice into internal system",
        "plan": [],
        "current_step_index": 4,
        "scratchpad": scratchpad.to_dict(),
        "action_history": [],
        "errors": [],
        "retry_count": {},
        "verification_result": None,
        "evidence_packet": None,
        "requires_approval": False,
        "approval_prompt": None,
        "human_feedback": None,
        "status": "executing",
        "start_time": 0.0,
        "last_execution_result": None
    }
    
    result = verifier_node(state)
    verif = result["verification_result"]
    assert verif.is_verified is False
    assert any("Amount mismatch" in d for d in verif.discrepancies)
