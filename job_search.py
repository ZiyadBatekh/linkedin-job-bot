import os
import re
import sys
import json
import hashlib
import time
import requests
from urllib.parse import quote_plus
from datetime import datetime, timedelta
from dotenv import load_dotenv
from bs4 import BeautifulSoup

load_dotenv()

TELEGRAM_TOKEN  = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

SEEN_JOBS_FILE    = os.path.join(os.path.dirname(__file__), "seen_jobs.json")
SEEN_JOBS_TTL_DAYS = 7
TOP_N = 10

# كل عمليات البحث ريموت بس (f_WT=2، متفرضة في search_linkedin)، ومحصورة
# في المناطق المستهدفة: شمال أوروبا (الأولوية الأولى)، الخليج، مصر، وباقي
# أوروبا. غيّر القايمة دي حسب البلاد اللي إنت عايز تشتغل فيها.
LINKEDIN_SEARCHES = [

    # =========================================================
    # الخليج — الأولوية الأولى
    # =========================================================

    # UAE
    {"keywords": "Frontend Developer",       "location": "United Arab Emirates"},
    {"keywords": "Angular Developer",        "location": "United Arab Emirates"},
    {"keywords": "Frontend Engineer",        "location": "United Arab Emirates"},
    {"keywords": "React Developer",          "location": "United Arab Emirates"},
    {"keywords": "Angular Engineer",          "location": "United Arab Emirates"},

    # Saudi Arabia
    {"keywords": "Frontend Developer",       "location": "Saudi Arabia"},
    {"keywords": "Angular Developer",        "location": "Saudi Arabia"},
    {"keywords": "Frontend Engineer",        "location": "Saudi Arabia"},
    {"keywords": "React Developer",          "location": "Saudi Arabia"},
    {"keywords": "Angular Engineer",          "location": "Saudi Arabia"},

    # Qatar
    {"keywords": "Frontend Developer",       "location": "Qatar"},
    {"keywords": "Angular Developer",        "location": "Qatar"},
    {"keywords": "Frontend Engineer",        "location": "Qatar"},
    {"keywords": "React Developer",          "location": "Qatar"},

    # Kuwait
    {"keywords": "Frontend Developer",       "location": "Kuwait"},
    {"keywords": "Angular Developer",        "location": "Kuwait"},
    {"keywords": "Frontend Engineer",        "location": "Kuwait"},

    # Bahrain
    {"keywords": "Frontend Developer",       "location": "Bahrain"},
    {"keywords": "Angular Developer",        "location": "Bahrain"},
    {"keywords": "Frontend Engineer",        "location": "Bahrain"},

    # Oman
    {"keywords": "Frontend Developer",       "location": "Oman"},
    {"keywords": "Angular Developer",        "location": "Oman"},
    {"keywords": "Frontend Engineer",        "location": "Oman"},


    # =========================================================
    # مصر — الأولوية الثانية
    # =========================================================

    {"keywords": "Frontend Developer",       "location": "Egypt"},
    {"keywords": "Angular Developer",        "location": "Egypt"},
    {"keywords": "Frontend Engineer",        "location": "Egypt"},
    {"keywords": "Angular Engineer",          "location": "Egypt"},
    {"keywords": "React Developer",          "location": "Egypt"},
    {"keywords": "React Engineer",            "location": "Egypt"},
    {"keywords": "Next.js Developer",        "location": "Egypt"},
    {"keywords": "React Native Developer",   "location": "Egypt"},


    # =========================================================
    # أوروبا — الأولوية الثالثة
    # =========================================================

    # United Kingdom
    {"keywords": "Frontend Developer",       "location": "United Kingdom"},
    {"keywords": "Angular Developer",        "location": "United Kingdom"},
    {"keywords": "Frontend Engineer",        "location": "United Kingdom"},
    {"keywords": "React Developer",          "location": "United Kingdom"},

    # Ireland
    {"keywords": "Frontend Developer",       "location": "Ireland"},
    {"keywords": "Angular Developer",        "location": "Ireland"},
    {"keywords": "Frontend Engineer",        "location": "Ireland"},

    # Germany
    {"keywords": "Frontend Developer",       "location": "Germany"},
    {"keywords": "Angular Developer",        "location": "Germany"},
    {"keywords": "Frontend Engineer",        "location": "Germany"},
    {"keywords": "React Developer",          "location": "Germany"},

    # Netherlands
    {"keywords": "Frontend Developer",       "location": "Netherlands"},
    {"keywords": "Angular Developer",        "location": "Netherlands"},
    {"keywords": "Frontend Engineer",        "location": "Netherlands"},

    # Sweden
    {"keywords": "Frontend Developer",       "location": "Sweden"},
    {"keywords": "Angular Developer",        "location": "Sweden"},
    {"keywords": "Frontend Engineer",        "location": "Sweden"},

    # Denmark
    {"keywords": "Frontend Developer",       "location": "Denmark"},
    {"keywords": "Angular Developer",        "location": "Denmark"},
    {"keywords": "Frontend Engineer",        "location": "Denmark"},

    # Finland
    {"keywords": "Frontend Developer",       "location": "Finland"},
    {"keywords": "Angular Developer",        "location": "Finland"},
    {"keywords": "Frontend Engineer",        "location": "Finland"},

    # Norway
    {"keywords": "Frontend Developer",       "location": "Norway"},
    {"keywords": "Angular Developer",        "location": "Norway"},
    {"keywords": "Frontend Engineer",        "location": "Norway"},

    # France
    {"keywords": "Frontend Developer",       "location": "France"},
    {"keywords": "Angular Developer",        "location": "France"},
    {"keywords": "Frontend Engineer",        "location": "France"},

    # Spain
    {"keywords": "Frontend Developer",       "location": "Spain"},
    {"keywords": "Angular Developer",        "location": "Spain"},
    {"keywords": "Frontend Engineer",        "location": "Spain"},

    # Italy
    {"keywords": "Frontend Developer",       "location": "Italy"},
    {"keywords": "Angular Developer",        "location": "Italy"},
    {"keywords": "Frontend Engineer",        "location": "Italy"},

    # Poland
    {"keywords": "Frontend Developer",       "location": "Poland"},
    {"keywords": "Angular Developer",        "location": "Poland"},
    {"keywords": "Frontend Engineer",        "location": "Poland"},

    # Belgium
    {"keywords": "Frontend Developer",       "location": "Belgium"},
    {"keywords": "Angular Developer",        "location": "Belgium"},
    {"keywords": "Frontend Engineer",        "location": "Belgium"},


    # =========================================================
    # Worldwide Remote — الأولوية الأخيرة
    # =========================================================

    {"keywords": "Frontend Developer",       "location": "Worldwide", "remote_only": True},
    {"keywords": "Angular Developer",        "location": "Worldwide", "remote_only": True},
    {"keywords": "Frontend Engineer",        "location": "Worldwide", "remote_only": True},
    {"keywords": "Angular Engineer",          "location": "Worldwide", "remote_only": True},
    {"keywords": "React Developer",          "location": "Worldwide", "remote_only": True},
    {"keywords": "React Engineer",            "location": "Worldwide", "remote_only": True},
    {"keywords": "Next.js Developer",        "location": "Worldwide", "remote_only": True},
    {"keywords": "React Native Developer",   "location": "Worldwide", "remote_only": True},

]

