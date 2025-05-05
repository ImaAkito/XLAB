import json
from collections import defaultdict
from statistics import mean, median
from app.config import Config
import requests

_area_tree = None
_area_name_by_id = {}
_area_level1 = set()
YANDEX_API_KEY = "329c30aa-ac19-49f0-87ba-1281c6c28fc9"
_geocode_cache = {}

def load_area_structure():
    global _area_tree, _area_name_by_id, _area_level1
    if _area_tree:
        return

    with open(Config.AREA_PATH, encoding='utf-8') as f:
        _area_tree = json.load(f)

    def recurse(area, level=0):
        _area_name_by_id[area["id"]] = area["name"]
        if level == 1:
            _area_level1.add(area["id"])
        for child in area.get("areas", []):
            recurse(child, level + 1)

    recurse(_area_tree)

def get_area_name(area_id):
    load_area_structure()
    return _area_name_by_id.get(area_id, f"ID {area_id}")

def yandex_geocode(address):
    if not address:
        print("[GEOCODE] Пустой адрес")
        return None, None
    if address in _geocode_cache:
        print(f"[GEOCODE] Кэш: {address} -> {_geocode_cache[address]}")
        return _geocode_cache[address]
    print(f"[GEOCODE] Запрос: {address}")
    url = "https://geocode-maps.yandex.ru/1.x/"
    params = {
        "apikey": YANDEX_API_KEY,
        "geocode": address,
        "format": "json",
        "lang": "ru_RU"
    }
    try:
        resp = requests.get(url, params=params, timeout=5)
        resp.raise_for_status()
        geo = resp.json()
        pos = geo["response"]["GeoObjectCollection"]["featureMember"]
        if not pos:
            print(f"[GEOCODE] Не найдено: {address}")
            _geocode_cache[address] = (None, None)
            return None, None
        coords = pos[0]["GeoObject"]["Point"]["pos"].split()
        lat, lng = float(coords[1]), float(coords[0])
        print(f"[GEOCODE] Найдено: {address} -> {lat}, {lng}")
        _geocode_cache[address] = (lat, lng)
        return lat, lng
    except Exception as e:
        print(f"[YANDEX GEOCODE ERROR] {address}: {e}")
        _geocode_cache[address] = (None, None)
        return None, None

def get_map_data(vacancies, selected_city=None):
    print(f"[DEBUG] get_map_data called! selected_city={selected_city}")
    """
    Для каждой вакансии:
    1. Если есть координаты — используем их.
    2. Если есть адрес — геокодируем адрес + город.
    3. Если есть компания — геокодируем 'Компания, Город'.
    4. Если ничего не найдено — ставим в центр города.
    Если выбран несколько городов — группируем вакансии по городу и применяем логику для каждого.
    """
    from collections import defaultdict
    map_points = []
    city_to_vacancies = defaultdict(list)
    if selected_city and isinstance(selected_city, list):
        for v in vacancies:
            city = None
            addr = v.get("address", {})
            if addr.get("city"):
                city = addr["city"]
            elif v.get("area", {}).get("name"):
                city = v["area"]["name"]
            for sc in selected_city:
                if city and city.lower() == sc.lower():
                    city_to_vacancies[sc].append(v)
                    break
            else:
                city_to_vacancies[selected_city[0]].append(v)
    else:
        city_to_vacancies[selected_city] = vacancies

    for city, vacs in city_to_vacancies.items():
        city_center_coords = yandex_geocode(city) if city else (None, None)
        for v in vacs:
            addr = v.get("address", {})
            lat, lng = addr.get("lat"), addr.get("lng")
            debug_info = f"[MAP] {v.get('name')} | "
            if lat and lng:
                debug_info += f"coords from vacancy: {lat}, {lng}"
            else:
                address_parts = []
                if addr.get("street"):
                    address_parts.append(addr["street"])
                if city:
                    address_parts.append(city)
                address = ", ".join(address_parts)
                if address:
                    lat, lng = yandex_geocode(address)
                    debug_info += f"geocode address: {address} -> {lat}, {lng} | "
                if (not lat or not lng) and v.get("employer", {}).get("name") and city:
                    query = f"{v['employer']['name']}, {city}"
                    lat, lng = yandex_geocode(query)
                    debug_info += f"geocode company: {query} -> {lat}, {lng} | "
                if (not lat or not lng) and city_center_coords:
                    lat, lng = city_center_coords
                    debug_info += f"city center fallback: {lat}, {lng}"
            print(debug_info)
            if not lat or not lng:
                print(f"[SKIP] {v.get('name')} — no coordinates even after fallback")
                continue
            point = {
                "lat": lat,
                "lng": lng,
                "title": v.get("name"),
                "employer": v.get("employer", {}).get("name"),
                "salary": v.get("salary"),
            }
            map_points.append(point)
    return map_points

def get_region_aggregates(vacancies):
    load_area_structure()
    region_data = defaultdict(list)

    for v in vacancies:
        area = v.get("area", {})
        area_id = str(area.get("id"))
        if not area_id:
            continue

        top_region = find_top_level_region(area_id)
        if not top_region:
            continue

        region_data[top_region].append(v)

    region_summary = {
        "count": {},
        "mean": {},
        "median": {}
    }

    for region_id, region_vacancies in region_data.items():
        salaries = []
        for v in region_vacancies:
            s = v.get("salary")
            if not s:
                continue
            f, t = s.get("from"), s.get("to")
            if f and t:
                salaries.append((f + t) / 2)
            elif f:
                salaries.append(f)
            elif t:
                salaries.append(t)

        region_summary["count"][region_id] = len(region_vacancies)
        if salaries:
            region_summary["mean"][region_id] = round(mean(salaries), 2)
            region_summary["median"][region_id] = round(median(salaries), 2)
        else:
            region_summary["mean"][region_id] = None
            region_summary["median"][region_id] = None

    return region_summary

def find_top_level_region(area_id):
    load_area_structure()
    current = area_id
    visited = set()

    while current and current not in visited:
        visited.add(current)
        if current in _area_level1:
            return current
        parent = find_parent_id(current)
        if parent == current:
            break
        current = parent

    return None

def find_parent_id(child_id):
    def search(tree, parent=None):
        if tree["id"] == child_id:
            return parent
        for sub in tree.get("areas", []):
            result = search(sub, tree["id"])
            if result:
                return result
        return None

    return search(_area_tree)
