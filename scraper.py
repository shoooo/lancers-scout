"""
Lancers project scraper.
Scrapes project listings from lancers.jp for given keywords.
"""

import time
import random
import requests
from bs4 import BeautifulSoup
from dataclasses import dataclass
from typing import Optional

BASE_URL = "https://www.lancers.jp"
SEARCH_URL = f"{BASE_URL}/work/search"

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
]


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
    """Fetch a page with polite delay and return parsed soup."""
    time.sleep(random.uniform(1.5, 3.0))
    try:
        resp = requests.get(url, headers=HEADERS, params=params, timeout=15)
        resp.raise_for_status()
        resp.encoding = "utf-8"
        return BeautifulSoup(resp.text, "html.parser")
    except requests.RequestException as e:
        print(f"  [fetch error] {url}: {e}")
        return None


def _parse_card(card, keyword: str) -> Optional[Project]:
    """Parse a project card element into a Project."""
    # Title + URL
    title_el = (
        card.select_one(".p-work-card__title a")
        or card.select_one(".p-search-job__title a")
        or card.select_one('a[href*="/work/detail/"]')
    )
    if not title_el:
        return None

    title = title_el.get_text(strip=True)
    href = title_el.get("href", "")
    url = href if href.startswith("http") else BASE_URL + href

    # Budget
    budget_el = (
        card.select_one(".p-work-card__budget")
        or card.select_one('[class*="budget"]')
        or card.select_one('[class*="price"]')
        or card.select_one('[class*="reward"]')
    )
    budget = budget_el.get_text(strip=True) if budget_el else "不明"

    # Category
    cat_el = (
        card.select_one(".p-work-card__category a")
        or card.select_one('[class*="category"] a')
    )
    category = cat_el.get_text(strip=True) if cat_el else "不明"

    # Short description
    desc_el = (
        card.select_one(".p-work-card__description")
        or card.select_one('[class*="description"]')
        or card.select_one('[class*="body"]')
    )
    description = desc_el.get_text(strip=True) if desc_el else ""

    # Proposal count
    proposal_el = (
        card.select_one('[class*="proposal"]')
        or card.select_one('[class*="entry"]')
    )
    proposal_count = proposal_el.get_text(strip=True) if proposal_el else "不明"

    # NEW badge
    is_new = bool(card.select_one('[class*="new"]'))

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
            "page": page,
        }
        print(f"  Fetching '{keyword}' page {page}...")
        soup = _get(SEARCH_URL, params=params)
        if not soup:
            continue

        cards = soup.select(".p-work-card, .p-search-job__item, [class*='work-card']")

        if not cards:
            # Fallback: group by parent of /work/detail/ links
            parents_seen: set[int] = set()
            for a in soup.select('a[href*="/work/detail/"]'):
                parent = a.find_parent("li") or a.find_parent("div")
                if parent and id(parent) not in parents_seen:
                    parents_seen.add(id(parent))
                    cards.append(parent)

        for card in cards:
            proj = _parse_card(card, keyword)
            if proj and proj.url not in seen_urls:
                seen_urls.add(proj.url)
                projects.append(proj)

    return projects


def scrape_all(keywords: list[str] = None, pages_per_keyword: int = 2) -> list[Project]:
    """Scrape all target keywords and return deduplicated projects."""
    if keywords is None:
        keywords = TARGET_KEYWORDS

    all_projects: list[Project] = []
    seen_urls: set[str] = set()

    for kw in keywords:
        results = scrape_keyword(kw, pages=pages_per_keyword)
        for p in results:
            if p.url not in seen_urls:
                seen_urls.add(p.url)
                all_projects.append(p)
        print(f"  → {len(results)} projects found for '{kw}'")

    print(f"\nTotal unique projects scraped: {len(all_projects)}")
    return all_projects
