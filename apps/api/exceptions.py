from __future__ import annotations


class StateConflictError(RuntimeError):
    """Raised when an incident transition violates the state machine."""


class AccessDeniedError(RuntimeError):
    """Raised when a partner tries to operate outside its sandbox boundary."""
