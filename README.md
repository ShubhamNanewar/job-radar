# Job Radar

Surfaces graduate **trader** roles (and your **risk** backup roles) from across the whole
market, filtered to what fits you and your visa situation, with each firm's assessment
criteria attached. No Gmail, no credentials to read jobs, nothing to run by hand.

## It is firm-agnostic
Two layers work together:
1. **The open net (aggregator).** Adzuna searches **every company** by keyword + location,
   so any firm that posts a matching role shows up, including ones not in the list below
   (Goldman, QRT, Cubist, brand-new entrants). Arbeitnow adds free EU coverage.
2. **Priority firms.** The curated list pulls each firm's own ATS feed for the freshest,
   richest data plus a built-in assessment-criteria table. It is a priority list, **not the
   limit** of what you see.

Covers all major ATS: Greenhouse, Lever, Ashby, SmartRecruiters, **Workday** (myworkdayjobs),
Recruitee, Workable. Same role from a firm feed and the aggregator is de-duplicated.

## How it reaches you (any/all, all credential-free)
1. **GitHub Issue** when new roles appear -> GitHub notifies you through its own email/app.
2. **Dashboard** `docs/index.html`, rewritten every run (turn on Pages, deploy from `/docs`).
3. **RSS** `docs/feed.xml` -> add to any reader for push.

## What each role comes with
Title, firm, location, direct apply link, a location **bucket** (Amsterdam/NL always;
rest-of-EU flagged "verify sponsorship"; elsewhere only if the posting mentions visa /
sponsorship / relocation), a **level** tag, a **fit score**, the **requirements** from the
posting, and the firm's **assessment format + what they look for** where known.

## Filters
Trading: graduate / junior / trainee / options / derivatives / digital-assets / crypto
trader, trading internship, market maker, quant/systematic/execution trader, trading
analyst, QIS. Risk: quant / market / model / counterparty risk, risk analyst / manager.
Senior / lead / head / VP / director titles excluded.

## Setup
The only step I can't do from a chat is create the repo on your account. Two easy ways:

**A. Claude Code (recommended, near-zero effort).** Open this folder in the Claude Code app
and tell it: *"create a GitHub repo from this folder, push it, and set the repo secrets."*
See `SETUP.md` for the exact runbook to hand it.

**B. By hand (~5 min).**
```bash
git init && git add . && git commit -m "job radar"
git branch -M main
git remote add origin https://github.com/<you>/job-radar.git
git push -u origin main
```
Then on GitHub: Actions tab -> enable -> run **Job Radar** once. Settings -> Pages -> deploy
from `/docs` (optional). Settings -> Notifications -> ensure issue notifications reach you.

### Repo secrets (Settings -> Secrets -> Actions)
- `ADZUNA_APP_ID` and `ADZUNA_APP_KEY` — **free** from https://developer.adzuna.com. These
  power the all-firm coverage. Without them, only the priority firm feeds + Arbeitnow run.
- `ANTHROPIC_API_KEY` — optional; lets it read each posting for clean requirements, deadline
  and visa line. Falls back to keyword extraction with no key.

### Verify a firm's feed (optional)
```bash
pip install -r requirements.txt
python job_radar.py --detect "https://<a firm careers url>"
```
Send me any firm that won't auto-detect and I'll give you the exact config line.

## How often
GitHub's scheduler runs in minutes, not seconds; the workflow runs every ~30 min
(`*/30`, tighten to `*/15` if you like). New roles appear within that window.

## Files
`job_radar.py` · `config.yaml` (firms, filters, aggregators, criteria) ·
`.github/workflows/job-radar.yml` · `SETUP.md` · outputs `digest.md`, `docs/index.html`,
`docs/feed.xml` · `state/seen.json`.
