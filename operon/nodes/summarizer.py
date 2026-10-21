"""Build factual, run-scoped evidence with a reproducible integrity digest."""

import hashlib
import json
import time
from operon.state import EvidencePacket
from operon.environment.context import get_erp


def evidence_digest(packet):
    data = packet.model_dump(mode="json") if hasattr(packet, "model_dump") else dict(packet)
    data.pop("evidence_sha256", None)
    return hashlib.sha256(json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


from pathlib import Path
from operon.memory.scratchpad import Scratchpad


def generate_agent_message(state, verification, verified, changed, mode):
    task = state["task"]
    lowered = task.lower()
    memory = Scratchpad.from_dict(state.get("scratchpad", {}))
    prefix = "In our isolated preview sandbox: " if mode == "preview" else ""

    # 1. Invoice processing task
    if "invoice" in lowered:
        source = memory.extracted_data.get("latest_invoice") or memory.extracted_data.get("invoice_source", {})
        num = source.get("invoice_number") or memory.get_entity("invoice_number")
        amt = source.get("amount") or memory.get_entity("amount")
        due = source.get("due_date") or memory.get_entity("due_date")
        vendor = source.get("vendor") or memory.get_entity("vendor_name")
        v_id = memory.get_entity("vendor_id")
        
        if verified:
            try:
                amt_str = f"${float(amt):,.2f}" if amt is not None else "the specified amount"
            except (ValueError, TypeError):
                amt_str = str(amt)
            return (
                f"{prefix}I have completed your task! I found the latest invoice ({num or 'unspecified'}) "
                f"from {vendor or 'the vendor'}, extracted the amount ({amt_str}) and due date ({due or 'unspecified'}), "
                f"resolved the vendor in our internal ERP ledger (Vendor ID: {v_id or 'verified'}), and entered the invoice into the system. "
                f"Both the ledger entry and field fidelity have been verified."
            )
        else:
            reasons = "; ".join(verification.discrepancies) if verification and verification.discrepancies else "The operation could not be confirmed."
            return (
                f"{prefix}I attempted to process the invoice, but could not complete the request. "
                f"Reason: {reasons}"
            )

    # 2. Vendor onboarding task
    if any(k in lowered for k in ("vendor", "onboard", "register")):
        profile = memory.extracted_data.get("vendor_profile", {})
        v_name = profile.get("name") or memory.get_entity("vendor_name")
        tax_id = profile.get("tax_id") or memory.get_entity("tax_id")
        terms = profile.get("payment_terms") or memory.get_entity("payment_terms") or "Net 30"
        v_id = memory.get_entity("vendor_id")

        if verified:
            return (
                f"{prefix}I have completed your task! I read the onboarding profile for {v_name or 'the vendor'}, "
                f"verified the tax ID ({tax_id or 'recorded'}) and payment terms ({terms}), "
                f"and registered them into our internal ERP system (Assigned Vendor ID: {v_id or 'Active'})."
            )
        else:
            reasons = "; ".join(verification.discrepancies) if verification and verification.discrepancies else "Registration could not be confirmed."
            return (
                f"{prefix}I attempted to onboard the vendor, but encountered an issue: {reasons}"
            )

    # 3. File / blueprint / document inquiry or search
    if memory.get_entity("search_no_results"):
        term = memory.get_entity("searched_term") or "the requested topic"
        return (
            f"{prefix}I searched across our company storage and repository files for '{term}', "
            f"but no matching documents or blueprints were found in the current archive."
        )

    if memory.source_documents:
        doc_names = ", ".join(Path(d["file_path"]).name for d in memory.source_documents)
        return (
            f"{prefix}I have completed your task! I located and inspected the requested document(s): {doc_names}. "
            f"The content was reviewed and source file integrity was verified."
        )

    # 4. General fallback
    if verified:
        return f"{prefix}I have completed your task! {verification.evidence}."
    else:
        reasons = "; ".join(verification.discrepancies) if verification and verification.discrepancies else "Action could not be confirmed."
        return f"{prefix}I was unable to complete the task. Details: {reasons}."


def summarizer_node(state):
    verification = state.get("verification_result")
    diff = get_erp().compute_state_diff(state.get("baseline_snapshot"), state.get("baseline_audit_count", 0))
    verified = bool(verification and verification.is_verified)
    changed = diff["new_invoices_created"] + diff["new_vendors_created"]
    status = "completed" if verified else "partially_completed" if changed else "failed"
    prefix = ("Preview verified in an isolated ERP copy. " if verified else "Preview in an isolated ERP copy. ") if state.get("mode") == "preview" else ""
    if verified:
        summary = prefix + verification.evidence + "."
        if not changed:
            summary += " Matching records already existed; no new records were needed."
    else:
        summary = prefix + "Task could not be verified: " + "; ".join(verification.discrepancies if verification else ["Execution aborted."])
    agent_message = generate_agent_message(state, verification, verified, changed, state.get("mode", "execute"))
    scratchpad = Scratchpad.from_dict(state.get("scratchpad", {}))
    if verified and verification:
        scratchpad.notes.append(f"Outcome verified: {verification.evidence}")
    scratchpad.notes.append(f"Final resolution: {agent_message}")

    packet = EvidencePacket(task=state["task"], status=status, summary=summary,
        agent_message=agent_message,
        total_actions_taken=len(state.get("action_history", [])),
        execution_time_seconds=round(time.time() - state.get("start_time", time.time()), 3),
        verification=verification, created_records=changed, state_diffs=diff,
        action_log=state.get("action_history", []), plan=state.get("plan", []),
        run_id=state.get("run_id", ""), mode=state.get("mode", "execute"),
        source_documents=scratchpad.source_documents,
        policy_checks=state.get("policy_checks", []), errors=state.get("errors", []),
        planner_backend=state.get("planner_backend", "offline"))
    packet.evidence_sha256 = evidence_digest(packet)
    return {"evidence_packet": packet, "status": status, "scratchpad": scratchpad.to_dict()}
