"""Unit tests for correlator scoring/tier/clustering logic.

Run from backend/: pytest tests/test_correlator.py
"""
import sys
import os
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

# Mock cache so correlator can be imported without a live DB
_cache_mock = MagicMock()
_cache_mock.get_entity_baseline.return_value = 0.0
sys.modules['cache'] = _cache_mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from correlator import (
    _assign_tier, _compute_score, _compute_momentum,
    _apply_signal_caps, _prefer_specific_over_umbrella,
    _signal_key, _merge_cross_domain,
)
from config import MIN_SCORE, EMERGING_SCORE, BREAKING_MOMENTUM, AMBIENT_SOURCE_CAP, CROSS_DOMAIN_MIN_SCORE


def make_signal(source_type="news", raw_weight=2.0, hours_ago=1.0,
                title="test signal", url="", entities=None):
    ts = (datetime.now(timezone.utc) - timedelta(hours=hours_ago)).isoformat()
    return {
        "source_type": source_type,
        "raw_weight": raw_weight,
        "timestamp": ts,
        "title": title,
        "url": url,
        "entities": entities or [],
        "title_hash": f"hash-{title}",
    }


def make_formatted(title="test", url="", source_type="news"):
    return {"title": title, "url": url, "source_type": source_type,
            "timestamp": datetime.now(timezone.utc).isoformat(), "entities": []}


# --- _assign_tier ---

def test_below_min_score_is_none():
    assert _assign_tier(MIN_SCORE - 0.1, {"news"}, 1.0, "Test") is None


def test_watch_tier():
    assert _assign_tier(MIN_SCORE + 1, {"news"}, 1.0, "Test") == "watch"


def test_emerging_by_score():
    assert _assign_tier(EMERGING_SCORE + 1, {"news"}, 1.0, "Test") == "emerging"


def test_momentum_alone_does_not_emerge_below_score_floor():
    # Momentum past MOMENTUM_THRESHOLD but a low score stays watch: EMERGING_MOMENTUM_MIN_SCORE
    # keeps a quiet entity from being lifted into emerging on ratio alone.
    assert _assign_tier(MIN_SCORE + 1, {"news"}, 2.5, "Test") == "watch"


def test_emerging_by_source_diversity():
    assert _assign_tier(MIN_SCORE + 1, {"news", "arxiv", "jobs"}, 1.0, "Test") == "emerging"


def test_breaking_by_momentum():
    # BREAKING_MIN_SCORE floor must be cleared for momentum to force breaking
    assert _assign_tier(EMERGING_SCORE + 1, {"news"}, BREAKING_MOMENTUM + 0.1, "Test") == "breaking"


def test_low_score_momentum_does_not_break():
    # A momentum spike on a tiny score stays below breaking (no single-article breaking)
    assert _assign_tier(MIN_SCORE + 1, {"news"}, BREAKING_MOMENTUM + 1, "Test") != "breaking"


# --- _compute_score ---

def test_score_is_positive_for_fresh_signal():
    now = datetime.now(timezone.utc)
    sigs = [make_signal(raw_weight=2.0, hours_ago=0)]
    assert _compute_score(sigs, now) > 0


def test_decay_reduces_score_over_time():
    now = datetime.now(timezone.utc)
    fresh = _compute_score([make_signal(raw_weight=2.0, hours_ago=0)], now)
    old = _compute_score([make_signal(raw_weight=2.0, hours_ago=48)], now)
    assert fresh > old


def test_multiple_signals_sum():
    now = datetime.now(timezone.utc)
    sigs = [make_signal(raw_weight=2.0, hours_ago=0)] * 3
    score = _compute_score(sigs, now)
    assert score > 5.0  # ~6 with negligible decay


# --- _compute_momentum ---

def test_all_recent_signals_boost_momentum():
    now = datetime.now(timezone.utc)
    sigs = [make_signal(raw_weight=4.0, hours_ago=1)] * 4
    assert _compute_momentum(sigs, now) > 1.0


def test_empty_signals_gives_neutral_momentum():
    now = datetime.now(timezone.utc)
    # smoothing means ratio ≈ 1.0 for empty input
    assert abs(_compute_momentum([], now) - 1.0) < 0.05


def test_old_signals_give_low_momentum():
    now = datetime.now(timezone.utc)
    sigs = [make_signal(raw_weight=4.0, hours_ago=10)] * 4  # all in prev window
    assert _compute_momentum(sigs, now) < 1.0


# --- _apply_signal_caps ---

