"""End-to-End integration tests for Operon Autonomous AI Task Worker."""

import pytest
from operon.agent import OperonAgent
from operon.environment.erp_system import default_erp

def test_autonomous_invoice_processing_end_to_end():
    """Verify the reference task from the Problem Statement runs autonomously to completion."""
    task = "Find the latest invoice from Company X, extract the amount and due date, enter it into our internal system, and tell me once it is done."
    agent = OperonAgent()
    packet = agent.run(task)
    
    assert packet is not None
    assert packet.status == "completed"
    assert packet.total_actions_taken >= 4
    assert packet.execution_time_seconds > 0
    
    # Verify independent auditor result
    assert packet.verification is not None
    assert packet.verification.is_verified is True
    assert packet.verification.confidence_score == 1.0
    
    # Ground-truth verification against internal ERP state
    invoice_record = default_erp.get_invoice("INV-X-2026-003")
    assert invoice_record is not None
    assert invoice_record["vendor_id"] == "VND-001"
    assert invoice_record["due_date"] == "2026-04-10"
    assert invoice_record["amount"] == 13446.00

def test_autonomous_vendor_onboarding_generalization():
    """Verify Operon generalizes to a completely different enterprise task."""
    task = "Read the vendor profile for Apex Technologies and register them into our internal ERP system."
    agent = OperonAgent()
    packet = agent.run(task)
    
    assert packet is not None
    assert packet.status == "completed"
    
    # Verify vendor exists in ERP
    vendor = default_erp.find_vendor("Apex Technologies")
    assert vendor is not None
    assert vendor["status"] == "Active"
