"""
scraper.py
==========
Parsează main.article-content din HTML-ul paginii și populează baza de date SQLite.

Utilizare:
    python scraper.py --html input.html --db guide.db
    python scraper.py --url https://www.opti.ro/ai-2026/... --db guide.db

Dependențe:
    pip install beautifulsoup4 requests
"""

import argparse
import json
import re
import sqlite3
import sys
from pathlib import Path

try:
    from bs4 import BeautifulSoup, Tag, NavigableString
except ImportError:
    sys.exit("Instalează: pip install beautifulsoup4")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def slug_from_url(url: str) -> str:
    return url.rstrip("/").split("/")[-1] or "page"


def inner_html(tag) -> str:
    """Returnează innerHTML-ul unui tag (string)."""
    if tag is None:
        return ""
    return "".join(str(c) for c in tag.children).strip()


def text_of(tag) -> str:
    if tag is None:
        return ""
    return tag.get_text(separator=" ").strip()


def detect_callout_variant(tag) -> str:
    classes = tag.get("class", [])
    cls_str = " ".join(classes)
    if "ais_scenario_box--blue" in cls_str or "scenario_box--blue" in cls_str:
        return "managed"
    if "s_newpar--cream" in cls_str:
        return "build"
    if "s_newpar--teal" in cls_str:
        return "teal"
    if "s_newpar" in cls_str:
        return "default"
    if "ais_scenario_box" in cls_str:
        return "blue"
    return "default"


def is_callout(tag) -> bool:
    classes = " ".join(tag.get("class", []))
    return any(k in classes for k in [
        "s_newpar", "ais_scenario_box", "s_newpar--cream",
        "s_newpar--teal", "ais_scenario_box--blue"
    ])


def is_code_block(tag) -> bool:
    return tag.name == "section" and "fig-container" in " ".join(tag.get("class", []))


def is_link_ref(tag) -> bool:
    classes = " ".join(tag.get("class", []))
    return tag.name == "p" and (
        "fa-hand-back-point-right" in str(tag) or
        "intralinking-box" in classes
    )


def extract_code_language(pre_tag) -> str:
    code = pre_tag.find("code")
    if code:
        for cls in code.get("class", []):
            for lang in ["python", "sql", "javascript", "json", "yaml", "java", "bash"]:
                if lang in cls.lower():
                    return lang
    return "text"


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

def init_db(db_path: str, schema_path: str = "schema.sql") -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    schema = Path(schema_path).read_text(encoding="utf-8")
    conn.executescript(schema)
    conn.commit()
    return conn


def insert_page(conn, slug, url, chapter_num, chapter_label, title, subtitle, updated_at) -> int:
    cur = conn.execute(
        """INSERT INTO pages (slug, url, chapter_num, chapter_label, title, subtitle, updated_at)
           VALUES (?,?,?,?,?,?,?)
           ON CONFLICT(slug) DO UPDATE SET
             url=excluded.url, chapter_num=excluded.chapter_num,
             chapter_label=excluded.chapter_label, title=excluded.title,
             subtitle=excluded.subtitle, updated_at=excluded.updated_at
        """,
        (slug, url, chapter_num, chapter_label, title, subtitle, updated_at),
    )
    conn.commit()
    # re-fetch id
    row = conn.execute("SELECT id FROM pages WHERE slug=?", (slug,)).fetchone()
    return row["id"]


def insert_section(conn, page_id, sort_order, anchor_id, section_type,
                   heading_num, heading_supra, heading_title, heading_level=2) -> int:
    cur = conn.execute(
        """INSERT INTO sections
           (page_id, sort_order, anchor_id, section_type, heading_num, heading_supra, heading_title, heading_level)
           VALUES (?,?,?,?,?,?,?,?)""",
        (page_id, sort_order, anchor_id, section_type,
         heading_num, heading_supra, heading_title, heading_level),
    )
    conn.commit()
    return cur.lastrowid


def insert_block(conn, section_id, sort_order, block_type, variant=None,
                 title=None, content=None, anchor_id=None,
                 heading_num=None, heading_supra=None) -> int:
    cur = conn.execute(
        """INSERT INTO blocks
           (section_id, sort_order, block_type, variant, title, content, anchor_id, heading_num, heading_supra)
           VALUES (?,?,?,?,?,?,?,?,?)""",
        (section_id, sort_order, block_type, variant, title, content, anchor_id, heading_num, heading_supra),
    )
    conn.commit()
    return cur.lastrowid


def insert_element(conn, block_id, sort_order, element_type,
                   content=None, href=None, label=None, extra=None) -> int:
    cur = conn.execute(
        """INSERT INTO elements (block_id, sort_order, element_type, content, href, label, extra)
           VALUES (?,?,?,?,?,?,?)""",
        (block_id, sort_order, element_type, content, href, label,
         json.dumps(extra) if extra else None),
    )
    conn.commit()
    return cur.lastrowid


