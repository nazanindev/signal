import os
from dotenv import load_dotenv

load_dotenv()

# Master switch for all Claude API calls (the on-demand cluster summaries + the
# morning brief). Defaults OFF so the app never spends on the API unless this is
# explicitly enabled. Cached text already in the DB is still served when off.
AI_ENABLED = os.getenv("AI_ENABLED", "false").strip().lower() in ("1", "true", "yes", "on")

# --- News (general tech/business RSS) ---
# Swap these for whatever feeds you want the dashboard to watch.
TECH_FEEDS = [
    "https://feeds.arstechnica.com/arstechnica/index",
    "https://hnrss.org/frontpage",
    "https://feeds.reuters.com/reuters/businessNews",
    "https://www.wired.com/feed/rss",
    "https://www.technologyreview.com/feed/",
    "https://feeds.marketwatch.com/marketwatch/topstories/",
    "https://www.cnbc.com/id/10001147/device/rss/rss.html",
]

# --- Company Registry ---
# Single source of truth for tracked companies (public, pre-IPO, private, crypto).
# STOCK_TICKERS and the narrative/layer maps are derived from this list. Edit it to
# track whatever you care about — the rest of the engine follows automatically.
COMPANIES = [
    # ---- AI Infrastructure ----
    # layer: compute | foundry_cloud | model | data | application
    {"name": "Nvidia",      "ticker": "NVDA",  "narrative": "AI Infrastructure", "layer": "compute",       "stage": "public"},
    {"name": "AMD",         "ticker": "AMD",   "narrative": "AI Infrastructure", "layer": "compute",       "stage": "public"},
    {"name": "Intel",       "ticker": "INTC",  "narrative": "AI Infrastructure", "layer": "compute",       "stage": "public"},
    {"name": "CoreWeave",   "ticker": "CRWV",  "narrative": "AI Infrastructure", "layer": "foundry_cloud", "stage": "public"},
    {"name": "Anthropic",   "ticker": None,    "narrative": "AI Infrastructure", "layer": "model",         "stage": "pre-ipo"},
    {"name": "OpenAI",      "ticker": None,    "narrative": "AI Infrastructure", "layer": "model",         "stage": "pre-ipo"},
    {"name": "xAI",         "ticker": None,    "narrative": "AI Infrastructure", "layer": "model",         "stage": "pre-ipo"},
    {"name": "DeepMind",    "ticker": None,    "narrative": "AI Infrastructure", "layer": "model",         "stage": "pre-ipo"},
    {"name": "Mistral AI",  "ticker": None,    "narrative": "AI Infrastructure", "layer": "model",         "stage": "pre-ipo"},
    {"name": "Cohere",      "ticker": None,    "narrative": "AI Infrastructure", "layer": "model",         "stage": "pre-ipo"},
    {"name": "Scale AI",    "ticker": None,    "narrative": "AI Infrastructure", "layer": "data",          "stage": "pre-ipo"},
    {"name": "Perplexity",  "ticker": None,    "narrative": "AI Infrastructure", "layer": "application",   "stage": "pre-ipo"},
    {"name": "Runway",      "ticker": None,    "narrative": "AI Infrastructure", "layer": "application",   "stage": "pre-ipo"},
    # ---- AI Platforms ----
    {"name": "Apple",       "ticker": "AAPL",  "narrative": "AI Platforms", "layer": "application", "stage": "public"},
    {"name": "Microsoft",   "ticker": "MSFT",  "narrative": "AI Platforms", "layer": "application", "stage": "public"},
    {"name": "Meta",        "ticker": "META",  "narrative": "AI Platforms", "layer": "application", "stage": "public"},
    {"name": "Google",      "ticker": "GOOG",  "narrative": "AI Platforms", "layer": "application", "stage": "public"},
    {"name": "Amazon",      "ticker": "AMZN",  "narrative": "AI Platforms", "layer": "foundry_cloud","stage": "public"},
    {"name": "Tesla",       "ticker": "TSLA",  "narrative": "AI Platforms", "layer": "application", "stage": "public"},
    {"name": "Palantir",    "ticker": "PLTR",  "narrative": "AI Platforms", "layer": "application", "stage": "public"},
    # ---- Nuclear & Energy ----
    # layer: advanced_nuclear | fuel_cell | oil_gas | grid_infra
    {"name": "Oklo",        "ticker": "OKLO",  "narrative": "Nuclear & Energy", "layer": "advanced_nuclear", "stage": "public"},
    {"name": "GE",          "ticker": "GE",    "narrative": "Nuclear & Energy", "layer": "advanced_nuclear", "stage": "public"},
    {"name": "Bloom Energy","ticker": "BE",    "narrative": "Nuclear & Energy", "layer": "fuel_cell",        "stage": "public"},
    {"name": "Eaton",       "ticker": "ETN",   "narrative": "Nuclear & Energy", "layer": "grid_infra",       "stage": "public"},
    {"name": "ExxonMobil",  "ticker": "XOM",   "narrative": "Nuclear & Energy", "layer": "oil_gas",          "stage": "public"},
    # ---- Industrials ----
    {"name": "Boeing",      "ticker": "BA",    "narrative": "Industrials", "layer": None, "stage": "public"},
    # ---- Semiconductors ----
    # layer: supply_chain | compute
    {"name": "TSMC",    "ticker": "TSM",  "narrative": "Semiconductors", "layer": "supply_chain", "stage": "public"},
    {"name": "ASML",    "ticker": "ASML", "narrative": "Semiconductors", "layer": "supply_chain", "stage": "public"},
    {"name": "Broadcom","ticker": "AVGO", "narrative": "Semiconductors", "layer": "compute",      "stage": "public"},
    # ---- Power & Grid ----
    {"name": "Constellation Energy", "ticker": "CEG", "narrative": "Power & Grid", "layer": "nuclear",   "stage": "public"},
    {"name": "Vistra",               "ticker": "VST", "narrative": "Power & Grid", "layer": "generation", "stage": "public"},
    {"name": "NextEra Energy",       "ticker": "NEE", "narrative": "Power & Grid", "layer": "renewables", "stage": "public"},
    # ---- Cybersecurity ----
    {"name": "CrowdStrike",       "ticker": "CRWD", "narrative": "Cybersecurity", "layer": None, "stage": "public"},
    {"name": "Palo Alto Networks","ticker": "PANW", "narrative": "Cybersecurity", "layer": None, "stage": "public"},
    {"name": "Zscaler",           "ticker": "ZS",   "narrative": "Cybersecurity", "layer": None, "stage": "public"},
    # ---- Defense & Aerospace ----
    {"name": "Lockheed Martin",  "ticker": "LMT",  "narrative": "Defense & Aerospace", "layer": None, "stage": "public"},
    {"name": "Northrop Grumman", "ticker": "NOC",  "narrative": "Defense & Aerospace", "layer": None, "stage": "public"},
    {"name": "RTX",              "ticker": "RTX",  "narrative": "Defense & Aerospace", "layer": None, "stage": "public"},
    {"name": "Anduril",          "ticker": None,   "narrative": "Defense & Aerospace", "layer": None, "stage": "pre-ipo"},
    # ---- Space ----
    {"name": "SpaceX",          "ticker": None,   "narrative": "Space", "layer": None, "stage": "pre-ipo"},
    {"name": "Rocket Lab",      "ticker": "RKLB", "narrative": "Space", "layer": None, "stage": "public"},
    {"name": "AST SpaceMobile", "ticker": "ASTS", "narrative": "Space", "layer": None, "stage": "public"},
    # ---- Enterprise Tech ----
    {"name": "Salesforce",  "ticker": "CRM",   "narrative": "Enterprise Tech", "layer": None, "stage": "public"},
    {"name": "Datadog",     "ticker": "DDOG",  "narrative": "Enterprise Tech", "layer": None, "stage": "public"},
    {"name": "Snowflake",   "ticker": "SNOW",  "narrative": "Enterprise Tech", "layer": None, "stage": "public"},
    {"name": "Okta",        "ticker": "OKTA",  "narrative": "Enterprise Tech", "layer": None, "stage": "public"},
    # ---- Crypto ----
    {"name": "Bitcoin",  "ticker": "BTC", "narrative": "Crypto", "layer": None, "stage": "crypto"},
    {"name": "Ethereum", "ticker": "ETH", "narrative": "Crypto", "layer": None, "stage": "crypto"},
    {"name": "Solana",   "ticker": "SOL", "narrative": "Crypto", "layer": None, "stage": "crypto"},
    # ---- Macro / Indices ----
    {"name": "S&P 500",    "ticker": "SPY",  "narrative": None, "layer": None, "stage": "index"},
    {"name": "Nasdaq 100", "ticker": "QQQ",  "narrative": None, "layer": None, "stage": "index"},
    {"name": "VIX",        "ticker": "^VIX", "narrative": None, "layer": None, "stage": "index"},
]

