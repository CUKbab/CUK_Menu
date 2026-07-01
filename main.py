"""
Parser for Catholic University cafeteria weekly menu PDF -> JSON
Downloads two PDFs (pranzo + bona), parses them, saves latest.json and archive.

Usage:
  python main.py                                        # auto-download both
  python main.py <pranzo.pdf> <bona.pdf>                # local files, default output
  python main.py <pranzo.pdf> <bona.pdf> <out.json>     # local files, custom output

Layout history
--------------
Layout A — "old normal" (13 rows, dates in row 0):
  Sections: 천원의아침, 한식, Global Noodle, 플러스코너, 석식  +  separate Bona PDF
  Detection: len(table) >= 13 AND row 0 has date headers AND row 3 has kcal values

Layout B — "vacation/break" (14 rows, dates in row 0, row 3 empty):
  Same sections as A but condensed — 천원의아침 kcal merged into row 2,
  석식 gains its own kcal row at row 13.  Bona PDF shrinks to 3 rows.
  Detection: len(table) >= 13 AND row 0 has date headers AND row 3 is all-empty

Layout C — "new normal" (10 rows, title in row 0, dates in row 1):
  Sections: 중식, 석식 only.  Both PDFs are identical; bona is ignored.
  Detection: row 0 contains title text (주 간 메 뉴 표 / 가톨릭대) and no date headers
"""

import json
import os
import re
import sys
import urllib.request
import urllib.error
from datetime import datetime, timedelta

PRANZO_URL  = "https://www.catholic.ac.kr/cms/etcResourceOpen.do?site=$cms$NYeyA&key=$cms$MYQwLgFg9gNglsA+gBwE4gHYC8oDpkAmAZkA"
BONA_URL    = "https://www.catholic.ac.kr/cms/etcResourceOpen.do?site=$cms$NYeyA&key=$cms$MYQwLgFg9gNglsA+gIygOxAOgA4BMBmQA"
PRANZO_PDF  = "catholic_pranzo.pdf"
BONA_PDF    = "catholic_bona.pdf"
DEFAULT_OUT = "latest.json"


# ── Download ───────────────────────────────────────────────────────────────

def download_pdf(url: str, dest: str, timeout: int = 15) -> None:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if resp.status != 200:
                raise RuntimeError(f"HTTP {resp.status} from {url}")
            with open(dest, "wb") as f:
                f.write(resp.read())
    except urllib.error.URLError as e:
        raise RuntimeError(f"Failed to download PDF: {e}") from e
    print(f"Downloaded -> {dest}")


# ── Archive / save ─────────────────────────────────────────────────────────

def get_archive_path(dates: list) -> str:
    first_date = datetime.strptime(dates[0], "%Y-%m-%d")
    monday = first_date - timedelta(days=first_date.weekday())
    year, week, _ = monday.isocalendar()
    return os.path.join("menus", str(year), str(week), "menu.json")


def save_json(data: dict, path: str) -> None:
    os.makedirs(os.path.dirname(path) if os.path.dirname(path) else ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"Saved    -> {path}")


# ── Helpers ────────────────────────────────────────────────────────────────

def clean(cell) -> str:
    return cell.strip() if cell else ""


def cell_items(cell) -> list:
    if not cell:
        return []
    return [x.strip() for x in cell.split("\n") if x.strip()]


def extract_kcal(items: list) -> tuple:
    """Pop kcal token from item list; return (kcal_str, remaining_items)."""
    kcal, rest = "", []
    for item in items:
        if re.match(r"^\d+kcal$", item):
            kcal = item
        else:
            rest.append(item)
    return kcal, rest


def build_menu_str(items: list, kcal: str = "") -> str:
    parts = [i for i in items if i]
    result = "\n".join(parts)
    if kcal:
        result += f" ({kcal})"
    return result + " "


def _row_has_dates(row) -> bool:
    """Return True if any cell in the row contains a MM/DD date pattern."""
    return any(re.search(r"\d{2}/\d{2}", clean(c)) for c in row if c)


def detect_layout(table) -> str:
    """
    Return one of: 'new_normal', 'vacation', 'old_normal'.

    Layout C (new_normal): title text in row 0, dates in row 1.
    Layout B (vacation):   dates in row 0, row 3 is entirely empty/None.
    Layout A (old_normal): dates in row 0, row 3 has kcal content.
    """
    if not _row_has_dates(table[0]) and len(table) > 1 and _row_has_dates(table[1]):
        return "new_normal"
    row3_empty = all(c is None or (isinstance(c, str) and not c.strip()) for c in table[3])
    return "vacation" if row3_empty else "old_normal"


