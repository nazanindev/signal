import hashlib
import time
import httpx
from datetime import datetime, timezone
from config import STOCK_TICKERS, CRYPTO_COINS, SOURCE_WEIGHTS, ENTITY_ALIASES
from cache import upsert_signal, save_stock_price, save_earnings_date
from scrapers.utils import extract_entities

COINGECKO_URL = "https://api.coingecko.com/api/v3/simple/price"
COIN_SYMBOLS = {"bitcoin": "BTC", "ethereum": "ETH", "solana": "SOL"}

_YF_QUOTE_URL = "https://query1.finance.yahoo.com/v7/finance/quote"
_YF_SUMMARY_URL = "https://query2.finance.yahoo.com/v10/finance/quoteSummary/{symbol}"
_YF_HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json",
}
# Symbols that have no earnings calendar (indices, ETFs)
_NO_EARNINGS = {"SPY", "QQQ", "^VIX"}


def _move_strength_mult(abs_pct: float, vol_ratio: float) -> float:
    """Scale raw_weight by move magnitude and volume (capped at 3×, floor at 1×).
    Crossover into >1× at ~5% move or 1.5× volume — keeps small moves unchanged."""
    pct_mult = max(1.0, min(abs_pct / 5.0, 3.0))
    vol_mult = min(vol_ratio, 2.0) if vol_ratio >= 1.5 else 1.0
    return max(pct_mult, vol_mult)


def fetch():
    signals = []
    signals.extend(_fetch_stocks())
    signals.extend(_fetch_crypto())
    return signals


def _yf_quotes(symbols: list[str]) -> dict[str, dict]:
    """Fetch quote fields for all symbols in one request. Returns {symbol: fields}."""
    fields = "regularMarketPrice,regularMarketPreviousClose,regularMarketVolume,averageDailyVolume3Month,marketCap"
    for attempt in range(4):
        if attempt:
            time.sleep(2 ** attempt)  # 2s, 4s, 8s
        resp = httpx.get(
            _YF_QUOTE_URL,
            params={"symbols": ",".join(symbols), "fields": fields},
            headers=_YF_HEADERS,
            timeout=15,
        )
        if resp.status_code == 429:
            print(f"[stocks] Yahoo Finance rate-limited (attempt {attempt + 1}/4), retrying...")
            continue
        resp.raise_for_status()
        results = resp.json().get("quoteResponse", {}).get("result", [])
        return {r["symbol"]: r for r in results}
    resp.raise_for_status()  # raise the final 429 if all retries exhausted
    return {}


def _yf_earnings(symbol: str, client: httpx.Client) -> str | None:
    """Return the next earnings date string (YYYY-MM-DD) for a single symbol, or None."""
    try:
        resp = client.get(
            _YF_SUMMARY_URL.format(symbol=symbol),
            params={"modules": "calendarEvents"},
            headers=_YF_HEADERS,
            timeout=10,
        )
        data = resp.json()
        earnings = (
            data.get("quoteSummary", {})
            .get("result", [{}])[0]
            .get("calendarEvents", {})
            .get("earnings", {})
            .get("earningsDate", [])
        )
        if earnings:
            raw = earnings[0].get("raw") or earnings[0]
            # raw is a Unix timestamp (int) from quoteSummary
            if isinstance(raw, (int, float)):
                return datetime.fromtimestamp(raw, tz=timezone.utc).strftime("%Y-%m-%d")
            return str(raw)[:10]
    except Exception:
        pass
    return None


