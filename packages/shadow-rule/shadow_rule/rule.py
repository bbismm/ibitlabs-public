"""ShadowRule — evaluate a condition each tick, log when it fires, never act.

Core design invariants:

1. NEVER MUTATES CALLER STATE. The rule only reads. It never returns an
   "action" — the only observable output is a JSONL log line.
2. SWALLOWS ALL ITS OWN ERRORS. A broken shadow rule must NEVER break the
   caller's control flow. All exceptions in the fire path are caught,
   logged to the standard library `logging` module, and the caller
   continues.
3. FIRE-ONCE BY DEFAULT. Each (rule, session) pair fires at most one event
   — the "session" is whatever the caller is observing (a trade, a user
   flow, a deployment). Pass `fire_once_per_session=False` to fire every
   tick that the condition is true.
4. DETERMINISTIC LOG FORMAT. JSONL, one event per line, stable schema.
"""
from __future__ import annotations

import json
import logging
import os
import time
import uuid
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Callable, Optional

log = logging.getLogger("shadow_rule")


class ShadowError(Exception):
    """Raised only from the analyzer/constructor, never from evaluate()."""


@dataclass
class ShadowEvent:
    """One fire event written to the JSONL log.

    The caller's state dict is embedded under `state`. `rule_name` and
    `session_id` are used by the analyzer to pair fires with eventual
    outcomes.
    """
    schema_version: int
    rule_name: str
    session_id: str
    fire_ts: float
    fire_iso: str
    state: dict
    note: Optional[str] = None
    extra: dict = field(default_factory=dict)


class ShadowRule:
    """Shadow instrument for one hypothetical rule.

    Args:
        name: Identifier (becomes the `rule_name` in each event).
        condition: A callable that takes the state dict and returns bool.
            True means the rule would fire.
        log_path: Where to append JSONL fire events. Parent directory is
            created if missing.
        fire_once_per_session: If True (default), at most one event per
            session_id. Session boundary is reset by `reset_session()`.
        session_factory: Optional callable that returns a session id. Default
            generates a UUID4 on first evaluate().
    """
    SCHEMA_VERSION = 1

    def __init__(
        self,
        name: str,
        condition: Callable[[dict], bool],
        log_path: str | os.PathLike,
        fire_once_per_session: bool = True,
        session_factory: Optional[Callable[[], str]] = None,
    ):
        if not callable(condition):
            raise ShadowError("condition must be a callable state -> bool")
        if not name:
            raise ShadowError("name cannot be empty")
        self.name = name
        self.condition = condition
        self.log_path = Path(log_path)
        self.fire_once_per_session = fire_once_per_session
        self._fired_in_session = False
        self._session_id: Optional[str] = None
        self._session_factory = session_factory or (lambda: str(uuid.uuid4()))

    @property
    def session_id(self) -> str:
        if self._session_id is None:
            self._session_id = self._session_factory()
        return self._session_id

    def reset_session(self, new_session_id: Optional[str] = None) -> None:
        """Start a new observational session.

        Call this when the thing you're observing (trade, user flow,
        deployment window) concludes. Subsequent evaluate() calls start
        fresh.
        """
        self._fired_in_session = False
        self._session_id = new_session_id

    def evaluate(self, state: dict, note: Optional[str] = None,
                 **extra: Any) -> bool:
        """Evaluate the condition on the current state.

        Returns True if a fire event was written, False otherwise. Never
        raises. Never mutates `state`.
        """
        try:
            if self.fire_once_per_session and self._fired_in_session:
                return False
            try:
                fired = bool(self.condition(state))
            except Exception as e:
                log.warning("shadow-rule %s: condition error (non-fatal): %s",
                            self.name, e)
                return False
            if not fired:
                return False
            event = ShadowEvent(
                schema_version=self.SCHEMA_VERSION,
                rule_name=self.name,
                session_id=self.session_id,
                fire_ts=time.time(),
                fire_iso=time.strftime("%Y-%m-%dT%H:%M:%SZ",
                                       time.gmtime()),
                state=dict(state),   # defensive copy
                note=note,
                extra=dict(extra),
            )
            self._write(event)
            if self.fire_once_per_session:
                self._fired_in_session = True
            return True
        except Exception as e:
            log.warning("shadow-rule %s: fire path error (non-fatal): %s",
                        self.name, e)
            return False

    def _write(self, event: ShadowEvent) -> None:
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        with self.log_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(asdict(event),
                               ensure_ascii=False, default=str) + "\n")

    # Persistent-flag helpers — when your system restarts mid-session, you
    # want the fire_once flag to survive. These let the caller persist and
    # restore the flag on their own.
    def snapshot_flag(self) -> dict:
        """Return a small dict of internal state worth persisting."""
        return {
            "fired_in_session": self._fired_in_session,
            "session_id": self._session_id,
        }

    def restore_flag(self, snapshot: dict) -> None:
        """Restore internal state from a prior snapshot."""
        self._fired_in_session = bool(snapshot.get("fired_in_session", False))
        sid = snapshot.get("session_id")
        if sid:
            self._session_id = str(sid)
