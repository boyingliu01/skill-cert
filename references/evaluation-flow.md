# Evaluation Flow

## 核心原则

| 原则 | 说明 |
|------|------|
| **全自动评测** | 解析 → 生成 → 执行 → 评分 → 报告，无需人工介入 |
| **交叉验证** | with-skill vs without-skill 基线对比，量化技能的实际提升 |
| **多模型漂移** | 至少两个不同 provider 的模型，检测技能在不同模型下的一致性 |
| **零容忍** | Schema 不合法、覆盖率不足、漂移 high → 阻断或 FAIL |

## 评测模式

| 模式 | 触发 | 用途 |
|------|------|------|
| `single`（默认） | `skill-cert --skill <path>` | 单轮评测，验证基本功能 |
| `dialogue` | `skill-cert --skill <path> --mode dialogue --max-turns 10` | 多轮对话评测，模拟真实用户交互 |
| `replay` | `skill-cert --skill <path> --mode replay --session <file>` | 回归测试，使用历史会话数据 |

## 评测流程

### Phase 0: Skill 解析
- 读取 SKILL.md，提取语义结构（SkillSpec）：name、description、workflow_steps、anti_patterns、output_format、triggers
- 正则 + markdown-it-py AST 解析，fallback 到 LLM 辅助解析
- 8 维置信度评分：frontmatter(0.30) + workflow(0.25) + headings(0.15) + AP(0.10) + OF(0.08) + triggers(0.07) + examples(0.05) + bonus(0.05)
- Schema 验证：检查 Security Notes、Permissions（仅交互式技能）等必要章节
- 若 SKILL.md 同级存在 `references/` 目录，加载所有 `*.md` 子文件并追加到 SkillSpec

### Phase 1: 测试生成 + 自审循环
- 生成初始评测用例 → 审查质量 → 补充缺口 → 重新审查
- 循环直到覆盖率 >= 90%
- 保底：templates/minimum-evals.json

### Phase 2: 交叉验证执行
- with-skill 执行 vs without-skill 基线
- 确定性断言（contains、not_contains、regex、starts_with、json_valid）+ LLM-as-judge（温度=0）
- 安全扫描：19 种攻击模式，5 个类别（INJ/EXF/DCMD/CRD/OBF）
- 输出长度限制：100KB
- 真实 Token 追踪：TokenUsage dataclass（非近似值）

### Phase 3: 渐进补充
- 分析薄弱区域，补充针对性测试
- 收敛条件：L2 delta >= 20% 或达到最大轮数

### Phase 4: L1-L8 指标计算
- L1 触发准确性：>= 90% 达标
- L2 输出增幅（with vs without skill）：>= 20% 达标
- L3 步骤遵循度：>= 85% 达标
- L4 执行稳定性（std <= 10%）：排除 LLM judge 的确定性断言
- L5 步骤效率：包络线检查（steps/tokens/timeout/tool_calls）
- L6 轨迹质量：仅 dialogue 模式激活
- L7 成本效率：Token → $ 转换，cost delta，cost efficiency ratio
- L8 延迟指标：P50/P95/P99，with/without skill 开销对比

### Phase 5: 跨模型漂移检测
- 多模型执行同一 eval suite
- 方差阈值：none <= 0.10, low <= 0.20, moderate <= 0.35, high > 0.35
- none/low → 不影响判定，moderate → PASS_WITH_CAVEATS，high → FAIL

### Phase 6: 报告生成
- Markdown 报告 + JSON 结果 + 评测缓存
- 包含：执行摘要、L1-L8 指标、漂移分析、安全扫描、成本分析、延迟分析、改进建议、配置信息、基准信息
- 可靠性报告：错误分类、重试统计、优雅降级

### 扩展能力
- **多技能冲突检测**：trigger 重叠、prompt 干扰、token 预算溢出
- **压力测试**：并发公平性、内存追踪、可扩展性评分
- **SKILL.md 可维护性**：可读性、完整性、新鲜度评分
- **外部集成框架**：SkillLab / DeepEval providers（优雅降级）
- **多轮运行稳定性**：`--runs` flag 执行 L4 std dev
