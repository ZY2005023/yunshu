"""文档导入解析 —— 把上传的 txt / md / docx / pdf 转成文章草稿。

产品形态（与「AI 管理员」的协作方式）：
    上传 → 解析出标题与正文（HTML）→ **预填到编辑器** → 管理员校对后保存。
刻意不直接入库：① 文档解析难免有格式噪音，直接入库会污染 RAG 检索质量；
② 心理类内容上线前本来就该人审一遍。

设计要点：
· docx / pypdf 延迟导入 —— 没用到导入功能的环境不为它们付启动成本；
· 中文文本编码先试 UTF-8 再兜底 GBK —— Windows 记事本存的中文 txt 大量是 GBK，
  只按 UTF-8 解会得到一片替换符（真实场景，不是边角料）；
· 产出的 HTML 最后统一过 `sanitizer.sanitize()`（纵深防御，与文章入库同一口径）；
· 解析出内容过少（< 10 字）视为失败并说明原因 —— 扫描件 PDF 没有文字层、
  加密文档解不开，这两种要给用户看得懂的提示，而不是丢一个空编辑器过去。
"""

from __future__ import annotations

import html as html_mod
import io
import re

from app.core.config import settings
from app.core.errors import FILE_SIZE_EXCEEDED, FILE_TYPE_NOT_SUPPORTED
from app.core.exceptions import BusinessError
from app.core.sanitizer import sanitize

ALLOWED_IMPORT_EXTS: tuple[str, ...] = ("txt", "md", "docx", "pdf")

# 少于这个字数视为解析失败（空文件 / 扫描件 / 加密文档）
MIN_TEXT_LENGTH = 10
TITLE_MAX = 200


# ===========================================================================
# 入口
# ===========================================================================


def parse_document(filename: str | None, raw: bytes) -> dict:
    """解析上传的文档，返回 {title, content, charCount, paragraphCount, warnings}。

    Raises:
        BusinessError: 类型不支持 / 超大小 / 内容为空 / 解析不出有效文字
    """
    max_size = settings.file.max_size
    if len(raw) > max_size:
        raise BusinessError(FILE_SIZE_EXCEEDED, f"文件超过 {max_size // 1024 // 1024}MB 上限")
    if not raw:
        raise BusinessError("文件内容为空")

    ext = _ext_of(filename)
    if ext not in ALLOWED_IMPORT_EXTS:
        raise BusinessError(
            FILE_TYPE_NOT_SUPPORTED, "知识库导入仅支持 txt / md / docx / pdf"
        )

    warnings: list[str] = []

    if ext in ("txt", "md"):
        text, decode_warnings = _decode_text(raw)
        warnings.extend(decode_warnings)
        content = _md_to_html(text) if ext == "md" else _text_to_html(text)
    elif ext == "docx":
        text = _docx_text(raw, warnings)
        content = _text_to_html(text)
    else:  # pdf
        text = _pdf_text(raw, warnings)
        content = _text_to_html(text)

    content = sanitize(content) or ""
    plain = _plain_of(content)
    if len(plain) < MIN_TEXT_LENGTH:
        raise BusinessError(
            "没能从文件里解析出有效文字 —— 若是扫描件 PDF（整页是图片）或加密文档，"
            "本系统暂不支持；可换成 Word / txt 或手动录入"
        )

    paragraph_count = content.count("<p>") + content.count("<li>") + content.count("<h")
    return {
        "title": _title_of(filename, plain),
        "content": content,
        "char_count": len(plain),
        "paragraph_count": max(1, paragraph_count),
        "warnings": warnings,
    }


# ===========================================================================
# 各格式解析
# ===========================================================================


def _ext_of(filename: str | None) -> str:
    if not filename or "." not in filename:
        return ""
    return filename.rsplit(".", 1)[1].strip().lower()


def _decode_text(raw: bytes) -> tuple[str, list[str]]:
    """UTF-8 优先，GBK 兜底（Windows 记事本中文文件的高频真实现状）。"""
    for enc in ("utf-8-sig", "utf-8"):
        try:
            return raw.decode(enc), []
        except UnicodeDecodeError:
            continue
    try:
        return raw.decode("gbk"), ["文件不是 UTF-8 编码，已按 GBK（常见于 Windows 记事本）解析，请校对"]
    except UnicodeDecodeError:
        return raw.decode("utf-8", errors="replace"), ["文件编码无法识别，部分字符已替换为 �，请仔细校对"]


