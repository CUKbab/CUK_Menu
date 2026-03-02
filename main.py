"""
Parser for Catholic University cafeteria weekly menu PDF -> JSON
Usage: python parse_menu.py [pdf_path] [output_json_path]

Run without arguments to auto-download this week's PDF, parse it, and delete it.
"""

import json
import os
import re
import sys
import urllib.request
import urllib.error

PDF_URL     = "https://www.catholic.ac.kr/cms/etcResourceOpen.do?site=$cms$NYeyA&key=$cms$MYQwLgFg9gNglsA+gBwE4gHYC8oDpkAmAZkA"
DEFAULT_PDF = "catholic_pranzo.pdf"
DEFAULT_OUT = "parsed_menu.json"


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


# ── Helpers ────────────────────────────────────────────────────────────────

def clean(cell) -> str:
    return cell.strip() if cell else ""


def cell_items(cell) -> list:
    if not cell:
        return []
    return [x.strip() for x in cell.split("\n") if x.strip()]


def extract_kcal(items: list) -> tuple:
    """Pop a kcal string from item list; return (kcal_str, remaining_items)."""
    kcal, rest = "", []
    for item in items:
        if re.match(r"^\d+kcal$", item):
            kcal = item
        else:
            rest.append(item)
    return kcal, rest


def build_menu_str(items: list, kcal: str = "") -> str:
    parts = [i for i in items if i]
    result = parts[0] if parts else ""
    for part in parts[1:]:
        result += f"\n{part}"
    if kcal:
        result += f"\n({kcal})"
    return result + " "


# ── Page 2 parsing (drinks + kcal for 보나) ────────────────────────────────

def parse_page2(pdf) -> tuple:
    """
    Dynamically parses drinks and kcals for 보나 from page 2.
    The drink line is the line immediately before the kcal line.
    Returns (drinks: list[str], kcals: list[str]) for active (non-holiday) days.
    """
    text = pdf.pages[1].extract_text() or ""
    lines = [l.strip() for l in text.splitlines() if l.strip()]

    drinks, kcals = [], []
    for idx, line in enumerate(lines):
        # kcal line: contains only "NNNkcal" tokens
        if re.match(r"^(\d{3,4}kcal\s*)+$", line):
            kcals = [f"{k}kcal" for k in re.findall(r"(\d{3,4})kcal", line)]
            # The drink line is immediately above the kcal line
            if idx > 0:
                drinks = lines[idx - 1].split()
            break

    return drinks[:4], kcals[:4]


# ── Core parser ────────────────────────────────────────────────────────────

def parse_menu_pdf(pdf_path: str) -> dict:
    import pdfplumber

    with pdfplumber.open(pdf_path) as pdf:
        page = pdf.pages[0]
        raw_text = page.extract_text() or ""
        tables = page.extract_tables()
        page2_drinks, page2_kcals = parse_page2(pdf)

    if not tables:
        raise ValueError("No tables found in PDF.")

    table = tables[0]

    # ── Dates ──────────────────────────────────────────────────────────────
    year_match = re.search(r"(\d{4})\.", raw_text)
    year = year_match.group(1) if year_match else "2026"

    date_cols = []
    for col_idx, cell in enumerate(table[0]):
        m = re.search(r"(\d{2})/(\d{2})", clean(cell))
        if m:
            date_cols.append((col_idx, f"{year}-{m.group(1)}-{m.group(2)}"))

    if not date_cols:
        raise ValueError("Could not parse dates from PDF header.")

    dates = [d for _, d in date_cols]
    data_col_start = date_cols[0][0]

    def day_cells(row):
        return [row[data_col_start + i] if (data_col_start + i) < len(row) else None
                for i in range(len(dates))]

    # ── Holiday detection: scan early rows for "대체공휴일" per column ───────
    holiday_indices: set = set()
    for row in table[1:6]:
        for i in range(len(dates)):
            col = data_col_start + i
            if col < len(row) and row[col] and "대체공휴일" in str(row[col]):
                holiday_indices.add(i)

    def no_menu():
        return {d: "No Menu " for d in dates}

    result = {
        "Morning": no_menu(),
        "Pranzo-Korean": no_menu(),
        "Pranzo-Global-Noodle": no_menu(),
        "Pranzo-Plus-Corner": no_menu(),
        "Pranzo-Dinner": no_menu(),
        "Bona-Rice-Bowl": no_menu(),
    }

    def fill_section(section_key, main_row, rest_row, kcal_row):
        for i, date in enumerate(dates):
            if i in holiday_indices:
                result[section_key][date] = "No Menu"
                continue
            main = clean(main_row[i])
            rest = cell_items(rest_row[i])
            kcal_from_rest, rest = extract_kcal(rest)
            kcal_raw = clean(kcal_row[i]) if kcal_row[i] else kcal_from_rest
            kcal_num = re.sub(r"\D", "", kcal_raw)
            kcal_str = f"{kcal_num}kcal" if kcal_num else ""
            all_items = ([main] if main else []) + rest
            result[section_key][date] = (
                build_menu_str(all_items, kcal_str) if all_items else "No Menu"
            )

    # Row indices based on inspected table structure
    fill_section("Morning",                   day_cells(table[1]),  day_cells(table[2]),  day_cells(table[3]))
    fill_section("Pranzo-Korean",          day_cells(table[4]),  day_cells(table[5]),  day_cells(table[6]))
    fill_section("Pranzo-Global-Noodle", day_cells(table[7]),  day_cells(table[8]),  day_cells(table[9]))
    fill_section("Pranzo-Dinner",          day_cells(table[11]), day_cells(table[12]), day_cells(table[13]))

    # 플러스코너: single item per day (row 10)
    plus_row = day_cells(table[10])
    for i, date in enumerate(dates):
        if i in holiday_indices:
            result["Pranzo-Plus-Corner"][date] = "No Menu "
            continue
        item = clean(plus_row[i])
        result["Pranzo-Plus-Corner"][date] = (item + " ") if item else "No Menu "

    # 보나 덮밥: main (row 14) + rest (row 15) + drink/kcal dynamically from page 2
    # Page 2 lists drinks and kcals only for active (non-holiday) days, in order
    main_row = day_cells(table[14])
    rest_row = day_cells(table[15])
    active_days = [i for i in range(len(dates)) if i not in holiday_indices]

    for slot, i in enumerate(active_days):
        date = dates[i]
        main     = clean(main_row[i])
        rest     = cell_items(rest_row[i])
        drink    = page2_drinks[slot] if slot < len(page2_drinks) else ""
        kcal_str = page2_kcals[slot]  if slot < len(page2_kcals)  else ""
        all_items = ([main] if main else []) + rest + ([drink] if drink else [])
        result["Bona-Rice-Bowl"][date] = (
            build_menu_str(all_items, kcal_str) if all_items else "No Menu "
        )

    return result


# ── Entry point ────────────────────────────────────────────────────────────

def main():
    auto_download = len(sys.argv) == 1
    pdf_path = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_PDF
    out_path  = sys.argv[2] if len(sys.argv) > 2 else DEFAULT_OUT

    if auto_download:
        download_pdf(PDF_URL, pdf_path)

    try:
        print(f"Parsing: {pdf_path}")
        data = parse_menu_pdf(pdf_path)
    finally:
        # Always clean up the downloaded file, even if parsing fails
        if auto_download and os.path.exists(pdf_path):
            os.remove(pdf_path)
            print(f"Deleted  -> {pdf_path}")

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"Saved    -> {out_path}\n")
    print(json.dumps(data, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
