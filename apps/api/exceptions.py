from __future__ import annotations


class StateConflictError(RuntimeError):
    """Raised when an incident transition violates the state machine."""
