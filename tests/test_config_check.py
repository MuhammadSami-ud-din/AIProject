import pytest

from backend.ai import config_check, observation, zones
from backend.ai.config_check import check_settings, find_problems


def test_current_settings_are_fine():
    assert find_problems() == []
    assert check_settings()


def test_mixed_up_distance_limits_are_found(monkeypatch):
    monkeypatch.setattr(zones, "FAR_LIMIT", 50)    # smaller than CLOSE_LIMIT
    with pytest.raises(ValueError, match="CLOSE_LIMIT"):
        check_settings()


def test_tiny_arena_is_found(monkeypatch):
    monkeypatch.setattr(zones, "ARENA_WIDTH", 150)
    problems = " ".join(find_problems())
    assert "Shadow" in problems                    # Shadow likes 200 pixels


def test_bad_time_settings_are_found(monkeypatch):
    monkeypatch.setattr(observation, "LOW_TIME", 100)
    assert any("LOW_TIME" in p for p in config_check.find_problems())
