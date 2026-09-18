from __future__ import annotations

import json
import re
from typing import Any

NAV_NOISE_WORDS = (
    "首页", "退出", "注销", "个人中心", "修改密码", "登录",
    "返回首页", "返回", "面包屑", "全部菜单", "收起", "展开",
)
BUTTON_OP_RULES: tuple[tuple[tuple[str, ...], str], ...] = (
    (("新增", "新建", "添加", "创建"), "新增"),
    (("编辑", "修改"), "编辑"),
    (("删除", "移除"), "删除"),
    (("查询", "搜索", "筛选"), "查询"),
    (("导出", "下载"), "导出"),
    (("导入", "上传"), "导入"),
    (("审核", "审批"), "审核"),
    (("查看", "详情", "预览"), "查看"),
)


def clean_page_text(raw: str, buttons: list[str]) -> str:
    if not raw:
        return ""
    text = raw
    for word in NAV_NOISE_WORDS:
        text = text.replace(word, "")
    for button in buttons:
        if button and len(button) < 10:
            text = text.replace(button, "")
    text = re.sub(r"Copyright.*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"备案号.*", "", text)
    text = re.sub(r"ICP.*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"©.*", "", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    lines = [line for line in text.splitlines() if line.strip()]
    return "\n".join(lines)[:600].strip()


def rule_description(buttons: list[str], has_table: bool, has_form: bool) -> str:
    lowered = [b.lower() for b in buttons]
    ops: list[str] = []
    for keywords, op in BUTTON_OP_RULES:
        if any(any(k in b for k in keywords) for b in lowered):
            ops.append(op)
    if has_table and "查询" not in ops:
        ops.insert(0, "查询")
    if not ops:
        ops = ["信息填写"] if has_form else ["浏览查看"]
    return f"可实现对相关数据{'、'.join(ops)}的功能。"


PROMPT_TEMPLATE = """你是软件检测机构的功能清单编写助手。根据页面探测证据，为每个页面生成一句规范的功能描述。
要求：句式为"可实现……的功能。"，概括该页面的核心业务能力，不超过60字，不要编造证据外的功能。

页面证据：
{pages_json}

只输出 JSON 数组，元素形如 {{"index": 1, "description": "可实现……的功能。", "confidence": 0.9}}，index 与输入序号一致。"""


def _strip_code_fence(text: str) -> str:
    return re.sub(r"^```(json)?|```$", "", text.strip(), flags=re.MULTILINE)


async def generate_descriptions(pages: list[dict], model: Any = None) -> None:
    for page in pages:
        if not page.get("functionDescription"):
            page["functionDescription"] = rule_description(
                page.get("buttons", []),
                bool(page.get("hasTable")),
                bool(page.get("hasForm")),
            )
            page.setdefault("descriptionConfidence", 0.5)
    if model is None or not pages:
        return
    digest = [
        {
            "index": page["id"],
            "name": page.get("name", ""),
            "moduleName": page.get("moduleName", ""),
            "buttons": page.get("buttons", []),
            "hasTable": page.get("hasTable", False),
            "hasForm": page.get("hasForm", False),
            "contentDigest": (page.get("contentDigest") or "")[:300],
        }
        for page in pages
    ]
    try:
        response = await model.ainvoke(
            PROMPT_TEMPLATE.format(pages_json=json.dumps(digest, ensure_ascii=False))
        )
        content = response.content if hasattr(response, "content") else str(response)
        if isinstance(content, list):
            content = "".join(
                block.get("text", "") for block in content if isinstance(block, dict)
            )
        payload = json.loads(_strip_code_fence(str(content)))
        by_index = {
            int(item["index"]): item
            for item in payload
            if isinstance(item, dict) and "index" in item
        }
        for page in pages:
            item = by_index.get(page["id"])
            if not item:
                continue
            description = str(item.get("description", "")).strip()
            if description:
                page["functionDescription"] = description
            try:
                confidence = float(item.get("confidence", 0.5))
            except (TypeError, ValueError):
                confidence = 0.5
            page["descriptionConfidence"] = min(1.0, max(0.0, confidence))
    except Exception:
        return
