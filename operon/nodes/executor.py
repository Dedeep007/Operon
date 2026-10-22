"""Executor Node for Operon.

Selects the current planned step, enforces safety gates,
interpolates parameters from working memory, and executes the tool.
"""

from typing import Dict, Any
from operon.state import OperonState, ActionRecord
from operon.tools.registry import registry
from operon.memory.scratchpad import Scratchpad
from operon.safety.approval import safety_controller, action_fingerprint
from operon.tools.registry import ToolExecutionResult

PREVIEW_TOOLS = {
    "search_files", "read_document", "extract_invoice_data", "find_latest_invoice_file",
    "read_vendor_profile", "erp_lookup_vendor", "erp_create_invoice", "erp_get_invoice",
    "erp_list_invoices", "erp_register_vendor", "erp_verify_invoice_status",
    "find_latest_signed_deal", "read_deal_quotation", "search_company_records",
}

def executor_node(state: OperonState) -> Dict[str, Any]:
    """Execute the current step in the plan."""
    plan = list(state["plan"])
    idx = state["current_step_index"]
    
    if idx >= len(plan):
        return {"status": "verifying"}
        
    current_step = plan[idx]
    current_step.status = "in_progress"
    
    # Load working memory
    scratchpad = Scratchpad.from_dict(state.get("scratchpad", {}))
    
    # Interpolate arguments using working memory
    resolved_args = scratchpad.interpolate_args(current_step.tool_args)
    current_step.tool_args = resolved_args
    
    # Approval applies only to this resolved action fingerprint.
    fingerprint = action_fingerprint(current_step.step_id, current_step.tool_name, resolved_args)
    assessment = safety_controller.evaluate_step(current_step.tool_name, resolved_args)
    policy_checks = list(state.get("policy_checks", []))
    if assessment.requires_approval:
        must_pause = state.get("mode") != "preview" or assessment.approval_scope == "all_modes"
        check = {
            "step_id": current_step.step_id,
            "tool_name": current_step.tool_name,
            "action_fingerprint": fingerprint,
            "decision": "approval_required" if must_pause else "would_require_on_execution",
            **assessment.model_dump(),
        }
        if not any(item.get("action_fingerprint") == fingerprint for item in policy_checks):
            policy_checks.append(check)
        if must_pause and state.get("approved_action") != fingerprint:
            return {
                "plan": plan,
                "policy_checks": policy_checks,
                "requires_approval": True,
                "approval_prompt": assessment.approval_prompt,
                "approval_context": assessment.model_dump(),
                "status": "waiting_approval"
            }
            
    # Execute Tool
    if state.get("mode") == "preview" and current_step.tool_name not in PREVIEW_TOOLS:
        exec_result = ToolExecutionResult(success=False, tool_name=current_step.tool_name, args=resolved_args,
            error="PreviewBlockedError: This tool cannot run in the isolated ERP preview.", error_type="PreviewBlockedError")
    elif "{{" in str(resolved_args):
        exec_result = ToolExecutionResult(success=False, tool_name=current_step.tool_name, args=resolved_args,
            error="MissingContextError: Required information could not be resolved from earlier steps.", error_type="MissingContextError")
    else:
        exec_result = registry.execute(current_step.tool_name, **resolved_args)
    
    # Create action audit record
    record = ActionRecord(
        step_id=current_step.step_id,
        tool_name=current_step.tool_name,
        tool_args=resolved_args,
        observation=exec_result.data if exec_result.success else exec_result.error,
        success=exec_result.success,
        error=exec_result.error
    )
    
    current_step.result = exec_result.data
    current_step.error = exec_result.error
    
    action_history = list(state.get("action_history", []))
    action_history.append(record)
    
    return {
        "plan": plan,
        "action_history": action_history,
        "requires_approval": False,
        "approval_prompt": None,
        "approval_context": None,
        "human_feedback": None,
        "approved_action": None,
        "policy_checks": policy_checks,
        "status": "executing",
        "last_execution_result": exec_result.model_dump()
    }
