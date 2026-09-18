# Website Exploration

[![skills.sh](https://skills.sh/b/weqi-pan/website-exploration)](https://skills.sh/weqi-pan/website-exploration/website-exploration)

自包含的 Playwright 网站探索 Skill：在**用户明确授权**的前提下，逐步探索网站、记录页面与交互证据，并生成中文报告（Markdown、JSON、截图，可选 Word 功能清单）。

## 安装

```powershell
# 通过 skills CLI 安装
npx skills add weqi-pan/website-exploration

# 或直接克隆
git clone https://github.com/weqi-pan/website-exploration.git
cd website-exploration
```

## 快速开始

首次使用先安装依赖并启动 Runtime（在技能目录内执行）：

```powershell
python scripts/bootstrap.py
python scripts/runtime.py
```

`bootstrap.py` 会创建技能本地虚拟环境（`.venv/`）并下载 Chromium（约 150 MB，存放在 `.playwright-browsers/`），不污染全局 Python 环境。

创建会话时必须指定输出目录：

```powershell
python scripts/tool.py open_website --url https://example.com --output-dir .\reports --scope section
```

后续工具使用返回的 `sessionId`：

```powershell
python scripts/tool.py observe_page --session-id <sessionId>
python scripts/tool.py get_navigation_map --session-id <sessionId>
python scripts/tool.py click_element --session-id <sessionId> --element-id 12
```

完成后 `finish_exploration` 生成报告与证据（见下文"输出产物"）。

## 安全模型

这个技能只为**授权的、以产出文档为目的**的网站探索设计：

- 只访问起始 URL 的**同域**页面；支持 `--scope current|section|subtree|site` 或 `--target "一级板块 > 二级板块"` 精确圈定范围，未提供范围不会开始探索。
- **危险操作拦截**：支付、删除、注销、发布、权限绕过、验证码绕过和真实敏感提交会被拒绝。
- **凭据脱敏**：URL 查询串中的 `token` / `api_key` / `password` 等参数、`Authorization` / `Bearer` 头、键值对形式的密钥，在证据与报告中统一替换为 `[REDACTED]`；账号在证据中掩码显示。
- **验证码 / MFA 即停**：遇到验证码、多因素认证或需要人工登录时停止并报告，不做绕过。
- **Runtime 只绑定本机**：`127.0.0.1`，不对外监听；报告、截图与日志只写入用户指定的 `--output-dir`，不写入技能目录。

## 登录与配置（可选）

需要登录时，把配置写成 JSON 文件（只放在本地，凭据会脱敏后才进入证据）：

```json
{
  "name": "示例系统",
  "loginUrl": "https://example.com/login",
  "username": "demo",
  "password": "……",
  "navMode": "cards",
  "loginSelectors": { "usernameInput": "#username", "passwordInput": "#password", "submitButton": "#submit" },
  "allowFormSubmit": false,
  "blockedActionKeywords": ["删除", "注销"]
}
```

```powershell
python scripts/tool.py open_website --url https://example.com --output-dir .\reports --config-path .\config.json --system-name "示例系统"
```

## 工具

`open_website`、`observe_page`、`click_element`、`fill_element`、`inspect_form`、`login`、`submit_form`、`visit_url`、`go_back`、`get_navigation_map`、`return_to_base`、`get_exploration_log`、`take_screenshot`、`finish_exploration`、`session_status`、`close_session`。全部返回 JSON；第一次调用 `tool.py` 会自动启动 Runtime。

## 输出产物

`finish_exploration` 后写入门户目录：

| 文件 | 说明 |
|---|---|
| `report.md` | 中文探索报告（Markdown） |
| `pages.json` / `events.json` | 页面与事件的结构化证据 |
| `screenshots/` | 页面截图 |
| `function-list.docx` | Word 功能清单（可选，缺 python-docx 时跳过） |

## 依赖

- Python >= 3.10；Playwright 1.61（`scripts/requirements.txt` 为唯一依赖清单，`bootstrap.py` 安装它）。
- `python-docx`：生成 Word 功能清单；缺失时自动跳过 DOCX 导出，不影响 Markdown/JSON 报告。
- 不需要 Office 或桌面浏览器安装包（Chromium 由 Playwright 管理）。

## 测试

```powershell
python -m pip install -r requirements-dev.txt
python -m pytest tests -q
```

## License

[MIT](LICENSE)