# ---------------------------------------------------------------------------
# Parsare meta-informații pagină
# ---------------------------------------------------------------------------

def parse_page_meta(article: Tag) -> dict:
    meta = {
        "updated_at": "",
        "chapter_num": "",
        "chapter_label": "",
        "title": "",
        "subtitle": "",
    }

    badge = article.find(class_="ais_update_badge")
    if badge:
        strong = badge.find("strong")
        if strong:
            strong.decompose()
        meta["updated_at"] = badge.get_text(strip=True)

    hero = article.find(class_="ais_hero_section")
    if hero:
        num_tag = hero.find(class_="number_chapter")
        if num_tag:
            meta["chapter_num"] = num_tag.get_text(strip=True)
        supra = hero.find(class_="ais_hero_supra")
        if supra:
            meta["chapter_label"] = supra.get_text(strip=True)
        h1 = hero.find("h1")
        if h1:
            meta["title"] = h1.get_text(strip=True)
        pill = hero.find(class_="ais_hero_pill")
        if pill:
            meta["subtitle"] = pill.get_text(strip=True)

    return meta


# ---------------------------------------------------------------------------
# Parsare TOC
# ---------------------------------------------------------------------------

def parse_toc(toc_tag: Tag) -> list[dict]:
    """Extrage intrările din TOC ca listă de dict."""
    items = []
    for a in toc_tag.find_all("a", class_="toc-link"):
        num = a.find(class_="toc-num")
        text = a.find(class_="toc-text")
        tags_div = a.find_next_sibling("div", class_="tag-group")
        tags = []
        if tags_div:
            tags = [t.get_text(strip=True) for t in tags_div.find_all(class_="tag")]
        items.append({
            "num": num.get_text(strip=True) if num else "",
            "text": text.get_text(strip=True) if text else "",
            "href": a.get("href", ""),
            "tags": tags,
        })
    return items


# ---------------------------------------------------------------------------
# Parsare conținut principal
# ---------------------------------------------------------------------------

