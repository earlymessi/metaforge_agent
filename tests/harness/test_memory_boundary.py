"""State / Memory / factual boundary."""

from __future__ import annotations

import pytest

from metaforge.memory.boundary import (
    check_memory_write,
    classify_key,
    classify_payload,
)
from metaforge.memory.manager import MemoryManager


def test_classify_factual_and_session():
    assert classify_key("gantt_data") == "factual"
    assert classify_key("jobs") == "factual"
    assert classify_key("pending_clarification") == "session"
    assert classify_key("order_analysis") == "task"


def test_check_memory_write_warns_on_gantt():
    warnings = check_memory_write("working", "gantt_data", {"ops": []})
    assert warnings
    assert "factual" in warnings[0]


def test_manager_records_boundary_warnings():
    mm = MemoryManager(context={})
    mm.set_working("demo", "gantt_data", {"x": 1})
    assert mm.boundary_warnings
    assert mm._context.get("memory_boundary_warnings")


def test_manager_strict_raises(monkeypatch):
    monkeypatch.setenv("METAFORGE_MEMORY_STRICT", "1")
    mm = MemoryManager(context={})
    with pytest.raises(RuntimeError, match="factual"):
        mm.set_working("demo", "inventory", {"sku": 1})


def test_classify_payload_prefers_factual():
    assert classify_payload({"gantt_data": [], "note": "x"}) == "factual"
