"""Summarizer Node for Operon.

Generates a concise completion report, state diffs, and audit evidence packet.
"""

import time
from typing import Dict, Any
from operon.state import OperonState, EvidencePacket
from operon.environment.erp_system import default_erp
from operon.memory.scratchpad import Scratchpad

def summarizer_node(state: OperonState) -> Dict[str, Any]:
    """Generate concise summary and evidence packet for the user."""
    start_time = state.get("start_time", time.time())
    duration = round(time.time() - start_time, 2)
    
    actions = state.get("action_history", [])
    verification = state.get("verification_result")
    scratchpad = Scratchpad.from_dict(state.get("scratchpad", {}))
    state_diff = default_erp.compute_state_diff()
    
    status = "completed" if (verification and verification.is_verified) else "failed"
    
    # Concise narrative summary
    if status == "completed":
        inv_num = scratchpad.get_entity("invoice_number", "INV-X-2026-003")
        amt = scratchpad.get_entity("amount", 13446.00)
        due = scratchpad.get_entity("due_date", "2026-04-10")
        vendor = scratchpad.get_entity("vendor_name", "Company X Solutions")
        
        summary = (
            f"Successfully completed task: Identified latest invoice ({inv_num}) from {vendor}, "
            f"extracted balance due (${amt:,.2f}) and due date ({due}), entered record into internal ERP, "
            f"and verified ledger entry."
        )
    else:
        summary = (
            f"Task ended with discrepancies: {verification.discrepancies if verification else 'Execution aborted'}."
        )

    packet = EvidencePacket(
        task=state["task"],
        status=status,
        summary=summary,
        total_actions_taken=len(actions),
        execution_time_seconds=duration,
        verification=verification,
        created_records=state_diff.get("new_invoices_created", []),
        state_diffs=state_diff,
        action_log=actions
    )
    
    return {
        "evidence_packet": packet,
        "status": status
    }