# Restrict results to the requested countries. In particular, never query
# LinkedIn's Worldwide location because it returns jobs from unrelated regions.
ALLOWED_SEARCH_LOCATIONS = {
    "Egypt", "United Arab Emirates", "Saudi Arabia", "Qatar", "Kuwait",
    "Bahrain", "Oman",
}
LINKEDIN_SEARCHES = [
    search for search in LINKEDIN_SEARCHES
    if search["location"] in ALLOWED_SEARCH_LOCATIONS
]
SEARCH_KEYWORDS = tuple(dict.fromkeys(search["keywords"] for search in LINKEDIN_SEARCHES))

# تم إيقاف Target Company Searches.
# البوت يركز فقط على وظائف Frontend / Angular / React.
COMPANY_SEARCHES = []

# الوظيفة اللي بتيجي من بحث الشركات لازم يكون في عنوانها كلمة على الأقل من
# دول عشان تتحسب مناسبة. ضيف الكلمات بتاعة مجالك إنت هنا.
# COMPANY_RELEVANCE_TITLE_WORDS = {
#     "automation", "ai", "agentic", "rpa", "analyst", "developer",
#     "engineer", "operations", "product", "data", "digital", "technical",
#     "software", "platform", "workflow", "process", "integration",
#     "solution", "consultant", "api", "system", "no-code", "low-code",
#     "marketing", "social", "n8n", "claude", "codex",
# }

LINKEDIN_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "en-US,en;q=0.9",
}

# ── حساب النقط ────────────────────────────────────────────────────────────────

