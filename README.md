# HTML Content CMS — Scraper + Generator

Sistem de extracție și regenerare a conținutului HTML dintr-o pagină web structurată,
cu stocare intermediară într-o bază de date SQLite.

**Pagina țintă:** [`opti.ro/ai-2026/ghid-recomandari-upsell/cookbook-cod-recomandari-ai`](https://www.opti.ro/ai-2026/ghid-recomandari-upsell/cookbook-cod-recomandari-ai)  
**Container procesat:** `main.article-content.opti-container-md.guide-content`

---

## Structura proiectului

```
├── schema.sql       # Definiția bazei de date SQLite (structură + indexuri)
├── scraper.py       # Parsează HTML-ul și populează baza de date
├── generator.py     # Citește din baza de date și regenerează HTML-ul
├── requirements.txt # Dependențe Python
└── README.md
```

---

## Instalare

```bash
pip install -r requirements.txt
```

---

## Utilizare

### Pasul 1 — Inițializare DB și scraping

**Din fișier HTML local:**
```bash
python scraper.py --html pagina.html --db guide.db
```

**Direct de la URL:**
```bash
python scraper.py --url https://www.opti.ro/ai-2026/ghid-recomandari-upsell/cookbook-cod-recomandari-ai --db guide.db
```

Opțiuni disponibile:
| Argument | Descriere | Default |
|---|---|---|
| `--html` | Cale către fișier HTML local | — |
| `--url` | URL-ul paginii de scrapat | — |
| `--db` | Cale către fișierul SQLite | `guide.db` |
| `--schema` | Cale către schema SQL | `schema.sql` |

> **Notă:** `--html` și `--url` se exclud reciproc. Unul dintre ele este obligatoriu.

---

### Pasul 2 — Export DB ca SQL dump (opțional)

```bash
sqlite3 guide.db .dump > guide_dump.sql
```

---

### Pasul 3 — Generare HTML

```bash
python generator.py --db guide.db --slug cookbook-cod-recomandari-ai --out output.html
```

Opțiuni disponibile:
| Argument | Descriere | Default |
|---|---|---|
| `--db` | Cale către fișierul SQLite | `guide.db` |
| `--slug` | Slug-ul paginii din DB | primul slug găsit |
| `--out` | Fișier de output | stdout |

---

## Arhitectura bazei de date

Conținutul paginii este stocat într-o ierarhie în 4 niveluri:

```
pages
  └── sections          (grupuri logice de conținut, separate de headings)
        └── blocks       (unități de conținut: paragrafe, callout-uri, cod etc.)
              └── elements  (atomi: iteme de listă, snippet-uri, link-uri)
```

### Tabelul `pages`
Metadatele paginii: slug, URL, numărul capitolului, titlu, dată actualizare.

### Tabelul `sections`
Fiecare `<header class="guide-heading">` din HTML creează o secțiune nouă.  
Câmpuri cheie:
- `section_type` — `content` | `intro` | `faq` | `chapter_nav` | `pdf_cta`
- `anchor_id` — ID-ul HTML pentru navigare internă (ex: `minimal-complete-ai-pipeline`)
- `heading_num` — numărul din ghid (ex: `4.1`, `4.2.3`)

### Tabelul `blocks`
Unitățile de conținut din interiorul unei secțiuni.  
`block_type` poate fi:

| Tip | Descriere |
|---|---|
| `paragraph` | Paragraf `<p>` simplu |
| `callout` | Casetă Build/Managed/teal/cream |
| `code_example` | Secțiune `fig-container` cu snippet-uri de cod |
| `toc` | Cuprinsul paginii (stocat ca JSON în câmpul `content`) |
| `summary_box` | Caseta "Pe scurt" |
| `ordered_list` / `unordered_list` | Liste de nivel superior |
| `link_ref` | Link de referință spre alt ghid |
| `faq_item` | Întrebare din secțiunea FAQ |
| `chapter_card` | Card de navigare între capitole |

Câmpul `variant` diferențiază subtipurile de callout:
- `build` — casetă cream (`s_newpar--cream`)
- `managed` — casetă albastră (`ais_scenario_box--blue`)
- `teal` — casetă rezumat
- `conclusion` — casetă concluzie finală

### Tabelul `elements`
Atomii din interiorul unui bloc.  
`element_type` poate fi:

| Tip | Folosit în |
|---|---|
| `list_item` | Liste, callout-uri, cod introductiv |
| `code_snippet` | Codul efectiv (cu limbajul în câmpul `extra` JSON) |
| `note_item` | Notele din `<details class="ais_codeblock--teal">` |
| `link` | Link-uri din chapter cards, referințe |
| `faq_answer` | Răspunsul la o întrebare FAQ |
| `summary_item` | Item din caseta "Pe scurt" |

---

## Detalii tehnice

### De ce SQLite?
Pentru un tool de generare HTML cu o singură sursă de date, SQLite este alegerea corectă:
nu necesită server, baza de date e un singur fișier portabil, și suportă interogări SQL complete.
Dacă sistemul ar trebui să suporte scriere concurentă din mai multe procese, PostgreSQL ar fi alternativa.

### De ce ierarhia în 4 niveluri și nu un tabel plat?
Un tabel plat cu toate blocurile ar forța duplicarea metadatelor heading-ului în fiecare bloc.
Ierarhia permite interogări precise:

```sql
-- Toate blocurile de cod din secțiunea 4.2
SELECT b.* FROM blocks b
JOIN sections s ON b.section_id = s.id
WHERE s.heading_num LIKE '4.2%'
AND b.block_type = 'code_example';
```

### De ce `content` stochează innerHTML brut în plus față de `elements`?
Decizie deliberată de robustețe. Parsarea completă a fiecărui tip de conținut în `elements`
ar fi fragilă la variații minore de HTML. `content` ca fallback garantează că HTML-ul
regenerat nu va fi niciodată gol, chiar dacă un tip de bloc nu e acoperit perfect de generator.

### Cum funcționează iterarea în `scraper.py`?
`parse_article()` iterează doar prin **copiii direcți** ai `<main>`, nu recursiv.
Motivul: iterarea recursivă ar procesa același `<li>` de mai multe ori
(o dată ca descendent al `<ul>`, o dată ca descendent al `<div>` etc.).
La primul nivel, fiecare element e procesat exact o dată,
iar sub-elementele sunt delegate funcției specifice tipului de bloc.

### Specificitate vs. generalitate
Scraper-ul are două straturi:
- **Generic** — paragrafe, liste, headings standard HTML funcționează pe orice pagină
- **Specific** — detectarea callout-urilor Build/Managed, a blocurilor `fig-container`,
  a structurii `guide-heading` e adaptată claselor CSS ale acestui site

Această specificitate e intenționată — cerința era pentru o pagină concretă cu un container definit.
Pentru a scala la alte site-uri, pattern-urile de clase CSS ar putea fi extrase
într-un fișier de configurare separat.

---

## Dependențe

| Pachet | Versiune | Utilizare |
|---|---|---|
| `beautifulsoup4` | ≥ 4.12 | Parsare HTML |
| `requests` | ≥ 2.31 | Fetch URL (opțional, doar pentru `--url`) |

Python minim: **3.10** (folosește `list[str]` și `str | None` ca type hints)