def test_ambient_source_capped():
    sigs = [make_signal(source_type="news") for _ in range(AMBIENT_SOURCE_CAP + 5)]
    result = _apply_signal_caps(sigs)
    count = sum(1 for s in result if s["source_type"] == "news")
    assert count <= AMBIENT_SOURCE_CAP


def test_curated_sources_not_capped():
    sigs = [make_signal(source_type="sec") for _ in range(10)]
    result = _apply_signal_caps(sigs)
    assert len(result) == 10


# --- _signal_key ---

def test_signal_key_prefers_url():
    sig = {"title": "foo", "url": "https://example.com/bar"}
    assert _signal_key(sig) == ("url", "https://example.com/bar")


def test_signal_key_falls_back_to_title():
    sig = {"title": "foo", "url": ""}
    assert _signal_key(sig) == ("title", "foo")


# --- _prefer_specific_over_umbrella ---

def test_umbrella_dropped_when_specific_overlaps():
    shared = [
        make_formatted(title="AI chip demand surges", url="https://ex.com/1"),
        make_formatted(title="New accelerator unveiled", url="https://ex.com/2"),
    ]
    raw = {
        "AI": {
            "signals": shared,
            "tier": "emerging", "score": 10.0, "momentum": 1.0,
            "source_types": ["news"], "entities": ["AI"], "id": "ai",
        },
        "Nvidia": {
            "signals": shared[:],
            "tier": "emerging", "score": 12.0, "momentum": 1.0,
            "source_types": ["news"], "entities": ["Nvidia"], "id": "nv",
        },
    }
    result = _prefer_specific_over_umbrella(raw)
    assert "AI" not in result
    assert "Nvidia" in result


def test_umbrella_kept_when_no_overlap():
    raw = {
        "AI": {
            "signals": [make_formatted(title="AI policy debate", url="https://ex.com/A"),
                        make_formatted(title="AI safety summit", url="https://ex.com/B")],
            "tier": "watch", "score": 5.0, "momentum": 1.0,
            "source_types": ["news"], "entities": ["AI"], "id": "ai",
        },
        "Nvidia": {
            "signals": [make_formatted(title="Nvidia earnings beat", url="https://ex.com/C"),
                        make_formatted(title="Nvidia new GPU", url="https://ex.com/D")],
            "tier": "watch", "score": 5.0, "momentum": 1.0,
            "source_types": ["news"], "entities": ["Nvidia"], "id": "nv",
        },
    }
    result = _prefer_specific_over_umbrella(raw)
    assert "AI" in result
    assert "Nvidia" in result


# --- _merge_cross_domain ---

def make_cluster(entity, tier, score, source_types):
    return {
        "id": entity.lower(),
        "entities": [entity],
        "tier": tier,
        "score": score,
        "momentum": 1.0,
        "source_types": source_types,
        "signals": [],
    }


def test_cross_domain_requires_min_score():
    # stock + news = finance + tech, but score is low — should NOT become breaking
    raw = {"Nvidia": make_cluster("Nvidia", "emerging", 15.0, ["stock", "news"])}
    result = _merge_cross_domain(raw)
    assert result[0]["tier"] == "emerging"


def test_cross_domain_promotes_at_high_score():
    # Same combo but score is above threshold
    raw = {"Nvidia": make_cluster("Nvidia", "emerging", CROSS_DOMAIN_MIN_SCORE + 5, ["stock", "news"])}
    result = _merge_cross_domain(raw)
    assert result[0]["tier"] == "breaking"


def test_single_domain_never_promoted():
    raw = {"AI": make_cluster("AI", "emerging", 50.0, ["news"])}
    result = _merge_cross_domain(raw)
    assert result[0]["tier"] == "emerging"


def test_url_based_overlap_catches_different_titles():
    # Same URL but slightly different titles (different scrapers)
    umbrella_sig = make_formatted(title="AI sector news", url="https://reuters.com/story/1")
    specific_sig = make_formatted(title="Nvidia leads rally", url="https://reuters.com/story/1")
    raw = {
        "AI": {
            "signals": [umbrella_sig, make_formatted(title="other", url="https://reuters.com/story/2")],
            "tier": "watch", "score": 5.0, "momentum": 1.0,
            "source_types": ["news"], "entities": ["AI"], "id": "ai",
        },
        "Nvidia": {
            "signals": [specific_sig, make_formatted(title="other", url="https://reuters.com/story/2")],
            "tier": "watch", "score": 5.0, "momentum": 1.0,
            "source_types": ["news"], "entities": ["Nvidia"], "id": "nv",
        },
    }
    result = _prefer_specific_over_umbrella(raw)
    assert "AI" not in result