ROLE_SCORES = {
    "angular developer": 50,
    "frontend developer": 48,
    "front end developer": 48,
    "frontend engineer": 46,
    "angular engineer": 46,
    "react developer": 44,
    "react engineer": 42,
    "next.js developer": 40,
    "nextjs developer": 40,
    "react native developer": 36,

    "junior frontend developer": 30,
    "junior front end developer": 30,
    "mid-level frontend developer": 38,
    "mid level frontend developer": 38,

    
    "web developer": 25,
}

SKILL_SCORES = {
    "angular": 25,
    "typescript": 20,
    "react": 18,
    "next.js": 17,
    "nextjs": 17,
    "javascript": 15,
    "react native": 14,
    "rxjs": 12,
    "ngrx": 10,
    "html": 8,
    "css": 8,
    "tailwind": 7,
    "rest api": 7,
    "rest": 6,
}

# ── فلترة وظائف Frontend فقط ──────────────────────────────────────────────────

ALLOWED_ROLE_PATTERNS = [
    r"\bfrontend developer\b",
    r"\bfront[- ]end developer\b",
    r"\bfrontend engineer\b",
    r"\bfront[- ]end engineer\b",

    r"\bangular developer\b",
    r"\bangular engineer\b",

    r"\breact developer\b",
    r"\breact engineer\b",

    r"\bnext\.?js developer\b",
    r"\bnext\.?js engineer\b",

    r"\breact native developer\b",
    r"\breact native engineer\b",
]

# أدوار لا نريدها حتى لو كان فيها Angular / React
EXCLUDED_ROLE_PATTERNS = [
    r"\bsolution architect\b",
    r"\bsoftware architect\b",
    r"\benterprise architect\b",
    r"\btechnical architect\b",
    r"\bcloud architect\b",

    r"\bdata engineer\b",
    r"\bdata scientist\b",
    r"\bmachine learning\b",
    r"\bai engineer\b",
    r"\bdevops\b",
    r"\bbackend\b",
    r"\bback[- ]end\b",

    r"\bproduct manager\b",
    r"\bproduct marketing\b",
    r"\bproject manager\b",

    r"\bqa\b",
    r"\bquality assurance\b",
    r"\btechnical support\b",
    r"\bsolution consultant\b",
]


def is_frontend_role(title: str) -> bool:
    """يسمح فقط بعناوين وظائف Frontend / Angular / React المناسبة."""

    title = (title or "").strip().lower()

    if not title:
        return False

    # استبعاد الأدوار غير المطلوبة أولاً
    for pattern in EXCLUDED_ROLE_PATTERNS:
        if re.search(pattern, title, re.I):
            return False

    # لازم العنوان نفسه يكون Frontend / Angular / React
    for pattern in ALLOWED_ROLE_PATTERNS:
        if re.search(pattern, title, re.I):
            return True

    return False


def is_remote_job(job: dict) -> bool:
    """
    LinkedIn search نفسها تستخدم f_WT=2 للـ Remote.
    هنا نضيف طبقة حماية تستبعد أي نتيجة ظاهر فيها Hybrid / On-site.
    """

    title = (job.get("job_title") or "").lower()
    location = (job.get("job_city") or "").lower()

    combined = f"{title} {location}"

    forbidden_remote_modes = [
        "on-site",
        "onsite",
        "on site",
        "office based",
        "office-based",
    ]

    if any(mode in combined for mode in forbidden_remote_modes):
        return False

    return bool(job.get("job_is_remote", False))

LOCATION_SCORES = {
    # شمال أوروبا — الأولوية الأولى، بنقط أعلى من أي منطقة تانية
    "switzerland": 26, "zurich": 26, "geneva": 26,
    "denmark": 25, "copenhagen": 25,
    "finland": 25, "helsinki": 25,
    "sweden": 25, "stockholm": 25,
    "norway": 25, "oslo": 25,
    "ae": 20, "uae": 20, "dubai": 20, "abu dhabi": 20, "sharjah": 20, "united arab emirates": 20,
    "sa": 18, "saudi": 18, "riyadh": 18, "jeddah": 18, "saudi arabia": 18,
    "qa": 16, "qatar": 16, "doha": 16,
    "kw": 15, "kuwait": 15,
    "bh": 15, "bahrain": 15,
    "om": 15, "oman": 15, "muscat": 15,
    "eg": 16, "egypt": 16, "cairo": 16,
    "worldwide": 15, "global": 15,
    "united kingdom": 16, "uk": 16, "london": 16,
    "ireland": 16, "dublin": 16,
    "germany": 16, "berlin": 16, "munich": 16,
    "france": 16, "paris": 16,
    "netherlands": 16, "amsterdam": 16,
    "spain": 16, "madrid": 16, "barcelona": 16,
    "portugal": 16, "lisbon": 16,
    "italy": 16, "milan": 16, "rome": 16,
    "poland": 16, "warsaw": 16,
    "belgium": 16, "brussels": 16,
    "remote": 14,
}

