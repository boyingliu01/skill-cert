---
name: harness-taskgen
version: 1.0.0
updated: 2026-08-23
---

# Harness 评测任务生成器

你是 skill 评测专家。基于以下 skill 定义，生成恰好 {task_count} 个评测任务，每个任务附带隐藏评分标准（rubric）。这些任务将交给 coding agent 在空沙箱中非交互完成（安装 skill 与不安装 skill 各跑一次），用于测量 skill 带来的真实增量。

## Skill 定义

**name**: {skill_name}

**description**: {skill_description}

**SKILL.md 全文**:

```markdown
{skill_content}
```

## 生成要求

1. 任务必须可由 coding agent 在空沙箱目录中非交互完成，最终回复文本即产出
2. 任务应覆盖 skill 声称的核心场景；部分任务让未加载 skill 的 agent 也能部分完成（这样才能测出 instruction-following 增量），部分任务只有遵循 skill 才可能达标
3. 每个任务可定义 input_files（path 为沙箱内相对路径），会在执行前写入沙箱；无输入文件则留空数组
4. rubric 分两个维度：
   - `task_completion`：任务完成质量的客观标准（与 skill 无关，2-4 条）
   - `instruction_following`：是否遵循 skill 规定的流程/格式/约束（从 SKILL.md 派生，2-4 条，with-skill 条件应显著更优）
5. criterion 必须可由第三方依据最终回复与轨迹客观评判，避免主观措辞（如"优雅的""高质量的"）
6. points 为 1-3 的整数，反映该条重要性
7. **严禁泄漏**：任务 description 只描述"做什么"，不得出现 rubric 措辞、skill 规定的格式名、步骤名或检查点原文
8. description 使用用户视角的自然语言，像真实用户会发出的请求

## 输出格式（严格 JSON 对象，禁止输出任何其他内容）

```json
{
  "leakage_check": "对每个任务自检 description 是否泄漏 rubric 措辞，结论一句话",
  "tasks": [
    {
      "id": "task-1",
      "description": "用户视角的任务描述",
      "input_files": [{"path": "data.txt", "content": "..."}],
      "rubrics": {
        "task_completion": [
          {"id": "task-1-tc1", "criterion": "客观可判的完成标准", "points": 2}
        ],
        "instruction_following": [
          {"id": "task-1-if1", "criterion": "源自 skill 的流程/格式要求", "points": 3}
        ]
      }
    }
  ]
}
```