# ── Date / column helpers ──────────────────────────────────────────────────

def parse_dates_from_row(row, raw_text) -> tuple:
    """
    Scan a header row for MM/DD patterns, infer the year, return
    (dates: list[str], col_indices: list[int]).
    """
    year_match = re.search(r"(\d{4})\.", raw_text)
    if year_match:
        year = year_match.group(1)
    else:
        # New-layout PDFs omit the year from the title; use current year
        # but roll forward if the month looks ahead of today (e.g. parsing
        # a December menu in January).
        now = datetime.now()
        year = str(now.year)

    date_cols = []
    for col_idx, cell in enumerate(row):
        m = re.search(r"(\d{2})/(\d{2})", clean(cell))
        if m:
            date_cols.append((col_idx, f"{year}-{m.group(1)}-{m.group(2)}"))

    if not date_cols:
        raise ValueError("Could not parse dates from PDF header row.")

    return [d for _, d in date_cols], [c for c, _ in date_cols]


def find_holidays(table, col_indices, scan_rows) -> set:
    """Return set of date-indices where '대체공휴일' appears."""
    holiday_indices = set()
    for row in scan_rows:
        for i, col in enumerate(col_indices):
            if col < len(row) and row[col] and "대체공휴일" in str(row[col]):
                holiday_indices.add(i)
    return holiday_indices


def make_safe(table, col_indices, n_dates):
    """Return safe(row_idx) -> list[n_dates cells]."""
    def safe(row_idx):
        if row_idx >= len(table):
            return [None] * n_dates
        row = table[row_idx]
        return [row[col] if col < len(row) else None for col in col_indices]
    return safe


# ── Layout C parser (new normal: 중식 + 석식 only) ─────────────────────────

def parse_new_normal(table, raw_text) -> tuple:
    """
    Layout C — 10-row table, title in row 0, dates in row 1.

      ROW 00: title (주 간 메 뉴 표 / 가톨릭대 학생식당 1점)
      ROW 01: header (구 분 | dates…)
      ROW 02: 중식 - main dish
      ROW 03: 중식 - rest part 1 (multiline)
      ROW 04: 중식 - rest part 2 + section label (multiline)
      ROW 05: 중식 - kcal
      ROW 06: 석식 - main + first side (multiline)
      ROW 07: 석식 - rest (multiline)
      ROW 08: 석식 - kcal
      ROW 09: footnotes

    Returns (result: dict, dates: list)
    """
    dates, col_indices = parse_dates_from_row(table[1], raw_text)
    holiday_indices = find_holidays(table, col_indices, table[2:6])
    safe = make_safe(table, col_indices, len(dates))
    n = len(dates)

    def no_menu():
        return {d: "No Menu " for d in dates}

    result = {
        "Lunch": no_menu(),
        "Dinner": no_menu(),
    }

    for i, date in enumerate(dates):
        if i in holiday_indices:
            result["Lunch"][date] = "No Menu"
            result["Dinner"][date] = "No Menu"
            continue

        # 중식: main (row 2) + rest rows 3+4 merged + kcal (row 5)
        main_lunch = clean(safe(2)[i])
        rest_lunch  = cell_items(safe(3)[i]) + cell_items(safe(4)[i])
        kcal_raw    = clean(safe(5)[i])
        kcal_num    = re.sub(r"\D", "", kcal_raw)
        kcal_str    = f"{kcal_num}kcal" if kcal_num else ""
        all_lunch   = ([main_lunch] if main_lunch else []) + rest_lunch
        result["Lunch"][date] = build_menu_str(all_lunch, kcal_str) if all_lunch else "No Menu "

        # 석식: rows 6+7 merged + kcal (row 8)
        rest_dinner = cell_items(safe(6)[i]) + cell_items(safe(7)[i])
        kcal_raw    = clean(safe(8)[i])
        kcal_num    = re.sub(r"\D", "", kcal_raw)
        kcal_str    = f"{kcal_num}kcal" if kcal_num else ""
        result["Dinner"][date] = build_menu_str(rest_dinner, kcal_str) if rest_dinner else "No Menu "

    return result, dates


# ── Layout A/B parser (old normal + vacation: full pranzo menu) ────────────

