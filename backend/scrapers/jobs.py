import hashlib
import uuid
import httpx
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from config import JOB_SEARCHES, SOURCE_WEIGHTS
from cache import upsert_signal, save_job_count, get_job_count_delta
from scrapers.utils import extract_entities

ATS_URLS = {
    "greenhouse": "https://boards-api.greenhouse.io/v1/boards/{slug}/jobs",
    "ashby":      "https://api.ashbyhq.com/posting-api/job-board/{slug}",
    "lever":      "https://api.lever.co/v0/postings/{slug}?mode=json",
}

HEADERS = {"User-Agent": "Mozilla/5.0"}


def _fetch_jobs(ats: str, slug: str) -> tuple[list[dict], str]:
    url = ATS_URLS[ats].format(slug=slug)
    r = httpx.get(url, timeout=10, headers=HEADERS, follow_redirects=True)
    r.raise_for_status()
    raw = r.json()
    if ats != "lever":
        raw = raw.get("jobs", [])
    jobs = []
    for job in raw:
        if ats == "greenhouse":
            jobs.append({
                "title":      job.get("title", ""),
                "url":        job.get("absolute_url", ""),
                "location":   (job.get("location") or {}).get("name", ""),
                "department": "",
                "posted_at":  job.get("first_published") or job.get("updated_at", ""),
            })
        elif ats == "ashby":
            jobs.append({
                "title":      job.get("title", ""),
                "url":        job.get("jobUrl", ""),
                "location":   job.get("location", ""),
                "department": job.get("department", ""),
                "posted_at":  job.get("publishedAt", ""),
            })
        elif ats == "lever":
            cats = job.get("categories", {})
            jobs.append({
                "title":      job.get("text", ""),
                "url":        job.get("hostedUrl", ""),
                "location":   cats.get("location", ""),
                "department": cats.get("department", ""),
                "posted_at":  str(job.get("createdAt", "")),
            })
    return jobs, url


def _fetch_count(ats: str, slug: str) -> tuple[int, str]:
    jobs, url = _fetch_jobs(ats, slug)
    return len(jobs), url


def fetch_listings() -> list[dict]:
    """Return all individual job listings across all tracked companies, newest first."""
    all_jobs = []

    def _for_company(search):
        try:
            listings, _ = _fetch_jobs(search["ats"], search["slug"])
            return [{"company": search["company"], **j} for j in listings]
        except Exception as e:
            print(f"[jobs] Error fetching listings for {search['company']}: {e}")
            return []

    with ThreadPoolExecutor(max_workers=len(JOB_SEARCHES)) as pool:
        for result in as_completed([pool.submit(_for_company, s) for s in JOB_SEARCHES]):
            all_jobs.extend(result.result())

    all_jobs.sort(key=lambda j: j.get("posted_at", ""), reverse=True)
    return all_jobs


def fetch():
    signals = []

    for search in JOB_SEARCHES:
        company = search["company"]
        ats = search["ats"]
        slug = search["slug"]
        try:
            count, url = _fetch_count(ats, slug)
            print(f"[jobs] {company}: {count} open roles")
            save_job_count(company, "all", count)

            current, previous = get_job_count_delta(company, "all")
            if previous == 0 or current == 0:
                continue

            ratio = current / previous
            delta = current - previous

            if ratio < 1.2 and delta < 3:
                continue

            title = f"{company} hiring surge: {count} open roles (+{delta} vs last check, {ratio:.1f}x)"
            title_hash = hashlib.md5(f"jobs-{company}-{datetime.utcnow().date()}".encode()).hexdigest()

            signal = {
                "id": str(uuid.uuid4()),
                "source_type": "jobs",
                "entities": extract_entities(company) or [company],
                "title": title,
                "url": url,
                "raw_weight": SOURCE_WEIGHTS["jobs"],
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "title_hash": title_hash,
            }
            upsert_signal(signal)
            signals.append(signal)
        except Exception as e:
            print(f"[jobs] Error for {company}: {e}")

    return signals
