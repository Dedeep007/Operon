"""Unit tests for the Simulated Enterprise ERP System."""

import pytest
from operon.environment.erp_system import ERPSystem, ERPValidationError, ERPNotFoundError

def test_erp_initial_state():
    erp = ERPSystem()
    snapshot = erp.get_state_snapshot()
    assert snapshot["vendor_count"] >= 3
    assert "VND-001" in snapshot["vendors"]
    assert snapshot["vendors"]["VND-001"]["name"] == "Company X Solutions"

def test_erp_find_vendor_by_name_and_alias():
    erp = ERPSystem()
    v1 = erp.find_vendor("Company X Solutions")
    assert v1 is not None
    assert v1["vendor_id"] == "VND-001"
    
    # Alias lookup
    v2 = erp.find_vendor("Company X")
    assert v2 is not None
    assert v2["vendor_id"] == "VND-001"

def test_erp_create_invoice_success():
    erp = ERPSystem()
    inv = erp.create_invoice(
        invoice_number="INV-TEST-001",
        vendor_id="VND-001",
        amount=1250.50,
        due_date="2026-05-01"
    )
    assert inv["invoice_number"] == "INV-TEST-001"
    assert inv["amount"] == 1250.50
    assert inv["status"] == "PENDING"
    
    # Verify invoice in ledger
    fetched = erp.get_invoice("INV-TEST-001")
    assert fetched is not None
    assert fetched["amount"] == 1250.50

def test_erp_create_invoice_duplicate_error():
    erp = ERPSystem()
    erp.create_invoice("INV-DUP-01", "VND-001", 100.0, "2026-05-01")
    with pytest.raises(ERPValidationError) as exc:
        erp.create_invoice("INV-DUP-01", "VND-001", 200.0, "2026-05-01")
    assert "DuplicateInvoiceError" in str(exc.value)

def test_erp_create_invoice_invalid_date():
    erp = ERPSystem()
    with pytest.raises(ERPValidationError) as exc:
        erp.create_invoice("INV-BAD-DATE", "VND-001", 100.0, "May 1st, 2026")
    assert "InvalidDateFormatError" in str(exc.value)

def test_erp_register_new_vendor():
    erp = ERPSystem()
    new_v = erp.register_vendor(
        name="Apex Technologies LLC",
        tax_id="TX-99999",
        payment_terms="Net 45"
    )
    assert new_v["name"] == "Apex Technologies LLC"
    assert new_v["payment_terms"] == "Net 45"
    assert erp.find_vendor("Apex Technologies") is not None

def test_erp_compute_state_diff():
    erp = ERPSystem()
    erp.create_invoice("INV-DIFF-01", "VND-001", 5000.0, "2026-06-01")
    diff = erp.compute_state_diff()
    assert diff["total_new_invoices"] == 1
    assert diff["new_invoices_created"][0]["invoice_number"] == "INV-DIFF-01"
