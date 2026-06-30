import re
import uuid
import math
from datetime import datetime, timezone
from collections import defaultdict
from config import (
    CLUSTER_WINDOW_HOURS, DECAY_RATE, DECAY_RATES, MIN_SCORE, EMERGING_SCORE,
    SOURCE_WEIGHTS,
    MOMENTUM_THRESHOLD, EMERGING_MOMENTUM_MIN_SCORE, BREAKING_MOMENTUM, BREAKING_MIN_SCORE, MOMENTUM_CAP, MOMENTUM_SMOOTHING,
    NOVELTY_CAP, CROSS_DOMAIN_MIN_SCORE,
    CURATED_SOURCE_TYPES, AMBIENT_SOURCE_TYPES, AMBIENT_SOURCE_CAP,
    INTENT_CURATED_MULT, INTENT_AMBIENT_MULT,
    GENERIC_UMBRELLA_ENTITIES, ENTITY_SYNONYMS, ENTITY_NARRATIVE_MAP, ENTITY_LAYER_MAP,
)
from cache import get_recent_signals, save_clusters, get_entity_baseline, update_entity_baseline

EPSILON = 1e-6

# Domain groupings for cross-domain super-cluster detection. A cluster that spans
# 2+ of these domains (and clears CROSS_DOMAIN_MIN_SCORE) is promoted to breaking.
DOMAIN_GROUPS = {
    "tech":        {"news", "arxiv", "jobs", "sec"},
    "finance":     {"stock", "sec"},
    "monitoring":  {"watcher"},
}


def run():
    now = datetime.now(timezone.utc)
    signals = get_recent_signals(hours=CLUSTER_WINDOW_HOURS)

    if not signals:
        save_clusters([])
        return

    # --- Step 1: Group by entity (canonicalize synonyms first) ---
    entity_signals: dict[str, list[dict]] = defaultdict(list)
    for sig in signals:
        canonical_entities = {ENTITY_SYNONYMS.get(entity, entity) for entity in sig["entities"]}
        for canonical in canonical_entities:
            entity_signals[canonical].append(sig)

    # --- Step 2: Build raw clusters per entity ---
    raw_clusters: dict[str, dict] = {}
    stock_only_by_entity: dict[str, list[dict]] = {}  # for narrative co-movement (B)
    for entity, sigs in entity_signals.items():
        # Deduplicate by title_hash
        seen = set()
        unique_sigs = []
        for s in sigs:
            if s["title_hash"] not in seen:
                seen.add(s["title_hash"])
                unique_sigs.append(s)

        unique_sigs = _dedupe_stock_signals_newest_per_entity(unique_sigs)

        source_types = {s["source_type"] for s in unique_sigs}

        # B: stash stock-only signals before any filtering for narrative merge
        if source_types == {"stock"} and unique_sigs:
            stock_only_by_entity[entity] = list(unique_sigs)

        # C: notable solo stock move (≥4% or 2× vol) bypasses length + diversity gates
        notable_solo = source_types == {"stock"} and _has_notable_stock_move(unique_sigs)

        if not notable_solo:
            # The core thesis: surface an entity only when 2+ independent signals,
            # from 2+ distinct source types, converge on it.
            if len(unique_sigs) < 2:
                continue
            if len(source_types) < 2:
                continue

        capped_sigs = _apply_signal_caps(unique_sigs)
        min_capped = 1 if notable_solo else 2
        if len(capped_sigs) < min_capped:
            continue

        score = _compute_score(capped_sigs, now)
        momentum = _compute_momentum(capped_sigs, now)

        baseline = get_entity_baseline(entity)
        novelty_ratio = min(len(capped_sigs) / (baseline + EPSILON), NOVELTY_CAP)
        score *= novelty_ratio

        has_curated = bool(source_types & CURATED_SOURCE_TYPES)
        score *= INTENT_CURATED_MULT if has_curated else INTENT_AMBIENT_MULT

        # Generic umbrella entities need corroboration; otherwise they crowd out specific topics.
        if (
            entity in GENERIC_UMBRELLA_ENTITIES
            and len(source_types) < 2
            and momentum < MOMENTUM_THRESHOLD
        ):
            score *= 0.7

        tier = _assign_tier(score, source_types, momentum, entity)
        if tier is None:
            continue

        cluster_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, entity))
        raw_clusters[entity] = {
            "id": cluster_id,
            "entities": [entity],
            "tier": tier,
            "score": round(score, 2),
            "momentum": round(momentum, 2),
            "source_types": list(source_types),
            "signals": _format_signals(capped_sigs),
        }

        update_entity_baseline(entity, len(capped_sigs))

    raw_clusters = _prefer_specific_over_umbrella(raw_clusters)

    # --- Step 3: Merge clusters that share ≥2 signals ---
    raw_clusters = _merge_signal_overlap(raw_clusters, now)

    # --- Step 3b: Narrative co-movement clusters (B) ---
    raw_clusters = _add_narrative_mover_clusters(raw_clusters, stock_only_by_entity, now)

    # --- Step 4: Cross-domain super-clusters ---
    clusters = _merge_cross_domain(raw_clusters)

    # Tag each cluster with its narrative, layer coherence, and dominant layer
    for cluster in clusters:
        cluster["narrative"] = _tag_narrative(cluster["entities"])
        cluster["coherence"] = round(_compute_coherence(cluster["entities"]), 2)
        cluster["dominant_layer"] = _dominant_layer(cluster["entities"])
        # Incoherent mixed-layer emerging clusters get demoted to watch.
        # Coherence < 0.5 means less than half the tagged entities share the same layer
        # (e.g. ExxonMobil + Oklo in "Nuclear & Energy" — oil_gas vs advanced_nuclear).
        if cluster["coherence"] < 0.5 and cluster["tier"] == "emerging":
            cluster["tier"] = "watch"

    tier_order = {"breaking": 0, "emerging": 1, "watch": 2}
    clusters.sort(key=lambda c: (tier_order.get(c["tier"], 9), -c["score"]))

    save_clusters(clusters)
    print(f"[correlator] {len(clusters)} clusters surfaced from {len(signals)} signals")


