"""Tests for the shared EventRecorder helper."""

from __future__ import annotations

import datetime as dt

from custom_components.adaptive_cover_pro.managers.common import EventRecorder


class _FakeBuffer:
    def __init__(self) -> None:
        self.records: list[dict] = []

    def record(self, event: dict) -> None:
        self.records.append(event)


def test_record_stamps_ts_and_event_and_fields():
    buf = _FakeBuffer()
    rec = EventRecorder(buf)
    rec.record("something_happened", entity_id="cover.a", count=3)
    assert len(buf.records) == 1
    event = buf.records[0]
    assert event["event"] == "something_happened"
    assert event["entity_id"] == "cover.a"
    assert event["count"] == 3
    # ts is an ISO-8601 string parseable back to a datetime
    assert isinstance(event["ts"], str)
    dt.datetime.fromisoformat(event["ts"])


def test_record_is_noop_without_buffer():
    rec = EventRecorder(None)
    # must not raise
    rec.record("ignored", foo="bar")


def test_custom_now_fn_drives_ts():
    buf = _FakeBuffer()
    fixed = dt.datetime(2026, 6, 4, 12, 0, 0, tzinfo=dt.UTC)
    rec = EventRecorder(buf, now_fn=lambda: fixed)
    rec.record("clocked")
    assert buf.records[0]["ts"] == fixed.isoformat()


def test_fields_only_no_extra_keys():
    buf = _FakeBuffer()
    EventRecorder(buf).record("bare")
    assert set(buf.records[0]) == {"ts", "event"}
