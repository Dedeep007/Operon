"""Enterprise Resource Planning (ERP) tools for Operon."""

from typing import Dict, Any, List, Optional
from operon.tools.registry import registry
from operon.environment.erp_system import ERPValidationError, ERPNotFoundError
from operon.environment.context import get_erp
from operon.validation import parse_amount

@registry.register(
    name="erp_lookup_vendor",
    description="Search internal ERP records for a vendor by company name, alias, or vendor ID. Returns vendor details including vendor_id and payment_terms."
)
def erp_lookup_vendor(
    query: Optional[str] = None,
    company_name: Optional[str] = None,
    vendor_name: Optional[str] = None,
    name: Optional[str] = None,
    vendor_id: Optional[str] = None
) -> Dict[str, Any]:
    """Find a vendor in the internal accounting system."""
    target = query or company_name or vendor_name or name or vendor_id
    if not target:
        raise ERPValidationError("A vendor name or ID is required.")
    vendor = get_erp().find_vendor(target)
    if not vendor:
        raise ERPNotFoundError(f"VendorNotFoundError: No vendor found matching '{target}'.")
    return vendor

@registry.register(
    name="erp_create_invoice",
    description="Enter a new invoice record into the internal accounting/ERP system. Requires invoice_number, vendor_id, amount (float), and due_date (YYYY-MM-DD)."
)
def erp_create_invoice(
    invoice_number: Optional[str] = None,
    vendor_id: Optional[str] = None,
    amount: Optional[Any] = None,
    due_date: Optional[str] = None,
    **kwargs
) -> Dict[str, Any]:
    """Create a new invoice entry in the ERP ledger."""
    inv_num = invoice_number or kwargs.get("id") or kwargs.get("invoice_num")
    if not inv_num or "{{" in str(inv_num):
        raise ERPValidationError("MissingContextError: A source invoice number is required.")
    v_id = vendor_id or kwargs.get("vendor")
    raw_amount = amount if amount is not None else kwargs.get("total_amount")
    due = due_date or kwargs.get("due")
    if not v_id or not due:
        raise ERPValidationError("MissingContextError: Vendor ID and due date are required.")
    
    # Auto-clean amount if passed as string e.g. "$13,446.00"
    try:
        parsed_amount = parse_amount(raw_amount)
    except ValueError as exc:
        raise ERPValidationError(f"InvalidAmountError: {exc}") from exc

    existing = get_erp().get_invoice(str(inv_num))
    if existing and existing["vendor_id"] == str(v_id) and existing["amount"] == parsed_amount and existing["due_date"] == str(due):
        return {**existing, "already_exists": True}

    return get_erp().create_invoice(
        invoice_number=str(inv_num),
        vendor_id=str(v_id),
        amount=parsed_amount,
        due_date=str(due)
    )

@registry.register(
    name="erp_get_invoice",
    description="Query internal ERP for an invoice by its invoice number."
)
def erp_get_invoice(invoice_number: Optional[str] = None, invoice_num: Optional[str] = None, **kwargs) -> Dict[str, Any]:
    """Fetch invoice record from internal system."""
    target = invoice_number or invoice_num or kwargs.get("id")
    if not target:
        raise ERPValidationError("invoice_number is required.")
    inv = get_erp().get_invoice(str(target))
    if not inv:
        raise ERPNotFoundError(f"InvoiceNotFoundError: Invoice '{target}' does not exist in the ERP.")
    return inv

@registry.register(
    name="erp_list_invoices",
    description="List all invoices in the internal system, optionally filtered by vendor_id."
)
def erp_list_invoices(vendor_id: Optional[str] = None, **kwargs) -> List[Dict[str, Any]]:
    """List invoices from ERP."""
    return get_erp().list_invoices(vendor_id=vendor_id)

@registry.register(
    name="erp_register_vendor",
    description="Register a new company/vendor in the internal ERP system with tax ID and payment terms."
)
def erp_register_vendor(
    name: Optional[str] = None,
    company_name: Optional[str] = None,
    tax_id: Optional[str] = None,
    payment_terms: str = "Net 30",
    contact_email: str = "",
    **kwargs
) -> Dict[str, Any]:
    """Register a new vendor."""
    v_name = name or company_name or kwargs.get("vendor_name", "")
    t_id = tax_id or kwargs.get("tax_identification_number", "")
    return get_erp().register_vendor(
        name=str(v_name),
        tax_id=str(t_id),
        payment_terms=payment_terms,
        contact_email=contact_email
    )

@registry.register(
    name="erp_verify_invoice_status",
    description="Perform an independent verification check on whether an invoice exists in the ERP and matches expected amount and due date."
)
def erp_verify_invoice_status(
    invoice_number: Optional[str] = None,
    expected_amount: Optional[Any] = None,
    expected_due_date: Optional[str] = None,
    **kwargs
) -> Dict[str, Any]:
    """Verify invoice existence and field fidelity."""
    target = invoice_number or kwargs.get("invoice_num") or kwargs.get("id")
    if not target:
        return {"verified": False, "reason": "No invoice number provided for verification."}
        
    inv = get_erp().get_invoice(str(target))
    if not inv:
        return {
            "verified": False,
            "reason": f"Invoice '{target}' not found in internal ERP."
        }
        
    mismatches = []
    if expected_amount is not None:
        try:
            exp_f = parse_amount(expected_amount)
            actual_amt = float(inv.get("amount", 0.0))
            if round(actual_amt, 2) != round(exp_f, 2):
                mismatches.append(f"Amount mismatch: expected {exp_f}, found {actual_amt}")
        except (ValueError, TypeError):
            mismatches.append("Expected amount is invalid; verification cannot pass.")
            
    if expected_due_date is not None:
        actual_due = inv.get("due_date", "")
        if actual_due != str(expected_due_date):
            mismatches.append(f"Due date mismatch: expected {expected_due_date}, found {actual_due}")
            
    return {
        "verified": len(mismatches) == 0,
        "invoice_record": inv,
        "mismatches": mismatches
    }

@registry.register(
    name="erp_delete_record",
    description="HIGH RISK: Delete a record from the ERP ledger. Requires explicit human approval.",
    is_high_risk=True,
    requires_approval=True
)
def erp_delete_record(record_type: str, record_id: str) -> str:
    """Simulated destructive deletion action."""
    raise NotImplementedError("Record deletion is outside this prototype's supported workflows.")
