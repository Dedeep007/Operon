"""Human-in-the-Loop and Safety Approvals for Operon."""

from typing import Dict, Any, Optional, Literal
from pydantic import BaseModel, Field
from operon.config import settings
from operon.validation import parse_amount
from operon.tools.registry import registry
from operon.safety.data_policy import POLICY_VERSION, classify_action
import hashlib
import json


def action_fingerprint(step_id, tool_name, args):
    return hashlib.sha256(json.dumps([POLICY_VERSION, step_id, tool_name, args], sort_keys=True).encode()).hexdigest()

class SafetyAssessment(BaseModel):
    """Result of evaluating a proposed action against safety boundaries."""
    requires_approval: bool
    risk_level: str = "LOW"  # LOW, MEDIUM, HIGH, CRITICAL
    reason: Optional[str] = None
    approval_prompt: Optional[str] = None
    policy_id: str = f"{POLICY_VERSION}:autonomous"
    approval_scope: Literal["execution", "all_modes"] = "execution"
    resource: Optional[str] = None
    data_classification: Optional[str] = None
    data_categories: list[str] = Field(default_factory=list)

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
        definition = registry.get_definition(tool_name)
        if tool_name in self.high_risk_tools or "delete" in tool_name.lower() or (definition and definition.requires_approval):
            return SafetyAssessment(
                requires_approval=True,
                risk_level="HIGH",
                reason=f"Action '{tool_name}' performs destructive modifications to enterprise records.",
                approval_prompt=f"Operon wants to run the high-risk action '{tool_name}'. Review the exact arguments below before approving it once.",
                policy_id=f"{POLICY_VERSION}:high-risk-tool",
            )

        # 2. Data classification and transmission policy
        resource = classify_action(tool_name, args)
        if resource and resource.requires_approval:
            categories = ", ".join(resource.data_categories)
            return SafetyAssessment(
                requires_approval=True,
                risk_level="HIGH" if resource.data_classification == "RESTRICTED" else "MEDIUM",
                reason=resource.reason,
                approval_prompt=(
                    f"Operon wants to access {resource.data_classification.lower()} data in "
                    f"{resource.resource}. This may involve {categories}. Approve this exact action once?"
                ),
                policy_id=resource.policy_id,
                approval_scope=resource.approval_scope,
                resource=resource.resource,
                data_classification=resource.data_classification,
                data_categories=resource.data_categories,
            )

        # 3. Financial threshold check
        amount = args.get("amount")
        if amount is not None:
            try:
                val = parse_amount(amount)
                if val > self.financial_approval_threshold:
                    return SafetyAssessment(
                        requires_approval=True,
                        risk_level="MEDIUM",
                        reason=f"Transaction amount ${val:,.2f} exceeds financial autonomous threshold of ${self.financial_approval_threshold:,.2f}.",
                        approval_prompt=f"This invoice entry is ${val:,.2f}, above the ${self.financial_approval_threshold:,.2f} autonomous limit. Approve this exact registration once?",
                        policy_id=f"{POLICY_VERSION}:financial-threshold",
                        resource="Company ledger invoice entry",
                        data_classification="CONFIDENTIAL",
                        data_categories=["financial record"],
                    )
            except Exception:
                pass

        # 3. Safe to proceed autonomously
        return SafetyAssessment(requires_approval=False, risk_level="LOW")

safety_controller = SafetyController()
