import pdfplumber
import re
import json
import urllib.request
import os

def request():
    #urllib.request.urlretrieve("https://www.catholic.ac.kr/cms/etcResourceOpen.do?site=$cms$NYeyA&key=$cms$MYQwLgFg9gNglsA+gBwE4gHYC8oDpkAmAZkA", "catholic_pranzo.pdf")
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
    menu_data = {"Lunch": {}, "Dinner": {}}
    days_of_week = ["Mon", "Tue", "Wed", "Thu", "Fri"]

    # Initialize menu entries for each day and each meal
    for meal in menu_data:
        for day in days_of_week:
            menu_data[meal][day] = []

    # Combine all menu items into a single list
    menu_items = " ".join(text.strip().split('\n')).split()

    # Helper function to distribute menu items across meals and days
    def distribute_menu_items(menu_items):
        lunch_day_index = 0  # Index for Lunch and Dinner (cycles every 5 days: Mon-Fri)
        dinner_day_index = 0
        current_meal = "Lunch"  # Start with Lunch

        # Iterate through the menu items and distribute them
        for i, item in enumerate(menu_items):
            if current_meal == "Lunch":
                #i+=1
                # Fill Lunch menus (cycle every 5 days: Mon-Fri)
                lunch_day_index = i % 5 # Cycle through 4 days (Mon-Thu)
                menu_data["Lunch"][days_of_week[lunch_day_index]].append(item)
                # Switch to Dinner after filling 30 Lunch items (6 items * 5 days)
                if i == 35: # 7 items * 5 days = 35 items
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
    menu_data = "방학중 미운영"

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
    #os.remove("catholic_pranzo.pdf")
    os.remove("catholic_bona.pdf")
    
if __name__ == "__main__":
    request()
    final()