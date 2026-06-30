# Signal

A calmer news feed.

**[Live demo →](#)** *(sample data, no backend)*

Most feeds show you everything and let the loudest thing win. Signal does the opposite: it stays quiet until **several independent sources land on the same thing at the same time**, and only then surfaces it.

One article about a company is noise. A stock move *and* an insider filing *and* a hiring spike — all pointing at the same company in the same window — is a signal. Nothing shows up unless at least two unrelated sources agree, so the feed is mostly empty, and worth reading when it isn't.

It watches six things out of the box, no API keys needed: tech/business RSS, new arXiv papers, stock & volume moves, SEC insider filings, hiring velocity, and a set of pages it diffs for changes.

> This is the engine extracted from a larger personal dashboard I run for myself — the convergence core, with my own feeds and verticals stripped out so it stands on its own.

## Run it

Backend:

```bash
cd backend
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --port 8000
```

Frontend:

```bash
cd frontend
npm install
npm run dev
```

That's it — it spins up a local database, scrapes, and starts surfacing clusters a couple of minutes in.

## Notes

- Everything's configured in `backend/config.py` — the feeds, the companies it tracks, the scoring thresholds.
- Optional: set `AI_ENABLED=true` with an `ANTHROPIC_API_KEY` for plain-English summaries on each card and a daily morning brief.
- The production build (`frontend/.env.production`) ships as a static demo with bundled sample data, so it deploys to any static host with no backend. Point it at a real API instead with `VITE_DEMO=false` + `VITE_API_URL`.

FastAPI + SQLite on the back, React + Vite + Tailwind on the front. MIT licensed.
