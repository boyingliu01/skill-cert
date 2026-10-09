# Harness Spike Notes — opencode run --format json

日期：2026-08-22 ｜ opencode 版本：**1.18.21**（Windows，验证通过）｜ 模型：opencode/hy3-free

## 结论

`opencode run --format json` 事件流包含 harness 评测所需的全部数据，
**无需 fallback 到 `opencode export`**。目录级 skill 安装/隔离完全生效。

## 命令形态

```
opencode run --format json --model <provider/model> --auto --dir <sandbox> --title <t> <prompt>
```

- stdout：每行一个 JSON 事件；stderr 为空（正常路径）
- 退出码 0 = 正常结束
- `--auto` 自动批准权限（非交互必需）

## 事件流结构（实测字段清单）

每行：`{"type", "timestamp"(epoch ms), "sessionID", "part"}`

| type | part 关键字段 | 用途 |
|---|---|---|
| `step_start` | `{id, messageID, sessionID, type:"step-start"}` | 轮次开始 |
| `tool_use` | `{type:"tool", tool, callID, state:{status, input, output, time{start,end}}}` | 工具调用轨迹 |
| `text` | `{type:"text", text, time{start,end}}` | 模型文本输出（取最后一个作为 final_output） |
| `step_finish` | `{reason("stop"/"tool-calls"), tokens{total,input,output,reasoning,cache{write,read}}, cost}` | 计量 |

### 关键判定规则（实现依据）

1. **skill 触发检测**：存在 `part.type=="tool" && part.tool=="skill"` 的事件，且
   `part.state.input.name == <目标skill名>`。state.output 即渐进披露加载的完整 SKILL.md 内容。
2. **final_output**：最后一个 `type=="text"` 事件的 `part.text`（多轮 agent 会有多个 text，
   取最后一个是最终回复）。
3. **token 汇总**：Σ 各 step_finish 的 `tokens`（每个 step 是增量；注意第二 step 起
   input 较小、cache.read 较大，属缓存复用，总量按 total 累加即可）。
   cost 在 `part.cost`（免费模型为 0，缺失时由 skill-cert pricing 表兜底换算）。
4. **tool_call_count**：`tool_use` 事件计数。
5. **sessionID**：每个事件顶层都有（格式 `ses_...`）。

## 隔离性验证

- with-skill（沙箱 `.opencode/skills/demo-greeting/SKILL.md`）：skill 工具被调用，
  输出严格遵循 skill 规定格式（GREETING-PROTO v1 / 3 bullets / END-OF-GREETING）。
- without-skill（空沙箱）：无 skill 调用，输出自由格式。
- **渐进披露机制真实生效**：agent 先看到 name/description，按需调用 skill 工具加载全文。

## dsh（DeepSeek Harness）状态（2026-08-22）

- developer preview（实测包版本 0.1.0-rc.6，社区报告），入口仅 `dsh web`（Web UI），
  **无非交互 CLI 模式**；官方预告兼容性破坏变更。
- 结论：MVP 不接入；`adapters/harness/dsh_harness.py` 留 stub + 本节备注。
  复查节奏：v1 前每周关注 deepseek-ai/deepseek-harness 的 CLI/server 能力。

## 遗留注意

- `--attach http://localhost:4096`（配合 `opencode serve`）可复用常驻实例加速批量执行，
  MVP 作为 `--serve` 可选项，默认直跑。
- 免费模型 cost 恒为 0：报告成本时区分 "harness 上报成本" 与 "pricing 表估算成本"。
