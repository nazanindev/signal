import feedparser
import hashlib
from datetime import datetime, timezone
from config import TECH_FEEDS, SOURCE_WEIGHTS
from cache import upsert_signal
from scrapers.utils import extract_entities, parse_feed_date


def fetch():
    signals = []
    seen_hashes = set()
    total_entries = 0

    for feed_url in TECH_FEEDS:
        try:
            feed = feedparser.parse(feed_url)
            for entry in feed.entries[:15]:
                title = entry.get("title", "").strip()
                url = entry.get("link", "")
                if not title:
                    continue

                total_entries += 1
                title_hash = hashlib.md5(title.lower().encode()).hexdigest()
                if title_hash in seen_hashes:
                    continue
                seen_hashes.add(title_hash)

                signal = {
                    "id": f"news-{title_hash}",
                    "source_type": "news",
                    "entities": extract_entities(title),
                    "title": title,
                    "url": url,
                    "raw_weight": SOURCE_WEIGHTS["news"],
                    "timestamp": parse_feed_date(entry),
                    "title_hash": title_hash,
                }
                upsert_signal(signal)
                signals.append(signal)
        except Exception as e:
            print(f"[tech] Error fetching {feed_url}: {e}")

    print(f"[tech] {len(signals)} unique articles from {len(TECH_FEEDS)} feeds ({total_entries} raw entries)")
    return signals
