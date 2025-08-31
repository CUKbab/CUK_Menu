import pdfplumber
import re
import json
import urllib.request
import os

def request():
    urllib.request.urlretrieve("https://www.catholic.ac.kr/cms/etcResourceOpen.do?site=$cms$NYeyA&key=$cms$MYQwLgFg9gNglsA+gBwE4gHYC8oDpkAmAZkA", "catholic_pranzo.pdf")
    urllib.request.urlretrieve("https://www.catholic.ac.kr/cms/etcResourceOpen.do?site=$cms$NYeyA&key=$cms$MYQwLgFg9gNglsA+gIygOxAOgA4BMBmQA", "catholic_bona.pdf")
    print("This week's menu has been updated.")

def extract_text_from_pdf(pdf_path):
    try:
        with pdfplumber.open(pdf_path) as pdf:
            text = ""
            for page in pdf.pages:
                text += page.extract_text() + "\n"
            return text.strip()
    except Exception as e:
        print(f"Error extracting text from PDF: {e}")
        return ""

def is_buon_pranzo_vacation(text):
    return "방학 중 미운영" in text or ("방학" in text and "미운영" in text)

def is_bona_morning_vacation(text):
    # NEW: Detect if "아침" (Morning) section is completely missing from the table
    #return "아침" not in text
    return False


def is_bona_special_vacation(text):
    return "집중휴무기간" in text


def extract_vacation_range(text):
    match = re.search(r'\d{1,2}/\d{1,2}\(?.*?\)?\s*~\s*\d{1,2}/\d{1,2}\(?.*?\)?', text)
    return match.group(0) if match else None

def preprocess_text_first(text):
    lines = text.strip().split('\n')
    cleaned_lines = []
    for line in lines:
        if any(keyword in line for keyword in ["주 간 메 뉴 표", "구 분", "상기메뉴는", "저희 식당은", "원산지 표시는", "kcal"]):
            continue
        line = re.sub(r"\d{2}/\d{2}\(\w+\)", "", line)
        line = re.sub(r"\(\d{1,3},\d{3}원\)", "", line)
        line = line.replace(" / ", "/")
        if line.strip():
            cleaned_lines.append(line.strip())
    return "\n".join(cleaned_lines)

def preprocess_text_second(text):
    lines = text.strip().split('\n')
    cleaned_lines = []
    for line in lines:
        if any(keyword in line for keyword in ["주 간 메 뉴 표", "구분", "상기메뉴는", "저희 식당은", "원산지 표시는", "kcal"]):
            continue
        line = re.sub(r"\d{2}/\d{2}\(\w+\)", "", line)
        line = re.sub(r"\(\d{1,3},\d{3}원\)", "", line)
        line = line.replace(" / ", "/")
        for word in ["0", "plus", "아침", "점심", "저녁"]:
            line = line.replace(word, "")
        if line.strip():
            cleaned_lines.append(line.strip())
    return "\n".join(cleaned_lines)

def parse_first_restaurant_menu(text):
    menu_data = {"Global Noodle": {}, "One Plate": {}, "metadata": {"isVacation": False}}
    days_of_week = ["Mon", "Tue", "Wed", "Thu", "Fri"]

    # Only initialize day slots for food sections, not metadata
    for section in ["Global Noodle", "One Plate"]:
        for day in days_of_week:
            menu_data[section][day] = []

    global_noodle_lines, one_plate_lines = [], []
    current_section = "Global Noodle"

    for line in text.strip().split('\n'):
        if not line.strip():
            continue
        if "점심" in line:  # Switch section
            current_section = "One Plate"
            continue
        (global_noodle_lines if current_section == "Global Noodle" else one_plate_lines).append(line.strip())

    global_noodle_menu = " ".join(global_noodle_lines).split(" ")
    one_plate_menu = " ".join(one_plate_lines).split(" ")

    def distribute(menu, section):
        for i, item in enumerate(menu):
            menu_data[section][days_of_week[i % 5]].append(item)

    distribute(global_noodle_menu, "Global Noodle")
    distribute(one_plate_menu, "One Plate")

    return menu_data

