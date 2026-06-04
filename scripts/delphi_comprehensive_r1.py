"""Delphi Review Round 1 — Anonymous Independent Review.

Two experts independently review the comprehensive redesign document.
Expert A: deepseek-v4-pro (DeepSeek) — Architect
Expert B: kimi-k2.6 (Moonshot) — Implementation Engineer
"""

import json
import os
import sys
import time
from pathlib import Path
from datetime import datetime, timezone

# ── Configuration ──────────────────────────────────────────────
PROXY_URL = "https://lab.iwhalecloud.com/gpt-proxy"
API_KEY = "ailab_YL+F7NNalGHNiJUHB46TaCAiMPJk2Q9PrgOcdm2aSqbEHUtxgnQjudORt2Z5BxP2BZ/qMmtBdRHHxCg6rcDlWf+CpV6em2iubEdJzVy5AiDQ"

DESIGN_DOC = Path(__file__).parent.parent / "docs" / "plans" / "2026-06-04-comprehensive-redesign.md"
OUTPUT_DIR = Path(__file__).parent.parent / ".sprint-state" / "phase-outputs"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

EXPERTS = {
    "A": {
        "model": "glm-5.1",
        "provider": "Zhipu (GLM)",
        "role": "架构师",
        "focus": "架构一致性、数据模型设计、向后兼容性、模块边界",
    },
    "B": {
        "model": "kimi-k2.6",
        "provider": "Moonshot (Kimi)",
        "role": "实现工程师",
        "focus": "实现可行性、代码改造范围、测试覆盖、性能影响、依赖管理",
    },
}

REVIEW_PROMPT_TEMPLATE = """你是一位资深的 {role}，正在参与一个匿名的多专家评审（Delphi Method）。

你评审的目标文档是 skill-cert 项目的通盘重构设计方案，涵盖三个维度：
1. 评测报告结构化输出（Pydantic 模型 + JSON Schema + CLI --format）
2. Skill 可观测性（ExecutionTrace + EventBus + Trace Export）
3. Token 占用监测（TokenLedger + per-eval/per-phase/per-model 分解）

你的专业关注领域：{focus}

===== 设计文档开始 =====
{design_content}
===== 设计文档结束 =====

请独立评审此设计方案。你不知道其他专家的意见。

评审要点：
1. 架构设计是否合理？数据流是否清晰？
2. 向后兼容策略是否充分？
3. 模型设计（ExecutionTrace, TokenAccounting, TokenLedger）是否完备？
4. Phase 划分和依赖关系是否合理？
5. 风险识别是否完整？缓解措施是否有效？
6. 是否有遗漏的关键问题？
7. 与前序已 APPROVED 的设计（结构化报告输出）的衔接是否顺畅？

请按以下格式输出评审结果：

## 独立评审 - Expert {expert_id}

### 优点
1. [具体优点 + 文档位置]

### 问题清单

#### Critical Issues (必须修复才能批准)
1. [问题] - 位置: [Phase/Task] - 修复建议: [...]

#### Major Concerns (必须处理)
1. [问题] - 位置: [Phase/Task] - 修复建议: [...]

#### Minor Concerns (需要说明)
1. [...]

### 裁决: [APPROVED / REQUEST_CHANGES / REJECTED]
### 置信度: [X/10]
### 关键理由
1. [...]

最后，请输出以下 JSON 格式的结构化裁决：
```json
{{
  "expert_id": "{expert_id}",
  "round": 1,
  "mode": "design",
  "verdict": "APPROVED|REQUEST_CHANGES|REJECTED",
  "confidence": X,
  "critical_issues": ["..."],
  "major_concerns": ["..."],
  "minor_concerns": ["..."],
  "consensus_report": {{
    "agreed_items": ["..."],
    "disagreed_items": ["..."],
    "final_verdict": "APPROVED|REQUEST_CHANGES"
  }}
}}
```"""


def call_model(model: str, prompt: str) -> str:
    """Call model via proxy."""
    import httpx

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "你是一位严谨的技术评审专家。请用中文回答。"},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.2,
        "max_tokens": 4096,
    }

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {API_KEY}",
    }

    try:
        resp = httpx.post(
            f"{PROXY_URL}/v1/chat/completions",
            json=payload,
            headers=headers,
            timeout=300.0,
        )
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"]
    except Exception as e:
        return f"ERROR: {type(e).__name__}: {e}"


