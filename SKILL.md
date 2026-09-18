---
name: website-exploration
description: 用 Playwright 逐步探索用户明确授权的网站，自动记录页面、导航与交互证据，生成中文探索报告（Markdown、JSON、截图，可选 Word 功能清单）。仅限同域探索，拦截支付、删除、注销等危险操作并自动脱敏凭据，遇验证码或 MFA 停止。用于「探索这个网站」「梳理网站功能清单」「生成网站调研报告」「网站走查」「website exploration」「site walkthrough」等请求。
---

# Website Exploration

使用 Skill 内的脚本执行浏览器动作。

## 快速开始

首次使用先安装依赖并启动 Runtime：

```powershell
python scripts/bootstrap.py
python scripts/runtime.py
```

创建会话时必须指定用户输出目录：

```powershell
python scripts/tool.py open_website --url "https://example.com" --output-dir ".\reports" --scope section
```

后续工具使用返回的 `sessionId`：

```powershell
python scripts/tool.py observe_page --session-id <sessionId>
python scripts/tool.py get_navigation_map --session-id <sessionId>
python scripts/tool.py click_element --session-id <sessionId> --element-id 12
```

工具命令包括 `open_website`, `observe_page`, `click_element`, `fill_element`, `inspect_form`, `login`, `submit_form`, `visit_url`, `go_back`, `get_navigation_map`, `return_to_base`, `get_exploration_log`, `take_screenshot`, `finish_exploration`, `session_status` 和 `close_session`。第一次调用 `tool.py` 会自动启动 Runtime。

可选参数：`open_website` 支持 `--config-path` 加载登录、导航和安全配置，支持 `--system-name` 设置报告名称。配置含 `loginUrl`、`username`、`password` 和 `loginSelectors` 时可调用 `login`。完成后 `finish_exploration` 会生成 Markdown `report.md`、JSON `pages.json`/`events.json`、页面证据与截图，以及 Word 功能清单 `function-list.docx`（依赖可用时）。

`open_website` 必须明确指定探索范围：`--scope current|section|subtree|site`，或使用一个或多个 `--target "一级板块 > 二级板块"` 指定目标。未提供范围或目标时不会启动探索。`--max-pages` 与 `--max-actions` 为可选的用户自定义上限，未提供时不设固定页面数或动作数上限。

## 探索循环

1. `open_website`
2. `get_navigation_map`
3. `observe_page`
4. 阅读返回的页面文本和元素，决定下一步工具
5. 页面变化后必须重新 `observe_page`，不要复用旧 element ID
6. 需要时调用 `visit_url`、`go_back`、`fill_element` 或 `take_screenshot`
7. 导航模式为 cards 时，进入功能页后先 `return_to_base`
8. 接近页面数或动作数限制时调用 `get_exploration_log`
9. 完成后调用 `finish_exploration`

只访问起始 URL 同域页面。危险操作、支付、删除、注销、发布和真实敏感提交会被拦截。遇到验证码、MFA 或人工登录时停止并报告。

## 工具

`open_website`, `observe_page`, `click_element`, `fill_element`, `inspect_form`, `submit_form`, `visit_url`, `go_back`, `get_navigation_map`, `return_to_base`, `get_exploration_log`, `take_screenshot`, `finish_exploration`, `session_status`, `close_session`。

所有工具返回 JSON。报告、截图、页面证据和事件日志均写入创建会话时指定的 `outputDir`，不会写入 Skill 目录。
