import time
from datetime import datetime, timedelta, timezone
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger
import scrapers.tech as tech
import scrapers.stocks as stocks
import scrapers.sec as sec
import scrapers.jobs as jobs
import scrapers.watcher as watcher
import scrapers.arxiv as arxiv
import correlator
from cache import vacuum_old_signals

scheduler = BackgroundScheduler()

# Per-scraper health state: name → {last_run, last_error, ok, duration_s}
scraper_health: dict[str, dict] = {}


def _run(name: str, fn):
    t = time.monotonic()
    try:
        fn()
        scraper_health[name] = {
            "last_run": datetime.now(timezone.utc).isoformat(),
            "last_error": None,
            "ok": True,
            "duration_s": round(time.monotonic() - t, 1),
        }
    except Exception as e:
        scraper_health[name] = {
            "last_run": datetime.now(timezone.utc).isoformat(),
            "last_error": str(e),
            "ok": False,
            "duration_s": round(time.monotonic() - t, 1),
        }
        print(f"[scheduler] {name} error: {e}")


def run_scrapers():
    print("[scheduler] Running scrapers...")
    _run("tech", tech.fetch)
    _run("stocks", stocks.fetch)
    _run("sec", sec.fetch)
    _run("jobs", jobs.fetch)
    _run("watcher", watcher.fetch)
    _run("arxiv", arxiv.fetch)
    print("[scheduler] Scrapers done.")


def run_correlator():
    print("[scheduler] Running correlator...")
    _run("correlator", correlator.run)


def run_vacuum():
    vacuum_old_signals(days=14)
    print("[scheduler] Vacuumed signals older than 14 days.")


def run_morning_brief():
    import morning_brief
    morning_brief.run()


def start():
    # Scrape every 30 minutes
    scheduler.add_job(run_scrapers, IntervalTrigger(minutes=30), id="scrapers", replace_existing=True)
    # Correlate every 5 minutes — delay first run by 2 min so initial scrape can finish
    scheduler.add_job(
        run_correlator,
        IntervalTrigger(minutes=5, start_date=datetime.now(timezone.utc) + timedelta(minutes=2)),
        id="correlator",
        replace_existing=True,
    )
    # Vacuum old signals once a day
    scheduler.add_job(run_vacuum, IntervalTrigger(hours=24), id="vacuum", replace_existing=True)
    # Morning brief at 7am PT daily — uses the Claude API, so only schedule it when AI is
    # explicitly enabled (otherwise it would spend on the API).
    from config import AI_ENABLED
    if AI_ENABLED:
        scheduler.add_job(
            run_morning_brief,
            CronTrigger(hour=7, minute=0, timezone="America/Los_Angeles"),
            id="morning_brief",
            replace_existing=True,
        )
    scheduler.start()
    brief_note = "brief at 7am PT" if AI_ENABLED else "brief OFF (AI disabled)"
    print(f"[scheduler] Started — scrapers every 30min, correlator every 5min, vacuum daily, {brief_note}")


def stop():
    scheduler.shutdown()