def _compute_score(signals: list[dict], now: datetime) -> float:
    total = 0.0
    for sig in signals:
        src = sig["source_type"]
        weight = sig.get("raw_weight") or SOURCE_WEIGHTS.get(src, 2)
        try:
            ts = datetime.fromisoformat(sig["timestamp"].replace("Z", "+00:00"))
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            hours_ago = (now - ts).total_seconds() / 3600
            decay = math.exp(-DECAY_RATES.get(src, DECAY_RATE) * hours_ago)
            total += weight * decay
        except Exception:
            total += weight * 0.5
    return total


def _apply_signal_caps(signals: list[dict]) -> list[dict]:
    # Keep most recent, but cap noisy ambient-source contributions per entity before scoring.
    ambient_counts: dict[str, int] = defaultdict(int)
    kept = []
    sorted_sigs = sorted(signals, key=lambda x: x.get("timestamp", ""), reverse=True)
    for sig in sorted_sigs:
        src = sig["source_type"]
        if src in AMBIENT_SOURCE_TYPES:
            ambient_counts[src] += 1
            if ambient_counts[src] > AMBIENT_SOURCE_CAP:
                continue
        kept.append(sig)
    return kept


def _compute_momentum(signals: list[dict], now: datetime) -> float:
    score_recent = 0.0
    score_prev = 0.0
    for sig in signals:
        try:
            ts = datetime.fromisoformat(sig["timestamp"].replace("Z", "+00:00"))
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            hours_ago = (now - ts).total_seconds() / 3600
            if hours_ago <= 6:
                score_recent += sig["raw_weight"]
            elif hours_ago <= 12:
                score_prev += sig["raw_weight"]
        except Exception:
            pass
    # Prior 6h window empty → ratio blows up (EPSILON); smooth like Laplace + cap for sane tiers/UI.
    w = MOMENTUM_SMOOTHING
    ratio = (score_recent + w) / (score_prev + w)
    return min(ratio, MOMENTUM_CAP)


