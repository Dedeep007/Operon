"""Tests always use local, isolated state and never call a model service."""

import pytest
from operon.config import settings
from operon.environment.erp_system import default_erp
from operon.llm import llm_provider


@pytest.fixture(autouse=True)
def offline_environment(monkeypatch):
    monkeypatch.setattr(llm_provider, "_client", None)
    monkeypatch.setattr(settings, "require_human_approval", True)
    default_erp.reset()
    yield
    default_erp.reset()