def _docx_text(raw: bytes, warnings: list[str]) -> str:
    from docx import Document  # 延迟导入：不用导入功能就不付启动成本

    try:
        doc = Document(io.BytesIO(raw))
    except Exception as exc:  # noqa: BLE001 —— 加密/损坏的 docx
        raise BusinessError(f"无法读取这份 Word 文档（可能已加密或损坏）：{exc}") from exc

    parts: list[str] = [p.text.strip() for p in doc.paragraphs if p.text.strip()]
    # 表格里的内容常是正文的一部分（学校材料尤其常见），一并提取
    for table in doc.tables:
        for row in table.rows:
            cells = [c.text.strip() for c in row.cells if c.text.strip()]
            if cells:
                parts.append(" ｜ ".join(cells))
    if doc.tables:
        warnings.append(f"文档含 {len(doc.tables)} 个表格，已按行转为文本，请校对排版")
    return "\n\n".join(parts)


def _pdf_text(raw: bytes, warnings: list[str]) -> str:
    from pypdf import PdfReader  # 延迟导入

    try:
        reader = PdfReader(io.BytesIO(raw))
        pages = [page.extract_text() or "" for page in reader.pages]
    except Exception as exc:  # noqa: BLE001 —— 加密/损坏的 pdf
        raise BusinessError(f"无法读取这份 PDF（可能已加密或损坏）：{exc}") from exc

    text = "\n\n".join(p.strip() for p in pages if p.strip())
    if len(re.sub(r"\s", "", text)) < MIN_TEXT_LENGTH:
        # 交给入口的统一校验去报错（带扫描件提示），这里补一条页数信息
        warnings.append(f"PDF 共 {len(reader.pages)} 页，未提取到文字层")
    elif len(reader.pages) > 1:
        warnings.append(f"PDF 共 {len(reader.pages)} 页，已合并为一个草稿，请校对分页处的衔接")
    return text


# ===========================================================================
# 文本 → HTML
# ===========================================================================


def _text_to_html(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    blocks = [b.strip() for b in re.split(r"\n{2,}", text) if b.strip()]
    # 很多 txt 是每行一段、没有空行 —— 直接当一个超长段落会很难读，按行拆开
    if len(blocks) == 1 and blocks[0].count("\n") > 2:
        blocks = [line.strip() for line in blocks[0].split("\n") if line.strip()]
    return "\n".join(
        f"<p>{html_mod.escape(block, quote=False).replace(chr(10), '<br>')}</p>"
        for block in blocks
    )


def _md_to_html(md: str) -> str:
    """极简 Markdown → HTML。与前端 MarkdownRenderer 同一口径的先转义后转换，
    最后还会过一遍 sanitize() 白名单（调用方做）。"""
    s = html_mod.escape(md.replace("\r\n", "\n").replace("\r", "\n"), quote=False)

    # 围栏代码块（先处理，避免内部被行内规则改写）
    s = re.sub(r"```[^\n]*\n(.*?)```", lambda m: f"<pre>{m.group(1)}</pre>", s, flags=re.S)
    s = re.sub(r"`([^`\n]+)`", r"<code>\1</code>", s)
    s = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", s)
    s = re.sub(r"(?<![*\w])\*([^*\n]+)\*(?!\*)", r"<em>\1</em>", s)

    for level in range(6, 0, -1):  # ## 在前，# 在后，避免短前缀先吃掉长前缀
        s = re.sub(
            rf"^{'#' * level} (.+)$", rf"<h{level}>\1</h{level}>", s, flags=re.M
        )

    s = re.sub(r"^> (.+)$", r"<blockquote>\1</blockquote>", s, flags=re.M)
    s = re.sub(r"^[-*] (.+)$", r"<li>\1</li>", s, flags=re.M)
    s = re.sub(r"(<li>.*?</li>\n?)+", lambda m: f"<ul>{m.group(0).strip()}</ul>\n", s, flags=re.S)
    s = re.sub(r"^\d+\. (.+)$", r"<li>\1</li>", s, flags=re.M)

    blocks = [b.strip() for b in re.split(r"\n{2,}", s) if b.strip()]
    out: list[str] = []
    for block in blocks:
        if block.startswith(("<h", "<ul", "<pre", "<blockquote", "<li")):
            out.append(block)
        else:
            out.append(f"<p>{block.replace(chr(10), '<br>')}</p>")
    return "\n".join(out)


def _plain_of(html: str) -> str:
    """HTML → 纯文本（用于字数统计与有效性校验）。"""
    text = re.sub(r"<[^>]+>", "", html)
    text = html_mod.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def _title_of(filename: str | None, fallback_text: str) -> str:
    if filename:
        base = filename.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
        if "." in base:
            base = base.rsplit(".", 1)[0]
        title = re.sub(r"[_\-]+", " ", base).strip()
        if title:
            return title[:TITLE_MAX]
    return (fallback_text[:TITLE_MAX] or "未命名文档").strip()