def parse_pranzo_ab(table, raw_text, vacation: bool) -> tuple:
    """
    Layouts A and B share the same row skeleton except where noted.

    Layout A — old_normal:
      ROW 00: header (dates)          ROW 07: Global Noodle - main
      ROW 01: 천원의아침 - main        ROW 08: Global Noodle - rest
      ROW 02: 천원의아침 - rest        ROW 09: Global Noodle - kcal
      ROW 03: 천원의아침 - kcal        ROW 10: 플러스코너 - single item
      ROW 04: 한식 - main              ROW 11: 석식 - main
      ROW 05: 한식 - rest              ROW 12: 석식 - rest (kcal embedded)
      ROW 06: 한식 - kcal

    Layout B — vacation (row 3 empty,석식 gains explicit kcal row 13):
      ROW 02: 천원의아침 - rest + kcal merged (no separate kcal row)
      ROW 03: (empty)
      ROW 11: 석식 - main
      ROW 12: 석식 - rest
      ROW 13: 석식 - kcal             (new row only in vacation layout)

    Returns (result: dict, dates: list)
    """
    dates, col_indices = parse_dates_from_row(table[0], raw_text)
    holiday_indices = find_holidays(table, col_indices, table[1:6])
    safe = make_safe(table, col_indices, len(dates))

    def no_menu():
        return {d: "No Menu " for d in dates}

    result = {
        "Morning": no_menu(),
        "Pranzo-Korean": no_menu(),
        "Pranzo-Global-Noodle": no_menu(),
        "Pranzo-Plus-Corner": no_menu(),
        "Pranzo-Dinner": no_menu(),
    }

    def fill_section(key, main_row, rest_row, kcal_row):
        for i, date in enumerate(dates):
            if i in holiday_indices:
                result[key][date] = "No Menu"
                continue
            main = clean(main_row[i])
            rest = cell_items(rest_row[i])
            kcal_from_rest, rest = extract_kcal(rest)
            kcal_raw = clean(kcal_row[i]) if kcal_row[i] else kcal_from_rest
            kcal_num = re.sub(r"\D", "", kcal_raw)
            kcal_str = f"{kcal_num}kcal" if kcal_num else ""
            all_items = ([main] if main else []) + rest
            result[key][date] = build_menu_str(all_items, kcal_str) if all_items else "No Menu"

    if vacation:
        # 천원의아침: kcal embedded in rest row 2; row 3 is empty
        fill_section("Morning", safe(1), safe(2), [None] * len(dates))
        fill_section("Pranzo-Korean",        safe(4), safe(5), safe(6))
        fill_section("Pranzo-Global-Noodle", safe(7), safe(8), safe(9))
        fill_section("Pranzo-Dinner",        safe(11), safe(12), safe(13))
    else:
        fill_section("Morning",              safe(1),  safe(2),  safe(3))
        fill_section("Pranzo-Korean",        safe(4),  safe(5),  safe(6))
        fill_section("Pranzo-Global-Noodle", safe(7),  safe(8),  safe(9))
        # 석식: kcal embedded in rest row 12
        fill_section("Pranzo-Dinner",        safe(11), safe(12), [None] * len(dates))

    # 플러스코너: single item row 10 — same in both layouts
    for i, date in enumerate(dates):
        if i in holiday_indices:
            result["Pranzo-Plus-Corner"][date] = "No Menu "
            continue
        item = clean(safe(10)[i])
        result["Pranzo-Plus-Corner"][date] = (item + " ") if item else "No Menu "

    return result, dates


# ── Bona parser (layouts A/B only) ────────────────────────────────────────

