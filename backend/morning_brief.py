"""
Morning brief: a once-a-day, plain-English readout of what converged overnight.

It reads the current clusters, asks Claude for a short overview plus a one-line "vibe"
per active cluster, and (optionally) emails it to you. Scheduled in scheduler.py at 7am
PT, and only when AI_ENABLED is set.

Optional env vars (skip the email entirely by leaving GMAIL_APP_PASSWORD unset):
  ANTHROPIC_API_KEY   — already used by the rest of the app
  GMAIL_APP_PASSWORD  — Gmail App Password (Gmail → Security → App Passwords)
  GMAIL_FROM          — sending address
  BRIEF_RECIPIENT     — receiving address (default: same as GMAIL_FROM)
"""

import json
import os
import smtplib
import ssl
import time
import traceback
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import anthropic

GMAIL_FROM  = os.getenv("GMAIL_FROM", "")
GMAIL_PASS  = os.getenv("GMAIL_APP_PASSWORD", "")
RECIPIENT   = os.getenv("BRIEF_RECIPIENT", GMAIL_FROM)


def _send_email(subject: str, html_body: str):
    if not GMAIL_PASS or not GMAIL_FROM:
        print("[morning_brief] GMAIL_APP_PASSWORD/GMAIL_FROM not set — skipping email send")
        return
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = f"Signal <{GMAIL_FROM}>"
    msg["To"]      = RECIPIENT
    msg.attach(MIMEText(html_body, "html"))

    def _attempt():
        try:
            with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=15) as server:
                server.login(GMAIL_FROM, GMAIL_PASS)
                server.sendmail(GMAIL_FROM, RECIPIENT, msg.as_string())
                return
        except ssl.SSLError:
            pass
        with smtplib.SMTP("smtp.gmail.com", 587, timeout=15) as server:
            server.ehlo()
            server.starttls()
            server.login(GMAIL_FROM, GMAIL_PASS)
            server.sendmail(GMAIL_FROM, RECIPIENT, msg.as_string())

    # Retry up to 3 times with backoff — network may be briefly unavailable at wake time
    for attempt in range(3):
        try:
            _attempt()
            print(f"[morning_brief] Email sent to {RECIPIENT}")
            return
        except OSError as e:
            if attempt < 2:
                wait = 30 * (attempt + 1)
                print(f"[morning_brief] Network error (attempt {attempt+1}/3), retrying in {wait}s: {e}")
                time.sleep(wait)
            else:
                raise


def _build_context() -> dict:
    from cache import get_clusters, get_all_stock_prices

    clusters = get_clusters()
    prices   = get_all_stock_prices()

    cluster_ctx = []
    for c in clusters:
        if not c.get("entities"):
            continue
        cluster_ctx.append({
            "entities":     c["entities"],
            "narrative":    c.get("narrative"),
            "tier":         c.get("tier"),
            "signal_phase": c.get("signal_phase"),
            "momentum":     round(c.get("momentum", 0), 2),
            "score":        round(c.get("score", 0), 2),
            "signals": [
                {"source": s.get("source_type"), "title": s.get("title")}
                for s in (c.get("signals") or [])[:6]
            ],
        })

    movers = {
        sym: {"price": v["price"], "pct": round(v["pct_change"], 2)}
        for sym, v in prices.items()
        if v.get("pct_change") is not None and abs(v.get("pct_change", 0)) > 1.5
    }

    return {"clusters": cluster_ctx, "movers": movers}


def _format_email(subject: str, overview: str, vibes: list[dict], today: str) -> str:
    def p(text: str) -> str:
        paragraphs = [t.strip() for t in text.strip().split("\n\n") if t.strip()]
        return "".join(f'<p style="margin:0 0 14px">{t}</p>' for t in paragraphs)

    vibes_html = ""
    for v in vibes:
        vibes_html += f"""
        <div style="padding:12px 0;border-top:1px solid #e5e7eb">
          <p style="margin:0 0 4px;font-weight:600;font-size:14px">{v.get('label', '')}</p>
          <p style="margin:0;color:#374151;font-size:14px;line-height:1.5">{v.get('vibe', '')}</p>
        </div>"""

    return f"""
<div style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;max-width:620px;margin:0 auto;color:#111827;line-height:1.6">

  <div style="border-bottom:2px solid #111827;padding-bottom:14px;margin-bottom:24px">
    <p style="margin:0 0 2px;font-size:12px;color:#6b7280;text-transform:uppercase;letter-spacing:.05em">Signal · {today}</p>
    <h1 style="margin:0;font-size:20px;font-weight:700">{subject}</h1>
  </div>

  <h2 style="font-size:14px;font-weight:600;text-transform:uppercase;letter-spacing:.05em;color:#6b7280;margin:0 0 12px">Overview</h2>
  <div style="font-size:14px;color:#374151">{p(overview)}</div>

  {f'''<h2 style="font-size:14px;font-weight:600;text-transform:uppercase;letter-spacing:.05em;color:#6b7280;margin:24px 0 0">What's Converging</h2>
  <div style="margin-top:12px">{vibes_html}</div>''' if vibes_html else ''}

</div>"""


def run():
    """Entry point called by scheduler at 7am PT."""
    from config import AI_ENABLED
    if not AI_ENABLED:
        print("[morning_brief] Skipped — AI disabled (set AI_ENABLED=true to enable).")
        return
    print("[morning_brief] Starting...")

    try:
        ctx   = _build_context()
        now   = datetime.now(timezone.utc).replace(tzinfo=None)
        today = now.strftime("%A, %B %-d, %Y")

        client = anthropic.Anthropic()
        prompt = f"""Today is {today}. You write the morning brief for a personal "signal" dashboard.
The dashboard only surfaces a topic when several independent sources converge on it in the
same window, so each cluster below is something multiple sources agree is happening.

Active clusters:
{json.dumps(ctx['clusters'], indent=2)}

Notable price movers today (>1.5% move):
{json.dumps(ctx['movers'], indent=2)}

Your job:
1. Write a short overview (1–3 plain-text paragraphs): what's converging this morning, which
   narratives are gaining or fading, what the day's notable moves are. Calm and factual — no hype.
2. For each notable cluster, give a one-sentence "vibe": what the signals say and whether the
   story is building or cooling.

Use hedged, non-financial-advice language ('suggests', 'consistent with', 'may indicate').
Respond ONLY with valid JSON, no markdown fences:
{{
  "overview": "plain text, 1-3 paragraphs separated by \\n\\n",
  "vibes": [
    {{"label": "short cluster name (e.g. the main entity)", "vibe": "one sentence"}}
  ],
  "email_subject": "Signal — {today}: <one-line theme>"
}}"""

        response = client.messages.create(
            model="claude-opus-4-8",
            max_tokens=4000,
            messages=[{"role": "user", "content": prompt}],
        )

        raw = response.content[0].text.strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1].rsplit("```", 1)[0]
        result = json.loads(raw)

        overview = result.get("overview", "")
        vibes    = result.get("vibes", [])
        subject  = result.get("email_subject", f"Signal — {today}")

        html = _format_email(subject, overview, vibes, today)
        try:
            _send_email(subject, html)
            email_status = "email sent"
        except Exception as e:
            print(f"[morning_brief] Email failed: {e}")
            email_status = "email FAILED"

        print(f"[morning_brief] Done — {len(vibes)} cluster vibes, {email_status}")

    except Exception:
        print("[morning_brief] ERROR:")
        traceback.print_exc()
