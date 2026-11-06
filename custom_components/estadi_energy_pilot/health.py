"""Persistent diagnostic event journal and deterministic health assessment.

Keep the previous successful planning timestamp separate from the last heartbeat:
a refreshing integration with no usable PV or SOC is *not* healthy.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

MAX_EVENTS = 100
STALE_SECONDS = 35 * 60


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso(value: datetime | None) -> str | None:
    return value.astimezone(timezone.utc).isoformat() if value else None


def parse_iso(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.astimezone(timezone.utc) if parsed.tzinfo else None
    except ValueError:
        return None


class HealthJournal:
    """A bounded journal with change-only error logging and durable timestamps."""

    def __init__(self, saved: Any = None):
        data = saved if isinstance(saved, dict) else {}
        self.events = list(data.get("events", []))[-MAX_EVENTS:]
        self.last_attempt = data.get("last_attempt")
        self.last_completed = data.get("last_completed")
        self.last_success = data.get("last_success")
        self.last_status = str(data.get("last_status", "start"))
        self.last_reason = str(data.get("last_reason", "Uruchomiono integrację"))
        self.run_count = int(data.get("run_count", 0))
        self.fail_count = int(data.get("fail_count", 0))
        self.last_duration_ms = data.get("last_duration_ms")

    def add(self, level: str, code: str, message: str, now: datetime | None = None):
        self.events.append({
            "at": iso(now or utc_now()), "level": level,
            "code": code[:64], "message": str(message)[:350],
        })
        self.events = self.events[-MAX_EVENTS:]

    def attempt(self, now: datetime):
        self.last_attempt = iso(now)
        self.run_count += 1

    def finish(self, now: datetime, status: str, reason: str,
               elapsed_ms: int | None = None):
        """Use status 'ok' only if both charging targets can be calculated."""
        self.last_completed = iso(now)
        self.last_duration_ms = elapsed_ms
        if status == "ok":
            self.last_success = iso(now)
        elif status == "error":
            self.fail_count += 1
        if status != self.last_status or reason != self.last_reason:
            level = "info" if status == "ok" else "error" if status == "error" else "warning"
            self.add(level, f"STATE_{status.upper()}", reason, now)
        self.last_status = status
        self.last_reason = reason

    def view(self, now: datetime) -> dict:
        last = parse_iso(self.last_completed)
        age = max(0, int((now - last).total_seconds())) if last else None
        stale = age is None or age > STALE_SECONDS
        state = "brak_odswiezania" if stale else self.last_status
        return {
            "status": state,
            "reason": "Brak aktualizacji przez ponad 35 min" if stale else self.last_reason,
            "last_attempt": self.last_attempt,
            "last_completed": self.last_completed,
            "last_success": self.last_success,
            "age_seconds": age,
            "refresh_count": self.run_count,
            "error_count": self.fail_count,
            "duration_ms": self.last_duration_ms,
            "events": list(reversed(self.events[-20:])),
        }

    def export(self):
        return {
            "events": self.events, "last_attempt": self.last_attempt,
            "last_completed": self.last_completed, "last_success": self.last_success,
            "last_status": self.last_status, "last_reason": self.last_reason,
            "run_count": self.run_count, "fail_count": self.fail_count,
            "last_duration_ms": self.last_duration_ms,
        }