TARGET_COMPANIES = [
    "maids", "justmop", "helperplace", "qureos", "bayzat", "huspy", "coraly",
    "halan", "paymob", "instabug", "breadfast", "rabbit",
    "g42", "presight", "careem", "noon", "talabat", "dubizzle",
    "stc", "neom", "zain", "tamara",
    "automattic", "zapier", "make.com", "n8n",
]

LOCATION_CODE_MAP = {
    "united arab emirates": "ae", "uae": "ae", "dubai": "ae", "abu dhabi": "ae",
    "saudi arabia": "sa", "riyadh": "sa", "jeddah": "sa",
    "egypt": "eg", "cairo": "eg",
    "qatar": "qa", "doha": "qa",
    "kuwait": "kw", "bahrain": "bh",
    "oman": "om", "muscat": "om",
    "worldwide": "global",
    "united kingdom": "gb", "ireland": "ie",
    "germany": "de", "france": "fr", "netherlands": "nl",
    "spain": "es", "portugal": "pt", "italy": "it", "poland": "pl",
    "belgium": "be", "switzerland": "ch",
    "denmark": "dk", "finland": "fi", "sweden": "se", "norway": "no",
}


def infer_country_code(location: str) -> str:
    loc = location.lower()
    for k, v in LOCATION_CODE_MAP.items():
        if k in loc:
            return v
    return "global"


def score_job(job: dict) -> int:
    title   = (job.get("job_title") or "").lower()
    desc    = (job.get("job_description") or "")[:500].lower()
    city    = (job.get("job_city") or "").lower()
    country = (job.get("job_country") or "").lower()
    company = (job.get("employer_name") or "").lower()
    is_remote = job.get("job_is_remote", False)

    score = 0
    for kw, pts in ROLE_SCORES.items():
        if kw in title:
            score += pts
            break
    skill_pts = sum(pts for kw, pts in SKILL_SCORES.items() if kw in title + " " + desc)
    score += min(skill_pts, 30)
    loc_hay = f"{city} {country}" + (" remote" if is_remote else "")
    for loc, pts in LOCATION_SCORES.items():
        if loc in loc_hay:
            score += pts
            break
    if any(name in company for name in TARGET_COMPANIES):
        score += 10
    if is_remote:
        score += 8
    elif any(w in title for w in ("hybrid", "remote")):
        score += 5
    return score


def score_label(score: int) -> str:
    if score >= 60: return "Excellent match"
    if score >= 45: return "Strong match"
    if score >= 30: return "Good match"
    return "Possible match"


# ── المنافسة (عدد المتقدمين) ──────────────────────────────────────────────────
# الوظايف اللي عليها متقدمين أقل بتاخد أولوية أعلى — دي أسهل حاجة فعلاً
# تتقبل فيها. عدد المتقدمين بيتجاب بس لأعلى الوظايف في كل مجموعة
# (APPLICANT_FETCH_LIMIT)، عشان عدد الطلبات الزيادة على لينكدإن يفضل محدود.

APPLICANT_FETCH_LIMIT = 15


def fetch_applicant_count(url: str) -> int | None:
    if not url:
        return None
    try:
        resp = requests.get(url, headers=LINKEDIN_HEADERS, timeout=10)
        if resp.status_code != 200:
            return None
        m = re.search(r'([\d,]+)\+?\s*(?:applicants|people clicked apply)', resp.text, re.I)
        if m:
            return int(m.group(1).replace(",", ""))
    except requests.RequestException:
        pass
    return None


def applicant_bonus(count: int | None) -> int:
    if count is None:
        return 0
    if count <= 10:
        return 20
    if count <= 25:
        return 14
    if count <= 50:
        return 8
    if count <= 100:
        return 2
    return -8  # heavily-applied jobs are deprioritized, not just unboosted


def enrich_with_competition(jobs: list) -> list:
    """بيجيب عدد المتقدمين لأعلى الوظايف نقط في المجموعة، بيضيف بونص
    المنافسة القليلة على النتيجة النهائية، وبعدين بيعيد ترتيب المجموعة
    كلها حسب النتيجة دي."""
    ranked = sorted(jobs, key=score_job, reverse=True)
    top, rest = ranked[:APPLICANT_FETCH_LIMIT], ranked[APPLICANT_FETCH_LIMIT:]
    for job in top:
        count = fetch_applicant_count(job.get("job_apply_link"))
        job["_applicants"] = count
        job["_score"] = score_job(job) + applicant_bonus(count)
        time.sleep(0.3)
    for job in rest:
        job["_applicants"] = None
        job["_score"] = score_job(job)
    return sorted(top + rest, key=lambda j: j["_score"], reverse=True)