def _fetch_stocks():
    signals = []
    skipped = 0
    checked = 0
    try:
        quotes = _yf_quotes(STOCK_TICKERS)
        with httpx.Client() as client:
            for symbol in STOCK_TICKERS:
                try:
                    q = quotes.get(symbol, {})
                    price = q.get("regularMarketPrice")
                    prev_close = q.get("regularMarketPreviousClose")

                    if price is None or prev_close is None:
                        continue

                    checked += 1

                    if symbol == "^VIX":
                        pct_change = ((price - prev_close) / prev_close) * 100
                        save_stock_price("^VIX", price, pct_change)
                        sig = _vix_signal(price, prev_close)
                        if sig:
                            upsert_signal(sig, replace=True)
                            signals.append(sig)
                        continue

                    volume = q.get("averageDailyVolume3Month")
                    last_volume = q.get("regularMarketVolume")
                    market_cap = q.get("marketCap")
                    pct_change = ((price - prev_close) / prev_close) * 100
                    volume_ratio = (last_volume / volume) if volume and last_volume else 1.0

                    save_stock_price(symbol, price, pct_change, volume_ratio, market_cap)

                    if symbol not in _NO_EARNINGS:
                        date_str = _yf_earnings(symbol, client)
                        if date_str:
                            save_earnings_date(symbol, date_str)

                    if abs(pct_change) < 1.5 and volume_ratio < 1.5:
                        skipped += 1
                        continue

                    direction = "+" if pct_change >= 0 else ""
                    vol_note = f" on {volume_ratio:.1f}x volume" if volume_ratio >= 1.5 else ""
                    title = f"{symbol} {direction}{pct_change:.1f}%{vol_note} (${price:.2f})"
                    today = datetime.now(timezone.utc).date()

                    signal = {
                        "id": f"stock-{symbol}-{today}",
                        "source_type": "stock",
                        "entities": extract_entities(symbol) or [ENTITY_ALIASES.get(symbol, symbol)],
                        "title": title,
                        "url": f"https://finance.yahoo.com/quote/{symbol}",
                        "raw_weight": SOURCE_WEIGHTS["stock"] * _move_strength_mult(abs(pct_change), volume_ratio),
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "title_hash": hashlib.md5(f"{symbol}-{today}".encode()).hexdigest(),
                    }
                    upsert_signal(signal, replace=True)
                    signals.append(signal)
                except Exception as e:
                    print(f"[stocks] Error for {symbol}: {e}")
    except Exception as e:
        print(f"[stocks] fetch error: {e}")
    print(f"[stocks] {len(signals)} signals emitted, {skipped}/{checked} tickers below threshold")
    return signals


def _vix_signal(price: float, prev_close: float) -> dict | None:
    pct_change = ((price - prev_close) / prev_close) * 100
    crosses = ""
    if prev_close < 20 <= price:
        crosses = " — crossed into elevated fear territory"
    elif prev_close < 30 <= price:
        crosses = " — crossed into high fear territory"
    elif abs(pct_change) < 5:
        return None

    direction = "+" if pct_change >= 0 else ""
    title = f"VIX {direction}{pct_change:.1f}% ({price:.1f}){crosses}"
    today = datetime.now(timezone.utc).date()
    return {
        "id": f"stock-VIX-{today}",
        "source_type": "stock",
        "entities": ["VIX"],
        "title": title,
        "url": "https://finance.yahoo.com/quote/%5EVIX",
        "raw_weight": SOURCE_WEIGHTS["stock"] * 1.5,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "title_hash": hashlib.md5(f"VIX-{today}".encode()).hexdigest(),
    }


def _fetch_crypto():
    signals = []
    try:
        ids = ",".join(CRYPTO_COINS)
        resp = httpx.get(
            COINGECKO_URL,
            params={"ids": ids, "vs_currencies": "usd", "include_24hr_change": "true"},
            timeout=10,
        )
        data = resp.json()
        for coin_id, info in data.items():
            price = info.get("usd", 0)
            change = info.get("usd_24h_change", 0)
            save_stock_price(COIN_SYMBOLS.get(coin_id, coin_id.upper()), price, change)
            if abs(change) < 2.0:
                continue
            direction = "+" if change >= 0 else ""
            title = f"{coin_id.capitalize()} {direction}{change:.1f}% (${price:,.0f})"
            today = datetime.now(timezone.utc).date()
            signal = {
                "id": f"crypto-{coin_id}-{today}",
                "source_type": "stock",
                "entities": [coin_id.capitalize()],
                "title": title,
                "url": f"https://www.coingecko.com/en/coins/{coin_id}",
                "raw_weight": SOURCE_WEIGHTS["stock"],
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "title_hash": hashlib.md5(f"{coin_id}-{today}".encode()).hexdigest(),
            }
            upsert_signal(signal, replace=True)
            signals.append(signal)
    except Exception as e:
        print(f"[crypto] Error: {e}")
    return signals
