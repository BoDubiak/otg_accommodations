import csv
import logging
import time

import requests

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)

API_KEY = "YOUR_GOOGLE_API_KEY"  # Замініть на свій Google API Key
OUTPUT_FILE = "lviv_otg_accommodations.csv"
TYPES = ["lodging", "hostel", "apartment"]  # Типи місць для пошуку

# Географічні межі Львівської ОТГ
BOUNDING_BOX = {
    "north": 49.940,  # Північ
    "south": 49.740,  # Південь
    "west": 23.870,   # Захід
    "east": 24.180    # Схід
}

# Крок сітки
GRID_STEP = 0.02  # Розмір кроку в градусах

def fetch_places(location, radius, place_type):
    """
    Отримує місця через Nearby Search API.
    """
    url = f"https://maps.googleapis.com/maps/api/place/nearbysearch/json?location={location}&radius={radius}&type={place_type}&language=uk&key={API_KEY}"
    all_results = []
    while url:
        try:
            response = requests.get(url, timeout=10)
            response.raise_for_status()
        except requests.RequestException as exc:
            logger.error("Failed to fetch places for %s (%s): %s", location, place_type, exc)
            break
        try:
            data = response.json()
        except ValueError as exc:
            logger.error("Failed to decode Nearby Search response for %s (%s): %s", location, place_type, exc)
            break
        status = data.get("status")
        if status and status not in {"OK", "ZERO_RESULTS"}:
            logger.warning(
                "Nearby Search returned status %s for %s (%s). Message: %s",
                status,
                location,
                place_type,
                data.get("error_message"),
            )
            break
        all_results.extend(data.get("results", []))
        # Перевірка наявності токена для наступної сторінки
        next_page_token = data.get("next_page_token")
        if next_page_token:
            time.sleep(2)  # Затримка для активації токена
            url = f"https://maps.googleapis.com/maps/api/place/nearbysearch/json?pagetoken={next_page_token}&language=uk&key={API_KEY}"
        else:
            url = None
    return all_results

def fetch_place_details(place_id):
    """
    Отримує детальну інформацію про місце через Place Details API.
    """
    url = f"https://maps.googleapis.com/maps/api/place/details/json?place_id={place_id}&fields=name,formatted_address,formatted_phone_number,website,types&language=uk&key={API_KEY}"
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
    except requests.RequestException as exc:
        logger.error("Failed to fetch details for place_id %s: %s", place_id, exc)
        return {}
    try:
        data = response.json()
    except ValueError as exc:
        logger.error("Failed to decode Place Details response for place_id %s: %s", place_id, exc)
        return {}
    status = data.get("status")
    if status and status not in {"OK"}:
        logger.warning(
            "Place Details returned status %s for place_id %s. Message: %s",
            status,
            place_id,
            data.get("error_message"),
        )
        return {}
    result = data.get("result", {})
    return {
        "phone": result.get("formatted_phone_number"),
        "website": result.get("website"),
        "types": result.get("types", []),
    }

def is_relevant(place, details):
    """
    Фільтрує результати за назвою та типами.
    """
    name = place.get("name", "").lower()
    types = details.get("types", [])
    excluded_keywords = ["restaurant", "bar", "shop", "museum"]
    if any(keyword in name for keyword in excluded_keywords):
        return False
    if "lodging" not in types and "hotel" not in name and "hostel" not in name and "apartment" not in name:
        return False
    return True

def write_to_csv(data):
    """
    Записує результати у CSV-файл із роздільником '|||'.
    """
    with open(OUTPUT_FILE, mode="w", newline="", encoding="utf-8") as file:
        writer = csv.writer(file, delimiter="|||")
        writer.writerow(["Назва", "Адреса", "Широта", "Довгота", "Рейтинг", "Телефон", "Сайт", "Place ID"])
        for place in data:
            writer.writerow([
                place.get("name"),
                place.get("address"),
                place.get("latitude"),
                place.get("longitude"),
                place.get("rating"),
                place.get("phone"),
                place.get("website"),
                place.get("place_id"),
            ])

# Основний процес
all_places = []
lat = BOUNDING_BOX["south"]
while lat <= BOUNDING_BOX["north"]:
    lng = BOUNDING_BOX["west"]
    while lng <= BOUNDING_BOX["east"]:
        location = f"{lat},{lng}"
        for place_type in TYPES:
            logger.info(f"Збираємо {place_type} у локації {location}")
            places = fetch_places(location, 1000, place_type)  # Радіус у метрах
            for place in places:
                details = fetch_place_details(place["place_id"])
                if not details:
                    continue
                if is_relevant(place, details):
                    all_places.append({
                        "name": place.get("name"),
                        "address": place.get("vicinity"),
                        "latitude": place["geometry"]["location"]["lat"],
                        "longitude": place["geometry"]["location"]["lng"],
                        "rating": place.get("rating"),
                        "phone": details.get("phone"),
                        "website": details.get("website"),
                        "place_id": place.get("place_id"),
                    })
        lng += GRID_STEP
    lat += GRID_STEP

# Запис даних у CSV
write_to_csv(all_places)
print(f"Дані збережено у {OUTPUT_FILE}")