# ── سحب البيانات من لينكدإن ───────────────────────────────────────────────────

def parse_card(card, search_location: str) -> dict | None:
    link_tag = card.find("a", class_="base-card__full-link")
    if not link_tag:
        return None
    raw_url = link_tag.get("href", "")
    # بيسيب لينك لينكدإن نضيف (بيشيل باراميترز التتبّع اللي بعد ?)
    apply_url = raw_url.split("?")[0].rstrip("/") if raw_url else ""
    match = re.search(r"-(\d{8,})$", apply_url)
    job_id = f"li_{match.group(1)}" if match else None
    if not job_id:
        return None

    title_tag   = card.find("h3", class_="base-search-card__title")
    company_tag = card.find("h4", class_="base-search-card__subtitle")
    loc_tag     = card.find("span", class_="job-search-card__location")

    title    = (title_tag.get_text(strip=True)   if title_tag   else "").strip()
    company  = (company_tag.get_text(strip=True) if company_tag else "").strip()
    location = (loc_tag.get_text(strip=True)     if loc_tag     else search_location).strip()

    card_text = card.get_text(" ", strip=True).lower()
    if "on-site" in card_text or "onsite" in card_text or "on site" in card_text:
        return None
    # LinkedIn's guest search already applies f_WT=2. Its result cards often do
    # not include the words Remote/Hybrid, so requiring those words here drops
    # valid results before they can reach Telegram.
    is_remote = True

    job = {
        "job_id":        job_id,
        "job_title":     title,
        "employer_name": company,
        "job_city":      location,
        "job_country":   search_location,
        "_search_country": infer_country_code(search_location),
        "job_is_remote": is_remote,
        "job_apply_link": apply_url,
        "job_description": "",
        "apply_options": [
            {
                "apply_link": apply_url,
                "is_direct": False,
                "publisher": "LinkedIn"
            }
        ],
    }

    # حماية إضافية ضد Hybrid / On-site
    if not is_remote_job(job):
        return None

    return job


def search_linkedin(keywords: str, location: str, remote_only: bool = False) -> list:
    url = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
    params = {
        "keywords": keywords,
        "f_TPR":    "r86400",  # last 24h
        "start":    0,
        "f_WT":     "2",  # LinkedIn remote-only search; external sources add Hybrid
    }
    if remote_only:
        # This branch is retained for compatibility, but it is not used by the
        # configured searches because Worldwide searches are filtered out.
        params["location"] = ""
    else:
        params["location"] = location
    try:
        resp = requests.get(url, headers=LINKEDIN_HEADERS, params=params, timeout=15)
        if resp.status_code != 200:
            print(f"Warning: LinkedIn returned {resp.status_code} for '{keywords}' / {location}")
            return []
        soup = BeautifulSoup(resp.text, "html.parser")
        jobs = []
        for card in soup.find_all("li"):
            job = parse_card(card, location)
            if job:
                jobs.append(job)
        return jobs
    except requests.RequestException as e:
        print(f"Warning: LinkedIn search failed for '{keywords}': {e}")
        return []


EXTERNAL_HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/125 Safari/537.36",
}


def parse_external_card(card, source: str, location: str) -> dict | None:
    title_tag = card.select_one(
        "h2 a, h3 a, h2, h3, .jobTitle a, a[href*='/job/'], "
        "a[href*='/jobs/'], a[href*='/job-detail/']"
    )
    company_tag = card.select_one(
        ".companyName, [data-testid='company-name'], .employer, "
        "[class*='company'], [class*='employer']"
    )
    location_tag = card.select_one(
        ".companyLocation, [data-testid='text-location'], .location, "
        "[class*='location']"
    )
    if not title_tag:
        return None

    title = title_tag.get_text(" ", strip=True)
    company = company_tag.get_text(" ", strip=True) if company_tag else "Unknown"
    listed_location = location_tag.get_text(" ", strip=True) if location_tag else location
    card_text = card.get_text(" ", strip=True)
    combined = f"{title} {listed_location} {card_text}".lower()
    if "on-site" in combined or "onsite" in combined or "on site" in combined:
        return None
    if "remote" not in combined and "hybrid" not in combined:
        return None

    link = title_tag.get("href", "")
    if not link:
        link = next(
            (a.get("href", "") for a in card.select("a[href]")
             if a.get_text(" ", strip=True) == title),
            "",
        )
    if link.startswith("/"):
        base_url = "https://wuzzuf.net" if source == "WUZZUF" else "https://www.naukrigulf.com"
        link = base_url + link
    if not link:
        return None

    stable_id = hashlib.sha1(link.split("?")[0].rstrip("/").encode("utf-8")).hexdigest()[:20]
    job_id = f"{source.lower()}_{stable_id}"
    return {
        "job_id": job_id,
        "job_title": title,
        "employer_name": company,
        "job_city": listed_location,
        "job_country": location,
        "job_is_remote": "remote" in combined or "hybrid" in combined,
        "job_apply_link": link,
        "_source": source,
        "_posted_text": card_text,
    }


