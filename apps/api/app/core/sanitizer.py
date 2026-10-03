"""零依赖 HTML 白名单清洗器 —— 逐条对齐 Java 版 `util/HtmlSanitizer`。

纵深防御的第二道（第一道是前端渲染时的 sanitize.js）。
入库前过滤的意义：将来若有别的消费端（App / 导出 / 第三方接口）
直接从库里读 HTML 渲染，也不会把带毒内容带出去。

策略（顺序不能变）：
    1. 危险容器连同内容整块删除
    2. 删除残留的孤立危险标签
    3. 删除注释
    4. 逐个标签做白名单过滤，白名单外的「拆壳保留文字」
    5. 属性白名单 + 剥离 on* 事件属性
    6. href/src 走协议白名单，挡掉 javascript: / data: / vbscript:
"""

from __future__ import annotations

import re

ALLOWED_TAGS: frozenset[str] = frozenset({
    "p", "br", "hr", "strong", "b", "em", "i", "u", "s", "del", "ins", "sub", "sup",
    "code", "pre", "blockquote", "ul", "ol", "li",
    "h1", "h2", "h3", "h4", "h5", "h6",
    "a", "span", "div",
    "table", "thead", "tbody", "tfoot", "tr", "th", "td",
    "img",
})

ALLOWED_ATTRS: dict[str, frozenset[str]] = {
    "a": frozenset({"href", "title", "target", "rel"}),
    "img": frozenset({"src", "alt", "title", "width", "height"}),
    "td": frozenset({"colspan", "rowspan"}),
    "th": frozenset({"colspan", "rowspan"}),
    "*": frozenset({"class"}),
}

_SAFE_URL = re.compile(r"^(https?://|mailto:|tel:|/|\./|\.\./|#)", re.IGNORECASE)

_DANGEROUS = "script|style|iframe|object|embed|svg|math|noscript|template|applet"

DROP_WITH_CONTENT = re.compile(rf"<({_DANGEROUS})\b[^>]*>.*?</\1\s*>", re.IGNORECASE | re.DOTALL)

DROP_TAG_ONLY = re.compile(rf"<({_DANGEROUS})\b[^>]*/?>", re.IGNORECASE | re.DOTALL)

COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)

TAG = re.compile(r"<(/?)([a-zA-Z][a-zA-Z0-9]*)((?:[^>\"']|\"[^\"]*\"|'[^']*')*)>")

ATTR = re.compile(r"([a-zA-Z_:][-a-zA-Z0-9_:.]*)(?:\s*=\s*(\"[^\"]*\"|'[^']*'|[^\s\"'>]+))?")

_CONTROL_CHARS = re.compile(r"[\x00-\x20]")


def sanitize(html: str | None) -> str | None:
    """清洗 HTML 片段。入参为 None 时原样返回 None。"""
    if html is None or html == "":
        return html

    s = DROP_WITH_CONTENT.sub("", html)
    s = DROP_TAG_ONLY.sub("", s)
    s = COMMENT.sub("", s)

    def _replace(m: re.Match[str]) -> str:
        slash, tag, raw_attrs = m.group(1), m.group(2).lower(), m.group(3) or ""
        if tag not in ALLOWED_TAGS:
            return ""  # 拆壳保留文字
        if slash:
            return f"</{tag}>"
        return f"<{tag}{clean_attributes(tag, raw_attrs)}>"

    return TAG.sub(_replace, s)


def clean_attributes(tag: str, raw_attrs: str) -> str:
    allowed = ALLOWED_ATTRS.get(tag, frozenset())
    common = ALLOWED_ATTRS["*"]

    out: list[str] = []
    has_target = False

    for m in ATTR.finditer(raw_attrs):
        name = m.group(1).lower()
        raw_value = m.group(2)

        if name.startswith("on"):  # on* 事件属性一律丢弃
            continue
        if name not in allowed and name not in common:
            continue

        value = unquote(raw_value)
        if name in ("href", "src") and not is_safe_url(value):
            continue

        if name == "target":
            has_target = True
        if raw_value is not None:
            out.append(f' {name}="{escape_attr(value)}"')
        else:
            out.append(f" {name}")

    # 外链统一补 rel，防止 window.opener 反向控制
    if tag == "a":
        out.append(' rel="noopener noreferrer"')
        if not has_target:
            out.append(' target="_blank"')
    return "".join(out)


def unquote(value: str | None) -> str:
    if value is None:
        return ""
    v = value.strip()
    if len(v) >= 2 and (
        (v.startswith('"') and v.endswith('"')) or (v.startswith("'") and v.endswith("'"))
    ):
        v = v[1:-1]
    return v


def escape_attr(value: str) -> str:
    return (
        value.replace("&", "&amp;")
        .replace('"', "&quot;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def is_safe_url(value: str | None) -> bool:
    """协议白名单。先去控制字符再判，防 `java\\nscript:` 这类绕过。"""
    if value is None or not value.strip():
        return False
    cleaned = _CONTROL_CHARS.sub("", value).lower()
    if cleaned.startswith(("javascript:", "data:", "vbscript:")):
        return False
    return _SAFE_URL.match(value.strip()) is not None
