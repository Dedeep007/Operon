"""State definitions and Pydantic models for Operon."""

from typing import List, Dict, Any, Optional, Literal, TypedDict
from pydantic import BaseModel, Field
import datetime

class PlanStep(BaseModel):
    """A single discrete step in the agent's execution plan."""
    step_id: int = Field(description="Step sequence number (1-indexed)")
    description: str = Field(description="Clear explanation of the action to perform")
    tool_name: str = Field(description="The tool to invoke for this step")
    tool_args: Dict[str, Any] = Field(default_factory=dict, description="Arguments for the tool")
    expected_outcome: str = Field(description="What condition indicates this step succeeded")
    status: Literal["pending", "in_progress", "completed", "failed", "skipped"] = "pending"
    result: Optional[Any] = None
    error: Optional[str] = None

class ActionRecord(BaseModel):
    """Audit record of a single tool execution."""
    timestamp: str = Field(default_factory=lambda: datetime.datetime.now().isoformat())
    step_id: int
    tool_name: str
    tool_args: Dict[str, Any]
    observation: Any
    success: bool
    error: Optional[str] = None

class ErrorRecord(BaseModel):
    """Categorized failure record for recovery and learning."""
    timestamp: str = Field(default_factory=lambda: datetime.datetime.now().isoformat())
    step_id: int
    error_type: str = Field(description="e.g. NotFoundError, ValidationError, NetworkError, AuthError")
    message: str
    recovery_strategy: Optional[str] = None
    resolved: bool = False

class VerificationResult(BaseModel):
    """Independent outcome verification check."""
    is_verified: bool = Field(description="Whether the end goal was genuinely achieved")
    confidence_score: float = Field(default=1.0, description="Verification confidence 0.0 to 1.0")
    checks_performed: List[str] = Field(default_factory=list, description="List of assertions verified")
    evidence: str = Field(description="Concrete proof from system state (e.g., DB record, file created)")
    discrepancies: List[str] = Field(default_factory=list, description="Any unmatched conditions or deviations")

class EvidencePacket(BaseModel):
    """Final auditable package of completion."""
    task: str
    status: Literal["completed", "failed", "partially_completed"]
    summary: str
    agent_message: str = Field(default="", description="Direct conversational response addressing the user")
    total_actions_taken: int
    execution_time_seconds: float
    verification: Optional[VerificationResult] = None
    created_records: List[Dict[str, Any]] = Field(default_factory=list)
    state_diffs: Dict[str, Any] = Field(default_factory=dict)
    action_log: List[ActionRecord] = Field(default_factory=list)
    run_id: str = ""
    mode: Literal["execute", "preview"] = "execute"
    plan: List[PlanStep] = Field(default_factory=list)
    source_documents: List[Dict[str, Any]] = Field(default_factory=list)
    policy_checks: List[Dict[str, Any]] = Field(default_factory=list)
    errors: List[ErrorRecord] = Field(default_factory=list)
    evidence_sha256: str = ""
    planner_backend: str = "offline"

class OperonState(TypedDict):
    """Central state passed across all LangGraph nodes."""
    task: str
    plan: List[PlanStep]
    current_step_index: int
    scratchpad: Dict[str, Any]
    action_history: List[ActionRecord]
    errors: List[ErrorRecord]
    retry_count: Dict[str, int]
    verification_result: Optional[VerificationResult]
    evidence_packet: Optional[EvidencePacket]
    requires_approval: bool
    approval_prompt: Optional[str]
    human_feedback: Optional[str]
    status: Literal["planning", "executing", "waiting_approval", "replanning", "verifying", "completed", "partially_completed", "failed"]
    start_time: float
    last_execution_result: Optional[Dict[str, Any]]
    run_id: str
    mode: Literal["execute", "preview"]
    baseline_snapshot: Dict[str, Any]
    baseline_audit_count: int
    approved_action: Optional[str]
    approval_rejected: bool
    policy_checks: List[Dict[str, Any]]
    planner_backend: str
