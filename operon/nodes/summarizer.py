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
    packet = EvidencePacket(task=state["task"], status=status, summary=summary,
        total_actions_taken=len(state.get("action_history", [])),
        execution_time_seconds=round(time.time() - state.get("start_time", time.time()), 3),
        verification=verification, created_records=changed, state_diffs=diff,
        action_log=state.get("action_history", []), plan=state.get("plan", []),
        run_id=state.get("run_id", ""), mode=state.get("mode", "execute"),
        source_documents=state.get("scratchpad", {}).get("source_documents", []),
        policy_checks=state.get("policy_checks", []), errors=state.get("errors", []),
        planner_backend=state.get("planner_backend", "offline"))
    packet.evidence_sha256 = evidence_digest(packet)
    return {"evidence_packet": packet, "status": status}
