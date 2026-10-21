"""Replanner Node for Operon.

Diagnoses execution failures and autonomously implements recovery strategies:
parameter normalization, fallback alternative tools, or human clarification.
"""

import re
from typing import Dict, Any
from operon.state import OperonState
from operon.config import settings
from operon.memory.scratchpad import Scratchpad

def replanner_node(state: OperonState) -> Dict[str, Any]:
    """Autonomous error recovery and adaptive replanning."""
    plan = list(state["plan"])
    idx = state["current_step_index"]
    current_step = plan[idx]
    
    errors = list(state.get("errors", []))
    latest_error = errors[-1] if errors else None
    
    step_key = f"step_{current_step.step_id}"
    retries = state.get("retry_count", {}).get(step_key, 0)
    
    if retries > settings.max_retries:
        # If human gave feedback or automatic mode, skip failing step and proceed
        current_step.status = "skipped"
        next_idx = idx + 1
        if latest_error:
            latest_error.recovery_strategy = f"Skipped step after {retries} attempts."
        return {
            "plan": plan,
            "current_step_index": next_idx,
            "requires_approval": False,
            "human_feedback": None,
            "status": "verifying" if next_idx >= len(plan) else "executing"
        }

    err_msg = latest_error.message if latest_error else ""
    err_type = latest_error.error_type if latest_error else ""
    scratchpad = Scratchpad.from_dict(state.get("scratchpad", {}))
    
    # Strategy 1: Amount formatting / type mismatch recovery
    if "InvalidAmountError" in err_msg or "amount" in err_msg.lower():
        raw_amt = str(current_step.tool_args.get("amount", ""))
        cleaned = re.sub(r"[^\d.]", "", raw_amt)
        try:
            fixed_amt = float(cleaned)
            current_step.tool_args["amount"] = fixed_amt
            scratchpad.record_entity("amount", fixed_amt)
            latest_error.recovery_strategy = f"Normalized amount from '{raw_amt}' to float {fixed_amt}"
            latest_error.resolved = True
            current_step.status = "pending"
            return {
                "plan": plan,
                "scratchpad": scratchpad.to_dict(),
                "status": "executing"
            }
        except Exception:
            pass

    # Strategy 2: Date formatting recovery (convert text date to YYYY-MM-DD)
    if "InvalidDateFormatError" in err_msg or "date" in err_msg.lower():
        raw_date = str(current_step.tool_args.get("due_date", ""))
        # Simple heuristics for common formats
        iso_m = re.search(r"\d{4}-\d{2}-\d{2}", raw_date)
        if iso_m:
            fixed_date = iso_m.group(0)
            current_step.tool_args["due_date"] = fixed_date
            scratchpad.record_entity("due_date", fixed_date)
            latest_error.recovery_strategy = f"Extracted ISO date '{fixed_date}' from '{raw_date}'"
            latest_error.resolved = True
            current_step.status = "pending"
            return {
                "plan": plan,
                "scratchpad": scratchpad.to_dict(),
                "status": "executing"
            }

    # Strategy 3: Vendor not found -> try broader alias lookup
    if "VendorNotFoundError" in err_msg:
        query = current_step.tool_args.get("query", "")
        broad_query = query.split()[0] if query else "Company"
        current_step.tool_args["query"] = broad_query
        latest_error.recovery_strategy = f"Fuzzy matching query broadened to '{broad_query}'"
        latest_error.resolved = True
        current_step.status = "pending"
        return {
            "plan": plan,
            "status": "executing"
        }

    # Strategy 4: File not found -> broaden glob pattern or fallback to sample directory
    if "FileNotFoundError" in err_type or "not found" in err_msg.lower():
        if current_step.tool_name == "find_latest_invoice_file":
            current_step.tool_args["directory"] = str(settings.sample_data_dir / "invoices")
            latest_error.recovery_strategy = "Redirected directory path to verified sample data storage"
            latest_error.resolved = True
            current_step.status = "pending"
            return {
                "plan": plan,
                "status": "executing"
            }

    # Fallback retry with same parameters if transient
    latest_error.recovery_strategy = "Standard retry attempt"
    current_step.status = "pending"
    return {
        "plan": plan,
        "status": "executing"
    }
