"""Round 2 Delphi Review — experts review fixes and decide."""
import httpx
import json
from pathlib import Path

API_KEY = "ailab_YL+F7NNalGHNiJUHB46TaCAiMPJk2Q9PrgOcdm2aSqbEHUtxgnQjudORt2Z5BxP2BZ/qMmtBdRHHxCg6rcDlWf+CpV6em2iubEdJzVy5AiDQ"
BASE_URL = "https://lab.iwhalecloud.com/gpt-proxy"

ROUND1 = json.loads(Path(".sprint-state/phase-outputs/delphi-round1.json").read_text(encoding="utf-8"))

FIX_REPORT = """## 修复报告

### Critical Issues 修复

#### 1. eval_details 数据映射机制（两位专家共同 Critical）
**修复方案**：在 `_run_single_phase()` 中，在调用 `reporter.generate_report()` 之前，构建 `eval_case_meta: dict[int, dict]` 映射表：
```python
eval_cases = spec["evals"].get("eval_cases", spec["evals"].get("cases", []))
eval_case_meta = {c["id"]: {"name": c.get("name", ""), "category": c.get("category", "normal")} for c in eval_cases}
```
然后将 `eval_case_meta` 作为新参数传入 `generate_report(..., eval_case_meta=eval_case_meta)`。
`_build_eval_details()` 使用该映射填充 name/category，找不到时赋值 "N/A" 并记录 Warning。

### Major Concerns 处理

#### 2. JSON Schema 与 Pydantic 双重维护（Expert A - Major）
**修复方案**：采纳。`schemas/report.schema.json` 由 `StructuredReport.model_json_schema()` 自动生成。新增辅助函数：
```python
def export_report_schema() -> dict:
    from engine.report_models import StructuredReport
    return StructuredReport.model_json_schema()
```
在 Task 2 中，先编写 Pydantic 模型，再通过脚本/CLI 命令导出为静态 JSON Schema 文件。不再手写维护。

#### 3. _generate_suggestions() 过渡方案（Expert A - Major）
**修复方案**：采纳。`ImprovementSuggestion` 实现 `__str__` 方法返回 `self.text`，确保 Jinja2 模板中 `{{ suggestion }}` 仍可工作。同时在 `generate_report()` 内部做类型适配：如果调用者传入旧格式 `list[str]`，自动转换为 `ImprovementSuggestion(text=s, priority="P2", expected_impact="low")`。

#### 4. security_scan 在 Schema 中为 optional（两位专家共同 Major）
**修复方案**：采纳。
- Pydantic 模型中 `security_scan: SecurityScanResult | None = None`
- JSON Schema 中 `security_scan` 不在 `required` 列表中
- `model_dump(exclude_none=True)` 确保为 None 时不输出
- 更新 AC-001 说明：security_scan 为可选字段，当 SecurityScanner 集成后自动填充
- REQ-REPORT-001 需求文档中 security_scan 标注为 "when available"

#### 5. Jinja2 模板重构测试（Expert B - Major）
**修复方案**：采纳。新增基于正则的 Markdown 表格结构验证测试：
```python
def test_markdown_metrics_table_structure():
    # 验证表格行格式: | L1 | ... | ... | PASS |
    assert re.search(r'\| L1 \|.*\|.*\|.*PASS.*\|', md_report)
```

#### 6. Suggestion 优先级阈值提取（Expert B - Major）
**修复方案**：采纳。将 P0/P1/P2 判定阈值提取到 `engine/constants.py` 的 `SuggestionThresholds` 类中：
```python
class SuggestionThresholds:
    P0_SCORE = 0.6
    P1_COST_DELTA = 0.5
    P1_ERROR_RATE = 0.2
```

#### 7. Pydantic 性能开销（Expert B - Major）
**修复方案**：部分采纳。在 Task 8 验证步骤中增加简单性能测试：
```python
import time
start = time.time()
report = StructuredReport(...)
report.model_dump(mode="json")
elapsed = time.time() - start
assert elapsed < 1.0  # 必须 < 1s
```

### Minor Concerns 说明

1. **阈值动态注入**：已采纳，MetricLevelDetail.threshold 从 VerdictThresholds 动态读取。
2. **Jinja2 模板外抽**：暂不采纳。当前内联方式与项目其他模板（prompts/*.md）风格不同，但外抽涉及加载路径和打包配置变更，建议作为后续独立重构。
3. **Benchmark 覆盖率兜底**：已采纳，Jinja2 模板增加 `{% if benchmark.test_coverage_rate is defined %}` 判断。
4. **依赖声明**：已确认 pyproject.toml 是唯一依赖源，CI/CD 通过 `pip install -e .` 安装。
5. **Schema 版本**：保持 Draft-07，因 jsonschema 库对 Draft-07 支持最稳定。
6. **错误处理粒度**：已采纳，validate_report_schema 返回人类可读错误信息。
7. **测试数量**：已采纳，增加至约 25 个新测试覆盖核心分支。
"""

