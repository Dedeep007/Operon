"""Optional Groq planner with explicit, deterministic offline workflows."""

import json
from contextvars import ContextVar
from operon.config import settings
from operon.workflows import offline_plan

_backend = ContextVar("operon_planner_backend", default="offline")


class LLMProvider:
    def __init__(self):
        self._client = None
        key = settings.groq_api_key.strip()
        if settings.environment != "simulation" and key and not key.startswith(("your_", "gsk_your_")):
            from langchain_groq import ChatGroq
            self._client = ChatGroq(model=settings.model_name, api_key=key,
                                    temperature=settings.temperature, max_retries=2, timeout=30)

    @property
    def is_live(self):
        return self._client is not None

    @property
    def model_name(self):
        return settings.model_name if self.is_live else "Offline workflow planner"

    def invoke(self, messages):
        if self._client:
            try:
                response = self._client.invoke(messages).content
                _backend.set("groq")
                return response
            except Exception:
                # The constrained fallback remains grounded in the current user's task.
                _backend.set("offline (Groq unavailable)")
        else:
            _backend.set("offline")
        return self._fallback_invoke(messages)

    @property
    def last_backend(self):
        return _backend.get()

    def _fallback_invoke(self, messages):
        user_messages = [m["content"] for m in messages if isinstance(m, dict) and m.get("role") == "user"]
        task = user_messages[-1] if user_messages else ""
        return json.dumps(offline_plan(task))


llm_provider = LLMProvider()
