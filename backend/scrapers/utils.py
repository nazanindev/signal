import re
from datetime import datetime, timezone
from config import ENTITY_LIST, ENTITY_ALIASES, ENTITY_FALSE_POSITIVE_CONTEXT


def extract_entities(text: str, title: str | None = None) -> list[str]:
    """Extract entity mentions from text.

    When a separate title is provided (e.g. for arxiv), an entity must appear
    in the title OR at least twice in the body — single passing mentions in
    abstracts (related-work citations, one-off comparisons) are ignored.
    """
    found = set()
    for entity in ENTITY_LIST:
        # Require the match to not be immediately followed by a hyphen so that
        # "meta-analysis" doesn't match "Meta", "pre-Roe" doesn't match "Roe", etc.
        pattern = r'\b' + re.escape(entity) + r'(?!-)\b'
        # All-caps acronyms / tickers (e.g. NVDA, ASML, SEC) match case-sensitively
        # to avoid false positives like "sec" inside "second".
        flags = 0 if (entity.isupper() and len(entity) > 2) else re.IGNORECASE

        if title is not None:
            in_title = bool(re.search(pattern, title, flags))
            body_count = len(re.findall(pattern, text, flags))
            if not in_title and body_count < 2:
                continue
        else:
            if not re.search(pattern, text, flags):
                continue

        canonical = ENTITY_ALIASES.get(entity, entity)
        fp_phrases = ENTITY_FALSE_POSITIVE_CONTEXT.get(canonical, [])
        combined = (title or "") + " " + text
        if any(phrase.lower() in combined.lower() for phrase in fp_phrases):
            continue
        found.add(canonical)
    return list(found)


def parse_feed_date(entry) -> str:
    if hasattr(entry, "published_parsed") and entry.published_parsed:
        try:
            dt = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
            return dt.isoformat()
        except Exception:
            pass
    if hasattr(entry, "updated_parsed") and entry.updated_parsed:
        try:
            dt = datetime(*entry.updated_parsed[:6], tzinfo=timezone.utc)
            return dt.isoformat()
        except Exception:
            pass
    return datetime.now(timezone.utc).isoformat()
