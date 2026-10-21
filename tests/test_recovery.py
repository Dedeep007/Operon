"""Unit tests for the Self-Healing Replanner and Error Recovery."""

import pytest
from operon.nodes.replanner import replanner_node
from operon.state import PlanStep, ErrorRecord
from operon.memory.scratchpad import Scratchpad

def test_replanner_recovers_from_string_formatted_amount():
    # Simulate step failing because amount was "$13,446.00" instead of float
    failing_step = PlanStep(
        step_id=3,
        description="Enter invoice into ERP",
        tool_name="erp_create_invoice",
        tool_args={"invoice_number": "INV-REC-01", "vendor_id": "VND-001", "amount": "$13,446.00", "due_date": "2026-04-10"},
        expected_outcome="Success",
        status="failed"
    )
    
    error = ErrorRecord(
        step_id=3,
        error_type="ERPValidationError",
        message="InvalidAmountError: Amount '$13,446.00' must be a positive number."
    )
    
    state = {
        "task": "Enter invoice",
        "plan": [failing_step],
        "current_step_index": 0,
        "scratchpad": Scratchpad().to_dict(),
        "action_history": [],
        "errors": [error],
        "retry_count": {"step_3": 1},
        "requires_approval": False,
        "status": "replanning"
    }
    
    res = replanner_node(state)
    assert res["status"] == "executing"
    fixed_step = res["plan"][0]
    assert fixed_step.tool_args["amount"] == 13446.00
    assert fixed_step.status == "pending"
    assert "Normalized amount" in error.recovery_strategy

def test_replanner_recovers_from_non_iso_date_format():
    # Simulate step failing because date was written in text
    failing_step = PlanStep(
        step_id=3,
        description="Enter invoice into ERP",
        tool_name="erp_create_invoice",
        tool_args={"invoice_number": "INV-REC-02", "vendor_id": "VND-001", "amount": 500.0, "due_date": "Due: 2026-04-10 end of business"},
        expected_outcome="Success",
        status="failed"
    )
    
    error = ErrorRecord(
        step_id=3,
        error_type="ERPValidationError",
        message="InvalidDateFormatError: Due date must follow ISO format YYYY-MM-DD."
    )
    
    state = {
        "task": "Enter invoice",
        "plan": [failing_step],
        "current_step_index": 0,
        "scratchpad": Scratchpad().to_dict(),
        "action_history": [],
        "errors": [error],
        "retry_count": {"step_3": 1},
        "requires_approval": False,
        "status": "replanning"
    }
    
    res = replanner_node(state)
    assert res["status"] == "executing"
    fixed_step = res["plan"][0]
    assert fixed_step.tool_args["due_date"] == "2026-04-10"
    assert fixed_step.status == "pending"

def test_replanner_skips_after_max_retries():
    failing_step = PlanStep(
        step_id=1,
        description="Unrecoverable action",
        tool_name="nonexistent_tool",
        tool_args={},
        expected_outcome="Success",
        status="failed"
    )
    
    error = ErrorRecord(
        step_id=1,
        error_type="FatalError",
        message="Unrecoverable service failure."
    )
    
    state = {
        "task": "Some task",
        "plan": [failing_step],
        "current_step_index": 0,
        "scratchpad": Scratchpad().to_dict(),
        "action_history": [],
        "errors": [error],
        "retry_count": {"step_1": 5},  # > max_retries (3)
        "requires_approval": False,
        "status": "replanning"
    }
    
    res = replanner_node(state)
    assert res["plan"][0].status == "skipped"
    assert res["current_step_index"] == 1
    assert res["status"] == "verifying"
