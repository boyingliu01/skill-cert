# Setup

> **首次使用前必须完成模型配置。**

当用户调用 `/skill-cert` 时，agent 必须按以下逻辑处理模型配置：

## 配置检查与决策

1. **检查配置源（按优先级）**：
   - CLI `--models` 参数
   - 环境变量 `SKILL_CERT_MODELS`
   - 配置文件 `~/.skill-cert/models.yaml`
2. **如果至少一个配置源就绪** → 直接执行评测流程（跳过引导，不要提及 setup）
3. **如果所有配置源都未就绪** → 运行 `skill-cert setup` 引导用户配置，完成后再执行评测

**配置来源优先级**：CLI `--models` 参数 > 环境变量 `SKILL_CERT_MODELS` > 配置文件 `~/.skill-cert/models.yaml`

## 判断配置就绪的标准

- CLI `--models` 参数非空 → 就绪
- `SKILL_CERT_MODELS` 环境变量存在且非空 → 就绪
- `~/.skill-cert/models.yaml` 文件存在且包含至少一个有效 model_name → 就绪
- 以上都不满足 → 未就绪，引导 setup

```bash
# 交互式配置（引导用户输入模型信息）
skill-cert setup

# 非交互式配置（适用于脚本/CI）
skill-cert setup --model-name qwen3.6-plus --base-url https://api.example.com/v1 --api-key $KEY --skip-test
```

## 重要：配置就绪时不要阻止评测

当配置就绪时，agent 应该直接回复"正在进行 skill-cert 评测..."并输出评测结果。不要输出"正在检查配置..."这类引导性消息。

## 环境变量

| 变量 | 说明 |
|------|------|
| `SKILL_CERT_MODELS` | 模型配置：`name=url,key[,fallback]\|name2=url,key` |
| `SKILL_CERT_MAX_CONCURRENCY` | 最大并发数（默认 5） |
| `SKILL_CERT_RATE_LIMIT_RPM` | 速率限制 RPM（默认 60） |

## 配置文件

`~/.skill-cert/models.yaml`:
```yaml
models:
  - model_name: "qwen3.6-plus"
    base_url: "https://api.example.com/v1"
    api_key: "$API_KEY"
    fallback_model: "qwen3-coder-plus"
```