def parse_second_restaurant_menu(text, is_vacation=False, vacation_range=None):
    menu_data = {"Morning": {}, "Lunch": {}, "Dinner": {}}
    days_of_week = ["Mon", "Tue", "Wed", "Thu", "Fri"]

    for meal in menu_data:
        for day in days_of_week:
            menu_data[meal][day] = []

    menu_items = " ".join(text.strip().split('\n')).split()

    if is_vacation:
        for day in days_of_week:
            menu_data["Morning"][day] = ["방학 중 미운영"]
        current_meal = "Lunch"
        for i, item in enumerate(menu_items):
            if current_meal == "Lunch":
                menu_data["Lunch"][days_of_week[i % 5]].append(item)
                if i == 34:
                    current_meal = "Dinner"
                continue
            if current_meal == "Dinner":
                menu_data["Dinner"][days_of_week[i % 5]].append(item)
    else:
        current_meal = "Morning"
        for i, item in enumerate(menu_items):
            if current_meal == "Morning":
                menu_data["Morning"][days_of_week[i % 4]].append(item)
                if i == 23:
                    current_meal = "Lunch"
                continue
            if current_meal == "Lunch":
                menu_data["Lunch"][days_of_week[(i - 24) % 5]].append(item)
                if i == 59:
                    current_meal = "Dinner"
                continue
            if current_meal == "Dinner":
                menu_data["Dinner"][days_of_week[(i - 60) % 5]].append(item)
    return menu_data

def final():
    # Buon Pranzo
    pdf_path = 'catholic_pranzo.pdf'
    text = extract_text_from_pdf(pdf_path)
    if text:
        cleaned = preprocess_text_first(text)
        if is_buon_pranzo_vacation(text):
            vacation_range = extract_vacation_range(text)
            menu_data = {
                "Global Noodle": {day: ["방학 중 미운영"] for day in ["Mon", "Tue", "Wed", "Thu", "Fri"]},
                "One Plate": {day: ["운영 중지"] for day in ["Mon", "Tue", "Wed", "Thu", "Fri"]},
                "metadata": {
                    "isVacation": True,
                    "vacationMessage": "방학 중 미운영",
                    "vacationPeriod": vacation_range or ""
                }
            }
        else:
            menu_data = parse_first_restaurant_menu(cleaned)
        save_menu_to_json(menu_data, "./Buon_Pranzo.json")

    # Cafe Bona
    pdf_path = 'catholic_bona.pdf'
    text = extract_text_from_pdf(pdf_path)
    if text:
        cleaned = preprocess_text_second(text)
        is_vacation = is_bona_morning_vacation(text)
        is_special_vacation = is_bona_special_vacation(text)
        menu_data = parse_second_restaurant_menu(cleaned, is_vacation, extract_vacation_range(text) if is_vacation else None)
        
        if "metadata" not in menu_data:
            menu_data["metadata"] = {}

        if is_vacation:
            menu_data["metadata"]["morningVacation"] = True
            menu_data["metadata"]["vacationMessageMorning"] = "여름 방학 중 미운영"
            menu_data["metadata"]["vacationPeriod"] = extract_vacation_range(text) or ""
        else:
            menu_data["metadata"]["morningVacation"] = False
        
        if is_special_vacation:
            menu_data["metadata"]["isSpecialVacation"] = True
            menu_data["metadata"]["specialVacationMessage"] = "집중휴무기간"
        else:
            menu_data["metadata"]["isSpecialVacation"] = False
            
        save_menu_to_json(menu_data, "./Café_Bona.json")

    os.remove("catholic_pranzo.pdf")
    os.remove("catholic_bona.pdf")

def save_menu_to_json(menu_data, file_name):
    with open(file_name, "w", encoding="utf-8") as json_file:
        json.dump(menu_data, json_file, indent=4, ensure_ascii=False)
    print(f"Menu data saved to {file_name}")

if __name__ == "__main__":
    request()
    final()
