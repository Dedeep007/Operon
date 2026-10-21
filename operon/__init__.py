"""Operon: Autonomous AI Task Worker.

Built with LangGraph, LangChain, Groq API (Qwen 3.8 27B),
with self-healing execution, explicit verification, and human-in-the-loop safety.
"""

from operon.agent import OperonAgent
from operon.state import OperonState, PlanStep, ActionRecord, ErrorRecord, VerificationResult, EvidencePacket
from operon.config import settings

__version__ = "0.2.0"
__all__ = [
    "OperonAgent",
    "OperonState",
    "PlanStep",
    "ActionRecord",
    "ErrorRecord",
    "VerificationResult",
    "EvidencePacket",
    "settings"
]
