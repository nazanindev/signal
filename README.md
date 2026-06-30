# Signal

A calmer news feed.

**[Live demo](https://signal-ruddy-two.vercel.app/)** *(sample data, no backend)*

Most feeds show you everything and let the loudest thing win. Signal does the opposite: it stays quiet until **several independent sources land on the same thing at the same time**, and only then surfaces it.

One article about a company is noise. A stock move *and* an insider filing *and* a hiring spike — all pointing at the same company in the same window — is a signal. Nothing shows up unless at least two unrelated sources agree, so the feed is mostly empty, and worth reading when it isn't.

It watches six things out of the box, no API keys needed: tech/business RSS, new arXiv papers, stock & volume moves, SEC insider filings, hiring velocity, and a set of pages it diffs for changes.

> This is the engine extracted from a larger personal dashboard I run for myself — the convergence core, with my own feeds and verticals stripped out so it stands on its own.

## The math

Every signal is tagged with the entities it mentions. The correlator groups signals by entity inside a rolling window and scores each group:

```
score = Σ (weight · e^(−λ·hours_ago)) · novelty · intent
```

- **weight** — rarer, higher-intent sources count for more: an insider filing (10) outweighs a price move (6) outweighs a news article (2).
- **e^(−λ·hours_ago)** — exponential time decay, so old signals fade instead of lingering (λ ≈ 0.04 → a signal is worth ~40% of its weight a day later).
- **novelty** — `signal_count / 7-day baseline`, capped at 3×. An entity that's normally quiet spiking *now* counts for more than one that's always noisy.
- **intent** — ×1.5 if any deliberately-tracked source (filings, prices, hiring, watched pages) is involved; ×0.4 if it's only ambient news/arXiv. This is what keeps the feed from filling up with headlines.

Then **momentum** — recent vs. prior 6-hour score, Laplace-smoothed so a quiet window doesn't divide by ~zero:

```
momentum = (score_last_6h + k) / (score_prev_6h + k)
```

And a **tier**: *watch* once it clears the floor, *emerging* on enough score / source diversity / momentum, *breaking* when it's moving fast or spanning multiple domains (tech + finance + monitoring) at once. Clusters whose entities don't share a coherent sub-narrative get demoted, so unrelated things that happen to share a name don't fake a signal.

All the constants live at the top of `backend/config.py`.

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
