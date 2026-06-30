import hashlib
import os
import threading
import warnings
warnings.filterwarnings("ignore", ".*utcnow.*")
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import anthropic
from cache import (
    init_db, get_clusters, get_cached_summary, save_summary,
    get_all_stock_prices,
)
from config import ENTITY_ALIASES, AI_ENABLED
import scheduler as sched
import scrapers.tech as tech
import scrapers.stocks as stocks
import scrapers.sec as sec
import scrapers.jobs as jobs
import scrapers.watcher as watcher
import scrapers.arxiv as arxiv
import correlator


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    # Run first scrape + correlate in background so startup is fast
    def initial_run():
        print("[startup] Running initial scrape...")
        tech.fetch()
        stocks.fetch()
        sec.fetch()
        jobs.fetch()
        watcher.fetch()
        arxiv.fetch()
        correlator.run()
        print("[startup] Initial run complete.")
    threading.Thread(target=initial_run, daemon=True).start()
    sched.start()
    yield
    sched.stop()


app = FastAPI(title="Signal API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)


_anthropic_client: anthropic.Anthropic | None = None


def _get_anthropic() -> anthropic.Anthropic:
    global _anthropic_client
    if _anthropic_client is None:
        _anthropic_client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    return _anthropic_client


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/api/feed")
def feed():
    clusters = get_clusters()
    return {
        "clusters": clusters,
        "count": len(clusters),
    }


@app.get("/api/stocks")
def stock_prices():
    # Invert ENTITY_ALIASES (ticker→name) to entity_to_ticker (name→ticker) so the
    # frontend can link entity cards to their live price. Dict iteration order means
    # later entries win on name collisions (GOOG wins over GOOGL for Google).
    entity_to_ticker = {name: ticker for ticker, name in ENTITY_ALIASES.items()}
    return {
        "prices": get_all_stock_prices(),
        "entity_to_ticker": entity_to_ticker,
    }


@app.get("/api/health/scrapers")
def scraper_health():
    return {"scrapers": sched.scraper_health}


_SCRAPER_MAP = {
    "tech":       tech.fetch,
    "stocks":     stocks.fetch,
    "sec":        sec.fetch,
    "jobs":       jobs.fetch,
    "watcher":    watcher.fetch,
    "arxiv":      arxiv.fetch,
    "correlator": correlator.run,
}


@app.post("/api/run/{name}")
def run_scraper(name: str):
    fn = _SCRAPER_MAP.get(name)
    if not fn:
        raise HTTPException(status_code=404, detail=f"Unknown scraper '{name}'. Valid: {sorted(_SCRAPER_MAP)}")
    threading.Thread(target=lambda: sched._run(name, fn), daemon=True).start()
    return {"status": "started", "scraper": name}


@app.get("/api/clusters/{cluster_id}/summary")
def cluster_summary(cluster_id: str):
    from cache import get_conn as _get_conn
    clusters = get_clusters()
    cluster = next((c for c in clusters if c["id"] == cluster_id), None)

    # If the cluster expired from the live table, return any cached summary we have
    if not cluster:
        with _get_conn() as conn:
            row = conn.execute(
                "SELECT summary FROM cluster_summaries WHERE cluster_id = ?", (cluster_id,)
            ).fetchone()
        if row:
            return {"summary": row["summary"], "cached": True}
        raise HTTPException(status_code=404, detail="Cluster not found")

    signals = cluster["signals"]
    sig_titles = sorted(s["title"] for s in signals)
    signals_hash = hashlib.md5("|".join(sig_titles).encode()).hexdigest()

    cached = get_cached_summary(cluster_id, signals_hash)
    if cached:
        return {"summary": cached, "cached": True}

    if not AI_ENABLED:
        return {"summary": "AI summaries are off.", "cached": False, "disabled": True}

    signals_text = "\n".join(
        f"- [{s['source_type']}] {s['title']}"
        for s in signals
    )
    narrative = cluster.get("narrative") or ""
    signal_phase = cluster.get("signal_phase") or "event"

    phase_context = {
        "thesis": "Price/activity is moving before any news. Something is happening — no one's written the story yet.",
        "confirming": "Early signals are now backed by news. The story is catching up to the move.",
        "event": "This is driven by a specific event or announcement.",
    }.get(signal_phase, "")

    prompt = (
        f"You are writing a short summary for a personal signal dashboard. "
        f"Plain English only — no headers, no bullet points, no bold text. "
        f"Write 4 sentences: what's actually happening, why it's surfacing now, "
        f"what the signal sources suggest about how real this is, and what to watch next. "
        f"Under 100 words total. {phase_context} "
        f"Use hedged language only: 'suggests', 'consistent with', 'may indicate', 'points toward'.\n\n"
        f"Entities: {', '.join(cluster['entities'])}\n"
        f"Narrative: {narrative or 'n/a'}\n"
        f"Signals:\n{signals_text}"
    )

    message = _get_anthropic().messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=220,
        messages=[{"role": "user", "content": prompt}],
    )
    summary = message.content[0].text
    save_summary(cluster_id, signals_hash, summary)
    return {"summary": summary, "cached": False}