def main():
    print("=" * 60)
    print("Delphi Review — Round 1: Anonymous Independent Review")
    print("=" * 60)

    # Read design document
    if not DESIGN_DOC.exists():
        print(f"ERROR: Design document not found: {DESIGN_DOC}")
        sys.exit(1)

    design_content = DESIGN_DOC.read_text(encoding="utf-8")
    print(f"Design document: {DESIGN_DOC.name} ({len(design_content)} chars)")
    print(f"Experts: {len(EXPERTS)}")
    for eid, info in EXPERTS.items():
        print(f"  Expert {eid}: {info['model']} ({info['provider']}) — {info['role']}")
    print()

    results = {}
    for eid, info in EXPERTS.items():
        print(f"--- Expert {eid} ({info['model']}, {info['provider']}) ---")
        print(f"  Focus: {info['focus']}")

        prompt = REVIEW_PROMPT_TEMPLATE.format(
            role=info["role"],
            focus=info["focus"],
            design_content=design_content,
            expert_id=eid,
        )

        start = time.time()
        response = call_model(info["model"], prompt)
        elapsed = time.time() - start

        print(f"  Response received in {elapsed:.1f}s ({len(response)} chars)")

        # Save response
        output_file = OUTPUT_DIR / f"delphi-r1-expert-{eid}.md"
        output_file.write_text(
            f"# Delphi Review Round 1 — Expert {eid}\n\n"
            f"**Model**: {info['model']} ({info['provider']})\n"
            f"**Role**: {info['role']}\n"
            f"**Timestamp**: {datetime.now(timezone.utc).isoformat()}\n\n"
            f"---\n\n{response}\n",
            encoding="utf-8",
        )
        print(f"  Saved: {output_file}")

        # Try to extract JSON verdict
        verdict = "UNKNOWN"
        confidence = 0
        try:
            # Find JSON block in response
            json_start = response.rfind('{\n  "expert_id"')
            if json_start == -1:
                json_start = response.rfind('{"expert_id"')
            if json_start >= 0:
                json_str = response[json_start:]
                # Find closing brace
                depth = 0
                end_idx = 0
                for i, c in enumerate(json_str):
                    if c == '{':
                        depth += 1
                    elif c == '}':
                        depth -= 1
                        if depth == 0:
                            end_idx = i + 1
                            break
                if end_idx > 0:
                    verdict_data = json.loads(json_str[:end_idx])
                    verdict = verdict_data.get("verdict", "UNKNOWN")
                    confidence = verdict_data.get("confidence", 0)
        except (json.JSONDecodeError, KeyError):
            pass

        # Fallback: scan for verdict text
        if verdict == "UNKNOWN":
            for line in response.split("\n"):
                if "裁决" in line or "verdict" in line.lower():
                    if "APPROVED" in line.upper():
                        verdict = "APPROVED"
                    elif "REQUEST_CHANGES" in line.upper():
                        verdict = "REQUEST_CHANGES"
                    elif "REJECTED" in line.upper():
                        verdict = "REJECTED"

        results[eid] = {
            "model": info["model"],
            "provider": info["provider"],
            "verdict": verdict,
            "confidence": confidence,
            "response_file": str(output_file),
            "elapsed_s": round(elapsed, 1),
        }
        print(f"  Verdict: {verdict} (confidence: {confidence}/10)")
        print()

    # Summary
    print("=" * 60)
    print("Round 1 Summary")
    print("=" * 60)
    for eid, r in results.items():
        print(f"  Expert {eid} ({r['model']}): {r['verdict']} ({r['confidence']}/10)")

    verdicts = [r["verdict"] for r in results.values()]
    if all(v == "APPROVED" for v in verdicts):
        consensus = "100% — ALL APPROVED"
    elif len(set(verdicts)) == 1:
        consensus = f"100% — ALL {verdicts[0]}"
    else:
        consensus = f"DIVERGENT — {verdicts}"

    print(f"\n  Consensus: {consensus}")

    # Save summary
    summary = {
        "round": 1,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "experts": results,
        "consensus": consensus,
        "design_doc": str(DESIGN_DOC),
    }
    summary_file = OUTPUT_DIR / "delphi-round1.json"
    summary_file.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\n  Summary saved: {summary_file}")

    return 0 if all(v == "APPROVED" for v in verdicts) else 1


if __name__ == "__main__":
    sys.exit(main())