def parse_bona_ab(table, dates, col_indices, holiday_indices, vacation: bool) -> dict:
    """
    Layout A — normal bona (5 rows):
      ROW 00: header  ROW 01: main  ROW 02: rest  ROW 03: drink  ROW 04: kcal

    Layout B — vacation bona (3 rows):
      ROW 00: header  ROW 01: all items merged  ROW 02: kcal
    """
    def day_cells(row):
        return [row[col] if col < len(row) else None for col in col_indices]

    def safe(row_idx):
        if row_idx >= len(table):
            return [None] * len(dates)
        return day_cells(table[row_idx])

    result = {"Bona-Rice-Bowl": {d: "No Menu " for d in dates}}

    for i, date in enumerate(dates):
        if i in holiday_indices:
            result["Bona-Rice-Bowl"][date] = "No Menu"
            continue

        if vacation:
            all_raw  = cell_items(safe(1)[i])
            kcal_raw = clean(safe(2)[i])
            kcal_num = re.sub(r"\D", "", kcal_raw)
            kcal_str = f"{kcal_num}kcal" if kcal_num else ""
            result["Bona-Rice-Bowl"][date] = (
                build_menu_str(all_raw, kcal_str) if all_raw else "No Menu "
            )
        else:
            main  = clean(safe(1)[i])
            rest  = cell_items(safe(2)[i])
            drink = clean(safe(3)[i])
            kcal_raw = clean(safe(4)[i])
            kcal_num = re.sub(r"\D", "", kcal_raw)
            kcal_str = f"{kcal_num}kcal" if kcal_num else ""
            all_items = ([main] if main else []) + rest + ([drink] if drink else [])
            result["Bona-Rice-Bowl"][date] = (
                build_menu_str(all_items, kcal_str) if all_items else "No Menu "
            )

    return result


# ── Top-level parsers ──────────────────────────────────────────────────────

def parse_pranzo(pdf_path: str) -> tuple:
    """Open pranzo PDF, detect layout, dispatch to the right parser."""
    import pdfplumber

    with pdfplumber.open(pdf_path) as pdf:
        page = pdf.pages[0]
        raw_text = page.extract_text() or ""
        tables = page.extract_tables()

    if not tables:
        raise ValueError(f"No tables found in {pdf_path}")

    table = tables[0]
    layout = detect_layout(table)
    print(f"Detected layout '{layout}' for pranzo PDF.")

    if layout == "new_normal":
        return parse_new_normal(table, raw_text)
    else:
        return parse_pranzo_ab(table, raw_text, vacation=(layout == "vacation"))


def parse_bona(pdf_path: str, dates: list, col_indices: list, holiday_indices: set,
               skip: bool = False) -> dict:
    """
    Open bona PDF and parse it.
    Pass skip=True when the layout is new_normal (bona is redundant).
    """
    if skip:
        return {}

    import pdfplumber

    with pdfplumber.open(pdf_path) as pdf:
        page = pdf.pages[0]
        tables = page.extract_tables()

    if not tables:
        raise ValueError(f"No tables found in {pdf_path}")

    table = tables[0]
    vacation = len(table) <= 3
    if vacation:
        print("Detected vacation/break layout for bona PDF.")
    return parse_bona_ab(table, dates, col_indices, holiday_indices, vacation)


# ── Entry point ────────────────────────────────────────────────────────────

def main():
    auto_download = len(sys.argv) == 1
    pranzo_path = sys.argv[1] if len(sys.argv) > 1 else PRANZO_PDF
    bona_path   = sys.argv[2] if len(sys.argv) > 2 else BONA_PDF
    out_path    = sys.argv[3] if len(sys.argv) > 3 else DEFAULT_OUT

    if auto_download:
        download_pdf(PRANZO_URL, pranzo_path)
        download_pdf(BONA_URL,   bona_path)

    try:
        print(f"Parsing: {pranzo_path}")
        pranzo_data, dates = parse_pranzo(pranzo_path)

        # Re-open pranzo to get col_indices and holiday_indices for bona
        import pdfplumber
        with pdfplumber.open(pranzo_path) as pdf:
            table    = pdf.pages[0].extract_tables()[0]
            raw_text = pdf.pages[0].extract_text() or ""

        layout = detect_layout(table)

        if layout == "new_normal":
            # Both PDFs carry the same menu; bona is not a separate cafeteria
            print(f"Skipping bona PDF (new_normal layout — same menu as pranzo).")
            bona_data = {}
        else:
            header_row = table[1] if layout == "new_normal" else table[0]
            _, col_indices = parse_dates_from_row(header_row, raw_text)
            holiday_indices = find_holidays(table, col_indices, table[1:6])
            print(f"Parsing: {bona_path}")
            bona_data = parse_bona(bona_path, dates, col_indices, holiday_indices)

    finally:
        if auto_download:
            for path in [pranzo_path, bona_path]:
                if os.path.exists(path):
                    os.remove(path)
                    print(f"Deleted  -> {path}")

    data = {**pranzo_data, **bona_data}

    save_json(data, out_path)
    save_json(data, get_archive_path(dates))

    print(json.dumps(data, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
