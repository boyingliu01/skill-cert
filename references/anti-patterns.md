# Anti-Patterns

## 错误做法对照表

| 错误 | 正确 |
|------|------|
| 跳过 Phase 1 自审循环直接跑评测 | 必须完成 generate → review → gap-fill 循环，覆盖率 >= 90% |
| 只跑 with-skill 不跑 without-skill 基线 | 必须同时跑 with+without 才能计算 L2 delta |
| 忽略 L4 稳定性只关注 L2 delta | L4 std > 10% 需要排查，不能只看 L2 增幅 |
| 漂移检测 high 仍给 PASS | drift high → 直接 FAIL，不可降级 |
| 修改 Phase 2 执行后的 eval 用例 | eval 用例在执行前锁定，Phase 2 后不可修改（完整性规则） |
| SKILL.md 解析 confidence < 0.6 仍继续 | 低置信度时应该降级处理，标记为 PASS_WITH_CAVEATS |
| 覆盖率 < 70% 仍然执行评测 | 覆盖率不足应阻断，无法生成有效测试 |
| 单模型评测 | 至少需要两个不同 provider 的模型进行漂移检测 |
| temp > 0 用于 LLM-as-judge | LLM judge 必须使用 temp=0 确保确定性 |
| `as any`/`@ts-ignore` 压制类型错误 | 类型安全是 skill 质量的一部分，不可绕过 |

## Red Flags

- SKILL.md 解析 confidence < 0.6 → 结构模糊，评测结果不可信
- 覆盖率 < 70% → 阻断，无法生成有效测试
- 所有模型不可用 → 优雅终止，输出部分结果
- 漂移 high → 技能在不同模型下行为不一致，无法发布
