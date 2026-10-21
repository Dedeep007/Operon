"""High-level Operon Autonomous Agent Client."""

import time
import uuid
from typing import Dict, Any, Generator, Optional
from operon.graph import operon_app
from operon.state import OperonState, EvidencePacket

class OperonAgent:
    """Autonomous Enterprise Task Worker."""

    def __init__(self, thread_id: Optional[str] = None):
        self.thread_id = thread_id or f"operon_session_{uuid.uuid4().hex[:8]}"
        self.config = {"configurable": {"thread_id": self.thread_id}}

    def run(self, task: str) -> EvidencePacket:
        """Execute a natural language task to completion."""
        initial_state: OperonState = {
            "task": task,
            "plan": [],
            "current_step_index": 0,
            "scratchpad": {},
            "action_history": [],
            "errors": [],
            "retry_count": {},
            "verification_result": None,
            "evidence_packet": None,
            "requires_approval": False,
            "approval_prompt": None,
            "human_feedback": None,
            "status": "planning",
            "start_time": time.time()
        }

        final_state = operon_app.invoke(initial_state, config=self.config)
        return final_state.get("evidence_packet")

    def stream(self, task: str) -> Generator[Dict[str, Any], None, None]:
        """Stream execution events node-by-node."""
        initial_state: OperonState = {
            "task": task,
            "plan": [],
            "current_step_index": 0,
            "scratchpad": {},
            "action_history": [],
            "errors": [],
            "retry_count": {},
            "verification_result": None,
            "evidence_packet": None,
            "requires_approval": False,
            "approval_prompt": None,
            "human_feedback": None,
            "status": "planning",
            "start_time": time.time()
        }

        for event in operon_app.stream(initial_state, config=self.config):
            yield event
