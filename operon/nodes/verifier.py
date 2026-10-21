"""Verifier Node for Operon.

Performs independent ground-truth verification of the system state
to confirm whether the user's ultimate objective was genuinely achieved.
"""

from typing import Dict, Any, List
from operon.state import OperonState, VerificationResult
from operon.environment.erp_system import default_erp
from operon.memory.scratchpad import Scratchpad

def verifier_node(state: OperonState) -> Dict[str, Any]:
    """Independently audit environment state against task goals."""
    scratchpad = Scratchpad.from_dict(state.get("scratchpad", {}))
    task = state["task"].lower()
    
    checks: List[str] = []
    discrepancies: List[str] = []
    evidence_parts: List[str] = []
    
    # Check 1: Invoice Task Verification
    if "invoice" in task:
        inv_num = scratchpad.get_entity("invoice_number") or scratchpad.get_entity("created_invoice_number")
        expected_amt = scratchpad.get_entity("amount")
        expected_due = scratchpad.get_entity("due_date")
        
        checks.append("Verify invoice presence in ERP system")
        if not inv_num:
            discrepancies.append("No invoice number found in agent working memory.")
        else:
            db_record = default_erp.get_invoice(inv_num)
            if not db_record:
                discrepancies.append(f"Invoice '{inv_num}' is NOT present in the internal ERP database.")
            else:
                checks.append(f"Confirmed invoice record '{inv_num}' exists in ERP ledger")
                evidence_parts.append(f"ERP Record ID: {db_record.get('invoice_number')} (Status: {db_record.get('status')})")
                
                # Check amount
                if expected_amt is not None:
                    checks.append("Verify monetary amount fidelity")
                    actual_amt = float(db_record.get("amount", 0.0))
                    if abs(actual_amt - float(expected_amt)) < 0.01:
                        evidence_parts.append(f"Amount verified: ${actual_amt:,.2f}")
                    else:
                        discrepancies.append(f"Amount mismatch in ERP: expected ${expected_amt}, found ${actual_amt}")
                        
                # Check due date
                if expected_due:
                    checks.append("Verify due date fidelity")
                    actual_due = db_record.get("due_date")
                    if actual_due == expected_due:
                        evidence_parts.append(f"Due date verified: {actual_due}")
                    else:
                        discrepancies.append(f"Due date mismatch in ERP: expected {expected_due}, found {actual_due}")

    # Check 2: Vendor Onboarding Verification
    elif "vendor" in task or "onboard" in task:
        checks.append("Verify vendor registration in ERP")
        vendor_name = scratchpad.get_entity("vendor_name", "Apex")
        v_record = default_erp.find_vendor(vendor_name)
        if v_record:
            evidence_parts.append(f"Registered Vendor: {v_record['name']} (ID: {v_record['vendor_id']}, Status: {v_record['status']})")
        else:
            discrepancies.append(f"Vendor '{vendor_name}' not found in registered vendors table.")

    # Generic fallback verification
    else:
        checks.append("Verify non-empty action execution log")
        if len(state.get("action_history", [])) > 0:
            evidence_parts.append(f"Completed {len(state['action_history'])} actions successfully.")
        else:
            discrepancies.append("No actions were executed.")

    is_verified = (len(discrepancies) == 0)
    score = 1.0 if is_verified else max(0.0, 1.0 - (len(discrepancies) * 0.4))
    
    result = VerificationResult(
        is_verified=is_verified,
        confidence_score=score,
        checks_performed=checks,
        evidence=" | ".join(evidence_parts) if evidence_parts else "No affirmative evidence found.",
        discrepancies=discrepancies
    )
    
    return {
        "verification_result": result,
        "status": "completed" if is_verified else "failed"
    }
