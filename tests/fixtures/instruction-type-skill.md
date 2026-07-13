# Auto Plan Review

One-Shot Sprint 自动流水线。单一入口，自动串联 Think → Plan → Build → Review → Ship 流程。

## Triggers

| Trigger Type | Phrases |
|--------------|---------|
| **中文** | "开发新功能", "实现 X", "start sprint", "一键开发" |
| **English** | "implement feature", "build X", "start sprint", "one-shot development" |

## 完整流程（默认无参数）

Sprint Flow: PREP → DESIGN → BUILD → VERIFY → SHIP → CLOSE

Phase 1/6: PREP — worktree isolation + sizing
Phase 2/6: DESIGN — brainstorming + autoplan + delphi-review
Phase 3/6: BUILD — ralph-loop + TDD + blind review
Phase 4/6: VERIFY — code walkthrough + QA
Phase 5/6: SHIP — PR creation + merge
Phase 6/6: CLOSE — user acceptance + cleanup

## Anti-Patterns

- MUST NOT skip the design phase
- MUST NOT merge without user acceptance
- NEVER modify eval cases after Phase 2 execution begins
- Do NOT bypass the Delphi consensus gate

## 参数说明

| 参数 | 作用 |
|------|------|
| --stop-at <phase> | 执行到指定 Phase 后停止 |
| --resume-from <phase> | 从指定 Phase 恢复 |
| --no-isolate | 跳过 git worktree 隔离 |

## Security Notes

This skill does not execute any destructive commands. All operations are read-only or create new branches/worktrees.

## Permissions

- Read access to project files
- Write access to create branches and worktrees
- Git operations (branch, checkout, worktree)

## Scope

This skill orchestrates the sprint workflow. It does NOT implement features directly, but coordinates the planning, building, and shipping phases.
