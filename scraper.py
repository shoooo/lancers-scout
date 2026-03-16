"""
Lancers project scraper.
Scrapes project listings from lancers.jp for given keywords.
Uses Playwright when USE_PLAYWRIGHT=1 (required in CI to avoid bot detection).
"""

import os
import time
import random
import requests
from bs4 import BeautifulSoup
from dataclasses import dataclass
from typing import Optional

BASE_URL = "https://www.lancers.jp"
SEARCH_URL = f"{BASE_URL}/work/search"

USE_PLAYWRIGHT = os.environ.get("USE_PLAYWRIGHT", "0") == "1"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ja,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Referer": "https://www.lancers.jp/",
}

_playwright_browser = None

def _get_playwright_browser():
    global _playwright_browser
    if _playwright_browser is None:
        from playwright.sync_api import sync_playwright
        _pw = sync_playwright().start()
        _playwright_browser = _pw.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage"],
        )
        print(f"  [playwright] Browser launched: {_playwright_browser.version}")
    return _playwright_browser


def _fetch_html(url: str) -> Optional[str]:
    """Fetch page HTML via Playwright (headless browser)."""
    time.sleep(random.uniform(1.5, 2.5))
    try:
        browser = _get_playwright_browser()
        ctx = browser.new_context(
            user_agent=HEADERS["User-Agent"],
            locale="ja-JP",
        )
        page = ctx.new_page()
        resp = page.goto(url, wait_until="domcontentloaded", timeout=30000)
        if resp and resp.status >= 400:
            print(f"  [browser] HTTP {resp.status} for {url}")
        html = page.content()
        ctx.close()
        return html
    except Exception as e:
        print(f"  [browser fetch error] {url}: {e}")
        return None

# Search keywords targeting ecommerce + web building
TARGET_KEYWORDS = [
    "ECサイト",
    "ネットショップ",
    "Shopify",
    "ホームページ制作",
    "WordPress",
    "LP制作",
    "Webサイト制作",
    "WooCommerce",
    "コーポレートサイト",
    "サイト構築",
    "React Next.js",
    "Webアプリ 受託",
]

# Max projects to carry forward to AI analysis
MAX_PROJECTS = 120


@dataclass
class Project:
    title: str
    url: str
    budget: str
    category: str
    description: str
    proposal_count: str
    is_new: bool
    keyword: str
    full_description: str = ""


def _get(url: str, params: dict = None) -> Optional[BeautifulSoup]:
    """Fetch a page and return parsed soup. Uses Playwright if USE_PLAYWRIGHT=1."""
    if params:
        from urllib.parse import urlencode
        url = f"{url}?{urlencode(params)}"

    if USE_PLAYWRIGHT:
        html = _fetch_html(url)
        if not html:
            return None
        return BeautifulSoup(html, "html.parser")

    time.sleep(random.uniform(1.5, 3.0))
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        resp.encoding = "utf-8"
        return BeautifulSoup(resp.text, "html.parser")
    except requests.RequestException as e:
        print(f"  [fetch error] {url}: {e}")
        return None


def _parse_card(card, keyword: str) -> Optional[Project]:
    """Parse a project card element into a Project."""
    # Title + URL
    title_el = card.select_one("a.p-search-job-media__title, a.c-media__title, a[href*='/work/detail/']")
    if not title_el:
        return None

    title = title_el.get_text(strip=True)
    href = title_el.get("href", "")
    url = href if href.startswith("http") else BASE_URL + href

    # Budget
    budget_el = card.select_one(".p-search-job-media__price")
    budget = budget_el.get_text(" ", strip=True) if budget_el else "不明"

    # Category
    cat_el = card.select_one("a.p-search-job__division-link")
    category = cat_el.get_text(strip=True) if cat_el else "不明"

    # Short description (last .c-media__description block)
    desc_els = card.select("div.c-media__description")
    description = desc_els[-1].get_text(strip=True) if desc_els else ""

    # Proposal count (not always shown in list view)
    proposal_count = "提案非公開"

    # NEW badge
    is_new = bool(card.select_one('[class*="new"], [class*="New"]'))

    return Project(
        title=title,
        url=url,
        budget=budget,
        category=category,
        description=description,
        proposal_count=proposal_count,
        is_new=is_new,
        keyword=keyword,
    )


def fetch_project_detail(project: Project) -> Project:
    """Fetch the detail page and extract the full project description."""
    soup = _get(project.url)
    if not soup:
        return project

    body_el = (
        soup.select_one(".p-work-detail__body")
        or soup.select_one(".c-work-detail__description")
        or soup.select_one('[class*="work-detail"] [class*="body"]')
        or soup.select_one('[class*="detail"] [class*="description"]')
        or soup.select_one(".work_body")
        or soup.select_one("#work_body")
    )
    if body_el:
        project.full_description = body_el.get_text(separator="\n", strip=True)

    return project


def scrape_keyword(keyword: str, pages: int = 2) -> list[Project]:
    """Scrape project listings for a keyword across N pages."""
    projects = []
    seen_urls: set[str] = set()

    for page in range(1, pages + 1):
        params = {
            "keyword": keyword,
            "work_type[]": "project",
            "open": "1",
            "page": str(page),
        }
        print(f"  Fetching '{keyword}' page {page}...")
        soup = _get(SEARCH_URL, params=params)
        if not soup:
            print(f"  [warn] No soup returned for '{keyword}' page {page}")
            continue

        cards = soup.select("div.p-search-job-media")
        if not cards:
            # Debug: check if page has any content
            detail_links = soup.select('a[href*="/work/detail/"]')
            print(f"  [debug] 0 cards, {len(detail_links)} detail links, title={soup.title.string[:50] if soup.title else 'none'}")

        for card in cards:
            proj = _parse_card(card, keyword)
            if proj and proj.url not in seen_urls:
                seen_urls.add(proj.url)
                projects.append(proj)

    return projects


def scrape_all(keywords: list[str] = None, pages_per_keyword: int = 2) -> list[Project]:
    """Scrape all target keywords and return deduplicated projects (capped at MAX_PROJECTS)."""
    if keywords is None:
        keywords = TARGET_KEYWORDS

    all_projects: list[Project] = []
    seen_urls: set[str] = set()

    for kw in keywords:
        if len(all_projects) >= MAX_PROJECTS:
            print(f"  Reached {MAX_PROJECTS} project cap, stopping early.")
            break
        results = scrape_keyword(kw, pages=pages_per_keyword)
        added = 0
        for p in results:
            if p.url not in seen_urls:
                seen_urls.add(p.url)
                all_projects.append(p)
                added += 1
        print(f"  → {added} new projects for '{kw}' (total: {len(all_projects)})")

    print(f"\nTotal unique projects scraped: {len(all_projects)}")
    return all_projects
