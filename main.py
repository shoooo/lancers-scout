"""
Lancers Scout — main entry point.

Usage:
    python main.py                              # scrape all keywords, analyze, show top results
    python main.py --top 10                     # show top 10 only
    python main.py --keywords "Shopify,WordPress"  # custom keywords
    python main.py --detail                     # fetch full detail page before analysis
    python main.py --output results.json        # save results to JSON
    python main.py --filter apply               # show only "apply" recommendations
    python main.py --propose                    # generate Japanese proposal messages for top picks
    python main.py --propose-top 3              # generate proposals for top 3 "apply" projects
"""

import argparse
import json
import sys
from pathlib import Path
from scraper import scrape_all, fetch_project_detail, TARGET_KEYWORDS
from analyzer import analyze_projects, merge_and_rank, generate_proposal

COLORS = {
    "apply": "\033[92m",   # green
    "maybe": "\033[93m",   # yellow
    "skip":  "\033[91m",   # red
    "reset": "\033[0m",
    "bold":  "\033[1m",
    "dim":   "\033[2m",
}


def color(text: str, *keys: str) -> str:
    codes = "".join(COLORS.get(k, "") for k in keys)
    return f"{codes}{text}{COLORS['reset']}"


def print_result(r: dict, rank: int) -> None:
    rec = r["recommendation"]
    score_str = f"[{r['score']}/10]"

    print(f"\n{color(f'#{rank}', 'bold')} {color(score_str, rec, 'bold')} {color(r['title'], 'bold')}")
    print(f"  Budget:    {r['budget']}")
    print(f"  Category:  {r['category']}")
    print(f"  Proposals: {r['proposal_count']}")
    print(f"  New:       {'yes' if r['is_new'] else 'no'}")
    print(f"  Keyword:   {r['keyword']}")
    print(f"  URL:       {r['url']}")
    print(f"  Verdict:   {color(rec.upper(), rec, 'bold')} — {r['reason']}")
    print(f"  Tip:       {color(r['apply_tip'], 'dim')}")
    if r.get("proposal"):
        print(f"\n  {color('--- 提案文 ---', 'bold')}")
        for line in r["proposal"].splitlines():
            print(f"  {line}")
        print(f"  {color('--------------', 'dim')}")


def load_profile() -> dict:
    profile_path = Path(__file__).parent / "profile.json"
    if not profile_path.exists():
        print("profile.json not found. Create it from the example to personalize proposals.")
        return {}
    with open(profile_path, encoding="utf-8") as f:
        return json.load(f)


def main() -> None:
    parser = argparse.ArgumentParser(description="Lancers Scout — find side hustle projects")
    parser.add_argument("--top", type=int, default=20, help="Show top N results (default: 20)")
    parser.add_argument("--keywords", type=str, default=None, help="Comma-separated keywords")
    parser.add_argument("--pages", type=int, default=2, help="Pages per keyword (default: 2)")
    parser.add_argument("--detail", action="store_true", help="Fetch full detail page per project")
    parser.add_argument("--output", type=str, default=None, help="Save results to JSON file")
    parser.add_argument("--filter", type=str, choices=["apply", "maybe", "skip"], default=None,
                        help="Only show projects matching this recommendation")
    parser.add_argument("--propose", action="store_true",
                        help="Generate Japanese proposal messages for top 'apply' projects")
    parser.add_argument("--propose-top", type=int, default=3,
                        help="Number of proposals to generate when using --propose (default: 3)")
    args = parser.parse_args()

    keywords = [k.strip() for k in args.keywords.split(",")] if args.keywords else TARGET_KEYWORDS

    # --- SCRAPE ---
    print(color("\n=== Lancers Scout ===", "bold"))
    print(f"Keywords: {', '.join(keywords)}")
    print(f"Pages per keyword: {args.pages}\n")
    print("Scraping projects...")

    projects = scrape_all(keywords=keywords, pages_per_keyword=args.pages)

    if not projects:
        print("No projects found. Check your internet connection or try different keywords.")
        sys.exit(1)

    # --- DETAIL FETCH (optional) ---
    if args.detail:
        print(f"\nFetching detail pages for {len(projects)} projects...")
        for i, p in enumerate(projects, 1):
            print(f"  [{i}/{len(projects)}] {p.title[:50]}...")
            projects[i - 1] = fetch_project_detail(p)

    # --- ANALYZE ---
    print("\nAnalyzing projects with Claude...")
    assessments = analyze_projects(projects)
    ranked = merge_and_rank(projects, assessments)

    # --- FILTER ---
    if args.filter:
        ranked = [r for r in ranked if r["recommendation"] == args.filter]

    # --- PROPOSALS ---
    if args.propose:
        profile = load_profile()
        apply_projects = [r for r in ranked if r["recommendation"] == "apply"]
        targets = apply_projects[: args.propose_top]
        if not targets:
            print("No 'apply' projects found to generate proposals for.")
        else:
            print(f"\n{color('=== Generating Proposals ===', 'bold')}")
            print(f"Writing 提案文 for top {len(targets)} 'apply' project(s)...\n")
            for r in targets:
                print(f"  Writing proposal for: {r['title'][:60]}...")
                r["proposal"] = generate_proposal(r, profile)

    # --- DISPLAY ---
    top = ranked[: args.top]
    apply_count = sum(1 for r in ranked if r["recommendation"] == "apply")
    maybe_count = sum(1 for r in ranked if r["recommendation"] == "maybe")

    print(f"\n{color('=== Results ===', 'bold')}")
    print(f"Total analyzed: {len(ranked)}  |  "
          f"{color(f'Apply: {apply_count}', 'apply')}  "
          f"{color(f'Maybe: {maybe_count}', 'maybe')}  "
          f"{color(f'Skip: {len(ranked)-apply_count-maybe_count}', 'skip')}")

    for i, r in enumerate(top, 1):
        print_result(r, i)

    # --- SAVE ---
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(ranked, f, ensure_ascii=False, indent=2)
        print(f"\nSaved {len(ranked)} results to {args.output}")

    print()


if __name__ == "__main__":
    main()
