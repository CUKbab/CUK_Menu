# CUK-Menu

An unofficial parser for cafeteria menu data from the Catholic University of Korea (가톨릭대학교).  
Downloads weekly menu PDFs from the university website, parses them, and outputs structured JSON consumed by the **CUK밥** mobile app.

---

## Project Structure

```
CUK-Menu/
├── main.py                  # PDF downloader & parser (entry point)
├── requirements.txt         # Python dependencies
├── latest.json              # Current week's parsed menu (overwritten each run)
├── parsed_menu.json         # Legacy fallback — required by older app versions
├── Buon_Pranzo.json         # Legacy fallback — required by older app versions
├── Café_Bona.json           # Legacy fallback — required by older app versions
├── version.json             # App version metadata
├── privacy.html             # Privacy policy page for the CUK밥 app
└── menus/                   # Archive of all previously parsed menus
    └── <year>/
        └── <ISO week number>/
            └── menu.json
```

### Notes on specific files

**`latest.json`** — Always reflects the most recently parsed week. Overwritten on every run. This is the primary file the app reads.

**`menus/`** — A cumulative archive. Each run saves a copy of the parsed menu at `menus/<year>/<week>/menu.json` (e.g. `menus/2026/13/menu.json` for ISO week 13 of 2026). Old entries are never deleted.

**`parsed_menu.json`, `Buon_Pranzo.json`, `Café_Bona.json`** — Legacy files required for backward compatibility. Older versions of the CUK밥 app read these files directly on startup and **will crash if they are missing**. Do not delete them. Their contents are placeholder strings prompting users to update the app.

---

## Menu Sections

Each parsed JSON contains the following keys:

| Key | Korean name | Description |
|-----|-------------|-------------|
| `Morning` | 천원의 아침 | Budget breakfast |
| `Pranzo-Korean` | 한식 | Korean lunch |
| `Pranzo-Global-Noodle` | 글로벌 누들 | Noodle-focused lunch |
| `Pranzo-Plus-Corner` | 플러스코너 | Daily special add-on |
| `Pranzo-Dinner` | 석식 | Dinner |
| `Bona-Rice-Bowl` | 보나 덮밥 (1층) | Rice bowl at Café Bona |

Each key maps to an object of `"YYYY-MM-DD": "menu string"` pairs for Mon–Fri. Days with no service are marked `"No Menu"`.

---

## Usage

### Requirements

```bash
pip install -r requirements.txt
```

`pdfplumber` is the only dependency.

### Auto-download and parse (recommended)

```bash
python main.py
```

Fetches the latest Pranzo and Bona PDFs from the university website, parses them, saves `latest.json`, and archives the result under `menus/`. The downloaded PDFs are deleted after parsing.

### Parse local PDF files

```bash
python main.py <pranzo.pdf> <bona.pdf>
```

Parses two local PDF files and writes output to `latest.json`.

### Parse local PDFs with a custom output path

```bash
python main.py <pranzo.pdf> <bona.pdf> <output.json>
```

Same as above, but writes to the specified output file instead of `latest.json`. The archive under `menus/` is always written regardless.

---

## Output Format

```json
{
  "Morning": {
    "2026-03-23": "닭감자조림\n쌀밥\n미역국\n미니돈까스&케찹\n브로콜리참깨무침\n배추김치/그린샐러드 (901kcal)",
    "2026-03-24": "..."
  },
  "Pranzo-Korean": { ... },
  "Pranzo-Global-Noodle": { ... },
  "Pranzo-Plus-Corner": { ... },
  "Pranzo-Dinner": { ... },
  "Bona-Rice-Bowl": { ... }
}
```

Menu items within a day are newline-separated (`\n`). Calorie information appears at the end of the string in parentheses.

---

## Contact

cukqkq@gmail.com
