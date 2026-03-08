"""
generator.py
============
Citește din SQLite și regenerează HTML-ul pentru main.article-content.

Utilizare:
    python generator.py --db guide.db --slug cookbook-cod-recomandari-ai --out output.html
    python generator.py --db guide.db  # generează primul slug găsit
"""

import argparse
import json
import sqlite3
import sys
from pathlib import Path
from html import unescape


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

def open_db(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def get_page(conn, slug: str | None):
    if slug:
        return conn.execute("SELECT * FROM pages WHERE slug=?", (slug,)).fetchone()
    return conn.execute("SELECT * FROM pages ORDER BY id LIMIT 1").fetchone()


def get_sections(conn, page_id: int):
    return conn.execute(
        "SELECT * FROM sections WHERE page_id=? ORDER BY sort_order",
        (page_id,)
    ).fetchall()


def get_blocks(conn, section_id: int):
    return conn.execute(
        "SELECT * FROM blocks WHERE section_id=? ORDER BY sort_order",
        (section_id,)
    ).fetchall()


def get_elements(conn, block_id: int):
    return conn.execute(
        "SELECT * FROM elements WHERE block_id=? ORDER BY sort_order",
        (block_id,)
    ).fetchall()


# ---------------------------------------------------------------------------
# Render helpers
# ---------------------------------------------------------------------------

LANG_LABELS = {
    "python": "Python",
    "sql": "SQL",
    "javascript": "JavaScript",
    "json": "JSON",
    "yaml": "YAML",
    "bash": "Bash",
    "text": "",
}

CALLOUT_CLASSES = {
    "build":      "callout callout--build",
    "managed":    "callout callout--managed",
    "teal":       "callout callout--teal",
    "cream":      "callout callout--cream",
    "blue":       "callout callout--blue",
    "default":    "callout",
    "conclusion": "callout callout--conclusion",
}

CALLOUT_ICONS = {
    "build":   '<i class="fa-regular fa-gear"></i>',
    "managed": '<i class="fa-regular fa-cloud"></i>',
}


def h(text: str) -> str:
    """Escape HTML entities (pentru text pur; pentru innerHTML lăsăm as-is)."""
    return (text or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def render_heading(num: str, supra: str, title: str, level: int = 2,
                   anchor_id: str = None) -> str:
    parts = []
    if anchor_id:
        parts.append(f'<header class="guide-heading" id="{anchor_id}">')
    else:
        parts.append('<header class="guide-heading">')

    parts.append('<div class="guide-heading__top">')
    if supra:
        parts.append(f'<div class="guide-heading__supra">{h(supra)}</div>')
    if num:
        parts.append(f'<a class="guide-heading__num" href="#intro">{h(num)}</a>')
    parts.append("</div>")

    hl = max(1, min(6, level))
    parts.append(f'<h{hl} class="guide-heading__title">{h(title)}</h{hl}>')
    parts.append("</header>")
    return "\n".join(parts)


def render_toc(block) -> str:
    items = json.loads(block["content"] or "[]")
    lines = ['<nav class="guide-toc" aria-label="Cuprins">']
    lines.append(f'<h2 class="toc-title">{h(block["title"] or "Cuprins")}</h2>')
    lines.append('<ol class="toc-list">')
    for item in items:
        tags_html = ""
        if item.get("tags"):
            tags_html = " ".join(
                f'<span class="tag">{h(t)}</span>' for t in item["tags"]
            )
        lines.append(
            f'<li class="toc-item">'
            f'<a href="{item["href"]}" class="toc-link">'
            f'<span class="toc-num">{h(item["num"])}</span>'
            f'<span class="toc-text">{h(item["text"])}</span>'
            f'</a>{tags_html}</li>'
        )
    lines.append("</ol></nav>")
    return "\n".join(lines)


def render_callout(block, elements) -> str:
    variant = block["variant"] or "default"
    css = CALLOUT_CLASSES.get(variant, "callout")
    icon = CALLOUT_ICONS.get(variant, "")
    title = block["title"] or ""
    content = block["content"] or ""

    lines = [f'<div class="{css}">']
    # Conținutul innerHTML include deja titlul h4, deci nu-l duplicăm
    lines.append(content)
    lines.append("</div>")
    return "\n".join(lines)


def render_paragraph(block) -> str:
    content = block["content"] or ""
    return f"<p>{content}</p>"


def render_list(block, elements, ordered: bool = False) -> str:
    tag = "ol" if ordered else "ul"
    lines = [f"<{tag}>"]
    for e in elements:
        lines.append(f"<li>{e['content'] or ''}</li>")
    lines.append(f"</{tag}>")
    return "\n".join(lines)


def render_code_example(block, elements) -> str:
    title = block["title"] or ""
    lines = ['<section class="code-example">']
    if title:
        lines.append(f"<h4>{h(title)}</h4>")

    intro_items = [e for e in elements if e["element_type"] == "list_item"]
    note_items = [e for e in elements if e["element_type"] == "note_item"]
    snippets = [e for e in elements if e["element_type"] == "code_snippet"]

    for item in intro_items:
        lines.append(f"<p>{item['content'] or ''}</p>")

    for snippet in snippets:
        extra = json.loads(snippet["extra"]) if snippet["extra"] else {}
        lang = extra.get("language", "text")
        lang_label = LANG_LABELS.get(lang, lang.upper())
        summary = snippet["label"] or ""

        lines.append('<details class="code-block">')
        if summary:
            lines.append(f'<summary class="code-block__summary">{h(summary)}</summary>')
        if lang_label:
            lines.append(f'<div class="code-lang-label">{lang_label}</div>')
        code_content = snippet["content"] or ""
        lines.append(f'<pre><code class="language-{lang}">{h(code_content)}</code></pre>')
        lines.append("</details>")

    if note_items:
        lines.append('<details class="code-notes">')
        lines.append('<summary class="code-notes__summary">Note</summary>')
        lines.append("<ul>")
        for note in note_items:
            lines.append(f"<li>{note['content'] or ''}</li>")
        lines.append("</ul>")
        lines.append("</details>")

    lines.append("</section>")
    return "\n".join(lines)


def render_link_ref(block) -> str:
    href = block["anchor_id"] or "#"
    content = block["content"] or ""
    return (
        f'<p class="link-ref">'
        f'<a href="{href}">'
        f'<i class="fa-solid fa-hand-back-point-right"></i> {content}'
        f'</a></p>'
    )


def render_summary_box(block, elements) -> str:
    title = block["title"] or "Pe scurt"
    lines = ['<div class="summary-box summary-box--teal">']
    lines.append(f"<h3>{h(title)}</h3>")
    lines.append("<ul>")
    for e in elements:
        lines.append(f"<li>{e['content'] or ''}</li>")
    lines.append("</ul>")
    lines.append("</div>")
    return "\n".join(lines)


def render_faq_item(block, elements) -> str:
    title = block["title"] or ""
    answer = block["content"] or ""
    return (
        f'<div class="faq-item">'
        f'<div class="faq-question"><h4>{h(title)}</h4></div>'
        f'<div class="faq-answer">{answer}</div>'
        f"</div>"
    )


def render_chapter_card(block, elements) -> str:
    num = block["heading_num"] or ""
    title = block["title"] or ""
    desc = block["content"] or ""
    link_html = ""
    for e in elements:
        if e["element_type"] == "link":
            link_html = f'<a href="{e["href"] or "#"}" class="chapter-card__link">{h(e["label"] or "")}</a>'
    return (
        f'<div class="chapter-card">'
        f'<div class="chapter-card__num">{h(num)}</div>'
        f'<div class="chapter-card__title">{h(title)}</div>'
        f'<div class="chapter-card__desc">{desc}</div>'
        f'{link_html}'
        f"</div>"
    )


# ---------------------------------------------------------------------------
# Render bloc (dispatcher)
# ---------------------------------------------------------------------------

def render_block(block, elements) -> str:
    bt = block["block_type"]

    if bt == "paragraph":
        return render_paragraph(block)
    if bt == "toc":
        return render_toc(block)
    if bt == "callout":
        return render_callout(block, elements)
    if bt == "code_example":
        return render_code_example(block, elements)
    if bt in ("unordered_list", "ordered_list"):
        return render_list(block, elements, ordered=(bt == "ordered_list"))
    if bt == "link_ref":
        return render_link_ref(block)
    if bt == "summary_box":
        return render_summary_box(block, elements)
    if bt == "faq_item":
        return render_faq_item(block, elements)
    if bt == "chapter_card":
        return render_chapter_card(block, elements)

    # fallback — afișăm conținutul brut
    content = block["content"] or ""
    if content.strip():
        return f"<div>{content}</div>"
    return ""


# ---------------------------------------------------------------------------
# Render secțiune
# ---------------------------------------------------------------------------

def render_section(section, conn) -> str:
    parts = []
    st = section["section_type"]
    anchor = section["anchor_id"] or ""
    heading_num = section["heading_num"] or ""
    heading_supra = section["heading_supra"] or ""
    heading_title = section["heading_title"] or ""
    heading_level = section["heading_level"] or 2

    # Heading pentru secțiunile cu titlu (nu intro/hero)
    if st not in ("intro", "hero", "toc") and heading_title:
        parts.append(render_heading(
            heading_num, heading_supra, heading_title,
            heading_level, anchor or None
        ))
    elif st == "faq":
        parts.append(f'<section class="faq-section">')
        parts.append(f'<h2 class="faq-section__title">{h(heading_title)}</h2>')

    elif st == "chapter_nav":
        parts.append(f'<section class="chapter-nav">')
        parts.append(f'<h2>{h(heading_title)}</h2>')
        parts.append('<div class="chapter-grid">')

    # Blocuri
    blocks = get_blocks(conn, section["id"])
    for block in blocks:
        elements = get_elements(conn, block["id"])
        rendered = render_block(block, elements)
        if rendered:
            parts.append(rendered)

    # Închidere taguri speciale
    if st == "faq":
        parts.append("</section>")
    elif st == "chapter_nav":
        parts.append("</div></section>")

    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Render pagină completă
# ---------------------------------------------------------------------------

def render_page(conn, slug: str | None = None) -> str:
    page = get_page(conn, slug)
    if not page:
        sys.exit(f"Pagina cu slug='{slug}' nu a fost găsită în DB.")

    sections = get_sections(conn, page["id"])

    parts = ['<main class="article-content">']

    # Hero / meta
    if page["chapter_num"] or page["title"]:
        parts.append(
            f'<div class="guide-badges">'
            f'<span class="update-badge"><strong>Data actualizării:</strong> {h(page["updated_at"])}</span>'
            f'</div>'
        )
        parts.append(
            f'<header class="guide-heading">'
            f'<div class="hero-section">'
            f'<div class="hero-pill">CAPITOLUL <span class="chapter-number">{h(page["chapter_num"])}</span></div>'
            f'<div class="hero-supra">{h(page["chapter_label"])}</div>'
            f'<h1 class="hero-headline">{page["title"] or ""}</h1>'
            f'</div>'
            f'</header>'
        )

    for section in sections:
        rendered = render_section(section, conn)
        if rendered.strip():
            parts.append(rendered)

    parts.append("</main>")
    return "\n\n".join(parts)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generator HTML din SQLite")
    parser.add_argument("--db", default="guide.db", help="Calea către baza de date SQLite")
    parser.add_argument("--slug", default=None, help="Slug-ul paginii (dacă există mai multe)")
    parser.add_argument("--out", default=None, help="Fișier de output HTML (implicit: stdout)")
    args = parser.parse_args()

    conn = open_db(args.db)
    html = render_page(conn, args.slug)
    conn.close()

    if args.out:
        Path(args.out).write_text(html, encoding="utf-8")
        print(f"[generator] HTML generat în: {args.out}")
    else:
        print(html)