# Derived: tickers for yfinance (public stocks + indices, not crypto)
STOCK_TICKERS = [c["ticker"] for c in COMPANIES if c["ticker"] and c["stage"] in ("public", "index")]

CRYPTO_COINS = ["bitcoin", "ethereum", "solana"]

# Narrative map: canonical entity name / ticker → narrative label
# Used by the correlator to tag clusters. Covers both full names and tickers.
ENTITY_NARRATIVE_MAP: dict[str, str] = {}
for _c in COMPANIES:
    if _c.get("narrative"):
        ENTITY_NARRATIVE_MAP[_c["name"]] = _c["narrative"]
        if _c["ticker"]:
            ENTITY_NARRATIVE_MAP[_c["ticker"]] = _c["narrative"]

# Layer map: canonical entity name / ticker → sub-narrative layer tag
# Used by the correlator to compute cluster coherence (same-layer = coherent signal).
ENTITY_LAYER_MAP: dict[str, str] = {}
for _c in COMPANIES:
    if _c.get("layer"):
        ENTITY_LAYER_MAP[_c["name"]] = _c["layer"]
        if _c["ticker"]:
            ENTITY_LAYER_MAP[_c["ticker"]] = _c["layer"]

# Extra aliases that appear in cluster entities (canonical forms after ENTITY_SYNONYMS)
ENTITY_NARRATIVE_MAP.update({
    "Alphabet":           "AI Platforms",
    "GOOGL":              "AI Platforms",
    "Exxon":              "Nuclear & Energy",
    "General Electric":   "Nuclear & Energy",
    "Mistral":            "AI Infrastructure",
    "AI":                 "AI Infrastructure",
    "Palo Alto":          "Cybersecurity",
    "Lockheed":           "Defense & Aerospace",
    "Northrop":           "Defense & Aerospace",
    "Raytheon":           "Defense & Aerospace",
    "NextEra":            "Power & Grid",
    "Constellation":      "Power & Grid",
})

