import json
import requests
from datetime import datetime, timedelta
from app.config import Config
from concurrent.futures import ThreadPoolExecutor, as_completed
from time import sleep
import re
import os
API_URL = "https://api.rabota.by/vacancies"

_area_tree = None
_area_index = {}

def extract_filter_data(form):
    filters = {}

    for key in Config.ALLOWED_FILTERS:
        if key == "text":
            filters[key] = form.get("search", "").strip()
        elif key == "area":
            selected_areas = form.getlist("region")
            filters[key] = selected_areas if selected_areas else []
        elif key in ("experience", "employment", "schedule"):
            filters[key] = form.getlist(key + "[]")
        elif key in ("salary_from", "salary_to"):
            value = form.get(key)
            filters[key] = int(value) if value and value.isdigit() else None
        elif key == "only_with_salary":
            filters[key] = "only_with_salary" in form
        elif key in ("date_from", "date_to"):
            value = form.get(key)
            try:
                filters[key] = value if value else None
            except:
                filters[key] = None

    return filters

def generate_filter_query(filters):
    load_area_tree()
    params = {}

    if filters.get("text"):
        params["text"] = filters["text"]

    area_filter = filters.get("area")
    if area_filter:
        normalized_areas = [str(a) for a in area_filter]
        lca_area_id = find_common_area(normalized_areas)
        print(f"[DEBUG] LCA результат для {normalized_areas}: {lca_area_id}")
        if lca_area_id:
            params["area"] = lca_area_id
    else:
        print("[DEBUG] Регион не выбран — устанавливаю area = '16' (Беларусь)")
        params["area"] = "16"

    if filters.get("salary_from") is not None:
        params["salary_from"] = filters["salary_from"]
    if filters.get("salary_to") is not None:
        params["salary_to"] = filters["salary_to"]

    if "only_with_salary" in filters:
        params["only_with_salary"] = filters["only_with_salary"]

    for field in ("experience", "employment", "schedule"):
        values = filters.get(field)
        if isinstance(values, list) and values:
            params[field] = values

    for field in ("date_from", "date_to"):
        value = filters.get(field)
        if value:
            try:
                datetime.fromisoformat(value)
                params[field] = value
            except ValueError:
                print(f"[WARNING] Неверный формат даты: {field} = {value}")

    if "date_from" not in params or not params["date_from"]:
        params["date_from"] = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')
    if "date_to" not in params or not params["date_to"]:
        params["date_to"] = datetime.now().strftime('%Y-%m-%d')
    print(f"[DEBUG] Используем диапазон дат: {params['date_from']} — {params['date_to']}")

    return params

def load_area_tree():
    global _area_tree, _area_index
    if _area_tree:
        return

    with open(Config.AREA_PATH, encoding='utf-8') as f:
        _area_tree = json.load(f)
        _area_index = {}

        def index_area(area, parent=None):
            _area_index[area['id']] = {
                'name': area['name'],
                'parent_id': parent,
                'id': area['id']
            }
            for child in area.get('areas', []):
                index_area(child, area['id'])

        index_area(_area_tree)

def find_common_area(area_ids):
    load_area_tree()

    if not area_ids:
        return None

    if len(area_ids) == 1:
        print(f"[DEBUG] Одиночный регион: {area_ids[0]}")
        return area_ids[0]

    def get_path(area_id):
        path = []
        current = area_id
        visited = set()
        while current and current not in visited:
            visited.add(current)
            path.append(current)
            current = _area_index.get(current, {}).get("parent_id")
        return path[::-1]

    paths = [get_path(aid) for aid in area_ids if aid in _area_index]
    if not paths:
        print("[DEBUG] Нет путей для LCA")
        return None

    min_len = min(len(p) for p in paths)
    lca = None
    for i in range(min_len):
        step = [p[i] for p in paths]
        if all(x == step[0] for x in step):
            lca = step[0]
        else:
            break

    print(f"[DEBUG] Найден LCA: {lca}")
    return lca

from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import os
import re

