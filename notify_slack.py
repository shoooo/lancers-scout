"""
Post top Lancers picks to Slack via incoming webhook.
Usage: python notify_slack.py results.json
"""

import json
import os
import sys
import urllib.request
import urllib.error

WEBHOOK_URL = os.environ.get("SLACK_WEBHOOK_URL", "")

REC_EMOJI = {
    "apply": ":green_circle:",
    "maybe": ":yellow_circle:",
    "skip":  ":red_circle:",
}


def build_message(results: list[dict]) -> dict:
    apply = [r for r in results if r["recommendation"] == "apply"]
    maybe = [r for r in results if r["recommendation"] == "maybe"]

    lines = [
        f"*Lancers Scout — 新着おすすめ案件* :lancers:",
        f"Apply: *{len(apply)}件*　Maybe: *{len(maybe)}件*",
        "",
    ]

    for i, r in enumerate(results[:10], 1):
        emoji = REC_EMOJI.get(r["recommendation"], ":white_circle:")
        score = r.get("score", "?")
        lines.append(
            f"{emoji} *#{i} [{score}/10]* <{r['url']}|{r['title'][:55]}>"
        )
        lines.append(f"　　予算: {r['budget']}　提案数: {r['proposal_count']}")
        lines.append(f"　　_{r['reason']}_")
        lines.append("")

    return {"text": "\n".join(lines)}


def post(message: dict) -> None:
    if not WEBHOOK_URL:
        print("SLACK_WEBHOOK_URL not set, skipping notification.")
        return

    data = json.dumps(message).encode("utf-8")
    req = urllib.request.Request(
        WEBHOOK_URL,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            print(f"Slack response: {resp.status}")
    except urllib.error.URLError as e:
        print(f"Slack post failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    results_file = sys.argv[1] if len(sys.argv) > 1 else "results.json"
    with open(results_file, encoding="utf-8") as f:
        results = json.load(f)

    if not results:
        print("No results to post.")
        sys.exit(0)

    message = build_message(results)
    post(message)
    print(f"Posted {len(results[:10])} projects to Slack.")