def is_external_job_recent(job: dict, days: int = 7) -> bool:
    """Accept only external listings whose card says they were posted recently."""
    text = (job.get("_posted_text") or "").lower()
    if not text:
        return False
    if any(token in text for token in (
        "today", "just posted", "1 day ago", "1 day", "yesterday",
        "few hours ago", "hours ago", "mins ago", "minutes ago",
    )):
        return True

    day_match = re.search(r"(\d+)\s*days?\s*ago", text)
    if day_match:
        return int(day_match.group(1)) <= days

    week_match = re.search(r"(\d+)\s*weeks?\s*ago", text)
    if week_match:
        return int(week_match.group(1)) <= 1

    date_match = re.search(
        r"\b(\d{1,2})\s+(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\b",
        text,
    )
    if date_match:
        months = {
            "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
            "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
        }
        posted = datetime(datetime.now().year, months[date_match.group(2)], int(date_match.group(1)))
        if posted > datetime.now():
            posted = posted.replace(year=posted.year - 1)
        return datetime.now() - posted <= timedelta(days=days)

    return False


def search_wuzzuf(keywords: str, location: str) -> list:
    jobs, seen_links = [], set()
    country_slug = location.replace(" ", "-")
    for work_mode in ("remote", "hybrid"):
        slug = quote_plus(keywords).replace("+", "-")
        url = f"https://wuzzuf.net/a/{work_mode.title()}-{slug}-Jobs-in-{country_slug}"
        try:
            response = requests.get(url, headers=EXTERNAL_HEADERS, timeout=4)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, "html.parser")
            cards = soup.select(
                "article, [data-testid='job-card'], [class*='JobCard'], "
                "[class*='job-card'], [class*='search-job-card']"
            )
            if not cards:
                cards = [tag.find_parent(["article", "li"]) or tag.parent
                         for tag in soup.select("h2 a, h3 a")]
            for card in cards:
                job = parse_external_card(card, "WUZZUF", location)
                if job:
                    job["_work_mode_filter"] = work_mode
                if job and job["job_apply_link"] not in seen_links:
                    seen_links.add(job["job_apply_link"])
                    jobs.append(job)
        except requests.RequestException as exc:
            print(f"Warning: WUZZUF search failed for '{keywords}' / {work_mode}: {exc}")
    return jobs


def search_naukrigulf(keywords: str, location: str) -> list:
    location_slugs = {
        "United Arab Emirates": "uae", "Saudi Arabia": "saudi-arabia",
        "Qatar": "qatar", "Kuwait": "kuwait", "Bahrain": "bahrain",
        "Oman": "oman",
    }
    location_slug = location_slugs.get(location)
    if not location_slug:
        return []

    jobs, seen_links = [], set()
    for work_mode in ("remote", "hybrid"):
        slug = quote_plus(keywords).replace("+", "-").lower()
        url = f"https://www.naukrigulf.com/{work_mode}-{slug}-jobs-in-{location_slug}"
        try:
            response = requests.get(url, headers=EXTERNAL_HEADERS, timeout=4)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, "html.parser")
            cards = soup.select(
                "article, .jobTuple, .srpTuple, [class*='jobTuple'], "
                "[class*='job-card'], [data-job-id]"
            )
            if not cards:
                cards = [tag.find_parent(["article", "li"]) or tag.parent
                         for tag in soup.select("h2 a, h3 a")]
            for card in cards:
                job = parse_external_card(card, "Naukrigulf", location)
                if job:
                    job["_work_mode_filter"] = work_mode
                if job and job["job_apply_link"] not in seen_links:
                    seen_links.add(job["job_apply_link"])
                    jobs.append(job)
        except requests.RequestException as exc:
            print(f"Warning: Naukrigulf search failed for '{keywords}' / {location}: {exc}")
    return jobs


