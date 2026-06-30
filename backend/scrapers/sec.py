import feedparser
import hashlib
import uuid
import httpx
from datetime import datetime, timezone
from config import WATCHED_COMPANIES, SOURCE_WEIGHTS
from cache import upsert_signal
from scrapers.utils import extract_entities, parse_feed_date

# EDGAR full-text search RSS for Form 4 (insider trades)
EDGAR_RSS = "https://efts.sec.gov/LATEST/search-index?q=%22{ticker}%22&dateRange=custom&startdt={date}&forms=4&hits.hits._source=period_of_report,display_names,file_date,form_type"
EDGAR_BROWSE = "https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&company={ticker}&type=4&dateb=&owner=include&count=10&search_text=&output=atom"


def fetch():
    signals = []
    today = datetime.utcnow().date().isoformat()

    for ticker in WATCHED_COMPANIES:
        try:
            url = EDGAR_BROWSE.format(ticker=ticker)
            feed = feedparser.parse(url)
            for entry in feed.entries[:5]:
                title = entry.get("title", "").strip()
                link = entry.get("link", "")
                if not title or "ownership" not in title.lower():
                    continue

                title_hash = hashlib.md5(f"{ticker}-{title}".encode()).hexdigest()
                signal = {
                    "id": str(uuid.uuid4()),
                    "source_type": "sec",
                    "entities": extract_entities(ticker) or [ticker],
                    "title": f"[{ticker}] Insider filing: {title}",
                    "url": link,
                    "raw_weight": SOURCE_WEIGHTS["sec"],
                    "timestamp": parse_feed_date(entry),
                    "title_hash": title_hash,
                }
                upsert_signal(signal)
                signals.append(signal)
        except Exception as e:
            print(f"[sec] Error for {ticker}: {e}")

    return signals
