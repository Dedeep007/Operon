"""Bounded recovery using known facts; permanent failures stop dependent work."""

import re
from datetime import date
from operon.config import settings
from operon.memory.scratchpad import Scratchpad
from operon.validation import parse_amount


def replanner_node(state):
    plan = list(state["plan"])
    index = state["current_step_index"]
    step = plan[index]
    errors = list(state.get("errors", []))
    error = errors[-1] if errors else None
    retries = state.get("retry_count", {}).get(f"step_{step.step_id}", 0)
    memory = Scratchpad.from_dict(state.get("scratchpad", {}))

    def stop(reason):
        for remaining in plan[index:]:
            remaining.status = "skipped"
        if error:
            error.recovery_strategy = reason
        return {"plan": plan, "errors": errors, "current_step_index": len(plan),
                "requires_approval": False, "human_feedback": None, "status": "verifying"}

    def retry(reason):
        step.status = "pending"
        if error:
            error.recovery_strategy = reason
        return {"plan": plan, "errors": errors, "scratchpad": memory.to_dict(), "status": "executing"}

    if retries > settings.max_retries:
        return stop(f"Skipped step after {retries} attempts; stopped dependent actions.")
    message = error.message if error else ""
    if "InvalidAmountError" in message:
        raw = step.tool_args.get("amount")
        try:
            value = parse_amount(raw)
            if value != raw:
                step.tool_args["amount"] = value
                memory.record_entity("amount", value)
                return retry(f"Normalized amount from '{raw}' to float {value}")
        except ValueError:
            pass
        return stop("The amount is invalid. Provide a positive, finite monetary amount.")
    if "InvalidDateFormatError" in message:
        raw = str(step.tool_args.get("due_date", ""))
        match = re.search(r"\d{4}-\d{2}-\d{2}", raw)
        if match and match.group(0) != raw:
            try:
                value = date.fromisoformat(match.group(0)).isoformat()
                step.tool_args["due_date"] = value
                memory.record_entity("due_date", value)
                return retry(f"Extracted ISO date '{value}' from '{raw}'")
            except ValueError:
                pass
        return stop("The due date is invalid. Supply a real calendar date in YYYY-MM-DD format.")
    if "VendorNotFoundError" in message:
        known = memory.get_entity("vendor_id")
        if step.tool_name == "erp_create_invoice" and known and known != step.tool_args.get("vendor_id"):
            step.tool_args["vendor_id"] = known
            return retry(f"Resolved vendor_id to '{known}' from working memory")
        return stop("The source vendor could not be resolved. Check the registered vendor or onboard it first.")
    if error and error.error_type == "FileNotFoundError":
        if step.tool_name == "find_latest_invoice_file":
            fallback = str(settings.sample_data_dir / "invoices")
            if step.tool_args.get("directory") and step.tool_args["directory"] != fallback:
                step.tool_args["directory"] = fallback
                return retry("Redirected directory path to verified sample data storage")
            return stop(error.message or "No matching source invoice found in storage.")
        return stop(error.message or "Requested document was not found in storage.")
    if any(term in message for term in ("DuplicateInvoiceError", "DuplicateVendorError", "MissingContextError", "PreviewBlockedError")):
        return stop("The action cannot proceed with the available information. Check the source data and ledger conflict.")
    return retry("Retrying after an unexpected tool failure; attempts are capped.")
