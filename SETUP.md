# Setup runbook (hand this to Claude Code)

You can paste these instructions to the Claude Code app with the project folder open.

## Goal
Create a GitHub repo from this folder, push it, and configure it so the included
GitHub Actions workflow runs the job radar on a schedule.

## Steps for Claude Code to perform
1. Initialise git and make the first commit:
   ```bash
   git init && git add . && git commit -m "job radar: initial"
   git branch -M main
   ```
2. Create a new GitHub repo (public keeps Actions free and unlimited) and push:
   ```bash
   gh repo create job-radar --public --source=. --remote=origin --push
   ```
   (Requires the GitHub CLI `gh` to be authenticated, which it is in Claude Code.)
3. Set the repo secrets (ask me, the user, for the values, or I will add them in the
   GitHub UI under Settings -> Secrets and variables -> Actions):
   ```bash
   gh secret set ADZUNA_APP_ID   --body "<my adzuna app id>"
   gh secret set ADZUNA_APP_KEY  --body "<my adzuna app key>"
   gh secret set ANTHROPIC_API_KEY --body "<optional anthropic key>"
   ```
4. Enable and trigger the workflow once to seed it:
   ```bash
   gh workflow enable "Job Radar" || true
   gh workflow run "Job Radar"
   ```
5. (Optional) Turn on GitHub Pages from the `/docs` folder so the dashboard is viewable:
   tell me to do it in Settings -> Pages, or do it via the API if available.

## After setup
- New matching roles open a GitHub Issue automatically; make sure repo notifications are on.
- The dashboard is `docs/index.html`; the RSS feed is `docs/feed.xml`.
- To get the free Adzuna keys: register at https://developer.adzuna.com (takes a minute).
