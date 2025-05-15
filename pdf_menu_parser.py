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
    """
    Extracts text from the entire PDF.

    Args:
        pdf_path (str): The path to the PDF file.

    Returns:
        str: The extracted text, or an empty string if extraction fails.
    """
    try:
        with pdfplumber.open(pdf_path) as pdf:
            text = ""
            for page in pdf.pages:
                text += page.extract_text() + "\n"
            return text.strip()
    except Exception as e:
        print(f"Error extracting text from PDF: {e}")
        return ""  # Ensure an empty string is returned on failure

def preprocess_text_first(text):
    """
    Preprocesses the extracted text to remove unnecessary lines and content.

    Args:
        text (str): The raw text extracted from the PDF.

    Returns:
        str: The cleaned text.
    """
    lines = text.strip().split('\n')
    cleaned_lines = []

    for line in lines:
        # Remove lines containing unnecessary keywords or patterns
        if any(keyword in line for keyword in [
            "주 간 메 뉴 표", "구 분", "상기메뉴는", "저희 식당은", "원산지 표시는", "kcal"
        ]):
            continue
        # Remove dates like "03/24(월)" or "03/25(화)"
        line = re.sub(r"\d{2}/\d{2}\(\w+\)", "", line)
        # Remove prices like "(5,500원)" or "(6,500원)"
        line = re.sub(r"\(\d{1,3},\d{3}원\)", "", line)
        # Replace " / " with "/"
        line = line.replace(" / ", "/")
        # Add the cleaned line if it's not empty
        if line.strip():
            cleaned_lines.append(line.strip())

    return "\n".join(cleaned_lines)

def preprocess_text_second(text):
    """
    Preprocesses the extracted text to remove unnecessary lines and specific unwanted keywords.

    Args:
        text (str): The raw text extracted from the PDF.

    Returns:
        str: The cleaned text.
    """
    lines = text.strip().split('\n')
    cleaned_lines = []

    for line in lines:
        # Remove lines containing unnecessary keywords or patterns
        if any(keyword in line for keyword in [
            "주 간 메 뉴 표", "구분", "상기메뉴는", "저희 식당은", "원산지 표시는", "kcal"
        ]):
            continue

        # Remove dates like "03/24(월)" or "03/25(화)"
        line = re.sub(r"\d{2}/\d{2}\(\w+\)", "", line)
        # Remove prices like "(5,500원)" or "(6,500원)"
        line = re.sub(r"\(\d{1,3},\d{3}원\)", "", line)
        # Replace " / " with "/"
        line = line.replace(" / ", "/")
        # Remove specific unwanted keywords
        line = line.replace("0", "")
        line = line.replace("plus", "")
        line = line.replace("아침", "")
        line = line.replace("점심", "")
        line = line.replace("저녁", "")

        # Add the cleaned line if it's not empty
        if line.strip():
            cleaned_lines.append(line.strip())

    return "\n".join(cleaned_lines)

def parse_first_restaurant_menu(text):
    """
    Parses the cleaned text to allocate menu items to days of the week for Global Noodle and One Plate,
    cycling through every 5 menus for Monday to Friday.

    Args:
        text (str): The cleaned text extracted from the PDF.

    Returns:
        dict: A dictionary containing the parsed menu data, structured as follows:
              {
                  "Global Noodle": {
                      "월": ["menu1"],
                      "화": ["menu2"],
                      ...
                  },
                  "One Plate": {
                      "월": ["menu1"],
                      "화": ["menu2"],
                      ...
                  }
              }
    """
    menu_data = {"Global Noodle": {}, "One Plate": {}}
    days_of_week = ["Mon", "Tue", "Wed", "Thu", "Fri"]

    # Initialize menu entries for each day in both sections
    for section in menu_data:
        for day in days_of_week:
            menu_data[section][day] = []

    # Split the text into two sections based on the "점심" divider
    global_noodle_lines = []
    one_plate_lines = []
    current_section = "Global Noodle"
    for line in text.strip().split('\n'):
        line = line.strip()
        # Skip irrelevant lines
        if not line:
            continue

        # Switch to "One Plate" section when encountering the "점심" divider
        if "점심" in line:
            current_section = "One Plate"
            continue

        # Add lines to the appropriate section
        if current_section == "Global Noodle":
            global_noodle_lines.append(line)
        elif current_section == "One Plate":
            one_plate_lines.append(line)

    # Combine all menu items into a single list for each section
    global_noodle_menu = " ".join(global_noodle_lines).split(" ")
    one_plate_menu = " ".join(one_plate_lines).split(" ")

    # Helper function to distribute menu items across days (5-day cycle)
    def distribute_menu_items(menu, section):
        for i, item in enumerate(menu):
            day_index = i % 5  # Cycle through 5 days of the week
            menu_data[section][days_of_week[day_index]].append(item)

    # Distribute menu items for each section
    distribute_menu_items(global_noodle_menu, "Global Noodle")
    distribute_menu_items(one_plate_menu, "One Plate")

    return menu_data

