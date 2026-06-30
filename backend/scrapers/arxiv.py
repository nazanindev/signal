import feedparser
import hashlib
import uuid
from datetime import datetime, timezone
from config import ARXIV_CATEGORIES, ARXIV_MAX_RESULTS, SOURCE_WEIGHTS
from cache import upsert_signal
from scrapers.utils import extract_entities, parse_feed_date

ARXIV_RSS = "https://rss.arxiv.org/rss/{category}"


def fetch():
    signals = []
    seen_hashes = set()

    for category in ARXIV_CATEGORIES:
        try:
            url = ARXIV_RSS.format(category=category)
            feed = feedparser.parse(url)
            for entry in feed.entries[:ARXIV_MAX_RESULTS]:
                title = entry.get("title", "").strip()
                link = entry.get("link", "")
                summary = entry.get("summary", "")
                authors = entry.get("author", "")

                if not title:
                    continue

                title_hash = hashlib.md5(title.lower().encode()).hexdigest()
                if title_hash in seen_hashes:
                    continue
                seen_hashes.add(title_hash)

                display = f"[{category}] {title}"
                if authors:
                    display += f" — {authors[:80]}"

                signal = {
                    "id": str(uuid.uuid4()),
                    "source_type": "arxiv",
                    "entities": extract_entities(summary, title=title),
                    "title": display,
                    "url": link,
                    "raw_weight": SOURCE_WEIGHTS["arxiv"],
                    "timestamp": parse_feed_date(entry),
                    "title_hash": title_hash,
                }
                upsert_signal(signal)
                signals.append(signal)
        except Exception as e:
            print(f"[arxiv] Error for {category}: {e}")

    return signals
