"""
Parser for Catholic University cafeteria weekly menu PDF -> JSON
Downloads two PDFs (pranzo + bona), parses them, saves latest.json and archive.

Usage:
  python main.py                                        # auto-download both
  python main.py <pranzo.pdf> <bona.pdf>                # local files, default output
  python main.py <pranzo.pdf> <bona.pdf> <out.json>     # local files, custom output

Note on layout auto-detection:
  The university serves two different cafeteria menu layouts:
    - "multi" layout: several sections in one table (Morning / Korean /
      Global Noodle / Plus Corner / Dinner) -> the "부오프란조" cafeteria.
    - "simple" layout: a single section, one dish per day (e.g. the
      "ONE X PLATE" lunch menu) -> "Bona-Rice-Bowl".
  Historically the "multi" layout lived in the pranzo PDF and the "simple"
  layout lived in the bona PDF, but the university has since swapped which
  physical file (pranzo.pdf vs bona.pdf) serves which layout. Rather than
  trust the filename/URL, this parser inspects each PDF's table and detects
  which layout it actually contains, then assigns the output keys
  accordingly. This keeps the parser correct regardless of which file the
  site puts which content in.
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

KCAL_RE = re.compile(r"^\d+\s*kcal$", re.IGNORECASE)
MULTI_SECTION_KEYWORDS = ["천원의아침", "한식", "Global", "누들", "플러스코너", "석식"]


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
        if KCAL_RE.match(item):
            kcal = re.sub(r"\s+", "", item)
        else:
            rest.append(item)
    return kcal, rest


def build_menu_str(items: list, kcal: str = "") -> str:
    parts = [i for i in items if i]
    result = "\n".join(parts)
    if kcal:
        result += f" ({kcal})"
    return result + " "


# ── Table extraction ────────────────────────────────────────────────────────

def extract_table_and_text(pdf_path: str) -> tuple:
    import pdfplumber

    with pdfplumber.open(pdf_path) as pdf:
        page = pdf.pages[0]
        raw_text = page.extract_text() or ""
        tables = page.extract_tables()

    if not tables:
        raise ValueError(f"No tables found in {pdf_path}")
    return tables[0], raw_text


def find_header_row(table: list) -> int:
    """
    Find the row that actually holds the date labels (MM/DD). Some PDFs put a
    title-only row (no dates) before the real header row, so this can't be
    assumed to always be row 0.
    """
    best_idx, best_count = None, 0
    for idx, row in enumerate(table):
        count = sum(1 for cell in row if cell and re.search(r"\d{2}/\d{2}", clean(cell)))
        if count > best_count:
            best_idx, best_count = idx, count
    if best_idx is None:
        raise ValueError("Could not find a header row with dates in PDF.")
    return best_idx


def parse_dates(table: list, raw_text: str, year_hint: str = None) -> tuple:
    """
    Extract dates and holiday column indices from the header row.
    Returns (dates, col_indices, holiday_indices, header_row_idx)

    col_indices are the actual column positions for each date — these may not be
    contiguous (e.g. during vacation weeks, label columns sit between data columns).
    """
    header_idx = find_header_row(table)
    header_row = table[header_idx]

    if year_hint:
        year = year_hint
    else:
        year_match = re.search(r"(\d{4})\.", raw_text)
        year = year_match.group(1) if year_match else str(datetime.now().year)

    date_cols = []
    for col_idx, cell in enumerate(header_row):
        m = re.search(r"(\d{2})/(\d{2})", clean(cell))
        if m:
            date_cols.append((col_idx, f"{year}-{m.group(1)}-{m.group(2)}"))

    if not date_cols:
        raise ValueError("Could not parse dates from PDF header.")

    col_indices = [c for c, _ in date_cols]
    dates = [d for _, d in date_cols]

    # Detect holidays by scanning the rows after the header for "대체공휴일"
    holiday_indices = set()
    for row in table[header_idx + 1: header_idx + 6]:
        for i, col in enumerate(col_indices):
            if col < len(row) and row[col] and "대체공휴일" in str(row[col]):
                holiday_indices.add(i)

    return dates, col_indices, holiday_indices, header_idx


def make_day_cells(table, col_indices, n_dates):
    """
    Return a safe row accessor: safe(row_idx) -> list of n_dates cells.

    Uses the actual column positions from col_indices rather than sequential
    offsets — required when label columns sit between date columns (vacation weeks).
    """
    def day_cells(row):
        return [row[col] if col < len(row) else None for col in col_indices]

    def safe(row_idx):
        if row_idx < 0 or row_idx >= len(table):
            return [None] * n_dates
        return day_cells(table[row_idx])

    return safe


def merge_kcal_overflow_rows(table: list, col_indices: list) -> list:
    """
    Some merged cells (main dish + sides + kcal all on one logical line) wrap
    onto what pdfplumber reports as a separate table row: a row that's empty
    everywhere except one or two date columns holding a bare 'NNNkcal'
    fragment. Fold that fragment back into the previous row's cell (as an
    extra line) instead of leaving it stranded. The row is kept in place
    (blanked out) rather than deleted so fixed row offsets elsewhere in the
    parser stay valid.
    """
    if not table or not col_indices:
        return table

    label_end = min(col_indices)
    merged = [list(table[0])]
    for row in table[1:]:
        vals = [row[c] if c < len(row) else None for c in col_indices]
        non_empty = [(i, v) for i, v in enumerate(vals) if v and str(v).strip()]
        label_bits = [row[c] for c in range(label_end) if c < len(row)]
        label_empty = not any(b and str(b).strip() for b in label_bits)
        looks_like_overflow = (
            non_empty
            and len(non_empty) < len(col_indices)
            and label_empty
            and all(KCAL_RE.match(str(v).strip()) for _, v in non_empty)
        )
        if looks_like_overflow:
            prev = merged[-1]
            for i, v in non_empty:
                col = col_indices[i]
                if col >= len(prev):
                    continue
                old = (prev[col] or "").rstrip()
                token = re.sub(r"\s+", "", str(v).strip())
                prev[col] = f"{old}\n{token}" if old else token
            merged.append([None] * len(row))
        else:
            merged.append(list(row))
    return merged


# ── Layout detection ─────────────────────────────────────────────────────────

def is_multi_section(table: list, col_indices: list, header_idx: int) -> bool:
    label_end = min(col_indices) if col_indices else 0
    hits = set()
    for row in table[header_idx:]:
        text = " ".join(str(row[c]) for c in range(min(label_end, len(row))) if row[c])
        for kw in MULTI_SECTION_KEYWORDS:
            if kw in text:
                hits.add(kw)
    return len(hits) >= 3


# ── Multi-section parser (Morning / Korean / Global Noodle / Plus Corner / Dinner) ─

def parse_multi_section(table, dates, col_indices, holiday_indices, header_idx) -> dict:
    safe = make_day_cells(table, col_indices, len(dates))

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

    h = header_idx
    # 천원의아침: title row, then items+kcal merged into one cell (no separate kcal row)
    fill_section("Morning", safe(h + 1), safe(h + 2), [None] * len(dates))
    # 한식 / Global Noodle / 석식: title row, items row, separate kcal row
    fill_section("Pranzo-Korean",        safe(h + 4),  safe(h + 5),  safe(h + 6))
    fill_section("Pranzo-Global-Noodle", safe(h + 7),  safe(h + 8),  safe(h + 9))
    fill_section("Pranzo-Dinner",        safe(h + 11), safe(h + 12), safe(h + 13))

    # 플러스코너: single item row, no kcal
    for i, date in enumerate(dates):
        if i in holiday_indices:
            result["Pranzo-Plus-Corner"][date] = "No Menu "
            continue
        item = clean(safe(h + 10)[i])
        result["Pranzo-Plus-Corner"][date] = (item + " ") if item else "No Menu "

    return result


# ── Simple single-section parser (e.g. "ONE X PLATE" lunch) ─────────────────

def parse_simple_section(table, dates, col_indices, holiday_indices, header_idx) -> dict:
    """
    A single dish per day, spread across several rows (main dish, then one
    side item per row), terminated by a row where every date column holds a
    bare kcal value. Row count varies week to week (different numbers of side
    items), so the kcal row is located dynamically rather than assumed to sit
    at a fixed offset.
    """
    safe = make_day_cells(table, col_indices, len(dates))
    n = len(dates)

    kcal_row_idx = None
    for idx in range(header_idx + 1, len(table)):
        vals = safe(idx)
        if len(vals) == n and all(v and KCAL_RE.match(str(v).strip()) for v in vals):
            kcal_row_idx = idx
            break

    result = {"Bona-Rice-Bowl": {d: "No Menu " for d in dates}}

    items_by_col = [[] for _ in range(n)]
    end_idx = kcal_row_idx if kcal_row_idx is not None else len(table)
    for idx in range(header_idx + 1, end_idx):
        row_vals = safe(idx)
        for i, v in enumerate(row_vals):
            items_by_col[i].extend(cell_items(v))

    kcal_vals = safe(kcal_row_idx) if kcal_row_idx is not None else [None] * n

    for i, date in enumerate(dates):
        if i in holiday_indices:
            result["Bona-Rice-Bowl"][date] = "No Menu"
            continue
        items = items_by_col[i]
        kcal_raw = clean(kcal_vals[i]) if kcal_vals[i] else ""
        kcal_num = re.sub(r"\D", "", kcal_raw)
        kcal_str = f"{kcal_num}kcal" if kcal_num else ""
        result["Bona-Rice-Bowl"][date] = build_menu_str(items, kcal_str) if items else "No Menu "

    return result


# ── Top-level per-file parse ─────────────────────────────────────────────────

def parse_menu_pdf(pdf_path: str, year_hint: str = None) -> tuple:
    """
    Parse a weekly menu PDF, auto-detecting whether it's the multi-section
    layout or the simple single-section layout.
    Returns (kind, result_dict, dates, raw_text) where kind is 'multi' or 'simple'.
    """
    table, raw_text = extract_table_and_text(pdf_path)
    dates, col_indices, holiday_indices, header_idx = parse_dates(table, raw_text, year_hint)
    table = merge_kcal_overflow_rows(table, col_indices)

    if is_multi_section(table, col_indices, header_idx):
        result = parse_multi_section(table, dates, col_indices, holiday_indices, header_idx)
        return "multi", result, dates, raw_text
    else:
        result = parse_simple_section(table, dates, col_indices, holiday_indices, header_idx)
        return "simple", result, dates, raw_text


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
        kind_a, data_a, dates_a, text_a = parse_menu_pdf(pranzo_path)

        # Reuse the year from whichever PDF's text actually contains it, so
        # both files agree on the same year for their date strings.
        year_hint = None
        m = re.search(r"(\d{4})\.", text_a)
        if m:
            year_hint = m.group(1)

        print(f"Parsing: {bona_path}")
        kind_b, data_b, dates_b, text_b = parse_menu_pdf(bona_path, year_hint=year_hint)

        if kind_a == kind_b:
            raise ValueError(
                f"Both PDFs were detected as '{kind_a}' layout — expected one "
                "multi-section menu and one simple menu. The source PDFs may "
                "have changed format again; parser needs another look."
            )

        multi_data, simple_data, dates = (
            (data_a, data_b, dates_a) if kind_a == "multi" else (data_b, data_a, dates_b)
        )
        print(f"Detected layouts -> {pranzo_path}: {kind_a}, {bona_path}: {kind_b}")

    finally:
        if auto_download:
            for path in [pranzo_path, bona_path]:
                if os.path.exists(path):
                    os.remove(path)
                    print(f"Deleted  -> {path}")

    # Merge both results
    data = {**multi_data, **simple_data}

    save_json(data, out_path)
    save_json(data, get_archive_path(dates))

    print(json.dumps(data, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
