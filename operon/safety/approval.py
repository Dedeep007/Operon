"""Human-in-the-Loop and Safety Approvals for Operon."""

from typing import Dict, Any, Optional, Tuple
from pydantic import BaseModel, Field
from operon.config import settings

class SafetyAssessment(BaseModel):
    """Result of evaluating a proposed action against safety boundaries."""
    requires_approval: bool
    risk_level: str = "LOW"  # LOW, MEDIUM, HIGH, CRITICAL
    reason: Optional[str] = None
    approval_prompt: Optional[str] = None

class SafetyController:
    """Monitors planned actions and enforces guardrails & human approvals."""
    
    def __init__(self):
        self.high_risk_tools = set(settings.high_risk_tools)
        self.financial_approval_threshold = 25000.00  # Any transaction > $25,000 requires human review

    def evaluate_step(self, tool_name: str, args: Dict[str, Any]) -> SafetyAssessment:
        """Inspect proposed tool call and determine if execution should halt for user approval."""
        if not settings.require_human_approval:
            return SafetyAssessment(requires_approval=False, risk_level="LOW")

        # 1. High risk tool check
        if tool_name in self.high_risk_tools or "delete" in tool_name.lower():
            return SafetyAssessment(
                requires_approval=True,
                risk_level="HIGH",
                reason=f"Action '{tool_name}' performs destructive modifications to enterprise records.",
                approval_prompt=f"SAFETY INTERRUPT: The agent wants to execute high-risk action '{tool_name}' with arguments {args}. Do you approve this operation? (approve / reject / edit)"
            )

        # 2. Financial threshold check
        amount = args.get("amount")
        if amount is not None:
            try:
                val = float(amount)
                if val > self.financial_approval_threshold:
                    return SafetyAssessment(
                        requires_approval=True,
                        risk_level="MEDIUM",
                        reason=f"Transaction amount ${val:,.2f} exceeds financial autonomous threshold of ${self.financial_approval_threshold:,.2f}.",
                        approval_prompt=f"FINANCIAL APPROVAL REQUIRED: An invoice entry of ${val:,.2f} exceeds policy limit. Proceed with registration? (approve / reject)"
                    )
            except Exception:
                pass

        # 3. Safe to proceed autonomously
        return SafetyAssessment(requires_approval=False, risk_level="LOW")

safety_controller = SafetyController()
