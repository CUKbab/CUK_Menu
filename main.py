"""
Parser for Catholic University cafeteria weekly menu PDF -> JSON
Downloads two PDFs (pranzo + bona), parses them, saves latest.json and archive.

Usage:
  python main.py                                        # auto-download both
  python main.py <pranzo.pdf> <bona.pdf>                # local files, default output
  python main.py <pranzo.pdf> <bona.pdf> <out.json>     # local files, custom output
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


def parse_dates(table, raw_text) -> tuple:
    """
    Extract dates and holiday column indices from the header row.
    Returns (dates: list[str], data_col_start: int, holiday_indices: set[int])
    """
    year_match = re.search(r"(\d{4})\.", raw_text)
    year = year_match.group(1) if year_match else str(datetime.now().year)

    date_cols = []
    for col_idx, cell in enumerate(table[0]):
        m = re.search(r"(\d{2})/(\d{2})", clean(cell))
        if m:
            date_cols.append((col_idx, f"{year}-{m.group(1)}-{m.group(2)}"))

    if not date_cols:
        raise ValueError("Could not parse dates from PDF header.")

    dates = [d for _, d in date_cols]
    data_col_start = date_cols[0][0]

    # Detect holidays by scanning first few rows for "대체공휴일"
    holiday_indices = set()
    for row in table[1:6]:
        for i in range(len(dates)):
            col = data_col_start + i
            if col < len(row) and row[col] and "대체공휴일" in str(row[col]):
                holiday_indices.add(i)

    return dates, data_col_start, holiday_indices


def make_day_cells(table, data_col_start, n_dates):
    """Return a safe row accessor: safe(row_idx) -> list of n_dates cells."""
    def day_cells(row):
        return [row[data_col_start + i] if (data_col_start + i) < len(row) else None
                for i in range(n_dates)]

    def safe(row_idx):
        if row_idx >= len(table):
            return [None] * n_dates
        return day_cells(table[row_idx])

    return safe


# ── Pranzo parser ──────────────────────────────────────────────────────────

def parse_pranzo(pdf_path: str) -> tuple:
    """
    Parse catholic_pranzo.pdf.
    Table layout (this week):
      ROW 00: header (dates)
      ROW 01: 천원의아침 - main dish
      ROW 02: 천원의아침 - remaining items (kcal may be embedded)
      ROW 03: 천원의아침 - kcal row
      ROW 04: 한식 - main dish
      ROW 05: 한식 - remaining items
      ROW 06: 한식 - kcal
      ROW 07: Global Noodle - main dish
      ROW 08: Global Noodle - remaining items
      ROW 09: Global Noodle - kcal
      ROW 10: 플러스코너 - single item
      ROW 11: 석식 - main dish
      ROW 12: 석식 - remaining items (kcal embedded)
    Returns (result: dict, dates: list)
    """
    import pdfplumber

    with pdfplumber.open(pdf_path) as pdf:
        page = pdf.pages[0]
        raw_text = page.extract_text() or ""
        tables = page.extract_tables()

    if not tables:
        raise ValueError(f"No tables found in {pdf_path}")

    table = tables[0]
    dates, data_col_start, holiday_indices = parse_dates(table, raw_text)
    safe = make_day_cells(table, data_col_start, len(dates))

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

    fill_section("Morning",                   safe(1),  safe(2),  safe(3))
    fill_section("Pranzo-Korean",          safe(4),  safe(5),  safe(6))
    fill_section("Pranzo-Global-Noodle", safe(7),  safe(8),  safe(9))

    # 플러스코너: single item (row 10)
    for i, date in enumerate(dates):
        if i in holiday_indices:
            result["Pranzo-Plus-Corner"][date] = "No Menu "
            continue
        item = clean(safe(10)[i])
        result["Pranzo-Plus-Corner"][date] = (item + " ") if item else "No Menu "

    # 석식: main (row 11) + rest with embedded kcal (row 12), no separate kcal row
    fill_section("Pranzo-Dinner", safe(11), safe(12), [None] * len(dates))

    return result, dates


# ── Bona parser ────────────────────────────────────────────────────────────

def parse_bona(pdf_path: str, dates: list, holiday_indices: set) -> dict:
    """
    Parse catholic_bona.pdf.
    Table layout:
      ROW 00: header row (date labels: 04/20(월), 04/21(화), …)
      ROW 01: main dish per day
      ROW 02: remaining items (multi-line)
      ROW 03: drink
      ROW 04: kcal
    Returns partial result dict with just "보나 (1층) - 덮밥".
    """
    import pdfplumber

    with pdfplumber.open(pdf_path) as pdf:
        page = pdf.pages[0]
        raw_text = page.extract_text() or ""
        tables = page.extract_tables()

    if not tables:
        raise ValueError(f"No tables found in {pdf_path}")

    table = tables[0]

    # Bona PDF has no date labels in header — data always starts at col 3
    data_col_start = 3

    def day_cells(row):
        return [row[data_col_start + i] if (data_col_start + i) < len(row) else None
                for i in range(len(dates))]

    def safe(row_idx):
        if row_idx >= len(table):
            return [None] * len(dates)
        return day_cells(table[row_idx])

    result = {"Bona-Rice-Bowl": {d: "No Menu " for d in dates}}

    for i, date in enumerate(dates):
        if i in holiday_indices:
            result["Bona-Rice-Bowl"][date] = "No Menu"
            continue
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

        # Reuse holiday detection from pranzo for bona
        import pdfplumber
        with pdfplumber.open(pranzo_path) as pdf:
            table = pdf.pages[0].extract_tables()[0]
            raw_text = pdf.pages[0].extract_text() or ""
        _, _, holiday_indices = parse_dates(table, raw_text)

        print(f"Parsing: {bona_path}")
        bona_data = parse_bona(bona_path, dates, holiday_indices)

    finally:
        if auto_download:
            for path in [pranzo_path, bona_path]:
                if os.path.exists(path):
                    os.remove(path)
                    print(f"Deleted  -> {path}")

    # Merge both results
    data = {**pranzo_data, **bona_data}

    save_json(data, out_path)
    save_json(data, get_archive_path(dates))

    print(json.dumps(data, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
