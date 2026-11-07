from datetime import datetime, timezone
from types import SimpleNamespace

from app.main import attempt_times


def test_attempt_deadline_serializes_sqlite_time_as_utc():
    attempt = SimpleNamespace(started_at=datetime(2026, 11, 7, 10, 0, 0))
    exam = SimpleNamespace(duration_minutes=30)
    assert attempt_times(attempt, exam) == {
        "started_at": "2026-11-07T10:00:00+00:00",
        "expires_at": "2026-11-07T10:30:00+00:00",
    }


def test_attempt_deadline_preserves_aware_timestamp():
    attempt = SimpleNamespace(started_at=datetime(2026, 11, 7, 10, 0, 0, tzinfo=timezone.utc))
    exam = SimpleNamespace(duration_minutes=15)
    assert attempt_times(attempt, exam)["expires_at"] == "2026-11-07T10:15:00+00:00"
