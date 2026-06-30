import os
import sqlite3
import json
from datetime import datetime, timezone
from pathlib import Path
from config import LEADING_SOURCE_TYPES, CONFIRMING_SOURCE_TYPES


def _now() -> str:
    """UTC timestamp as naive ISO string, SQLite-compatible."""
    return datetime.now(timezone.utc).replace(tzinfo=None).isoformat()

# Local ./data dir by default so it runs out of the box. In production set DB_DIR to a
# persistent volume (e.g. /data on Railway) so the SQLite file survives restarts.
_default_dir = Path(__file__).resolve().parent / "data"
_data_dir = Path(os.environ.get("DB_DIR") or _default_dir)
_data_dir.mkdir(parents=True, exist_ok=True)
DB_PATH = _data_dir / "signal.db"


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with get_conn() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS signals (
                id          TEXT PRIMARY KEY,
                source_type TEXT NOT NULL,
                entities    TEXT NOT NULL,  -- JSON array
                title       TEXT NOT NULL,
                url         TEXT,
                raw_weight  REAL NOT NULL,
                timestamp   TEXT NOT NULL,
                title_hash  TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS clusters (
                id          TEXT PRIMARY KEY,
                entities    TEXT NOT NULL,   -- JSON array
                tier        TEXT NOT NULL,   -- watch | emerging | breaking
                score       REAL NOT NULL,
                momentum    REAL NOT NULL,
                signals     TEXT NOT NULL,   -- JSON array of signal rows
                updated_at  TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS url_snapshots (
                url         TEXT PRIMARY KEY,
                label       TEXT NOT NULL,
                content     TEXT NOT NULL,
                updated_at  TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS job_counts (
                company     TEXT NOT NULL,
                keyword     TEXT NOT NULL,
                count       INTEGER NOT NULL,
                recorded_at TEXT NOT NULL,
                PRIMARY KEY (company, keyword, recorded_at)
            );

            CREATE TABLE IF NOT EXISTS signal_baseline (
                entity      TEXT NOT NULL,
                day         TEXT NOT NULL,   -- YYYY-MM-DD
                count       INTEGER NOT NULL,
                PRIMARY KEY (entity, day)
            );

            CREATE TABLE IF NOT EXISTS stock_prices (
                symbol        TEXT PRIMARY KEY,
                price         REAL NOT NULL,
                pct_change    REAL NOT NULL,
                volume_ratio  REAL NOT NULL DEFAULT 1.0,
                market_cap    REAL,
                next_earnings TEXT,
                updated_at    TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS cluster_summaries (
                cluster_id   TEXT PRIMARY KEY,
                signals_hash TEXT NOT NULL,
                summary      TEXT NOT NULL,
                generated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS cluster_history (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                cluster_id   TEXT NOT NULL,
                entities     TEXT NOT NULL,
                narrative    TEXT,
                signal_phase TEXT NOT NULL,
                tier         TEXT NOT NULL,
                score        REAL NOT NULL,
                momentum     REAL NOT NULL,
                recorded_at  TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_ch_cluster ON cluster_history(cluster_id);
            CREATE INDEX IF NOT EXISTS idx_ch_recorded ON cluster_history(recorded_at);
            CREATE INDEX IF NOT EXISTS idx_ch_phase ON cluster_history(signal_phase, recorded_at);

            CREATE TABLE IF NOT EXISTS price_history (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol       TEXT NOT NULL,
                price        REAL NOT NULL,
                pct_change   REAL NOT NULL,
                volume_ratio REAL NOT NULL DEFAULT 1.0,
                recorded_at  TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_ph_symbol ON price_history(symbol);
            CREATE INDEX IF NOT EXISTS idx_ph_recorded ON price_history(recorded_at);
            CREATE UNIQUE INDEX IF NOT EXISTS idx_ph_symbol_minute
                ON price_history(symbol, strftime('%Y-%m-%dT%H:%M', recorded_at));

            CREATE INDEX IF NOT EXISTS idx_signals_timestamp ON signals(timestamp);
            CREATE INDEX IF NOT EXISTS idx_signals_hash ON signals(title_hash);
        """)
        try:
            conn.execute("ALTER TABLE stock_prices ADD COLUMN market_cap REAL")
        except Exception:
            pass
        try:
            conn.execute("ALTER TABLE stock_prices ADD COLUMN next_earnings TEXT")
        except Exception:
            pass
        try:
            conn.execute("ALTER TABLE signals ADD COLUMN diff_preview TEXT")
        except Exception:
            pass
        try:
            conn.execute("ALTER TABLE clusters ADD COLUMN narrative TEXT")
        except Exception:
            pass
        try:
            conn.execute("ALTER TABLE clusters ADD COLUMN signal_phase TEXT")
        except Exception:
            pass
        try:
            conn.execute("ALTER TABLE clusters ADD COLUMN thesis_entered_at TEXT")
        except Exception:
            pass
        try:
            conn.execute("ALTER TABLE clusters ADD COLUMN coherence REAL")
        except Exception:
            pass
        try:
            conn.execute("ALTER TABLE clusters ADD COLUMN dominant_layer TEXT")
        except Exception:
            pass


def upsert_signal(signal: dict, replace: bool = False):
    verb = "INSERT OR REPLACE" if replace else "INSERT OR IGNORE"
    with get_conn() as conn:
        conn.execute(f"""
            {verb} INTO signals
                (id, source_type, entities, title, url, raw_weight, timestamp, title_hash, diff_preview)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            signal["id"],
            signal["source_type"],
            json.dumps(signal["entities"]),
            signal["title"],
            signal.get("url", ""),
            signal["raw_weight"],
            signal["timestamp"],
            signal["title_hash"],
            signal.get("diff_preview"),
        ))


def get_recent_signals(hours: int = 48) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute("""
            SELECT * FROM signals
            WHERE timestamp >= datetime('now', ?)
            ORDER BY timestamp DESC
        """, (f"-{hours} hours",)).fetchall()
    result = []
    for r in rows:
        d = dict(r)
        d["entities"] = json.loads(d["entities"])
        result.append(d)
    return result


def _has_earnings_today(signals: list[dict]) -> bool:
    today = datetime.now(timezone.utc).date()
    stock_entities = [
        e
        for s in signals if s.get("source_type") == "stock"
        for e in (s.get("entities") or [])
    ]
    if not stock_entities:
        return False
    with get_conn() as conn:
        for entity in stock_entities:
            row = conn.execute(
                "SELECT next_earnings FROM stock_prices WHERE symbol = ?", (entity,)
            ).fetchone()
            if row and row["next_earnings"]:
                try:
                    days = (datetime.fromisoformat(row["next_earnings"]).date() - today).days
                    if days in (0, -1):
                        return True
                except Exception:
                    pass
    return False


def _compute_signal_phase(signals: list[dict], narrative: str | None) -> str:
    sig_types = [s["source_type"] for s in signals]
    has_leading   = any(t in LEADING_SOURCE_TYPES for t in sig_types)
    has_confirming = any(t in CONFIRMING_SOURCE_TYPES for t in sig_types)
    # Earnings-day moves are expected events, not forward-looking thesis signals
    if _has_earnings_today(signals):
        return "event"
    if has_leading and not has_confirming:
        return "thesis"
    if has_leading and has_confirming:
        # With a 30-day signal window, almost every cluster has old news in it.
        # Compare timestamps: if the freshest leading signal (jobs, watcher, sec,
        # arxiv) is newer than the freshest confirming signal, news hasn't caught
        # up to the move yet → still thesis.
        structural_sigs  = [s for s in signals if s["source_type"] in LEADING_SOURCE_TYPES]
        confirming_sigs  = [s for s in signals if s["source_type"] in CONFIRMING_SOURCE_TYPES]
        if structural_sigs:
            newest_structural = max(s["timestamp"] for s in structural_sigs)
            newest_confirming = max(s["timestamp"] for s in confirming_sigs)
            if newest_structural > newest_confirming:
                return "thesis"
        return "confirming"
    return "event"


def save_clusters(clusters: list[dict]):
    now = _now()
    active_ids = {c["id"] for c in clusters}
    with get_conn() as conn:
        # Snapshot existing phase+tier state before expiry
        existing_phase: dict[str, sqlite3.Row] = {}
        if active_ids:
            rows = conn.execute(
                "SELECT id, signal_phase, tier, thesis_entered_at FROM clusters WHERE id IN ({})".format(
                    ",".join("?" * len(active_ids))
                ),
                list(active_ids),
            ).fetchall()
            existing_phase = {r["id"]: r for r in rows}

        # Delete clusters the correlator no longer produces. No time-based grace
        # period — this runs inside the same transaction as the INSERTs below, so
        # it's atomic: if any insert fails, the whole batch rolls back.
        # The previous datetime-based guard was silently broken: _now() writes
        # ISO T-format strings ('2026-05-23T14:16:00') but SQLite's datetime('now')
        # returns space-format ('2026-05-23 14:16:00'); since 'T' > ' ' in ASCII,
        # the comparison was always false and stale clusters accumulated forever.
        conn.execute("""
            DELETE FROM clusters
            WHERE id NOT IN ({})
        """.format(",".join("?" * len(active_ids)) if active_ids else "SELECT NULL"),
            list(active_ids) if active_ids else [],
        )
        for c in clusters:
            signal_phase = _compute_signal_phase(c["signals"], c.get("narrative"))

            # Preserve thesis_entered_at: set on first thesis entry, never cleared after graduation
            prev = existing_phase.get(c["id"])
            if signal_phase == "thesis":
                thesis_entered_at = (prev["thesis_entered_at"] if prev else None) or now
            else:
                thesis_entered_at = prev["thesis_entered_at"] if prev else None

            conn.execute("""
                INSERT OR REPLACE INTO clusters
                    (id, entities, tier, score, momentum, signals, narrative,
                     signal_phase, thesis_entered_at, coherence, dominant_layer, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                c["id"],
                json.dumps(c["entities"]),
                c["tier"],
                c["score"],
                c["momentum"],
                json.dumps(c["signals"]),
                c.get("narrative"),
                signal_phase,
                thesis_entered_at,
                c.get("coherence"),
                c.get("dominant_layer"),
                now,
            ))

            # Log to cluster_history whenever phase or tier changes (or first seen)
            prev_phase = prev["signal_phase"] if prev else None
            prev_tier  = prev["tier"] if prev else None
            if signal_phase != prev_phase or c["tier"] != prev_tier:
                conn.execute("""
                    INSERT INTO cluster_history
                        (cluster_id, entities, narrative, signal_phase, tier, score, momentum, recorded_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    c["id"],
                    json.dumps(c["entities"]),
                    c.get("narrative"),
                    signal_phase,
                    c["tier"],
                    c["score"],
                    c["momentum"],
                    now,
                ))


def get_clusters() -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM clusters ORDER BY score DESC"
        ).fetchall()
    result = []
    for r in rows:
        d = dict(r)
        d["entities"] = json.loads(d["entities"])
        d["signals"] = json.loads(d["signals"])
        try:
            updated = datetime.fromisoformat(d["updated_at"])
            age = (datetime.now(timezone.utc).replace(tzinfo=None) - updated.replace(tzinfo=None)).total_seconds()
            d["stale"] = age > 3600
        except Exception:
            d["stale"] = False
        # Phase is now stored at write time; derive leading/confirming source lists on read
        d["signal_phase"] = d.get("signal_phase") or "event"
        sig_types = [s["source_type"] for s in d["signals"]]
        d["leading_sources"]    = list(dict.fromkeys(t for t in sig_types if t in LEADING_SOURCE_TYPES))
        d["confirming_sources"] = list(dict.fromkeys(t for t in sig_types if t in CONFIRMING_SOURCE_TYPES))

        result.append(d)
    return result


def get_url_snapshot(url: str) -> str | None:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT content FROM url_snapshots WHERE url = ?", (url,)
        ).fetchone()
    return row["content"] if row else None


def save_url_snapshot(url: str, label: str, content: str):
    with get_conn() as conn:
        conn.execute("""
            INSERT OR REPLACE INTO url_snapshots (url, label, content, updated_at)
            VALUES (?, ?, ?, ?)
        """, (url, label, content, _now()))


def save_job_count(company: str, keyword: str, count: int):
    with get_conn() as conn:
        conn.execute("""
            INSERT OR IGNORE INTO job_counts (company, keyword, count, recorded_at)
            VALUES (?, ?, ?, ?)
        """, (company, keyword, count, datetime.now(timezone.utc).date().isoformat()))


def get_job_count_delta(company: str, keyword: str) -> tuple[int, int]:
    """Returns (current_count, previous_count)."""
    with get_conn() as conn:
        rows = conn.execute("""
            SELECT count FROM job_counts
            WHERE company = ? AND keyword = ?
            ORDER BY recorded_at DESC LIMIT 2
        """, (company, keyword)).fetchall()
    counts = [r["count"] for r in rows]
    current = counts[0] if counts else 0
    previous = counts[1] if len(counts) > 1 else 0
    return current, previous


def get_entity_baseline(entity: str, days: int = 7) -> float:
    with get_conn() as conn:
        row = conn.execute("""
            SELECT AVG(count) as avg FROM signal_baseline
            WHERE entity = ?
            AND day >= date('now', ?)
        """, (entity, f"-{days} days")).fetchone()
    return row["avg"] or 0.0


def save_stock_price(symbol: str, price: float, pct_change: float, volume_ratio: float = 1.0, market_cap: float | None = None):
    now = _now()
    with get_conn() as conn:
        conn.execute("""
            INSERT OR REPLACE INTO stock_prices (symbol, price, pct_change, volume_ratio, market_cap, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (symbol, price, pct_change, volume_ratio, market_cap, now))
        # price_history: UNIQUE index on (symbol, minute) prevents duplicate rows per scrape cycle
        conn.execute("""
            INSERT OR IGNORE INTO price_history (symbol, price, pct_change, volume_ratio, recorded_at)
            VALUES (?, ?, ?, ?, ?)
        """, (symbol, price, pct_change, volume_ratio, now))


def save_earnings_date(symbol: str, next_earnings: str):
    with get_conn() as conn:
        conn.execute(
            "UPDATE stock_prices SET next_earnings = ? WHERE symbol = ?",
            (next_earnings, symbol),
        )


def get_all_stock_prices() -> dict:
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM stock_prices").fetchall()
    return {r["symbol"]: dict(r) for r in rows}


def get_cached_summary(cluster_id: str, signals_hash: str) -> str | None:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT summary FROM cluster_summaries WHERE cluster_id = ? AND signals_hash = ?",
            (cluster_id, signals_hash),
        ).fetchone()
    return row["summary"] if row else None


def save_summary(cluster_id: str, signals_hash: str, summary: str):
    with get_conn() as conn:
        conn.execute("""
            INSERT OR REPLACE INTO cluster_summaries (cluster_id, signals_hash, summary, generated_at)
            VALUES (?, ?, ?, ?)
        """, (cluster_id, signals_hash, summary, _now()))


def get_signal_by_id(signal_id: str) -> dict | None:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM signals WHERE id = ?", (signal_id,)
        ).fetchone()
    if not row:
        return None
    d = dict(row)
    d["entities"] = json.loads(d["entities"])
    return d


def update_entity_baseline(entity: str, count: int):
    today = datetime.now(timezone.utc).date().isoformat()
    with get_conn() as conn:
        conn.execute("""
            INSERT OR REPLACE INTO signal_baseline (entity, day, count)
            VALUES (?, ?, ?)
        """, (entity, today, count))


def vacuum_old_signals(days: int = 14):
    with get_conn() as conn:
        conn.execute(
            "DELETE FROM signals WHERE timestamp < datetime('now', ?)",
            (f"-{days} days",),
        )