EXPERT_A_SYSTEM_R2 = """你是一位资深软件架构师（Expert A）。
你之前对"评测报告结构化输出"设计文档进行了独立评审，给出了 REQUEST_CHANGES 裁决。
现在你看到了修复报告。请评估修复方案是否解决了你提出的所有问题。

请严格按以下格式输出：
## Round 2 Response - Expert A
### 响应修复报告
**原 Critical: eval_details 数据映射**
- 修复是否充分: [是/部分/否] - 理由: [...]
**原 Major: JSON Schema 双重维护**
- 修复是否充分: [是/部分/否] - 理由: [...]
**原 Major: _generate_suggestions() 过渡方案**
- 修复是否充分: [是/部分/否] - 理由: [...]
**原 Major: security_scan required 矛盾**
- 修复是否充分: [是/部分/否] - 理由: [...]
### 更新后裁决: [APPROVED / REQUEST_CHANGES]
### 更新后置信度: [X/10]
### 立场变化说明（如有）"""

EXPERT_B_SYSTEM_R2 = """你是一位资深实现工程师（Expert B）。
你之前对"评测报告结构化输出"设计文档进行了独立评审，给出了 REQUEST_CHANGES 裁决。
现在你看到了修复报告。请评估修复方案是否解决了你提出的所有问题。

请严格按以下格式输出：
## Round 2 Response - Expert B
### 响应修复报告
**原 Critical: eval_details 数据映射**
- 修复是否充分: [是/部分/否] - 理由: [...]
**原 Critical: 依赖声明风险**
- 修复是否充分: [是/部分/否] - 理由: [...]
**原 Critical: security_scan 数据源断裂**
- 修复是否充分: [是/部分/否] - 理由: [...]
**原 Major: Jinja2 模板测试**
- 修复是否充分: [是/部分/否] - 理由: [...]
**原 Major: Pydantic 性能**
- 修复是否充分: [是/部分/否] - 理由: [...]
**原 Major: Suggestion 优先级硬编码**
- 修复是否充分: [是/部分/否] - 理由: [...]
### 更新后裁决: [APPROVED / REQUEST_CHANGES]
### 更新后置信度: [X/10]
### 立场变化说明（如有）"""

EXPERTS_R2 = [
    ("A", "glm-5.1", EXPERT_A_SYSTEM_R2),
    ("B", "Qwen3.5-122B-A10B", EXPERT_B_SYSTEM_R2),
]

USER_PROMPT_R2 = f"""以下是针对 Round 1 评审问题的修复报告：

---
{FIX_REPORT}
---

请评估每个修复是否充分，并给出更新后的裁决。"""


def call_model(model, system, user):
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
            "max_tokens": 3000,
        },
        timeout=120.0,
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]


def main():
    results = {}
    for expert_id, model, system in EXPERTS_R2:
        print(f"\n{'='*60}")
        print(f"  Round 2: Expert {expert_id} ({model})...")
        print(f"{'='*60}")
        try:
            review = call_model(model, system, USER_PROMPT_R2)
            results[expert_id] = {"model": model, "review": review}
            print(review)
        except Exception as e:
            print(f"  ERROR: {e}")
            results[expert_id] = {"model": model, "review": f"ERROR: {e}"}

    out_path = Path(".sprint-state/phase-outputs/delphi-round2.json")
    out_path.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\n\nRound 2 results saved to: {out_path}")


if __name__ == "__main__":
    main()