def parse_second_restaurant_menu(text):
    """
    Parses the cleaned text to allocate menu items to Morning, Lunch, and Dinner
    for 5 days a week, ensuring Morning menus cycle every 4 times (Monday to Thursday)
    and Lunch/Dinner menus cycle every 5 times (Monday to Friday).

    Args:
        text (str): The cleaned text extracted from the PDF.

    Returns:
        dict: A dictionary containing the parsed menu data, structured as follows:
              {
                  "Morning": {
                      "월": ["item1", "item2", ...],
                      "화": [...],
                      ...
                  },
                  "Lunch": { ... },
                  "Dinner": { ... }
              }
    """
    menu_data = {"Morning": {}, "Lunch": {}, "Dinner": {}}
    days_of_week = ["Mon", "Tue", "Wed", "Thu", "Fri"]

    # Initialize menu entries for each day and each meal
    for meal in menu_data:
        for day in days_of_week:
            menu_data[meal][day] = []

    # Combine all menu items into a single list
    menu_items = " ".join(text.strip().split('\n')).split()

    # Helper function to distribute menu items across meals and days
    def distribute_menu_items(menu_items):
        morning_day_index = 0  # Index for Morning (cycles every 4 days: Mon-Thu)
        lunch_day_index = 0  # Index for Lunch and Dinner (cycles every 5 days: Mon-Fri)
        dinner_day_index = 0
        current_meal = "Morning"  # Start with Morning

        # Iterate through the menu items and distribute them
        for i, item in enumerate(menu_items):
            if current_meal == "Morning":
                morning_day_index = i % 4 # Cycle through 4 days (Mon-Thu)
                menu_data["Morning"][days_of_week[morning_day_index]].append(item)
                # Switch to Lunch after filling 24 Morning items
                if i == 23:  # 6 items * 4 days = 24 items
                    current_meal = "Lunch"
                continue

            if current_meal == "Lunch":
                i+=1
                # Fill Lunch menus (cycle every 5 days: Mon-Fri)
                lunch_day_index = i % 5 # Cycle through 4 days (Mon-Thu)
                menu_data["Lunch"][days_of_week[lunch_day_index]].append(item)
                # Switch to Dinner after filling 30 Lunch items (6 items * 5 days)
                if i == 59: # 7 items * 5 days = 35 items
                    current_meal = "Dinner"
                continue

            if current_meal == "Dinner":
                i+=1
                dinner_day_index = i % 5 # Cycle through 5 days (Mon-Fri)
                menu_data["Dinner"][days_of_week[dinner_day_index]].append(item)

    # Distribute menu items
    distribute_menu_items(menu_items)

    return menu_data

def save_menu_to_json(menu_data, file_name):
    """
    Saves the parsed menu data to a JSON file.

    Args:
        menu_data (dict): The parsed menu data.
        file_name (str): The name of the JSON file to save the data to.
    """
    with open(file_name, "w", encoding="utf-8") as json_file:
        json.dump(menu_data, json_file, indent=4, ensure_ascii=False)
    print(f"Menu data saved to {file_name}")

def final():
    pdf_file_path = 'catholic_pranzo.pdf'
    extracted_text = extract_text_from_pdf(pdf_file_path)
    if extracted_text:
        cleaned_text = preprocess_text_first(extracted_text)
        menu_data = parse_first_restaurant_menu(cleaned_text)

        # Save the parsed menu data to Buon_Pranzo.json
        output_file_path = "./Buon_Pranzo.json"
        with open(output_file_path, "w", encoding="utf-8") as json_file:
            json.dump(menu_data, json_file, indent=4, ensure_ascii=False)
        print(f"Menu data saved to {output_file_path}")

    # Example usage for the second restaurant
    pdf_file_path = 'catholic_bona.pdf'
    extracted_text = extract_text_from_pdf(pdf_file_path)
    if extracted_text:
        cleaned_text = preprocess_text_second(extracted_text)
        menu_data = parse_second_restaurant_menu(cleaned_text)

        # Save the parsed menu data to Café_Bona.json
        output_file_path = "./Café_Bona.json"
        with open(output_file_path, "w", encoding="utf-8") as json_file:
            json.dump(menu_data, json_file, indent=4, ensure_ascii=False)
        print(f"Menu data saved to {output_file_path}")
    else:
        print("Failed to extract text from the PDF.")

    #remove used pdf files
    os.remove("catholic_pranzo.pdf")
    os.remove("catholic_bona.pdf")
    
if __name__ == "__main__":
    request()
    final()
