#!/usr/bin/env python3
"""
Job Radar - pulls graduate trader and risk roles straight from each firm's
public ATS feed (Greenhouse / Lever / Ashby / SmartRecruiters / Workday /
Recruitee / Workable), filters to roles that fit you and your visa situation,
attaches the firm's known assessment criteria, and surfaces new ones via a
GitHub Issue + dashboard + RSS. Optional model layer reads each posting for
requirements, deadline and a fit rationale.
"""
import os, re, json, html, hashlib, datetime, sys, time
from urllib.parse import quote

ROOT = os.path.dirname(os.path.abspath(__file__))
STATE_DIR = os.path.join(ROOT, "state"); DOCS_DIR = os.path.join(ROOT, "docs")
SEEN_PATH = os.path.join(STATE_DIR, "seen.json")
UA = {"User-Agent": "job-radar/2.0 (personal job search)"}

def log(*a): print("[radar]", *a, flush=True)

# ---------- http ----------
def get_text(url):
    import requests
    r = requests.get(url, headers=UA, timeout=30); r.raise_for_status(); return r.text
def get_json(url):
    import requests
    r = requests.get(url, headers={**UA, "Accept": "application/json"}, timeout=30); r.raise_for_status(); return r.json()
def post_json(url, body):
    import requests
    r = requests.post(url, headers={**UA, "Content-Type": "application/json", "Accept": "application/json"},
                      json=body, timeout=30); r.raise_for_status(); return r.json()

def load_config():
    import yaml
    with open(os.path.join(ROOT, "config.yaml"), encoding="utf-8") as f: return yaml.safe_load(f)
def load_seen():
    try:
        with open(SEEN_PATH, encoding="utf-8") as f: return set(json.load(f))
    except Exception: return set()
def save_seen(seen):
    os.makedirs(STATE_DIR, exist_ok=True)
    with open(SEEN_PATH, "w", encoding="utf-8") as f: json.dump(sorted(seen), f, indent=0)
def strip_html(s): return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", s or "")).strip()

# ---------- ATS detection ----------
RX = {
    "greenhouse": re.compile(r"(?:boards(?:-api)?\.greenhouse\.io/(?:v1/boards/|embed/job_board\?for=)?|greenhouse\.io/embed/job_board\?for=)([A-Za-z0-9_-]+)"),
    "lever":      re.compile(r"jobs\.lever\.co/([A-Za-z0-9-]+)"),
    "ashby":      re.compile(r"(?:jobs\.ashbyhq\.com/|api\.ashbyhq\.com/posting-api/job-board/)([A-Za-z0-9-]+)"),
    "smartrecruiters": re.compile(r"(?:careers\.)?smartrecruiters\.com/([A-Za-z0-9-]+)"),
    "recruitee":  re.compile(r"([a-z0-9-]+)\.recruitee\.com"),
    "workable":   re.compile(r"apply\.workable\.com/([a-z0-9-]+)"),
    "workday":    re.compile(r"https?://([a-z0-9-]+)\.(wd\d+)\.myworkdayjobs\.com/([^\s\"'<>]+)"),
}
def detect_ats(careers_url):
    page = get_text(careers_url)
    # workday: parse from the careers_url itself if it is a myworkdayjobs link, else from page
    m = RX["workday"].search(careers_url) or RX["workday"].search(page)
    if m:
        tenant, dc, rest = m.group(1), m.group(2), m.group(3)
        segs = [s for s in rest.split("/") if s and not re.fullmatch(r"[a-z]{2}-[A-Z]{2}", s)
                and s.lower() not in ("wday", "cxs")]
        site = segs[0] if segs else tenant
        return "workday", {"tenant": tenant, "dc": dc, "site": site}
    for ats in ("greenhouse", "lever", "ashby", "smartrecruiters", "recruitee", "workable"):
        m = RX[ats].search(page) or RX[ats].search(careers_url)
        if m: return ats, m.group(1)
    return None, None

# ---------- normalize ----------
def norm(company, title, location, url, desc, posted=None):
    return {"company": company, "title": (title or "").strip(), "location": (location or "").strip(),
            "url": url or "", "description": (desc or "")[:8000], "posted": posted or ""}

def _pretitle(title, cfg):
    t = (title or "").lower()
    if any(x in t for x in cfg["filters"].get("title_exclude", [])): return False
    return any(k in t for cat in cfg["filters"]["title_include"].values() for k in cat)

