"""Round 1 Delphi Review — anonymous independent expert reviews."""
import json
from pathlib import Path

import httpx

API_KEY = "ailab_YL+F7NNalGHNiJUHB46TaCAiMPJk2Q9PrgOcdm2aSqbEHUtxgnQjudORt2Z5BxP2BZ/qMmtBdRHHxCg6rcDlWf+CpV6em2iubEdJzVy5AiDQ"
BASE_URL = "https://lab.iwhalecloud.com/gpt-proxy"

DESIGN_DOC = Path("docs/plans/2026-06-04-structured-report-output.md").read_text(encoding="utf-8")

EXPERT_A_SYSTEM = """你是一位资深软件架构师（Expert A），专注于系统设计和数据模型架构。
你正在对一个评测引擎的报告结构化输出方案进行独立评审。
你不知道其他专家的意见。请独立评审。

评审要点：
1. 架构合理性：Pydantic 模型设计、JSON Schema 设计、模块分层
2. 向后兼容性：现有 API 的破坏性变更风险
3. 可扩展性：未来新增指标或报告格式的扩展难度
4. 数据完整性：eval_details 数据来源的可靠性
5. 需求覆盖：4 个 REQ 是否全部覆盖

请严格按以下格式输出：
## 独立评审 - Expert A
### 优点
1. ...
### 问题清单
#### Critical Issues (必须修复才能批准)
1. [问题] - 位置: [...] - 修复建议: [...]
#### Major Concerns (必须处理)
1. ...
#### Minor Concerns (需要说明)
1. ...
### 裁决: [APPROVED / REQUEST_CHANGES / REJECTED]
### 置信度: [X/10]
### 关键理由
1. ..."""

EXPERT_B_SYSTEM = """你是一位资深实现工程师（Expert B），专注于 Python 工程实践、测试策略和 CLI 工具开发。
你正在对一个评测引擎的报告结构化输出方案进行独立评审。
你不知道其他专家的意见。请独立评审。

评审要点：
1. 实现可行性：代码改动量、复杂度、维护成本
2. 测试策略：测试覆盖率、回归风险、边界条件
3. CLI 用户体验：参数设计、错误处理、输出格式
4. 工程风险：依赖管理、性能影响、迁移路径
5. 需求覆盖：4 个 REQ 是否全部覆盖

请严格按以下格式输出：
## 独立评审 - Expert B
### 优点
1. ...
### 问题清单
#### Critical Issues (必须修复才能批准)
1. [问题] - 位置: [...] - 修复建议: [...]
#### Major Concerns (必须处理)
1. ...
#### Minor Concerns (需要说明)
1. ...
### 裁决: [APPROVED / REQUEST_CHANGES / REJECTED]
### 置信度: [X/10]
### 关键理由
1. ..."""

EXPERTS = [
    ("A", "glm-5.1", EXPERT_A_SYSTEM),
    ("B", "Qwen3.5-122B-A10B", EXPERT_B_SYSTEM),
]

USER_PROMPT = f"""请对以下设计文档进行独立评审：

---
{DESIGN_DOC}
---

项目背景补充：
- 当前 reporter.py 624 行，Jinja2 模板内联，JSON 报告是简单 dict
- 现有测试 580 行（test_reporter.py），6 个测试直接断言 suggestions 字符串内容
- CLI 层 3 个报告写入点：evals.py, multi_skill.py, stress.py
- metrics['_results'] 包含逐条结果但缺少 eval name/category 直接映射
- SecurityScanner 存在于 engine/security_probes.py 但未集成到 single mode pipeline
- 项目使用 Pydantic 2.x, Jinja2, jsonschema 已安装但未声明依赖

请按照系统提示中的格式输出你的评审。"""


def call_model(model: str, system: str, user: str) -> str:
    resp = httpx.post(
        f"{BASE_URL}/chat/completions",
        headers={"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"},
        json={
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": 0.3,
            "max_tokens": 4000,
        },
        timeout=120.0,
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]


def main():
    results = {}
    for expert_id, model, system in EXPERTS:
        print(f"\n{'='*60}")
        print(f"  Calling Expert {expert_id} ({model})...")
        print(f"{'='*60}")
        try:
            review = call_model(model, system, USER_PROMPT)
            results[expert_id] = {"model": model, "review": review}
            print(review)
        except Exception as e:
            print(f"  ERROR calling {model}: {e}")
            results[expert_id] = {"model": model, "review": f"ERROR: {e}"}

    # Save results
    out_dir = Path(".sprint-state/phase-outputs")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "delphi-round1.json"
    out_path.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\n\nRound 1 results saved to: {out_path}")


if __name__ == "__main__":
    main()
