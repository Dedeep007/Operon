"""Unit tests for Operon tools and registry."""

import pytest
from pathlib import Path
from operon.tools.registry import registry
from operon.tools.file_tools import search_files, read_document, extract_invoice_data, find_latest_invoice_file
from operon.tools.erp_tools import erp_lookup_vendor, erp_create_invoice, erp_verify_invoice_status

def test_registry_contains_core_tools():
    tool_names = [t.name for t in registry.list_definitions()]
    assert "find_latest_invoice_file" in tool_names
    assert "read_document" in tool_names
    assert "extract_invoice_data" in tool_names
    assert "erp_lookup_vendor" in tool_names
    assert "erp_create_invoice" in tool_names
    assert "erp_verify_invoice_status" in tool_names

def test_extract_invoice_data_from_text():
    sample_text = """
    COMPANY X SOLUTIONS
    INVOICE #INV-X-2026-003
    Issue Date: March 10, 2026 (2026-03-10)
    Due Date: April 10, 2026 (2026-04-10)
    TOTAL BALANCE DUE: $13,446.00
    """
    data = extract_invoice_data(sample_text)
    assert data["invoice_number"] == "INV-X-2026-003"
    assert data["due_date"] == "2026-04-10"
    assert data["amount"] == 13446.00

def test_extract_invoice_data_from_json():
    json_text = '{"invoice_number": "INV-JSON-99", "issuer": "Vendor Corp", "total_amount": 2500.75, "due_date": "2026-08-15"}'
    data = extract_invoice_data(json_text)
    assert data["invoice_number"] == "INV-JSON-99"
    assert data["amount"] == 2500.75
    assert data["due_date"] == "2026-08-15"

def test_find_latest_invoice_file():
    res = find_latest_invoice_file("Company X")
    assert "file_path" in res
    assert "company_x_inv_2026_03_latest" in res["filename"]
    assert res["invoice_data"]["invoice_number"] == "INV-X-2026-003"
    assert res["invoice_data"]["due_date"] == "2026-04-10"

def test_registry_execute_handles_exceptions_gracefully():
    # Calling with nonexistent tool
    res = registry.execute("non_existent_tool_123")
    assert not res.success
    assert "ToolNotFoundError" in res.error

    # Calling tool with invalid parameters
    res2 = registry.execute("erp_create_invoice", invoice_number="INV-ERR", vendor_id="VND-NONEXISTENT", amount=50.0, due_date="2026-01-01")
    assert not res2.success
    assert "VendorNotFoundError" in res2.error
