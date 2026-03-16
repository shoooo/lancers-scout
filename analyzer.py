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

SYSTEM_PROMPT = """あなたはランサーズ（日本最大のクラウドソーシングサービス）で副業案件を探しているフリーランサーをサポートするビジネスアドバイザーです。

フリーランサーのスキルと対象分野：
- ECサイト構築（Shopify、WooCommerce、BASE、STORES、カラーミーショップ）
- Webサイト・ホームページ制作（WordPress、HTML/CSS、LP制作）
- React / Next.js を使ったWebアプリ開発
- 小〜中規模の案件を中心に探している

各案件に対して以下のJSONで評価を返してください：
- score: 1〜10の整数（10＝必ず応募、1＝スキップ）
- recommendation: "apply" | "maybe" | "skip"
- reason: 1〜2文の評価コメント（日本語で）
- apply_tip: 提案文作成のための具体的なアドバイス1つ（日本語で）

スコア基準：
- 予算：高い固定報酬ほど高スコア。1万円未満のタスクは低スコア
- スキル適合度：EC・Shopify・WooCommerce・ネットショップ・WordPress・LP・ホームページ制作は高スコア
- 競争率：提案数が少ないほど有利
- 明確さ：要件が明確な案件は納品しやすい
- 注意：「応相談」の予算・単純作業・データ入力は低スコア"""

USER_PROMPT_TEMPLATE = """以下の{count}件のランサーズ案件を分析し、同じ順番でJSON配列として評価を返してください。

案件一覧：
{projects_json}

JSON配列のみ返してください。各要素には score, recommendation, reason, apply_tip を含めること。
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