def load_vacancies_with_filters(params, original_area_ids=None):
    def fetch_all_in_range(start_date, end_date, base_params):
        all_items = []
        step = timedelta(days=7)

        current_week_start = start_date
        while current_week_start < end_date:
            week_end = min(current_week_start + step, end_date)
            items = fetch_segment(current_week_start, week_end, base_params)
            if len(items) >= 2000:
                print(f"[INFO] Неделя {current_week_start.date()} — {week_end.date()} перегружена, дроблю по дням...")
                current_day_start = current_week_start
                while current_day_start < week_end:
                    day_end = current_day_start + timedelta(days=1)
                    items_day = fetch_segment(current_day_start, day_end, base_params)
                    if len(items_day) >= 2000:
                        print(f"[INFO] День {current_day_start.date()} перегружен, дроблю по 6 часам...")
                        current_hour = current_day_start
                        while current_hour < day_end:
                            next_hour = current_hour + timedelta(hours=6)
                            items_hour = fetch_segment(current_hour, next_hour, base_params)
                            all_items.extend(items_hour)
                            current_hour = next_hour
                    else:
                        all_items.extend(items_day)
                    current_day_start = day_end
            else:
                all_items.extend(items)
            current_week_start = week_end
        return all_items

    def fetch_segment(start, end, base_params):
        fmt = "%Y-%m-%dT%H:%M:%S" if isinstance(start, datetime) and start.time() != datetime.min.time() else "%Y-%m-%d"
        segment_params = dict(base_params)
        segment_params["date_from"] = start.strftime(fmt)
        segment_params["date_to"] = end.strftime(fmt)

        print(f"[INFO] Загружаю вакансии: {segment_params['date_from']} → {segment_params['date_to']}")
        segment_items = []

        try:
            first_page = fetch_page(0, segment_params)
            total_pages = first_page.get("pages", 0)
            segment_items.extend(first_page.get("items", []))
            print(f"[INFO] Получена страница 1/{total_pages}, вакансий: {len(first_page.get('items', []))}")

            with ThreadPoolExecutor(max_workers=10) as executor:
                futures = [executor.submit(fetch_page, page, segment_params) for page in range(1, total_pages)]
                for future in as_completed(futures):
                    result = future.result()
                    page_items = result.get("items", [])
                    print(f"[INFO] Получена страница {result.get('page', '?') + 1}/{total_pages}, вакансий: {len(page_items)}")
                    segment_items.extend(page_items)
        except Exception as e:
            print(f"[ERROR] Ошибка при загрузке сегмента {segment_params['date_from']} — {segment_params['date_to']}: {e}")

        print(f"[SUCCESS] Загружено всего за сегмент: {len(segment_items)}")
        return segment_items

    if "date_from" not in params or not params["date_from"]:
        params["date_from"] = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')
    if "date_to" not in params or not params["date_to"]:
        params["date_to"] = datetime.now().strftime('%Y-%m-%d')
    print(f"[DEBUG] Используем диапазон дат: {params['date_from']} — {params['date_to']}")

    start_date = datetime.strptime(params["date_from"].split("T")[0], "%Y-%m-%d")
    end_date = datetime.strptime(params["date_to"].split("T")[0], "%Y-%m-%d")

    all_items = fetch_all_in_range(start_date, end_date, params)
    cleaned = [extract_relevant_fields(v) for v in all_items]

    keywords_path = os.path.join("app", "data", "vacancies.json")
    try:
        with open(keywords_path, encoding="utf-8") as f:
            it_keywords = json.load(f).get("it_keywords", [])
            print(f"[DEBUG] Загружено ключевых слов для IT: {len(it_keywords)}")
    except Exception as e:
        print(f"[ERROR] Не удалось загрузить ключевые слова из vacancies.json: {e}")
        it_keywords = []

    def is_it_vacancy(v):
        fields = [
            (v.get('name') or '').lower(),
            (v.get('description') or '').lower(),
            ' '.join([s.get('name', '').lower() for s in (v.get('key_skills') or [])]),
            (v.get('employer', {}).get('name') or '').lower()
        ]
        joined = ' '.join(fields)
        for kw in it_keywords:
            kw_regex = re.escape(kw)
            if re.search(r'\b' + kw_regex + r'\b', joined) or kw in joined:
                return True
        return False

    before = len(cleaned)
    cleaned = [v for v in cleaned if is_it_vacancy(v)]
    print(f'[DEBUG] IT-фильтрация: до={before}, после={len(cleaned)}')

    if original_area_ids:
        original_area_ids = set(str(a) for a in original_area_ids)
        cleaned = [v for v in cleaned if str(v.get('area', {}).get('id')) in original_area_ids]
        print(f"[DEBUG] Фильтрация по исходным регионам: осталось {len(cleaned)} вакансий")

    return cleaned



def fetch_page(page, base_params):
    params = dict(base_params)
    params["page"] = page
    headers = {
        "User-Agent": "JobAnalyzer/1.0"
    }

    for attempt in range(3):
        try:
            response = requests.get(API_URL, params=params, headers=headers, timeout=10)
            if response.status_code == 200:
                data = response.json()
                data["page"] = page
                return data
            else:
                print(f"[WARNING] Ошибка {response.status_code} при загрузке страницы {page}")
        except Exception as e:
            print(f"[ERROR] Ошибка при запросе страницы {page}: {e}")
        sleep(1)

    print(f"[FAIL] Не удалось загрузить страницу {page}")
    return {"items": [], "page": page}

def extract_relevant_fields(v):
    address = v.get("address") or {}
    salary = v.get("salary") or {}
    employer = v.get("employer") or {}
    logo_urls = employer.get("logo_urls") or {}
    return {
        "id": v.get("id"),
        "name": v.get("name"),
        "type": v.get("type"),
        "archived": v.get("archived"),

        "area": v.get("area"),
        "address": {
            "lat": address.get("lat"),
            "lng": address.get("lng"),
        },

        "salary": {
            "from": salary.get("from"),
            "to": salary.get("to"),
            "currency": salary.get("currency"),
            "gross": salary.get("gross"),
        },

        "experience": v.get("experience"),
        "employment": v.get("employment"),
        "schedule": v.get("schedule"),
        "work_format": v.get("work_format"),

        "working_hours": v.get("working_hours"),
        "published_at": v.get("published_at"),
        "created_at": v.get("created_at"),
        "description": v.get("description"),

        "employer": {
            "id": employer.get("id"),
            "name": employer.get("name")
        },

        "key_skills": [s["name"] for s in v.get("key_skills", []) if "name" in s],
        "url": v.get("alternate_url"),
        "company_logo": logo_urls.get("90")
    }


