"""Observer Node for Operon.

Inspects tool outputs, extracts and persists newly discovered entities to working memory,
detects failures, and routes between next steps, replanning, and verification.
"""

from typing import Dict, Any
from operon.state import OperonState, ErrorRecord
from operon.memory.scratchpad import Scratchpad

def observer_node(state: OperonState) -> Dict[str, Any]:
    """Observe action outcome, update working memory, and determine state transition."""
    plan = list(state["plan"])
    idx = state["current_step_index"]
    current_step = plan[idx]
    
    last_exec = state.get("last_execution_result", {})
    success = last_exec.get("success", False)
    
    scratchpad = Scratchpad.from_dict(state.get("scratchpad", {}))
    errors = list(state.get("errors", []))
    retry_count = dict(state.get("retry_count", {}))
    
    if success:
        if current_step.tool_name == "search_files" and last_exec.get("data"):
            scratchpad.record_entity("search_no_results", False)
        # Update working memory with discovered knowledge
        scratchpad.update_from_observation(
            tool_name=current_step.tool_name,
            data=last_exec.get("data"),
            step_id=current_step.step_id
        )
        current_step.status = "completed"
        for error in errors:
            if error.step_id == current_step.step_id:
                error.resolved = True
        
        # Advance to next step
        next_idx = idx + 1

        # If a file search yielded zero results, skip dependent document-reading steps gracefully
        data = last_exec.get("data")
        empty_search = (current_step.tool_name == "search_files" and not data) or (
            current_step.tool_name == "search_company_records" and isinstance(data, dict)
            and not data.get("matches") and not data.get("skipped_files"))
        if empty_search:
            scratchpad.record_entity("search_no_results", True)
            term = (current_step.tool_args.get("pattern") or current_step.tool_args.get("query")
                    or current_step.tool_args.get("filename") or "requested file").replace("*", "").strip()
            scratchpad.record_entity("searched_term", term)
            scratchpad.add_note(f"Storage search completed: No matching files found for '{term}'.")
            # An explicit alternate search may still recover the lookup. Otherwise,
            # stop dependent work before unresolved paths can reach a write action.
            if next_idx >= len(plan) or plan[next_idx].tool_name not in ("search_files", "search_company_records"):
                for remaining in plan[next_idx:]:
                    remaining.status = "skipped"
                    remaining.error = f"Skipped: No matching files found in storage for '{term}'."
                next_idx = len(plan)

        if next_idx >= len(plan):
            next_status = "verifying"
        else:
            next_status = "executing"
            
        return {
            "plan": plan,
            "errors": errors,
            "scratchpad": scratchpad.to_dict(),
            "current_step_index": next_idx,
            "status": next_status
        }
    else:
        # Failure detected!
        current_step.status = "failed"
        err_msg = last_exec.get("error", "Unknown error")
        err_type = last_exec.get("error_type", "ExecutionError")
        
        # Categorize failure
        err_record = ErrorRecord(
            step_id=current_step.step_id,
            error_type=err_type,
            message=err_msg
        )
        errors.append(err_record)
        
        # Track retries for this step
        step_key = f"step_{current_step.step_id}"
        retry_count[step_key] = retry_count.get(step_key, 0) + 1
        
        return {
            "plan": plan,
            "errors": errors,
            "retry_count": retry_count,
            "status": "replanning"
        }