# ---------- fetchers ----------
def fetch_greenhouse(company, slug, cfg=None):
    d = get_json(f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true")
    return [norm(company, j.get("title"), (j.get("location") or {}).get("name", ""),
                 j.get("absolute_url"), strip_html(j.get("content")), j.get("updated_at")) for j in d.get("jobs", [])]

def fetch_lever(company, slug, cfg=None):
    d = get_json(f"https://api.lever.co/v0/postings/{slug}?mode=json")
    return [norm(company, j.get("text"), (j.get("categories") or {}).get("location", ""),
                 j.get("hostedUrl"), j.get("descriptionPlain"), j.get("createdAt")) for j in d]

def fetch_ashby(company, slug, cfg=None):
    d = get_json(f"https://api.ashbyhq.com/posting-api/job-board/{slug}?includeCompensation=true")
    return [norm(company, j.get("title"), j.get("location", ""), j.get("jobUrl") or j.get("applyUrl"),
                 j.get("descriptionPlain") or strip_html(j.get("descriptionHtml")), j.get("publishedAt")) for j in d.get("jobs", [])]

def fetch_smartrecruiters(company, slug, cfg=None):
    d = get_json(f"https://api.smartrecruiters.com/v1/companies/{slug}/postings?limit=100")
    out = []
    for j in d.get("content", []):
        loc = j.get("location") or {}
        out.append(norm(company, j.get("name"), ", ".join(x for x in [loc.get("city"), loc.get("country")] if x),
                        f"https://jobs.smartrecruiters.com/{slug}/{j.get('id')}", strip_html(j.get("jobAd", {}).get("sections", {}).get("jobDescription", {}).get("text", "")), j.get("releasedDate")))
    return out

def fetch_recruitee(company, slug, cfg=None):
    d = get_json(f"https://{slug}.recruitee.com/api/offers/")
    return [norm(company, j.get("title"), j.get("location") or j.get("city", ""), j.get("careers_url") or j.get("url"),
                 strip_html(j.get("description")), j.get("published_at")) for j in d.get("offers", [])]

def fetch_workable(company, slug, cfg=None):
    d = get_json(f"https://apply.workable.com/api/v1/widget/accounts/{slug}?details=true")
    out = []
    for j in d.get("jobs", []):
        loc = j.get("location") or {}
        out.append(norm(company, j.get("title"), ", ".join(x for x in [loc.get("city"), loc.get("country")] if x),
                        j.get("url") or j.get("application_url"), strip_html(j.get("description")), j.get("published_on")))
    return out

def fetch_workday(company, params, cfg=None):
    tenant, dc, site = params["tenant"], params["dc"], params["site"]
    base = f"https://{tenant}.{dc}.myworkdayjobs.com"
    cxs = f"{base}/wday/cxs/{tenant}/{site}"
    out, offset, total = [], 0, 1
    while offset < total and offset <= 400:
        d = post_json(f"{cxs}/jobs", {"appliedFacets": {}, "limit": 20, "offset": offset, "searchText": ""})
        total = d.get("total", 0)
        for p in d.get("jobPostings", []):
            path = p.get("externalPath", "")
            job = norm(company, p.get("title"), p.get("locationsText", ""),
                       f"{base}/{site}{path}", "", p.get("postedOn", ""))
            # fetch full description only for titles that look relevant (keeps calls low)
            if cfg and _pretitle(job["title"], cfg) and path:
                try:
                    det = get_json(f"{cxs}{path}")
                    info = det.get("jobPostingInfo", {})
                    job["description"] = strip_html(info.get("jobDescription"))
                    if info.get("externalUrl"): job["url"] = info["externalUrl"]
                except Exception as e:
                    log(f"  workday detail miss {company}: {e}")
                time.sleep(0.2)
            out.append(job)
        offset += 20
    return out

FETCHERS = {"greenhouse": fetch_greenhouse, "lever": fetch_lever, "ashby": fetch_ashby,
            "smartrecruiters": fetch_smartrecruiters, "recruitee": fetch_recruitee,
            "workable": fetch_workable, "workday": fetch_workday}

# ---------- aggregators (firm-agnostic: catch ANY company, incl. ones not in the list) ----------
def fetch_adzuna(cfg):
    aid, akey = os.environ.get("ADZUNA_APP_ID"), os.environ.get("ADZUNA_APP_KEY")
    agg = cfg.get("aggregators", {}).get("adzuna", {})
    if not agg.get("enabled"):
        return []
    if not (aid and akey):
        log("Adzuna: enabled but no ADZUNA_APP_ID/ADZUNA_APP_KEY set -> skipping (add free keys for all-firm coverage)")
        return []
    out, days = [], agg.get("max_days_old", 14)
    for country in agg.get("countries", ["nl"]):
        for term in agg.get("search_terms", []):
            try:
                url = (f"https://api.adzuna.com/v1/api/jobs/{country}/search/1?app_id={aid}&app_key={akey}"
                       f"&results_per_page=50&max_days_old={days}&what_phrase={quote(term)}&content-type=application/json")
                d = get_json(url)
                for j in d.get("results", []):
                    out.append(norm((j.get("company") or {}).get("display_name", "?"), j.get("title"),
                                    (j.get("location") or {}).get("display_name", ""),
                                    j.get("redirect_url"), strip_html(j.get("description")), j.get("created")))
            except Exception as e:
                log(f"Adzuna {country}/{term}: {e}")
            time.sleep(0.3)
    log(f"Adzuna: {len(out)} raw results across all firms")
    return out

def fetch_arbeitnow(cfg):
    if not cfg.get("aggregators", {}).get("arbeitnow", {}).get("enabled"):
        return []
    out = []
    try:
        d = get_json("https://www.arbeitnow.com/api/job-board-api")
        for j in d.get("data", []):
            out.append(norm(j.get("company_name", "?"), j.get("title"), j.get("location", ""),
                            j.get("url"), strip_html(j.get("description")), j.get("created_at")))
    except Exception as e:
        log(f"Arbeitnow: {e}")
    return out

def gather(cfg):
    jobs = []
    for firm in cfg.get("firms", []):
        name = firm.get("name", "?"); ats = firm.get("ats"); slug = firm.get("slug") or firm.get("params")
        try:
            if not ats and firm.get("careers_url"):
                ats, slug = detect_ats(firm["careers_url"])
                log(f"detected {name}: {ats}/{slug}" if ats else f"NO ATS detected for {name} - paste me its careers URL")
            if ats in FETCHERS and slug:
                got = FETCHERS[ats](name, slug, cfg); log(f"{name}: {len(got)} roles via {ats}"); jobs += got
        except Exception as e:
            log(f"WARN {name}: {e}")
        time.sleep(0.4)
    jobs += fetch_adzuna(cfg)
    jobs += fetch_arbeitnow(cfg)
    return jobs

# ---------- filter / score / enrich ----------
def title_match(title, cfg):
    t = title.lower()
    if any(x in t for x in cfg["filters"].get("title_exclude", [])): return False, None
    for cat, kws in cfg["filters"]["title_include"].items():
        if any(k in t for k in kws): return True, cat
    return False, None

def loc_tier(location, cfg):
    t = (location or "").lower()
    if any(k in t for k in cfg["filters"]["primary_locations"]): return "A"
    if any(k in t for k in cfg["filters"]["eu_locations"]): return "B"
    return "C"

def sponsor_signal(text, cfg): return any(k in (text or "").lower() for k in cfg["filters"]["sponsorship_terms"])

def seniority_tag(job):
    t = (job["title"] + " " + job["description"][:1500]).lower()
    if any(w in job["title"].lower() for w in ["graduate", "junior", "intern", "trainee", "entry"]): return "graduate/junior"
    m = re.search(r"(\d+)\+?\s*years", t)
    if m and int(m.group(1)) >= 3: return f"{m.group(1)}+ yrs (check)"
    return "check"

def fit_score(job, cfg):
    text = ((job["title"] + " ") * 3 + job["description"]).lower()
    score = 20 + sum(1 for k in cfg["profile"]["keywords_strong"] if k in text) * 10
    if any(w in job["title"].lower() for w in ["graduate", "junior", "intern", "trainee"]): score += 8
    return max(0, min(100, score))

def extract_requirements(desc):
    if not desc: return ""
    low = desc.lower()
    for marker in ["requirements", "qualifications", "what you", "you have", "we are looking",
                   "we're looking", "your profile", "skills", "who you are"]:
        i = low.find(marker)
        if i != -1: return desc[i:i + 500].strip()
    return desc[:300].strip()

def model_enrich(job):
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key: return None
    import requests
    prompt = (f"Job: {job['title']} at {job['company']} ({job['location']}).\n"
              f"Posting:\n{job['description'][:4500]}\n\n"
              "Candidate: MSc Quantitative Finance (VU Amsterdam, honours), FRM, CFA L1, strong Python, "
              "derivatives/options, risk (VaR/CVA/IRRBB), targeting graduate trader roles.\n"
              'Reply ONLY with JSON: {"fit":0-100,"why":"one short line","requirements":["3-5 bullets"],'
              '"deadline":"date or unknown","visa":"sponsorship/relocation note or unknown"}')
    try:
        r = requests.post("https://api.anthropic.com/v1/messages",
            headers={"x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
            json={"model": "claude-sonnet-4-6", "max_tokens": 500,
                  "messages": [{"role": "user", "content": prompt}]}, timeout=45)
        txt = r.json()["content"][0]["text"]
        return json.loads(txt[txt.find("{"): txt.rfind("}") + 1])
    except Exception as e:
        log(f"  model enrich skipped: {e}"); return None

def job_id(j): return hashlib.md5(f"{j['company']}|{j['title']}|{j['url']}".encode()).hexdigest()[:12]

def process(jobs, cfg, seen, enrich=False):
    crit = cfg.get("firm_criteria", {})
    matches = []
    for j in jobs:
        ok, cat = title_match(j["title"], cfg)
        if not ok: continue
        tier = loc_tier(j["location"], cfg)
        spons = sponsor_signal(j["title"] + " " + j["location"] + " " + j["description"], cfg)
        if tier == "C" and not spons: continue
        j = dict(j)
        j.update(id=job_id(j), category=cat, tier=tier, sponsor=spons, fit=fit_score(j, cfg),
                 seniority=seniority_tag(j), requirements=extract_requirements(j["description"]),
                 criteria=crit.get(j["company"], {}))
        if enrich and cfg.get("settings", {}).get("use_model_scoring"):
            me = model_enrich(j)
            if me:
                j["model"] = me
                if isinstance(me.get("fit"), (int, float)): j["fit"] = int(me["fit"])
        matches.append(j)
    # collapse the same role coming from both a firm feed and an aggregator (keep the first, ATS-sourced one)
    deduped, seen_pair = [], set()
    for m in matches:
        pair = (m["company"].lower().strip(), m["title"].lower().strip())
        if pair in seen_pair:
            continue
        seen_pair.add(pair)
        deduped.append(m)
    matches = deduped
    matches.sort(key=lambda x: (x["tier"], -x["fit"]))
    new = [m for m in matches if m["id"] not in seen]
    return matches, new

# ---------- render ----------
def tier_label(t): return {"A": "Amsterdam / NL", "B": "EU (verify sponsorship)", "C": "Other + sponsorship"}[t]

def role_md(m):
    lines = [f"- **{m['title']}** — {m['company']}  ",
             f"  {m['location']} · {tier_label(m['tier'])} · fit {m['fit']}/100 · {m['seniority']} · {m['category']}"
             + (" · sponsorship mentioned" if m["sponsor"] else "") + "  ",
             f"  apply: {m['url']}"]
    md = m.get("model") or {}
    if md.get("requirements"):
        lines.append("  requirements: " + "; ".join(md["requirements"][:5]))
    elif m.get("requirements"):
        lines.append("  requirements: " + m["requirements"].replace("\n", " ")[:300])
    if md.get("deadline") and md["deadline"] != "unknown": lines.append(f"  deadline: {md['deadline']}")
    if md.get("visa") and md["visa"] != "unknown": lines.append(f"  visa: {md['visa']}")
    c = m.get("criteria") or {}
    if c.get("assessment"): lines.append(f"  firm assessment: {c['assessment']}")
    if c.get("looks_for"): lines.append(f"  they look for: {c['looks_for']}")
    return "\n".join(lines)

def block_md(rows, title):
    if not rows: return ""
    return f"## {title} ({len(rows)})\n\n" + "\n".join(role_md(m) for m in rows) + "\n"

def write_digests(matches, new):
    date = datetime.date.today().isoformat()
    full = [f"# Job Radar — {date}", "", f"{len(matches)} matching roles open · {len(new)} new since last run", ""]
    for t, lab in [("A", "Amsterdam / Netherlands"), ("B", "Elsewhere in EU"), ("C", "Other locations (sponsorship mentioned)")]:
        full.append(block_md([m for m in matches if m["tier"] == t], lab))
    open(os.path.join(ROOT, "digest.md"), "w", encoding="utf-8").write("\n".join(full))
    newtxt = (f"**{len(new)} new role(s)** as of {date}:\n\n" + block_md(new, "New roles")) if new else ""
    open(os.path.join(ROOT, "new_digest.md"), "w", encoding="utf-8").write(newtxt)

def write_dashboard(matches):
    os.makedirs(DOCS_DIR, exist_ok=True)
    date = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    rows = ""
    for m in matches:
        badge = {"A": "#1E9C8A", "B": "#C8932B", "C": "#7A52B3"}[m["tier"]]
        req = (m.get("model") or {}).get("requirements")
        req = "; ".join(req[:4]) if req else (m.get("requirements") or "")[:160]
        rows += (f"<tr><td><a href='{html.escape(m['url'])}'>{html.escape(m['title'])}</a><br>"
                 f"<small>{html.escape(req)}</small></td>"
                 f"<td>{html.escape(m['company'])}</td><td>{html.escape(m['location'])}</td>"
                 f"<td><span style='background:{badge};color:#fff;padding:1px 7px;border-radius:8px;font-size:11px'>{tier_label(m['tier'])}</span></td>"
                 f"<td style='text-align:center'>{'✓' if m['sponsor'] else ''}</td>"
                 f"<td style='text-align:center'>{m['fit']}</td><td>{html.escape(m['seniority'])}</td></tr>")
    page = f"""<!doctype html><html><head><meta charset=utf-8><title>Job Radar</title>
<style>body{{font-family:Arial,system-ui;margin:24px;color:#1c2530}}h1{{color:#0E2A55;margin-bottom:2px}}
table{{border-collapse:collapse;width:100%;font-size:13px;margin-top:12px}}th{{background:#0E2A55;color:#fff;text-align:left;padding:7px}}
td{{padding:7px;border-bottom:1px solid #e2e8f0;vertical-align:top}}tr:hover td{{background:#f3f6fb}}small{{color:#5b6b7d}}</style></head><body>
<h1>Job Radar</h1><small>Updated {date} · {len(matches)} matching roles</small>
<table><tr><th>Role &amp; requirements</th><th>Firm</th><th>Location</th><th>Bucket</th><th>Spons.</th><th>Fit</th><th>Level</th></tr>{rows}</table></body></html>"""
    open(os.path.join(DOCS_DIR, "index.html"), "w", encoding="utf-8").write(page)

def write_rss(new):
    os.makedirs(DOCS_DIR, exist_ok=True)
    now = datetime.datetime.utcnow().strftime("%a, %d %b %Y %H:%M:%S GMT")
    items = "".join(
        f"<item><title>{html.escape(m['title'])} — {html.escape(m['company'])}</title>"
        f"<link>{html.escape(m['url'])}</link>"
        f"<description>{html.escape(m['location'])} · {tier_label(m['tier'])} · fit {m['fit']}/100</description>"
        f"<guid isPermaLink='false'>{m['id']}</guid><pubDate>{now}</pubDate></item>" for m in new)
    open(os.path.join(DOCS_DIR, "feed.xml"), "w", encoding="utf-8").write(
        f"<?xml version='1.0' encoding='UTF-8'?><rss version='2.0'><channel>"
        f"<title>Job Radar</title><link>https://example.com</link>"
        f"<description>Graduate trader and risk roles</description>{items}</channel></rss>")

def run(mock_jobs=None):
    cfg = load_config(); seen = load_seen()
    jobs = mock_jobs if mock_jobs is not None else gather(cfg)
    log(f"collected {len(jobs)} raw postings")
    matches, new = process(jobs, cfg, seen, enrich=(mock_jobs is None))
    log(f"{len(matches)} matches, {len(new)} new")
    write_digests(matches, new); write_dashboard(matches); write_rss(new)
    if mock_jobs is None:
        for m in new: seen.add(m["id"])
        save_seen(seen)
    return matches, new

if __name__ == "__main__":
    if "--detect" in sys.argv:
        print(detect_ats(sys.argv[sys.argv.index("--detect") + 1]))
    else:
        run()
