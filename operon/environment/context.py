"""Bind tools and verification to the same execution environment."""

from contextlib import contextmanager
from contextvars import ContextVar
from operon.environment.erp_system import default_erp

_current_erp = ContextVar("operon_erp", default=None)


def get_erp():
    return _current_erp.get() or default_erp


@contextmanager
def use_erp(erp):
    token = _current_erp.set(erp)
    try:
        yield erp
    finally:
        _current_erp.reset(token)
