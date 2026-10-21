"""Check the ledger independently against source facts and execution outcomes."""

from pathlib import Path
import hashlib
import re
from operon.state import VerificationResult
from operon.environment.context import get_erp
from operon.memory.scratchpad import Scratchpad
from operon.validation import parse_amount


def verifier_node(state):
    memory = Scratchpad.from_dict(state.get("scratchpad", {}))
    plan = state.get("plan", [])
    checks, discrepancies, evidence = [], [], []
    if state.get("approval_rejected"):
        discrepancies.append("The requested action was declined. No further actions were executed.")
    if any(s.status not in ("completed", "skipped") for s in plan):
        discrepancies.append("One or more planned steps did not complete.")
    elif any(s.status == "skipped" for s in plan) and not memory.get_entity("search_no_results"):
        discrepancies.append("One or more planned steps were skipped due to an earlier failure.")
    for error in state.get("errors", []):
        if error.step_id == 0:
            discrepancies.append(error.message)
    for source in memory.source_documents:
        checks.append("Check source document integrity")
        try:
            actual = hashlib.sha256(Path(source["file_path"]).read_bytes()).hexdigest()
            if actual != source["sha256"]:
                discrepancies.append("A source document changed during execution.")
        except OSError:
            discrepancies.append("A source document is no longer readable.")

    if "invoice" in state["task"].lower():
        source = memory.extracted_data.get("latest_invoice") or memory.extracted_data.get("invoice_source", {})
        if state.get("run_id") and not source:
            discrepancies.append("No source invoice was captured for independent verification.")
        number = source.get("invoice_number") or memory.get_entity("invoice_number")
        checks.append("Verify invoice presence in ERP system")
        record = get_erp().get_invoice(number) if number else None
        if not record:
            discrepancies.append(f"Invoice '{number or 'unknown'}' is NOT present in the internal ERP database.")
        else:
            evidence.append(f"ERP Record ID: {record['invoice_number']}")
            expected = {"amount": source.get("amount", memory.get_entity("amount")),
                        "due_date": source.get("due_date", memory.get_entity("due_date")),
                        "vendor_id": memory.get_entity("vendor_id")}
            if expected["due_date"]:
                iso = re.search(r"\d{4}-\d{2}-\d{2}", str(expected["due_date"]))
                if iso:
                    expected["due_date"] = iso.group(0)
            # Resolve vendor identity directly from the source issuer, independent of tool output.
            if source.get("vendor"):
                vendor = get_erp().find_vendor(source["vendor"])
                expected["vendor_id"] = vendor["vendor_id"] if vendor else "unresolved-source-vendor"
            for field, value in expected.items():
                if value is None:
                    if field != "vendor_id":
                        discrepancies.append(f"Missing source {field}; fidelity cannot be verified.")
                    continue
                checks.append(f"Verify {field.replace('_', ' ')} fidelity")
                try:
                    equal = parse_amount(record[field]) == parse_amount(value) if field == "amount" else record[field] == value
                except (ValueError, TypeError):
                    equal = False
                if equal:
                    label = {"amount": "Amount verified", "due_date": "Due date verified", "vendor_id": "Vendor verified"}[field]
                    evidence.append(f"{label}: {record[field]}")
                else:
                    label = {"amount": "Amount", "due_date": "Due date", "vendor_id": "Vendor"}[field]
                    discrepancies.append(f"{label} mismatch in ERP: expected {value}, found {record[field]}")
    elif any(s.tool_name == "erp_register_vendor" for s in plan):
        profile = memory.extracted_data.get("vendor_profile", {})
        name = profile.get("name") or memory.get_entity("vendor_name")
        checks.append("Verify vendor registration in ERP")
        record = get_erp().find_vendor(name) if name else None
        if not record:
            discrepancies.append(f"Vendor '{name or 'unknown'}' was not found in ERP.")
        elif not profile:
            discrepancies.append("No source vendor profile was captured for independent verification.")
        else:
            if record.get("status") != "Active":
                discrepancies.append("The registered vendor is not active.")
            for field, value in profile.items():
                checks.append(f"Verify vendor {field.replace('_', ' ')}")
                if record.get(field) != value:
                    discrepancies.append(f"Vendor {field} differs from the source profile.")
            evidence.append(f"Registered Vendor: {record['name']} (ID: {record['vendor_id']})")
    elif plan and all(s.status in ("completed", "skipped") for s in plan):
        if memory.get_entity("search_no_results"):
            checks.append("Verify storage search results")
            term = memory.get_entity("searched_term") or state["task"]
            evidence.append(f"Storage search completed: No matching files found for '{term}' in repository storage.")
        elif all(s.status == "completed" for s in plan):
            checks.append("Verify autonomous plan execution outcome")
            if memory.source_documents:
                docs = [Path(d["file_path"]).name for d in memory.source_documents]
                evidence.append(f"Source Document Verified: {', '.join(docs)}")
            elif memory.files_found:
                files = [Path(f).name for f in memory.files_found[:3]]
                evidence.append(f"Matching Files Discovered: {', '.join(files)}")
            else:
                last_action = state.get("action_history", [])[-1] if state.get("action_history") else None
                if last_action and last_action.success:
                    obs_summary = str(last_action.observation)[:120] if last_action.observation else "Success"
                    evidence.append(f"Action '{last_action.tool_name}' verified: {obs_summary}")
                else:
                    evidence.append("All planned steps completed without discrepancy.")
        else:
            discrepancies.append("One or more planned steps did not complete.")
    else:
        discrepancies.append("The requested outcome has no supported independent verifier.")

    verified = not discrepancies
    result = VerificationResult(is_verified=verified,
        confidence_score=1.0 if verified else 0.0, checks_performed=checks,
        evidence=" | ".join(evidence) or "No affirmative evidence found.", discrepancies=discrepancies)
    return {"verification_result": result, "status": "completed" if verified else "failed"}
