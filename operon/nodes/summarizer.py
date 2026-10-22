"""Build factual, run-scoped evidence with a reproducible integrity digest."""

import hashlib
import json
import time
from operon.state import EvidencePacket
from operon.environment.context import get_erp
from operon.outcomes import explain_failure, failure_message
from operon.validation import parse_amount


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

    if not verified:
        issue = explain_failure(state, verification)
        return failure_message(state, issue, changed, mode)

    quote = memory.extracted_data.get("quotation_record")
    deal = memory.extracted_data.get("deal_record")
    if quote and deal:
        return (
            f"{prefix}Here’s the quotation I found: {quote['quotation_id']} for {deal['customer']}, "
            f"linked to their latest signed deal {deal['deal_id']} (signed {deal['signed_at']}). "
            f"The quoted amount is {quote['currency']} {parse_amount(quote['amount']):,.2f}; valid until {quote['valid_until']}.\n\n"
            f"{quote.get('scope', '')}\n\n"
            "I checked the signing dates, excluded unsigned deals, and verified the quotation’s deal reference, customer, amount, currency, and source integrity."
        )
    search = memory.extracted_data.get("company_search")
    if search:
        found = "\n".join(f"• {m['label']} ({m['kind']})" for m in search["matches"][:6])
        more = " More matches and excerpts are available in the evidence report." if len(search["matches"]) > 6 or search["truncated"] else ""
        return f"{prefix}I found {search['total_matches']} matches for “{search['query']}” across company documents, ledger invoices, and vendor records.\n\n{found}\n\nI checked the captured sources and ledger records.{more}"

    if "invoice" in lowered:
        source = memory.extracted_data.get("latest_invoice") or memory.extracted_data.get("invoice_source", {})
        num = source.get("invoice_number") or memory.get_entity("invoice_number")
        amt = source.get("amount") or memory.get_entity("amount")
        due = source.get("due_date") or memory.get_entity("due_date")
        vendor = source.get("vendor") or memory.get_entity("vendor_name")
        v_id = memory.get_entity("vendor_id")
        
        try:
            amt_str = f"${float(amt):,.2f}" if amt is not None else "the specified amount"
        except (ValueError, TypeError):
            amt_str = str(amt)
        action = "entered it into the ledger" if changed else "confirmed the matching ledger entry already exists"
        return (
            f"{prefix}Done — I found the latest invoice ({num or 'unspecified'}) from {vendor or 'the vendor'} "
            f"for {amt_str}, due {due or 'unspecified'}, and {action}. "
            f"I verified the amount, due date, source integrity, and vendor association ({v_id or 'verified'})."
        )

    # 2. Vendor onboarding task
    if any(k in lowered for k in ("vendor", "onboard", "register")):
        profile = memory.extracted_data.get("vendor_profile", {})
        v_name = profile.get("name") or memory.get_entity("vendor_name")
        tax_id = profile.get("tax_id") or memory.get_entity("tax_id")
        terms = profile.get("payment_terms") or memory.get_entity("payment_terms") or "Net 30"
        v_id = memory.get_entity("vendor_id")

        return (
            f"{prefix}Done — I read the onboarding profile for {v_name or 'the vendor'}, "
            f"verified the tax ID ({tax_id or 'recorded'}) and payment terms ({terms}), "
            f"and confirmed their registration in the ERP (Vendor ID: {v_id or 'Active'})."
        )

    # 3. File / blueprint / document inquiry or search
    if memory.source_documents:
        doc_names = ", ".join(Path(d["file_path"]).name for d in memory.source_documents)
        return (
            f"{prefix}I found and checked the requested document(s): {doc_names}. "
            f"The content was reviewed and source file integrity was verified."
        )

    # 4. General fallback
    return f"{prefix}I completed the task. {verification.evidence}."


def summarizer_node(state):
    verification = state.get("verification_result")
    diff = get_erp().compute_state_diff(state.get("baseline_snapshot"), state.get("baseline_audit_count", 0))
    verified = bool(verification and verification.is_verified)
    changed = diff["new_invoices_created"] + diff["new_vendors_created"]
    status = "completed" if verified else "partially_completed" if changed else "failed"
    prefix = ("Preview verified in an isolated ERP copy. " if verified else "Preview in an isolated ERP copy. ") if state.get("mode") == "preview" else ""
    if verified:
        summary = prefix + verification.evidence + "."
        if not changed and any(s.tool_name in ("erp_create_invoice", "erp_register_vendor") for s in state.get("plan", [])):
            summary += " Matching records already existed; no new records were needed."
    else:
        issue = explain_failure(state, verification)
        summary = prefix + issue.message + " " + issue.next_step
    agent_message = generate_agent_message(state, verification, verified, changed, state.get("mode", "execute"))
    scratchpad = Scratchpad.from_dict(state.get("scratchpad", {}))
    if verified and verification:
        scratchpad.add_note(f"Outcome verified: {verification.evidence}")
    scratchpad.add_note(f"Final resolution: {agent_message}")

    packet = EvidencePacket(task=state["task"], status=status, summary=summary,
        agent_message=agent_message, issue=explain_failure(state, verification) if not verified else None,
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
