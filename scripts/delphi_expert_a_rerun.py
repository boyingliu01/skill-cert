"""Rerun only Expert A with glm-5.1 model."""
import json
import sys
import time
from pathlib import Path
from datetime import datetime, timezone
import httpx

API_KEY = "ailab_YL+F7NNalGHNiJUHB46TaCAiMPJk2Q9PrgOcdm2aSqbEHUtxgnQjudORt2Z5BxP2BZ/qMmtBdRHHxCg6rcDlWf+CpV6em2iubEdJzVy5AiDQ"
PROXY_URL = "https://lab.iwhalecloud.com/gpt-proxy"
DESIGN_DOC = Path("docs/plans/2026-06-04-comprehensive-redesign.md").read_text(encoding="utf-8")
OUTPUT_DIR = Path(".sprint-state/phase-outputs")

EXPERT_ID = "A"
MODEL = "glm-5.1"
PROVIDER = "Zhipu (GLM)"
ROLE = "架构师"
FOCUS = "架构一致性、数据模型设计、向后兼容性、模块边界"

SYSTEM_PROMPT = f"""你是一位资深{ROLE}（Expert {EXPERT_ID}），专注于{FOCUS}。
你正在对一个评测引擎的通盘重构设计方案进行独立评审（Delphi Method）。
你不知道其他专家的意见。请独立评审。

评审要点：
1. 架构合理性：ExecutionTrace/TokenAccounting/TokenLedger 模型设计、模块分层
2. 向后兼容性：现有 result dict / EnvelopeChecker / _DictTrace 的破坏性变更风险
3. 数据一致性：token 计算来源、并发安全、序列化完整性
4. 可扩展性：未来新增指标/导出格式/可观测工具的扩展难度
5. Phase 划分：依赖关系、渐进式交付、独立可测试性
6. 与前序已 APPROVED 设计（结构化报告输出）的衔接

请严格按以下格式输出：
## 独立评审 - Expert {EXPERT_ID}
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
1. ...

最后输出 JSON 格式裁决：
```json
{{"expert_id": "{EXPERT_ID}", "round": 1, "mode": "design", "verdict": "APPROVED|REQUEST_CHANGES|REJECTED", "confidence": X, "critical_issues": ["..."], "major_concerns": ["..."], "minor_concerns": ["..."], "consensus_report": {{"agreed_items": ["..."], "disagreed_items": ["..."], "final_verdict": "APPROVED|REQUEST_CHANGES"}}}}
```"""

print(f"--- Expert {EXPERT_ID} ({MODEL}, {PROVIDER}) ---")
print(f"  Focus: {FOCUS}")

payload = {
    "model": MODEL,
    "messages": [
        {"role": "system", "content": "你是一位严谨的技术评审专家。请用中文回答。"},
        {"role": "user", "content": f"请评审以下通盘重构设计方案：\n\n{DESIGN_DOC}"},
    ],
    "temperature": 0.2,
    "max_tokens": 4096,
}

start = time.time()
try:
    resp = httpx.post(
        f"{PROXY_URL}/v1/chat/completions",
        json=payload,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {API_KEY}"},
        timeout=300.0,
    )
    resp.raise_for_status()
    response = resp.json()["choices"][0]["message"]["content"]
except Exception as e:
    response = f"ERROR: {type(e).__name__}: {e}"

elapsed = time.time() - start
print(f"  Response received in {elapsed:.1f}s ({len(response)} chars)")

output_file = OUTPUT_DIR / f"delphi-r1-expert-A.md"
output_file.write_text(
    f"# Delphi Review Round 1 — Expert A\n\n"
    f"**Model**: {MODEL} ({PROVIDER})\n"
    f"**Role**: {ROLE}\n"
    f"**Timestamp**: {datetime.now(timezone.utc).isoformat()}\n\n---\n\n{response}\n",
    encoding="utf-8",
)
print(f"  Saved: {output_file}")

# Extract verdict
verdict = "UNKNOWN"
confidence = 0
try:
    json_start = response.rfind('{"expert_id"')
    if json_start >= 0:
        json_str = response[json_start:]
        depth = 0
        for i, c in enumerate(json_str):
            if c == '{': depth += 1
            elif c == '}':
                depth -= 1
                if depth == 0:
                    vdata = json.loads(json_str[:i+1])
                    verdict = vdata.get("verdict", "UNKNOWN")
                    confidence = vdata.get("confidence", 0)
                    break
except Exception:
    pass

if verdict == "UNKNOWN":
    for line in response.split("\n"):
        if "裁决" in line:
            if "APPROVED" in line.upper() and "REQUEST" not in line.upper():
                verdict = "APPROVED"
            elif "REQUEST_CHANGES" in line.upper():
                verdict = "REQUEST_CHANGES"
            elif "REJECTED" in line.upper():
                verdict = "REJECTED"

print(f"  Verdict: {verdict} (confidence: {confidence}/10)")
