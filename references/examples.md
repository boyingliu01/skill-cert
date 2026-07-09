# Usage Examples

## Basic single-model evaluation
```bash
skill-cert --skill path/to/SKILL.md --models "claude=https://api.openai.com/v1,$KEY" --output ./results/
```

## Multi-model drift detection
```bash
skill-cert --skill path/to/SKILL.md --models "m1=url,key|m2=url,key" --output ./results/
```

## Dialogue mode for orchestration skills
```bash
skill-cert --skill path/to/SKILL.md --mode dialogue --max-turns 10
```

## 命令行用法参考

```bash
# 单轮模式（默认）
skill-cert --skill /path/to/SKILL.md --models "m1=url,key|m2=url,key" --output ./results/

# 对话模式
skill-cert --skill /path/to/SKILL.md --mode dialogue --max-turns 10

# 重放模式
skill-cert --skill /path/to/SKILL.md --mode replay --session session.jsonl
```
