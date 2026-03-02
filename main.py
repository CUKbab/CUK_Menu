import json
import re
import sys
from pathlib import Path
import pdfplumber
import urllib.request
import os


# ──────────────────────────────────────────────
# Configuration
# ──────────────────────────────────────────────

# The section labels as they appear in the PDF (column 0 / 1 cells)
SECTION_MAP = {
    "천원의아침": "천원의아침",
    "한식": "프란조 (2층) - 한식",
    "Global\nNoodle": "프란조 (2층) - Global Noodle",
    "누들": "프란조 (2층) - Global Noodle",   # alt text
    "플러스코너": "프란조 (2층) - 플러스코너",
    "석식": "프란조 (2층) - 석식",
    "덮밥": "보나 (1층) - 덮밥",
}

# Days in order (Mon-Fri); dates are determined from the PDF title row
WEEKDAYS = ["월", "화", "수", "목", "금"]

def request():
    urllib.request.urlretrieve("https://www.catholic.ac.kr/cms/etcResourceOpen.do?site=$cms$NYeyA&key=$cms$MYQwLgFg9gNglsA+gBwE4gHYC8oDpkAmAZkA", "catholic_pranzo.pdf")
    print("This week's menu has been updated.")

def extract_dates_from_text(text: str) -> list[str]:
    """Pull yyyy-mm-dd dates from raw page text."""
    # Look for patterns like 03/02(월) -> we'll reconstruct with the year from title
    year_match = re.search(r"(\d{4})\.", text)
    year = year_match.group(1) if year_match else "2026"

    date_matches = re.findall(r"(\d{2})/(\d{2})\s*[（(][월화수목금][)）]", text)
    dates = []
    for month, day in date_matches:
        dates.append(f"{year}-{month}-{day}")
    return dates


def clean_cell(cell: str | None) -> str:
    if not cell:
        return ""
    # Collapse whitespace / newlines
    return re.sub(r"\s+", " ", cell.strip())


def parse_menu_pdf(pdf_path: str) -> dict:
    """Main parsing function. Returns the JSON-compatible dict."""

    result: dict[str, dict[str, str]] = {v: {} for v in dict.fromkeys(SECTION_MAP.values())}

    with pdfplumber.open(pdf_path) as pdf:
        page = pdf.pages[0]
        raw_text = page.extract_text() or ""

        dates = extract_dates_from_text(raw_text)
        if not dates:
            raise ValueError("Could not find dates in PDF.")

        # Mark Mon (index 0) as holiday if "대체공휴일" appears
        holiday_indices: set[int] = set()
        if "대체공휴일" in raw_text:
            holiday_indices.add(0)  # Monday is the holiday

        tables = page.extract_tables()
        if not tables:
            raise ValueError("No tables found in PDF.")

        table = tables[0]  # The menu is a single large table

        # ── Identify date columns ──────────────────────────────────────────
        # Row 0 is the header: [구분 col, 구분 col, 03/02(월), 03/03(화), ...]
        # Find which column indices correspond to each date
        header_row = table[0]
        date_col_indices: list[int] = []
        for col_idx, cell in enumerate(header_row):
            cleaned = clean_cell(cell)
            if re.search(r"\d{2}/\d{2}", cleaned):
                date_col_indices.append(col_idx)

        # Ensure we have as many date columns as dates
        # (Sometimes the header detection picks up extra; trim to len(dates))
        date_col_indices = date_col_indices[: len(dates)]

        if not date_col_indices:
            raise ValueError("Could not map date columns in table header.")

        # ── Walk rows and accumulate menu items per section ───────────────
        current_section: str | None = None
        # Buffer: section -> day_index -> list of items
        buffers: dict[str, dict[int, list[str]]] = {
            section: {i: [] for i in range(len(dates))}
            for section in result
        }

        for row in table[1:]:
            if not row:
                continue

            # Detect section label from first two columns
            label_raw = clean_cell(row[0]) + "\n" + clean_cell(row[1] if len(row) > 1 else "")
            for key, section_name in SECTION_MAP.items():
                if key.replace("\n", " ") in label_raw.replace("\n", " "):
                    current_section = section_name
                    break

            if current_section is None:
                continue

            # Extract data from date columns
            for day_idx, col_idx in enumerate(date_col_indices):
                if col_idx >= len(row):
                    continue
                cell_text = clean_cell(row[col_idx])
                if cell_text and cell_text not in ("", "-", "X"):
                    buffers[current_section][day_idx].append(cell_text)

        # ── Build final result ────────────────────────────────────────────
        for section, day_buffers in buffers.items():
            for day_idx, date in enumerate(dates):
                items = day_buffers[day_idx]
                if day_idx in holiday_indices or not items:
                    result[section][date] = "No Menu"
                else:
                    result[section][date] = ", ".join(items)

    return result


def main():
    request()
    pdf_path = sys.argv[1] if len(sys.argv) > 1 else "catholic_pranzo.pdf"
    out_path = sys.argv[2] if len(sys.argv) > 2 else "parsed_menu.json"

    print(f"Parsing: {pdf_path}")
    data = parse_menu_pdf(pdf_path)

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"Saved to: {out_path}")
    print(json.dumps(data, ensure_ascii=False, indent=2))
    os.remove("catholic_pranzo.pdf")


if __name__ == "__main__":
    main()
