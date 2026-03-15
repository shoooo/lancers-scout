"""
AI-powered project analyzer using Claude.
Scores and explains which Lancers projects are worth applying to.
"""

import os
import json
import anthropic
from pathlib import Path
from scraper import Project


def _load_api_key() -> str:
    """Resolve ANTHROPIC_API_KEY from env, .env file, or raise."""
    key = os.environ.get("ANTHROPIC_API_KEY")
    if key:
        return key
    # Try .env in project root
    env_path = Path(__file__).parent / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if line.startswith("ANTHROPIC_API_KEY="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    raise ValueError(
        "ANTHROPIC_API_KEY not found.\n"
        "Set it as an env var:  export ANTHROPIC_API_KEY=sk-ant-...\n"
        "Or create a .env file: echo 'ANTHROPIC_API_KEY=sk-ant-...' > .env"
    )


client = anthropic.Anthropic(api_key=_load_api_key())

SYSTEM_PROMPT = """You are a freelance business advisor helping a Japanese freelancer find the best side hustle projects on Lancers (Japan's top freelancing platform).

The freelancer's skills and target areas:
- E-commerce site building (Shopify, WooCommerce, BASE, STORES, カラーミーショップ)
- Website / homepage creation (WordPress, HTML/CSS, LP制作)
- Web design and implementation
- They are looking for side projects with reasonable budgets and good fit

For each project, you will return a JSON assessment with:
- score: integer 1-10 (10 = must apply, 1 = skip)
- recommendation: "apply" | "maybe" | "skip"
- reason: 1-2 sentence explanation in English
- apply_tip: one practical tip for the application message (in English)

Scoring criteria:
- Budget: higher fixed budgets score better; tasks under 10,000 円 score low
- Skill fit: ecommerce (EC, Shopify, WooCommerce, ネットショップ) and web building (WordPress, LP, ホームページ) score high
- Competition: fewer proposals = better chance
- Clarity: well-described projects are easier to deliver
- Red flags: vague budgets ("応相談"), very low pay, data entry tasks = lower score"""

USER_PROMPT_TEMPLATE = """Here are {count} Lancers projects scraped for ecommerce and web building keywords.
Analyze each one and return a JSON array of assessments in the same order.

Projects:
{projects_json}

Return ONLY a valid JSON array. Each element must have: score, recommendation, reason, apply_tip.
"""


def _build_project_summary(p: Project) -> dict:
    return {
        "title": p.title,
        "url": p.url,
        "budget": p.budget,
        "category": p.category,
        "keyword": p.keyword,
        "description": (p.full_description or p.description)[:500],
        "proposal_count": p.proposal_count,
        "is_new": p.is_new,
    }


def analyze_projects(projects: list[Project], batch_size: int = 15) -> list[dict]:
    """
    Send projects to Claude in batches for scoring.
    Returns list of assessment dicts in the same order as input.
    """
    all_assessments: list[dict] = []

    for i in range(0, len(projects), batch_size):
        batch = projects[i : i + batch_size]
        summaries = [_build_project_summary(p) for p in batch]
        prompt = USER_PROMPT_TEMPLATE.format(
            count=len(summaries),
            projects_json=json.dumps(summaries, ensure_ascii=False, indent=2),
        )

        print(f"  Analyzing projects {i+1}–{i+len(batch)} with Claude...")
        message = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=4096,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        )

        raw = message.content[0].text.strip()
        # Strip markdown code fences if present
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        raw = raw.strip()

        try:
            assessments = json.loads(raw)
            if len(assessments) != len(batch):
                # Pad or trim to match batch length
                while len(assessments) < len(batch):
                    assessments.append({"score": 5, "recommendation": "maybe", "reason": "N/A", "apply_tip": "N/A"})
                assessments = assessments[: len(batch)]
        except json.JSONDecodeError as e:
            print(f"  [parse error] Could not parse Claude response: {e}")
            assessments = [
                {"score": 5, "recommendation": "maybe", "reason": "Parse error", "apply_tip": "N/A"}
                for _ in batch
            ]

        all_assessments.extend(assessments)

    return all_assessments


PROPOSAL_SYSTEM_PROMPT = """You are an expert Japanese freelance copywriter. Your job is to write a compelling 提案文 (proposal message) on Lancers for a freelancer applying to a project.

Rules:
- Write entirely in natural, polite Japanese (敬語)
- Length: 250–400 characters (not too long, clients skim fast)
- Structure: ① 挨拶 + 興味を持った理由 → ② 自分の関連実績・スキル → ③ 具体的な進め方・提案 → ④ 締め・お願い
- Tailor the message specifically to this project — mention the client's goal or tech stack
- Sound like a real human, not a template
- Do NOT use bullet points or headers — write as flowing paragraphs
- End with a polite call to action (ご検討よろしくお願いいたします etc.)

Return ONLY the proposal text, no JSON, no explanation."""

PROPOSAL_USER_TEMPLATE = """Write a proposal message for this Lancers project.

Project:
- Title: {title}
- Budget: {budget}
- Category: {category}
- Description: {description}

Freelancer profile:
- Skills: {skills}
- Past work examples: {past_work}
- Strengths: {strengths}
- Availability: {availability}
- Note: {note}

Write the 提案文 now:"""


def generate_proposal(project: dict, profile: dict) -> str:
    """Generate a Japanese proposal message for a single project."""
    description = project.get("description", "") or project.get("full_description", "")
    prompt = PROPOSAL_USER_TEMPLATE.format(
        title=project["title"],
        budget=project["budget"],
        category=project["category"],
        description=description[:600],
        skills=", ".join(profile.get("skills", [])),
        past_work="; ".join(profile.get("past_work", [])),
        strengths=profile.get("strengths", ""),
        availability=profile.get("availability", ""),
        note=profile.get("note", ""),
    )
    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1024,
        system=PROPOSAL_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}],
    )
    return message.content[0].text.strip()


def merge_and_rank(projects: list[Project], assessments: list[dict]) -> list[dict]:
    """Merge project data with assessments and sort by score descending."""
    merged = []
    for p, a in zip(projects, assessments):
        merged.append(
            {
                "title": p.title,
                "url": p.url,
                "budget": p.budget,
                "category": p.category,
                "keyword": p.keyword,
                "proposal_count": p.proposal_count,
                "is_new": p.is_new,
                "score": a.get("score", 0),
                "recommendation": a.get("recommendation", "maybe"),
                "reason": a.get("reason", ""),
                "apply_tip": a.get("apply_tip", ""),
            }
        )
    return sorted(merged, key=lambda x: x["score"], reverse=True)