def _assign_tier(score: float, source_types: set, momentum: float, entity: str) -> str | None:
    if score < MIN_SCORE:
        return None
    # A score floor keeps a single article in a previously-silent window from hitting
    # breaking on momentum ratio alone.
    if momentum >= BREAKING_MOMENTUM and score >= BREAKING_MIN_SCORE:
        return "breaking"
    if (
        score >= EMERGING_SCORE
        or len(source_types) >= 3
        or (momentum >= MOMENTUM_THRESHOLD and score >= EMERGING_MOMENTUM_MIN_SCORE)
    ):
        return "emerging"
    return "watch"


def _signal_key(sig: dict) -> tuple:
    # Prefer URL as stable story identity; fall back to title for URL-less signals.
    url = (sig.get("url") or "").strip()
    return ("url", url) if url else ("title", sig["title"])


def _prefer_specific_over_umbrella(raw_clusters: dict[str, dict]) -> dict[str, dict]:
    # If a generic umbrella cluster overlaps with specific clusters on the same stories,
    # drop the umbrella one so the feed keeps diverse, concrete topics.
    keep = dict(raw_clusters)
    non_umbrella = [k for k in raw_clusters.keys() if k not in GENERIC_UMBRELLA_ENTITIES]
    for umbrella in GENERIC_UMBRELLA_ENTITIES:
        umbrella_cluster = raw_clusters.get(umbrella)
        if not umbrella_cluster:
            continue
        umbrella_keys = {_signal_key(s) for s in umbrella_cluster["signals"]}
        for specific in non_umbrella:
            overlap = umbrella_keys & {_signal_key(s) for s in raw_clusters[specific]["signals"]}
            if len(overlap) >= 2:
                keep.pop(umbrella, None)
                break
    return keep


