# Changelog

## 1.1.0 - 2026-09-18 — 公开发布整理

面向"作为独立技能仓库公开发布"的整理版本。发布仓库：`weqi-pan/website-exploration`，目录页 `https://skills.sh/weqi-pan/website-exploration/website-exploration`。

### 新增

- `README.md` 重写：安装方式（`npx skills add weqi-pan/website-exploration`）、安全模型（授权要求、同域限制、危险操作拦截、凭据脱敏、本机 runtime）、登录配置示例、输出产物清单、依赖说明与测试命令。
- `SKILL.md` 描述改为中英双语并补齐触发词（「探索这个网站」「梳理网站功能清单」「website exploration」「site walkthrough」等）。
- `.gitattributes`（统一 LF）。
- `metadata.json` 扩充：license、capabilities、exit 语义、install 地址、运行时网络行为说明。

### 变更

- **依赖统一**：顶层 `requirements.txt` 改为引用 `scripts/requirements.txt`（`bootstrap.py` 的唯一依赖来源），消除三处声明不一致；移除未使用的 `python-dotenv`。
- **DOCX 导出可降级**：`docx_export.py` 的 `python-docx` 导入改为可选，缺失时 `finish_exploration` 返回 `docxPath: null` 并照常产出 Markdown/JSON 证据（此前缺依赖会导致 runtime 启动失败）。
- **移除未使用的 LLM 配置**：`ModelSettings`/`Settings`、`MissingConfigurationError` 与 `errors.py`（读取 `OPENAI_API_KEY` 等环境变量的代码无任何调用方），以及 `D:\reports` 之类的本机绝对路径示例。

### 安全

- 审查确认：无硬编码密钥；LLM/API key 配置为死代码并已移除；`safety.py` 对 URL 参数、`Authorization`/`Bearer`、键值对密钥统一脱敏；`login.py` 对账号掩码；runtime 仅绑定 `127.0.0.1`；输出只写用户指定的 `--output-dir`。

### 验证（2026-09-18）

- `python -m compileall -q scripts runtime tests` 通过；`pytest tests -q` 2 个测试通过。
- `ExplorationConfig.from_json` 加载登录/导航/拦截配置正常；`normalize_url` 正常。
- 无 BOM；无客户/内部信息残留。