# --- arXiv ---
ARXIV_CATEGORIES = ["cs.AI", "cs.LG", "cs.CR"]
ARXIV_MAX_RESULTS = 20

# --- SEC Insider Trades ---
# Add ticker symbols — CIK lookup happens at runtime via EDGAR.
WATCHED_COMPANIES = [
    "AAPL", "NVDA", "MSFT", "GOOGL", "META", "AMZN", "TSLA", "PLTR",
    "UBER", "LYFT", "OKTA", "DDOG", "CRWV", "SNAP", "INTC", "AMD",
    "NFLX", "XOM", "SNOW", "BA", "LLY", "BX",
]

# --- Job Posting Velocity ---
# ats: "greenhouse" | "lever" | "ashby"
JOB_SEARCHES = [
    {"company": "Anthropic",    "ats": "greenhouse", "slug": "anthropic"},
    {"company": "xAI",          "ats": "greenhouse", "slug": "xai"},
    {"company": "DeepMind",     "ats": "greenhouse", "slug": "deepmind"},
    {"company": "OpenAI",       "ats": "ashby",      "slug": "openai"},
    {"company": "Scale AI",     "ats": "greenhouse", "slug": "scaleai"},
    {"company": "Perplexity",   "ats": "ashby",      "slug": "perplexity"},
    {"company": "Mistral AI",   "ats": "ashby",      "slug": "mistral"},
    {"company": "Cohere",       "ats": "ashby",      "slug": "cohere"},
    {"company": "Runway",       "ats": "ashby",      "slug": "runway"},
    {"company": "Palantir",     "ats": "lever",      "slug": "palantir"},
    {"company": "Zscaler",      "ats": "greenhouse", "slug": "zscaler"},
    {"company": "Anduril",      "ats": "greenhouse", "slug": "anduril-industries"},
    {"company": "Datadog",      "ats": "greenhouse", "slug": "datadog"},
    {"company": "Databricks",   "ats": "greenhouse", "slug": "databricks"},
]