def _merge_signal_overlap(raw_clusters: dict[str, dict], now: datetime) -> dict[str, dict]:
    """For signals shared across ≥2 entity clusters, create one merged story cluster
    and keep each entity's individual cluster with only its unique signals.

    e.g. Google + Nvidia both have the Foxconn article →
      • one "Google · Nvidia" card for the shared story
      • Google card kept if it has unique signals (stock move, other news)
      • Nvidia card kept if it has unique signals
    """
    # Map signal key → which entities claim it (set prevents double-counting
    # when the same entity has duplicate signals with the same URL)
    sig_to_entities: dict[tuple, set[str]] = defaultdict(set)
    for entity, cluster in raw_clusters.items():
        for sig in cluster["signals"]:
            sig_to_entities[_signal_key(sig)].add(entity)

    # Signals shared by ≥2 entities
    shared_sig_keys: set[tuple] = {
        k for k, ents in sig_to_entities.items() if len(ents) >= 2
    }

    if not shared_sig_keys:
        return raw_clusters

    # Union-find: connect entities that share ≥2 signals
    parent = {e: e for e in raw_clusters}

    def find(x: str) -> str:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(x: str, y: str) -> None:
        px, py = find(x), find(y)
        if px != py:
            parent[px] = py

    pair_overlap: dict[frozenset, int] = defaultdict(int)
    for k in shared_sig_keys:
        ents = list(sig_to_entities[k])
        for i in range(len(ents)):
            for j in range(i + 1, len(ents)):
                pair_overlap[frozenset({ents[i], ents[j]})] += 1

    for pair, count in pair_overlap.items():
        if count >= 1:
            a, b = tuple(pair)
            # Never merge through a generic umbrella entity — "AI" matching a Meta
            # article would otherwise vacuum all AI articles into the Meta card.
            if a in GENERIC_UMBRELLA_ENTITIES or b in GENERIC_UMBRELLA_ENTITIES:
                continue
            union(a, b)

    groups: dict[str, list[str]] = defaultdict(list)
    for entity in raw_clusters:
        groups[find(entity)].append(entity)

    result: dict[str, dict] = {}

    for root, members in groups.items():
        if len(members) == 1:
            result[members[0]] = raw_clusters[members[0]]
            continue

        member_set = set(members)

        # Which signal keys are shared within this group specifically
        group_shared_keys: set[tuple] = {
            k for k in shared_sig_keys
            if sum(1 for e in sig_to_entities[k] if e in member_set) >= 2
        }

        # --- One merged card: all signals from all members, deduplicated ---
        # Keeping separate "individual" cards caused the same entity (e.g. Meta) to
        # appear twice with duplicated price badges. One card per story group is cleaner.
        sorted_members = sorted(members, key=lambda e: -raw_clusters[e]["score"])
        seen: set = set()
        all_sigs: list[dict] = []
        for m in sorted_members:
            for sig in raw_clusters[m]["signals"]:
                k = _signal_key(sig)
                if k not in seen:
                    seen.add(k)
                    all_sigs.append(sig)

        combined_entity_names = list(dict.fromkeys(
            name for m in sorted_members for name in raw_clusters[m]["entities"]
        ))
        all_source_types: set[str] = set()
        for m in members:
            all_source_types.update(raw_clusters[m]["source_types"])

        score = _compute_score(all_sigs, now)
        momentum = max(raw_clusters[m]["momentum"] for m in members)
        tier = _assign_tier(score, all_source_types, momentum, combined_entity_names[0])
        if tier is None:
            tier = min(
                (raw_clusters[m]["tier"] for m in members),
                key=lambda t: {"breaking": 0, "emerging": 1, "watch": 2}.get(t, 9),
            )

        result[f"__story_{root}"] = {
            "id": str(uuid.uuid5(uuid.NAMESPACE_DNS, "|".join(sorted(combined_entity_names)))),
            "entities": combined_entity_names,
            "tier": tier,
            "score": round(score, 2),
            "momentum": round(momentum, 2),
            "source_types": list(all_source_types),
            "signals": _format_signals(all_sigs),
        }

    return result


def _merge_cross_domain(raw_clusters: dict[str, dict]) -> list[dict]:
    merged = []
    merged_entities: set[str] = set()

    for entity, cluster in raw_clusters.items():
        if entity in merged_entities:
            continue

        source_types = set(cluster["source_types"])
        domains_hit = {
            domain for domain, types in DOMAIN_GROUPS.items()
            if source_types & types
        }

        # Only promote to breaking when the cluster has enough substance.
        # A stock + one article trivially spans tech+finance but isn't a crisis.
        if len(domains_hit) >= 2 and cluster["score"] >= CROSS_DOMAIN_MIN_SCORE:
            cluster["tier"] = "breaking"
            if not entity.startswith("__"):
                cluster["entities"] = list({entity} | set(cluster["entities"]))

        merged.append(cluster)
        merged_entities.add(entity)

    return merged


def _dedupe_stock_signals_newest_per_entity(signals: list[dict]) -> list[dict]:
    """Keep one stock row per ticker/entity (newest timestamp wins).

    Stock scrapes use INSERT OR IGNORE on `id` only, so the DB can hold many
    same-day rows that share a title_hash; title_hash dedupe is not enough when
    UTC date rolls over or hashes drift. The UI also keys off `entities` per row.
    """
    non_stock = [s for s in signals if s["source_type"] != "stock"]
    stocks = [s for s in signals if s["source_type"] == "stock"]
    best: dict[str, dict] = {}
    for s in stocks:
        ents = s.get("entities") or []
        key = (ents[0] if ents else (s.get("title") or "").split()[0] or "").strip()
        if not key:
            non_stock.append(s)
            continue
        prev = best.get(key)
        if prev is None or s["timestamp"] > prev["timestamp"]:
            best[key] = s
    return non_stock + list(best.values())


_STOCK_PCT_RE = re.compile(r'[+-]?(\d+\.?\d*)%')
_STOCK_VOL_RE = re.compile(r'(\d+\.?\d*)x volume')


