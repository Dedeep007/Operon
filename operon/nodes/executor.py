"""Executor Node for Operon.

Selects the current planned step, enforces safety gates,
interpolates parameters from working memory, and executes the tool.
"""

from typing import Dict, Any
from operon.state import OperonState, ActionRecord
from operon.tools.registry import registry
from operon.memory.scratchpad import Scratchpad
from operon.safety.approval import safety_controller

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
    
    # Safety Check: Does this action require human approval?
    # (If human feedback was already received approving it, proceed)
    if not state.get("human_feedback"):
        assessment = safety_controller.evaluate_step(current_step.tool_name, resolved_args)
        if assessment.requires_approval:
            return {
                "requires_approval": True,
                "approval_prompt": assessment.approval_prompt,
                "status": "waiting_approval"
            }
            
    # Reset human feedback after use
    human_fb = state.get("human_feedback")
    
    # Execute Tool
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
        "human_feedback": None,
        "last_execution_result": exec_result.model_dump()
    }
