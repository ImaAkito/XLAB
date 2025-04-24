import json
import requests
from datetime import datetime
from app.config import Config
from concurrent.futures import ThreadPoolExecutor, as_completed
from time import sleep
import re

API_URL = "https://api.rabota.by/vacancies"

# Кэш структуры областей
_area_tree = None
_area_index = {}

def extract_filter_data(form):
    # Преобразуем значения фильтров из формы в словарь
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
    """
    Формирует словарь параметров (params) для запроса к API или локальной фильтрации.
    Обрабатывает все поля из filters: текст, area, зарплаты, опыт, занятость, график, даты.
    """
    load_area_tree()
    params = {}

    # Текст
    if filters.get("text"):
        params["text"] = filters["text"]

    # Регион
    if filters.get("area"):
        normalized_areas = [str(a) for a in filters["area"]]
        lca_area_id = find_common_area(normalized_areas)
        print(f"[DEBUG] LCA результат для {normalized_areas}: {lca_area_id}")
        if lca_area_id:
            params["area"] = lca_area_id

    # Зарплата
    if filters.get("salary_from") is not None:
        params["salary_from"] = filters["salary_from"]
    if filters.get("salary_to") is not None:
        params["salary_to"] = filters["salary_to"]

    # Даже если False — сохраняем
    if "only_with_salary" in filters:
        params["only_with_salary"] = filters["only_with_salary"]

    # Опыт, занятость, график
    for field in ("experience", "employment", "schedule"):
        values = filters.get(field)
        if isinstance(values, list) and values:
            params[field] = values

    # Даты
    for field in ("date_from", "date_to"):
        value = filters.get(field)
        if value:
            try:
                datetime.fromisoformat(value)
                params[field] = value
            except ValueError:
                print(f"[WARNING] Неверный формат даты: {field} = {value}")

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
    """
    Находит наименьшего общего предка (LCA) для списка ID регионов.
    Если один регион — возвращает его.
    """
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

def load_vacancies_with_filters(params):
    print("[INFO] Начинается загрузка вакансий через API rabota.by...")
    per_page = 50
    params = dict(params)  # создаём копию, чтобы не менять оригинал
    params["per_page"] = per_page
    params["page"] = 0

    # Получаем первую страницу, чтобы узнать количество
    first_response = fetch_page(0, params)
    total_pages = first_response.get("pages", 0)
    all_items = first_response.get("items", [])

    print(f"[INFO] Получена страница 1/{total_pages}, вакансий: {len(all_items)}")

    # Загружаем оставшиеся страницы
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = []
        for page in range(1, total_pages):
            futures.append(executor.submit(fetch_page, page, params))

        for future in as_completed(futures):
            result = future.result()
            page_num = result.get("page", "?")
            items = result.get("items", [])
            print(f"[INFO] Получена страница {page_num + 1}/{total_pages}, вакансий: {len(items)}")
            all_items.extend(items)

    print(f"[SUCCESS] Загружено всего вакансий: {len(all_items)}")

    cleaned = [extract_relevant_fields(v) for v in all_items]

    # ВКЛЮЧАЮ ФИЛЬТРАЦИЮ ПО IT-КЛЮЧЕВЫМ СЛОВАМ
    it_keywords = [
        "python", "java", "javascript", "frontend", "backend", "fullstack", "devops", "qa", "тестировщик",
        "data scientist", "data analyst", "ml", "ai", "business analyst", "системный аналитик", "ux/ui",
        "product manager", "project manager", "1c", "сетевой инженер", "системный администратор", "ux", "ui",
        "game developer", "android", "ios", "c++", "c#", "php", "kotlin", "go", "sql", "oracle", "linux", "unix",
        "docker", "kubernetes", "cloud", "aws", "azure", "flutter", "node", "react", "angular", "vue", "typescript"
    ]
    def is_it_vacancy(v):
        fields = [
            (v.get('name') or '').lower(),
            (v.get('description') or '').lower(),
            ' '.join([s.get('name', '').lower() for s in (v.get('key_skills') or [])]),
            (v.get('employer', {}).get('name') or '').lower()
        ]
        for kw in it_keywords:
            kw_regex = re.escape(kw)
            for field in fields:
                if re.search(r'\b' + kw_regex + r'\b', field) or kw in field:
                    return True
        return False
    before = len(cleaned)
    cleaned = [v for v in cleaned if is_it_vacancy(v)]
    print(f'[DEBUG] IT-фильтрация: до={before}, после={len(cleaned)}')

    return cleaned

def fetch_page(page, base_params):
    """
    Загружает одну страницу с API rabota.by
    """
    params = dict(base_params)
    params["page"] = page
    headers = {
        "User-Agent": "JobAnalyzer/1.0"
    }

    for attempt in range(3):  # Повторные попытки при ошибках
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
        sleep(1)  # Подождать перед следующей попыткой

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

        "key_skills": v.get("key_skills"),
        "url": v.get("alternate_url"),
        "company_logo": logo_urls.get("90")
    }