def _has_notable_stock_move(sigs: list[dict]) -> bool:
    for sig in sigs:
        title = sig.get("title", "")
        pct_match = _STOCK_PCT_RE.search(title)
        vol_match = _STOCK_VOL_RE.search(title)
        pct = float(pct_match.group(1)) if pct_match else 0.0
        vol = float(vol_match.group(1)) if vol_match else 1.0
        if pct >= 4.0 or vol >= 2.0:
            return True
    return False


def _add_narrative_mover_clusters(
    raw_clusters: dict[str, dict],
    stock_only_by_entity: dict[str, list[dict]],
    now: datetime,
) -> dict[str, dict]:
    """Create narrative Watch clusters when 2+ entities in same narrative have stock moves
    and none of them already have their own cluster (e.g. stock-only entities that were
    filtered out by the diversity gate but collectively signal a sector theme)."""
    represented = {e for c in raw_clusters.values() for e in c.get("entities", [])}

    narrative_entities: dict[str, list[str]] = defaultdict(list)
    for entity in stock_only_by_entity:
        if entity in represented:
            continue
        narrative = ENTITY_NARRATIVE_MAP.get(entity)
        if narrative:
            narrative_entities[narrative].append(entity)

    result = dict(raw_clusters)
    for narrative, entities in narrative_entities.items():
        if len(entities) < 2:
            continue
        all_sigs = []
        for e in entities:
            all_sigs.extend(stock_only_by_entity[e])
        all_sigs = _dedupe_stock_signals_newest_per_entity(all_sigs)
        if not all_sigs:
            continue

        score = _compute_score(all_sigs, now) * INTENT_CURATED_MULT
        momentum = _compute_momentum(all_sigs, now)
        tier = _assign_tier(score, {"stock"}, momentum, entities[0]) or "watch"

        result[f"__narrative_{narrative}"] = {
            "id": str(uuid.uuid5(uuid.NAMESPACE_DNS, f"narrative:{narrative}")),
            "entities": entities,
            "tier": tier,
            "score": round(score, 2),
            "momentum": round(momentum, 2),
            "source_types": ["stock"],
            "signals": _format_signals(all_sigs),
        }

    return result


def _tag_narrative(entities: list[str]) -> str | None:
    counts: dict[str, int] = {}
    for entity in entities:
        narrative = ENTITY_NARRATIVE_MAP.get(entity)
        if narrative:
            counts[narrative] = counts.get(narrative, 0) + 1
    if not counts:
        return None
    return max(counts, key=lambda n: counts[n])


def _dominant_layer(entities: list[str]) -> str | None:
    from collections import Counter
    layers = [ENTITY_LAYER_MAP.get(e) for e in entities if ENTITY_LAYER_MAP.get(e)]
    if not layers:
        return None
    return Counter(layers).most_common(1)[0][0]


def _compute_coherence(entities: list[str]) -> float:
    """Fraction of layer-tagged entities sharing the dominant layer.

    1.0 = all same layer (pure compute cluster), 0.5 = half split,
    0.0 not possible since dominant always wins at least 1/n.
    Returns 1.0 when no entities have layer tags (no penalty for untracked entities).
    """
    from collections import Counter
    layers = [ENTITY_LAYER_MAP.get(e) for e in entities if ENTITY_LAYER_MAP.get(e)]
    if not layers:
        return 1.0
    dominant_count = Counter(layers).most_common(1)[0][1]
    return dominant_count / len(layers)


def _format_signals(signals: list[dict]) -> list[dict]:
    out = []
    for s in sorted(signals, key=lambda x: x["timestamp"], reverse=True)[:10]:
        row = {
            "source_type": s["source_type"],
            "title": s["title"],
            "url": s.get("url", ""),
            "timestamp": s["timestamp"],
            "entities": s.get("entities") or [],
        }
        if s.get("diff_preview"):
            row["diff_preview"] = s["diff_preview"]
        out.append(row)
    return out
