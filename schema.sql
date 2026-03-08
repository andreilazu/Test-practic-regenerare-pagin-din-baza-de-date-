-- =============================================================
-- CMS Guide Schema
-- Structură: page → sections → blocks → elements
-- =============================================================

PRAGMA foreign_keys = ON;

-- Pagina principală
CREATE TABLE IF NOT EXISTS pages (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    slug        TEXT    NOT NULL UNIQUE,  -- ex: "cookbook-cod-recomandari-ai"
    url         TEXT,
    chapter_num TEXT,                     -- ex: "04"
    chapter_label TEXT,                   -- ex: "Recomandări inteligente..."
    title       TEXT,
    subtitle    TEXT,
    updated_at  TEXT                      -- ex: "24.02.2026"
);

-- Secțiuni de nivel 1 (H2 + conținut grupat)
CREATE TABLE IF NOT EXISTS sections (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    page_id      INTEGER NOT NULL REFERENCES pages(id),
    sort_order   INTEGER NOT NULL,
    anchor_id    TEXT,                    -- ex: "minimal-complete-ai-pipeline"
    section_type TEXT NOT NULL,          
    -- tipuri: 'hero', 'intro', 'toc', 'content', 'conclusion', 'cta', 'faq', 'chapter_nav', 'pdf_cta'
    heading_num  TEXT,                    -- ex: "4.1"
    heading_supra TEXT,                   -- ex: "PAS CU PAS"
    heading_title TEXT,                   -- ex: "Un flux minimal complet"
    heading_level INTEGER DEFAULT 2       -- 1=H1, 2=H2, 3=H3
);

-- Blocuri în cadrul unei secțiuni (paragrafe, callout-uri, liste, coduri etc.)
CREATE TABLE IF NOT EXISTS blocks (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    section_id   INTEGER NOT NULL REFERENCES sections(id),
    sort_order   INTEGER NOT NULL,
    block_type   TEXT NOT NULL,
    -- tipuri: 'paragraph', 'callout', 'code_example', 'subsection', 
    --         'summary_box', 'link_ref', 'ordered_list', 'unordered_list',
    --         'faq_item', 'chapter_card', 'badge'
    variant      TEXT,
    -- pentru callout: 'build' | 'managed' | 'teal' | 'cream' | 'blue' | 'default'
    -- pentru code_example: limbajul (python, sql, javascript, json, yaml)
    title        TEXT,                    -- titlu opțional al blocului
    content      TEXT,                    -- conținut principal (HTML sau text)
    anchor_id    TEXT,                    -- anchor propriu dacă există
    heading_num  TEXT,                    -- ex: "4.2.1" pentru subsecțiuni
    heading_supra TEXT
);

-- Elemente atomice din interiorul unui bloc (iteme de listă, note, link-uri)
CREATE TABLE IF NOT EXISTS elements (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    block_id     INTEGER NOT NULL REFERENCES blocks(id),
    sort_order   INTEGER NOT NULL,
    element_type TEXT NOT NULL,
    -- tipuri: 'list_item', 'note_item', 'link', 'code_snippet', 
    --         'summary_item', 'faq_answer', 'chapter_nav_item'
    content      TEXT,
    href         TEXT,                    -- pentru link-uri
    label        TEXT,                    -- text afișat pentru link
    extra        TEXT                     -- JSON pentru date extra (ex: tag-uri, atribute)
);

-- Index-uri pentru performanță
CREATE INDEX IF NOT EXISTS idx_sections_page   ON sections(page_id, sort_order);
CREATE INDEX IF NOT EXISTS idx_blocks_section  ON blocks(section_id, sort_order);
CREATE INDEX IF NOT EXISTS idx_elements_block  ON elements(block_id, sort_order);