# --- URL Watcher ("What Changed") ---
# Diffs the visible text of each page on a schedule and surfaces a ± preview when it moves.
WATCHED_URLS = [
    {"label": "FTC Tech Policy", "url": "https://www.ftc.gov/policy"},
    {"label": "White House OSTP", "url": "https://www.whitehouse.gov/ostp/"},
    {"label": "DOJ Antitrust", "url": "https://www.justice.gov/atr/press-releases"},
    {"label": "CFPB Newsroom", "url": "https://www.consumerfinance.gov/about-us/newsroom/"},
]

# --- Cluster Scoring ---
# Per-source raw weight: how much a single signal from each source contributes.
SOURCE_WEIGHTS = {
    "sec":          10.0,   # insider Form 4 filings — rare, high intent
    "watcher":       7.0,   # watched URL content changed
    "stock":         6.0,   # price / volume anomaly
    "jobs":          5.0,   # posting-velocity spike
    "arxiv":         4.0,   # research papers in tracked categories
    "news":          2.0,   # general RSS
}

CLUSTER_WINDOW_HOURS = 720  # 30-day max window; fast decay zeroes out old signals naturally
DECAY_RATE = 0.04           # default: e^(-λ × hours_ago), ~38% at 24h
# Per-source decay overrides (slower categories need slower decay). Empty by default —
# every source uses DECAY_RATE unless listed here.
DECAY_RATES: dict[str, float] = {}

MIN_SCORE = 3.0             # minimum to surface as "watch"
EMERGING_SCORE = 10.0
MOMENTUM_THRESHOLD = 2.0    # score_last_6h / score_prev_6h
EMERGING_MOMENTUM_MIN_SCORE = 10.0  # momentum alone can't lift a cluster below this into emerging
BREAKING_MOMENTUM = 4.0
BREAKING_MIN_SCORE = 8.0    # momentum alone can't break a cluster below this score floor
# Cross-domain promotion (≥2 domains) only forces Breaking at this score floor.
CROSS_DOMAIN_MIN_SCORE = 30.0
MOMENTUM_CAP = 15.0         # cap ratio after smoothing (avoids absurd × labels / tiers)
MOMENTUM_SMOOTHING = 2.5    # Laplace-style floor for prior-window silence
NOVELTY_CAP = 3.0           # max novelty multiplier for quiet-entity spikes

# Intent-based scoring: amplify deliberately-tracked signals, dampen ambient noise.
CURATED_SOURCE_TYPES = {"sec", "stock", "jobs", "watcher"}
AMBIENT_SOURCE_TYPES = {"news", "arxiv"}
AMBIENT_SOURCE_CAP = 3      # max signals per ambient source type counted toward score
INTENT_CURATED_MULT = 1.5   # cluster has ≥1 signal from a curated source
INTENT_AMBIENT_MULT = 0.4   # cluster is news/arxiv only

# Signal phase: leading = forward-looking (act before news), confirming = lagging (story catches up).
LEADING_SOURCE_TYPES    = {"jobs", "watcher", "sec", "arxiv"}
CONFIRMING_SOURCE_TYPES = {"news"}

# Generic umbrella entities to down-rank unless momentum/diversity proves significance.
# "AI" and "Technology" are too coarse — they catch unrelated stories and create noise.
GENERIC_UMBRELLA_ENTITIES = {"FDA", "AI", "Technology"}