# ── تليجرام ───────────────────────────────────────────────────────────────────

def esc(text: str) -> str:
    return (text or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def format_job(rank: int, job: dict) -> str:
    title      = esc(job.get("job_title") or "N/A")
    company    = esc(job.get("employer_name") or "N/A")
    location   = esc(job.get("job_city") or job.get("job_country") or "Unknown")
    is_remote  = job.get("job_is_remote", False)
    is_target  = job.get("_company_match", False)
    score      = job.get("_score", score_job(job))
    applicants = job.get("_applicants")

    title_lower = (job.get("job_title") or "").lower()
    if "hybrid" in title_lower or "hybrid" in location.lower():
        work_mode = "Hybrid"
    elif is_remote or "remote" in title_lower:
        work_mode = "Remote"
    else:
        work_mode = location

    apply_url  = job.get("job_apply_link") or ""
    safe_url   = apply_url.replace("&", "&amp;")
    source = job.get("_source", "LinkedIn")
    apply_part = f' | <a href="{safe_url}">Apply on {esc(source)}</a>' if safe_url else ""
    badge      = " [TARGET CO.]" if is_target else ""
    if applicants is None:
        competition = ""
    elif applicants <= 25:
        competition = f" | {applicants} applicants (low competition)"
    else:
        competition = f" | {applicants} applicants"

    return (
        f"<b>#{rank} {title}</b>{badge}\n"
        f"{company} | {work_mode}\n"
        f"<i>{score_label(score)} ({score} pts)</i>{competition}{apply_part}"
    )


def send_telegram(text: str):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    lines = text.split("\n")
    chunks, current = [], ""
    for line in lines:
        candidate = current + line + "\n"
        if len(candidate) > 4000:
            if current:
                chunks.append(current.rstrip())
            current = line + "\n"
        else:
            current = candidate
    if current.strip():
        chunks.append(current.rstrip())
    for chunk in chunks:
        try:
            resp = requests.post(url, json={
                "chat_id":   TELEGRAM_CHAT_ID,
                "text":      chunk,
                "parse_mode": "HTML",
                "disable_web_page_preview": True,
            }, timeout=15)
            resp.raise_for_status()
        except requests.RequestException as e:
            print(f"Error sending Telegram message: {e}")
            return False
    return True


# ── حفظ الذاكرة ───────────────────────────────────────────────────────────────

def check_config():
    missing = [k for k in ("TELEGRAM_TOKEN", "TELEGRAM_CHAT_ID")
               if not os.getenv(k) or "your_" in os.getenv(k)]
    if missing:
        print(f"ERROR: Missing values in .env: {', '.join(missing)}")
        sys.exit(1)


def load_seen_jobs() -> dict:
    if not os.path.exists(SEEN_JOBS_FILE):
        return {}
    with open(SEEN_JOBS_FILE, "r") as f:
        data = json.load(f)
    cutoff = (datetime.now() - timedelta(days=SEEN_JOBS_TTL_DAYS)).isoformat()
    return {jid: ts for jid, ts in data.items() if ts >= cutoff}


def save_seen_jobs(seen: dict):
    with open(SEEN_JOBS_FILE, "w") as f:
        json.dump(seen, f)


# ── الدالة الرئيسية ───────────────────────────────────────────────────────────

def main():
    check_config()
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Starting LinkedIn job search...")

    seen = load_seen_jobs()
    this_run_ids: set = set()
    general_jobs: list = []

    # ── الجولة ١: البحث العام عن الوظايف ──────────────────────────────────────
    print("--- General searches ---")
    for s in LINKEDIN_SEARCHES:
        jobs = search_linkedin(s["keywords"], s["location"], s.get("remote_only", False))
        kept = 0
        for job in jobs:
            job_id = job.get("job_id")
            title = job.get("job_title") or ""
            if not job_id or job_id in seen or job_id in this_run_ids:
                continue
            if not is_frontend_role(title) or not is_remote_job(job):
                continue
            this_run_ids.add(job_id)
            general_jobs.append(job)
            kept += 1
        print(f"  '{s['keywords']}' / {s['location']} -> {kept} new relevant remote jobs")

    # ── الجولة ٢: البحث في الشركات المستهدفة ──────────────────────────────────
    print("--- Target company searches ---")
    for s in COMPANY_SEARCHES:
        jobs = search_linkedin(s["keywords"], s["location"])
        kept = 0
        for job in jobs:
            job_id = job.get("job_id")
            if not job_id or job_id in seen or job_id in this_run_ids:
                continue
            # فلترة — بيسيب بس الوظايف اللي ليها علاقة بمجالك
            title_words = set((job.get("job_title") or "").lower().split())
            if not title_words & COMPANY_RELEVANCE_TITLE_WORDS:
                continue
            job["_company_match"] = True
            this_run_ids.add(job_id)
            kept += 1
        print(f"  '{s['keywords']}' / {s['location']} -> {kept} relevant")

    external_jobs = []
    external_searches = [
        {"keywords": "Frontend Developer", "location": location}
        for location in sorted(ALLOWED_SEARCH_LOCATIONS)
    ]
    external_counts = {"WUZZUF": 0, "Naukrigulf": 0}
    external_raw_counts = {"WUZZUF": 0, "Naukrigulf": 0}
    external_deadline = time.monotonic() + 90
    for s in external_searches:
        if time.monotonic() >= external_deadline:
            print("External search budget reached; continuing with collected results")
            break
        for search_fn in (search_wuzzuf, search_naukrigulf):
            if time.monotonic() >= external_deadline:
                break
            try:
                source_jobs = search_fn(s["keywords"], s["location"])
            except Exception as exc:
                print(f"Warning: {search_fn.__name__} failed: {exc}")
                source_jobs = []
            source_name = "WUZZUF" if search_fn is search_wuzzuf else "Naukrigulf"
            external_raw_counts[source_name] += len(source_jobs)
            for job in source_jobs:
                job_id = job.get("job_id")
                if not job_id or job_id in seen or job_id in this_run_ids:
                    continue
                if not is_external_job_recent(job):
                    continue
                if not is_frontend_role(job.get("job_title", "")) or not is_remote_job(job):
                    continue
                this_run_ids.add(job_id)
                external_jobs.append(job)
                external_counts[job.get("_source", "WUZZUF")] += 1

    print(
        "External source results (raw / accepted): "
        f"WUZZUF={external_raw_counts['WUZZUF']}/{external_counts['WUZZUF']}, "
        f"Naukrigulf={external_raw_counts['Naukrigulf']}/{external_counts['Naukrigulf']}"
    )

    all_new = general_jobs + external_jobs
    print(
        f"Relevant new jobs: {len(all_new)} "
        f"(LinkedIn: {len(general_jobs)}, WUZZUF/Naukrigulf: {len(external_jobs)})"
    )

    if not all_new:
        sent = send_telegram(
            "<b>Daily Job Report - " + datetime.now().strftime("%b %d, %Y") + "</b>\n"
            "No new jobs from LinkedIn, WUZZUF, or Naukrigulf since last run. Check back tomorrow!"
        )
        if not sent:
            raise RuntimeError("Telegram message could not be sent; jobs were not marked as seen")
    else:
        # بيجيب عدد المتقدمين لأعلى وظايف كل مجموعة (بونص المنافسة
        # القليلة)، بيعيد الترتيب، وبعدين بياخد أحسن ٥ من كل مجموعة.
        general_jobs = enrich_with_competition(general_jobs)
        ranked_jobs = sorted(general_jobs + external_jobs, key=score_job, reverse=True)
        top_general = ranked_jobs[:TOP_N]
        date_str = datetime.now().strftime("%b %d, %Y")
        lines = [
            f"<b>Frontend Job Report - {date_str}</b>\n"
            "Remote or Hybrid | Frontend / Angular / React | LinkedIn + WUZZUF + Naukrigulf\n"
        ]

        if top_general:
            lines.append("<b>-- Best Role Matches --</b>")
            lines.append("")
            for i, job in enumerate(top_general, 1):
                lines.append(format_job(i, job))
                lines.append("")

        # if top_company:
        #     lines.append("<b>-- Target Company Openings --</b>")
        #     lines.append("")
        #     for i, job in enumerate(top_company, 1):
        #         lines.append(format_job(i, job))
        #         lines.append("")

        if not send_telegram("\n".join(lines)):
            raise RuntimeError("Telegram message could not be sent; jobs were not marked as seen")
        print(f"Telegram sent: {len(top_general)} frontend matches.")

    now_iso = datetime.now().isoformat()
    ids_to_mark = this_run_ids if not all_new else {
        job.get("job_id") for job in top_general if job.get("job_id")
    }
    for job_id in ids_to_mark:
        seen[job_id] = now_iso
    save_seen_jobs(seen)


if __name__ == "__main__":
    main()