def parse_article(article: Tag, page_id: int, conn: sqlite3.Connection):
    """
    Iterează prin copiii direcți ai article și grupează conținutul pe secțiuni.
    O secțiune nouă începe la fiecare guide-heading H2/H3.
    """
    section_order = 0
    block_order = 0
    current_section_id = None

    def new_section(anchor_id, section_type, heading_num, heading_supra,
                    heading_title, heading_level=2):
        nonlocal section_order, block_order, current_section_id
        section_order += 1
        block_order = 0
        current_section_id = insert_section(
            conn, page_id, section_order,
            anchor_id, section_type,
            heading_num, heading_supra, heading_title, heading_level
        )

    def add_block(block_type, variant=None, title=None, content=None,
                  anchor_id=None, heading_num=None, heading_supra=None) -> int:
        nonlocal block_order
        block_order += 1
        return insert_block(
            conn, current_section_id, block_order,
            block_type, variant, title, content, anchor_id, heading_num, heading_supra
        )

    # Creăm o secțiune implicită pentru conținutul înainte de primul heading
    new_section(None, "intro", None, None, None)

    children = list(article.children)

    i = 0
    while i < len(children):
        child = children[i]

        if isinstance(child, NavigableString):
            i += 1
            continue

        tag = child
        classes = " ".join(tag.get("class", []))
        tag_name = tag.name

        # ── Guide heading (H2/H3) ──────────────────────────────────────────
        if "guide-heading" in classes and tag_name == "header":
            num_el = tag.find(class_="guide-heading__num")
            supra_el = tag.find(class_="guide-heading__supra") or tag.find(class_="ais_hero_supra")
            title_el = tag.find(["h2", "h3", "h4"])
            anchor = tag.get("id") or (num_el.get("href", "").lstrip("#") if num_el else None)

            heading_num = text_of(num_el) if num_el else ""
            heading_supra = text_of(supra_el) if supra_el else ""
            heading_title = text_of(title_el) if title_el else ""
            level = int(title_el.name[1]) if title_el else 2

            section_type = "content"
            if "intro" in (anchor or ""):
                section_type = "intro"

            new_section(anchor, section_type, heading_num, heading_supra, heading_title, level)
            i += 1
            continue

        # ── Badges / hero (procesate deja la meta) ────────────────────────
        if any(k in classes for k in ["ais_guide_badges", "guide-heading", "ais_hero_section"]):
            i += 1
            continue

        # ── TOC ───────────────────────────────────────────────────────────
        if "guide-toc" in classes:
            intro_el = tag.find(class_="toc-intro")
            intro_text = inner_html(intro_el) if intro_el else ""
            if intro_text:
                bid = add_block("paragraph", content=intro_text)

            toc_nav = tag.find("nav")
            if toc_nav:
                toc_items = parse_toc(toc_nav)
                bid = add_block("toc", title="Alege ce citești",
                                content=json.dumps(toc_items, ensure_ascii=False))
            i += 1
            continue

        # ── Callout-uri (Build / Managed / teal / cream) ──────────────────
        if is_callout(tag):
            variant = detect_callout_variant(tag)
            h4 = tag.find("h4")
            callout_title = text_of(h4) if h4 else ""
            bid = add_block("callout", variant=variant, title=callout_title,
                            content=inner_html(tag))
            # Elemente din liste interne
            elem_order = 0
            for li in tag.find_all("li"):
                elem_order += 1
                insert_element(conn, bid, elem_order, "list_item",
                               content=inner_html(li))
            i += 1
            continue

        # ── Secțiuni de cod (fig-container) ───────────────────────────────
        if is_code_block(tag):
            h4 = tag.find("h4")
            block_title = text_of(h4) if h4 else ""

            # Poate exista un guide-heading intern (subsecțiune H3)
            inner_heading = tag.find(class_="guide-heading")
            if inner_heading:
                num_el = inner_heading.find(class_="guide-heading__num")
                supra_el = inner_heading.find(class_="guide-heading__supra")
                title_el = inner_heading.find(["h3", "h4"])
                anchor = inner_heading.get("id")
                new_section(
                    anchor, "content",
                    text_of(num_el), text_of(supra_el), text_of(title_el), 3
                )

            bid = add_block("code_example", title=block_title)

            # Paragrafe introductive
            elem_order = 0
            for p in tag.find_all("p", recursive=False):
                elem_order += 1
                insert_element(conn, bid, elem_order, "list_item",
                               content=inner_html(p))

            # Liste
            for ul in tag.find_all("ul", recursive=False):
                for li in ul.find_all("li"):
                    elem_order += 1
                    insert_element(conn, bid, elem_order, "list_item",
                                   content=inner_html(li))

            # Fiecare <details> = snippet sau notă
            for details in tag.find_all("details"):
                summary = details.find("summary")
                summary_text = text_of(summary) if summary else ""
                is_note = "teal" in " ".join(details.get("class", []))

                pre = details.find("pre")
                if pre and not is_note:
                    code_tag = pre.find("code")
                    lang = extract_code_language(pre)
                    code_text = code_tag.get_text() if code_tag else pre.get_text()
                    elem_order += 1
                    insert_element(conn, bid, elem_order, "code_snippet",
                                   content=code_text.strip(),
                                   label=summary_text,
                                   extra={"language": lang})
                else:
                    # Note block
                    note_items = details.find_all("li")
                    if not note_items:
                        note_items = details.find_all("p")
                    for item in note_items:
                        elem_order += 1
                        insert_element(conn, bid, elem_order, "note_item",
                                       content=inner_html(item),
                                       label=summary_text)

            i += 1
            continue

        # ── Link de referință spre alt ghid ───────────────────────────────
        if tag_name == "p" and tag.find("a", class_="intralinking-box"):
            a = tag.find("a", class_="intralinking-box")
            bid = add_block("link_ref",
                            content=a.get_text(strip=True),
                            anchor_id=a.get("href", ""))
            i += 1
            continue

        if tag_name == "p" and "fa-hand-back-point-right" in str(tag):
            a = tag.find("a")
            if a:
                bid = add_block("link_ref",
                                content=a.get_text(strip=True),
                                anchor_id=a.get("href", ""))
            i += 1
            continue

        # ── Paragraf simplu ───────────────────────────────────────────────
        if tag_name == "p":
            txt = inner_html(tag)
            if txt.strip():
                add_block("paragraph", content=txt)
            i += 1
            continue

        # ── Liste (ul/ol) de nivel top ────────────────────────────────────
        if tag_name in ("ul", "ol"):
            btype = "ordered_list" if tag_name == "ol" else "unordered_list"
            bid = add_block(btype)
            for idx, li in enumerate(tag.find_all("li", recursive=False), 1):
                insert_element(conn, bid, idx, "list_item", content=inner_html(li))
            i += 1
            continue

        # ── H3 standalone (fără wrapper guide-heading) ────────────────────
        if tag_name == "h3":
            new_section(tag.get("id"), "content", None, None, tag.get_text(strip=True), 3)
            i += 1
            continue

        # ── Summary box teal ──────────────────────────────────────────────
        if "s_newpar--teal" in classes:
            h3 = tag.find("h3")
            bid = add_block("summary_box", variant="teal",
                            title=text_of(h3) if h3 else "Pe scurt")
            for idx, li in enumerate(tag.find_all("li"), 1):
                insert_element(conn, bid, idx, "summary_item", content=inner_html(li))
            i += 1
            continue

        # ── Concluzie / scenario box blue ─────────────────────────────────
        if "ais_scenario_box--blue" in classes and tag_name == "div":
            bid = add_block("callout", variant="conclusion", content=inner_html(tag))
            i += 1
            continue

        # ── FAQ section ───────────────────────────────────────────────────
        if tag_name == "section" and ("faq" in classes or tag.find(class_="faq")):
            new_section(None, "faq", None, None, "Întrebări rapide", 2)
            for faq_div in tag.find_all(class_="faq"):
                q = faq_div.find(class_="question")
                a_div = faq_div.find(class_="answer")
                if q and a_div:
                    h4 = q.find("h4")
                    bid = add_block("faq_item",
                                    title=text_of(h4) if h4 else text_of(q),
                                    content=inner_html(a_div))
                    insert_element(conn, bid, 1, "faq_answer", content=inner_html(a_div))
            i += 1
            continue

        # ── Chapter nav grid ──────────────────────────────────────────────
        if "ais_chapter_grid" in classes:
            new_section(None, "chapter_nav", None, None, "Continuă în ghid", 2)
            for card in tag.find_all(class_="ais_chapter_card"):
                num_el = card.find(class_="ais_chap_num")
                title_el = card.find(class_="ais_chap_title")
                desc_el = card.find(class_="ais_chap_desc")
                link_el = card.find(class_="ais_chap_link")
                bid = add_block("chapter_card",
                                title=text_of(title_el),
                                heading_num=text_of(num_el),
                                content=inner_html(desc_el) if desc_el else "")
                if link_el:
                    insert_element(conn, bid, 1, "link",
                                   href=link_el.get("href", ""),
                                   label=link_el.get_text(strip=True))
            i += 1
            continue

        # ── PDF CTA ───────────────────────────────────────────────────────
        if "pdf-container" in classes:
            new_section(None, "pdf_cta", None, None, "Cere formatul PDF complet", 2)
            add_block("paragraph", content=inner_html(tag))
            i += 1
            continue

        # ── Orice altceva (div generic, etc.) ─────────────────────────────
        raw = inner_html(tag)
        if raw.strip():
            add_block("paragraph", content=raw)
        i += 1


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def scrape(html_content: str, url: str, db_path: str, schema_path: str = "schema.sql"):
    soup = BeautifulSoup(html_content, "html.parser")
    article = soup.find("main", class_="article-content")
    if not article:
        # fallback: orice main sau body
        article = soup.find("main") or soup.find("body")
    if not article:
        sys.exit("Nu s-a găsit elementul main.article-content")

    conn = init_db(db_path, schema_path)

    meta = parse_page_meta(article)
    slug = slug_from_url(url)

    page_id = insert_page(
        conn, slug, url,
        meta["chapter_num"],
        meta["chapter_label"],
        meta["title"],
        meta["subtitle"],
        meta["updated_at"],
    )
    print(f"[scraper] Pagină inserată: id={page_id}, slug={slug}")

    parse_article(article, page_id, conn)

    # Statistici
    s_count = conn.execute("SELECT COUNT(*) FROM sections WHERE page_id=?", (page_id,)).fetchone()[0]
    b_count = conn.execute(
        "SELECT COUNT(*) FROM blocks b JOIN sections s ON b.section_id=s.id WHERE s.page_id=?",
        (page_id,)
    ).fetchone()[0]
    e_count = conn.execute(
        "SELECT COUNT(*) FROM elements e "
        "JOIN blocks b ON e.block_id=b.id "
        "JOIN sections s ON b.section_id=s.id "
        "WHERE s.page_id=?",
        (page_id,)
    ).fetchone()[0]
    print(f"[scraper] Insertat: {s_count} secțiuni, {b_count} blocuri, {e_count} elemente")
    conn.close()
    return page_id


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Scraper ghid → SQLite")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--html", help="Calea către fișierul HTML local")
    group.add_argument("--url", help="URL-ul paginii de scrapat")
    parser.add_argument("--db", default="guide.db", help="Calea către baza de date SQLite")
    parser.add_argument("--schema", default="schema.sql", help="Calea către schema.sql")
    args = parser.parse_args()

    if args.html:
        html = Path(args.html).read_text(encoding="utf-8")
        source_url = args.html
    else:
        try:
            import requests
        except ImportError:
            sys.exit("Instalează: pip install requests")
        resp = requests.get(args.url, timeout=30)
        resp.raise_for_status()
        html = resp.text
        source_url = args.url

    scrape(html, source_url, args.db, args.schema)
    print(f"[scraper] Finalizat. DB: {args.db}")