# Canonical name for ticker symbols and known aliases
ENTITY_ALIASES = {
    "AAPL": "Apple",   "NVDA": "Nvidia",     "MSFT": "Microsoft",
    "GOOGL": "Google", "GOOG": "Google",     "AMZN": "Amazon",
    "TSLA": "Tesla",   "AMD": "AMD",         "META": "Meta",
    "PLTR": "Palantir","LYFT": "Lyft",       "SNAP": "Snap",
    "NFLX": "Netflix", "PINS": "Pinterest",  "NKE": "Nike",
    "DDOG": "Datadog", "SBUX": "Starbucks",  "CRM": "Salesforce",
    "UBER": "Uber",    "BA": "Boeing",       "DIS": "Disney",
    "GE": "GE",        "HD": "Home Depot",   "XOM": "ExxonMobil",
    "INTC": "Intel",   "LLY": "Eli Lilly",   "SNOW": "Snowflake",
    "OKTA": "Okta",    "GME": "GameStop",    "BX": "Blackstone",
    "CRWV": "CoreWeave","OKLO": "Oklo",
    "SOL":  "Solana",
    "EBAY": "eBay",    "BRK-B": "Berkshire Hathaway",
    # Semiconductors
    "TSM":  "TSMC",    "AVGO": "Broadcom",   "ASML": "ASML",
    # Power & Grid
    "CEG":  "Constellation Energy", "VST": "Vistra", "NEE": "NextEra Energy",
    # Cybersecurity
    "CRWD": "CrowdStrike", "PANW": "Palo Alto Networks", "ZS": "Zscaler",
    # Defense & Aerospace
    "LMT":  "Lockheed Martin", "NOC": "Northrop Grumman", "RTX": "RTX",
    # Space
    "RKLB": "Rocket Lab", "ASTS": "AST SpaceMobile",
    # Nuclear & Energy extras
    "BE":   "Bloom Energy", "ETN": "Eaton",
}

# If any phrase appears in the text alongside an entity match, suppress the match.
# Used for entities whose name collides with a common government/program acronym.
ENTITY_FALSE_POSITIVE_CONTEXT: dict[str, list[str]] = {
    "Snap": ["SNAP benefit", "food stamp", "SNAP program", "SNAP recipient",
             "nutrition assistance", "EBT", "SNAP card", "food assistance",
             "supplemental nutrition"],
}

# Entity keyword list — signals are tagged with any matching entities.
ENTITY_LIST = [
    # Companies
    "Apple", "AAPL", "Nvidia", "NVDA", "Microsoft", "MSFT", "Google", "Alphabet",
    "GOOGL", "GOOG", "Meta", "META", "Amazon", "AMZN", "OpenAI", "Anthropic",
    "Tesla", "TSLA", "AMD", "Palantir", "PLTR",
    "Datadog", "DDOG", "Salesforce", "CRM",
    "Boeing", "BA", "GE", "General Electric",
    "ExxonMobil", "Exxon", "XOM",
    "Intel", "INTC", "Snowflake", "SNOW",
    "Okta", "OKTA",
    "CoreWeave", "CRWV", "Oklo", "OKLO",
    # Semiconductors
    "TSMC", "TSM", "Broadcom", "AVGO", "ASML",
    # Power & Grid
    "Constellation Energy", "Constellation", "CEG", "Vistra", "VST",
    "NextEra Energy", "NextEra", "NEE",
    # Cybersecurity
    "CrowdStrike", "CRWD", "Palo Alto Networks", "Palo Alto", "PANW", "Zscaler", "ZS",
    # Defense & Aerospace
    "Lockheed Martin", "Lockheed", "LMT", "Northrop Grumman", "Northrop", "NOC",
    "RTX", "Raytheon", "Anduril",
    # Space
    "SpaceX", "Rocket Lab", "RKLB", "AST SpaceMobile", "ASTS",
    # Private / pre-IPO AI companies
    "xAI", "Scale AI", "Perplexity", "Mistral AI", "Mistral", "Cohere", "Runway", "DeepMind",
    # Macro / topics
    "regulation", "antitrust", "SEC", "FDA", "FTC", "AI",
    # Crypto
    "crypto", "bitcoin", "ethereum", "Solana", "SOL",
]

# Synonym → canonical entity name (deduplicates variant spellings before clustering).
ENTITY_SYNONYMS = {
    # Company short-forms → canonical names
    "Palo Alto":          "Palo Alto Networks",
    "Lockheed":           "Lockheed Martin",
    "Northrop":           "Northrop Grumman",
    "Raytheon":           "RTX",
    "NextEra":            "NextEra Energy",
    "Constellation":      "Constellation Energy",
}
