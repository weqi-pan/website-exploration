"""Runtime server entrypoint; protocol implementation remains in scripts for compatibility."""
from scripts.runtime import dispatch, client, main, sessions

__all__ = ["dispatch", "client", "main", "sessions"]
