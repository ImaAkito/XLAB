class Config:
    DATA_PATH = 'app/data/vacancies.json'
    AREA_PATH = 'app/data/belarus_structure.json'
    ALLOWED_FILTERS = {
        "text": str,
        "area": int,
        "salary_from": int,
        "salary_to": int,
        "only_with_salary": bool,
        "experience": str,
        "employment": str,
        "schedule": str,
        "date_from": str,
        "date_to": str,
    }
    EXPERIENCE_VALUES = {
        "noExperience": "Нет опыта",
        "between1And3": "От 1 до 3 лет",
        "between3And6": "От 3 до 6 лет",
        "moreThan6": "Более 6 лет"
    }
    EMPLOYMENT_VALUES = {
        "full": "Полная занятость",
        "part": "Частичная занятость",
        "project": "Проектная работа",
        "volunteer": "Волонтёрство",
        "probation": "Стажировка"
    }
    SCHEDULE_VALUES = {
        "fullDay": "Полный день",
        "shift": "Сменный график",
        "flexible": "Гибкий график",
        "remote": "Удалённая работа",
        "flyInFlyOut": "Вахтовый метод"
    }


