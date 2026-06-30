import hashlib
import uuid
import difflib
import re
import httpx
from datetime import datetime, timezone
from config import WATCHED_URLS, SOURCE_WEIGHTS
from cache import upsert_signal, get_url_snapshot, save_url_snapshot
from scrapers.utils import extract_entities


def _strip_html(text: str) -> str:
    """Remove scripts, styles, and HTML tags; collapse whitespace to readable plain text."""
    text = re.sub(r'<script[^>]*>.*?</script>', ' ', text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'<style[^>]*>.*?</style>', ' ', text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'<[^>]+>', ' ', text)
    text = re.sub(r'&[a-zA-Z]+;', ' ', text)
    text = re.sub(r'&#\d+;', ' ', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text


# Patterns that change on every request but carry no signal (UUIDs, reference IDs,
# cache-busters, CSRF tokens, session nonces, epoch timestamps).
_DYNAMIC_NOISE = re.compile(
    r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}'  # UUID v4
    r'|(?:reference\s*id|ref\s*id|nonce|token|csrftoken)[:\s=]+[\w.\-]+'  # named tokens
    r'|\b[0-9a-f]{8,}\.[0-9a-f]{8,}\.[0-9a-f]{8,}\b'  # dot-separated hex blobs (SEC ref IDs)
    r'|\b\d{10,13}\b',  # epoch timestamps (10-13 digits)
    re.IGNORECASE,
)

def _normalize(text: str) -> str:
    """Strip dynamic per-request noise before diffing."""
    return _DYNAMIC_NOISE.sub('<dynamic>', text)


_ERROR_PAGE_MARKERS = [
    'request rate threshold exceeded',
    'access denied',
    '403 forbidden',
    '429 too many requests',
    'automated access',
    'captcha',
]

def _is_error_page(text: str) -> bool:
    lower = text.lower()
    return any(m in lower for m in _ERROR_PAGE_MARKERS)


def fetch():
    signals = []

    for item in WATCHED_URLS:
        url = item["url"]
        label = item["label"]
        try:
            resp = httpx.get(url, timeout=15, follow_redirects=True,
                             headers={"User-Agent": "Mozilla/5.0 (compatible; LifeDashboard/1.0)"})

            # Don't store or diff error pages — they'd poison the snapshot baseline
            if resp.status_code < 200 or resp.status_code >= 300:
                print(f"[watcher] {url} returned {resp.status_code}, skipping")
                continue

            current_text = resp.text

            previous_text = get_url_snapshot(url)
            save_url_snapshot(url, label, current_text)

            if previous_text is None:
                continue

            # If the stored snapshot was an error/rate-limit page, silently reset
            # the baseline to the current good content instead of diffing noise.
            if _is_error_page(previous_text):
                continue

            if previous_text == current_text:
                continue

            prev_plain = _normalize(_strip_html(previous_text)).splitlines()
            curr_plain = _normalize(_strip_html(current_text)).splitlines()

            plain_diff = list(difflib.unified_diff(prev_plain, curr_plain, lineterm="", n=0))
            n_added = sum(1 for l in plain_diff if l.startswith("+") and not l.startswith("+++"))
            n_removed = sum(1 for l in plain_diff if l.startswith("-") and not l.startswith("---"))

            if n_added == 0 and n_removed == 0:
                continue  # only scripts/styles changed, nothing visible

            added_plain = [l[1:].strip() for l in plain_diff if l.startswith("+") and not l.startswith("+++")]
            removed_plain = [l[1:].strip() for l in plain_diff if l.startswith("-") and not l.startswith("---")]

            preview_lines = []
            for line in removed_plain[:3]:
                if line:
                    preview_lines.append(f"− {line}")
            for line in added_plain[:3]:
                if line:
                    preview_lines.append(f"+ {line}")
            diff_preview = "\n".join(preview_lines) or None

            change_summary = f"{n_added} lines added, {n_removed} lines removed"
            title = f"[CHANGED] {label}: {change_summary}"
            title_hash = hashlib.md5(f"watcher-{url}-{datetime.now(timezone.utc).date()}".encode()).hexdigest()

            signal = {
                "id": str(uuid.uuid4()),
                "source_type": "watcher",
                "entities": extract_entities(label + " " + url),
                "title": title,
                "url": url,
                "raw_weight": SOURCE_WEIGHTS["watcher"],
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "title_hash": title_hash,
                "diff_preview": diff_preview,
            }
            upsert_signal(signal)
            signals.append(signal)
        except Exception as e:
            print(f"[watcher] Error for {url}: {e}")

    return signals
