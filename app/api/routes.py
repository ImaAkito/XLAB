from flask import Blueprint, render_template, request, redirect, url_for, jsonify
from app.api.utils import extract_filter_data, generate_filter_query, load_vacancies_with_filters, load_area_tree, _area_index
from app.services.visualization import generate_all_visualizations
import os
from datetime import datetime

api_bp = Blueprint('api', __name__)

@api_bp.route('/')
def index():
    return render_template('index.html')

@api_bp.route('/analyze', methods=['POST'])
def analyze():
    # Извлекаем фильтры из формы
    filters = extract_filter_data(request.form)

    # --- Fallback логика ---
    def get_vacancies_with_fallback(filters):
        # 1. Пробуем по выбранным регионам (города/области)
        filter_params = generate_filter_query(filters)
        filtered_vacancies = load_vacancies_with_filters(filter_params, original_area_ids=filters.get("area", []))
        if filtered_vacancies:
            return filtered_vacancies, filter_params
        # 2. Если выбраны города, пробуем по их областям
        area_ids = filters.get('area', [])
        load_area_tree()
        parent_areas = set()
        for aid in area_ids:
            parent = _area_index.get(aid, {}).get('parent_id')
            if parent:
                parent_areas.add(parent)
        if parent_areas:
            filters2 = dict(filters)
            filters2['area'] = list(parent_areas)
            filter_params2 = generate_filter_query(filters2)
            filtered_vacancies2 = load_vacancies_with_filters(filter_params2)
            if filtered_vacancies2:
                return filtered_vacancies2, filter_params2
        # 3. Если всё равно пусто — анализ по всей стране
        filters3 = dict(filters)
        filters3['area'] = []
        filter_params3 = generate_filter_query(filters3)
        filtered_vacancies3 = load_vacancies_with_filters(filter_params3)
        return filtered_vacancies3, filter_params3

    filtered_vacancies, used_filter_params = get_vacancies_with_fallback(filters)

    # Генерация визуализаций и сводки
    visualizations, summary_df = generate_all_visualizations(filtered_vacancies, filters)

    # Подготовка списка вакансий для отображения (ограничиваем 50)
    vacancies_list = []
    for v in filtered_vacancies[:50]:
        vacancy_info = {
            'id': v.get('id'),
            'name': v.get('name', 'Без названия'),
            'url': v.get('alternate_url', '#'),
            'company': v.get('employer', {}).get('name', 'Неизвестная компания'),
            'company_logo': v.get('employer', {}).get('logo_urls', {}).get('90', None),
            'location': v.get('area', {}).get('name', 'Не указан'),
            'published_at': v.get('published_at', '')[:10] if v.get('published_at') else '',
            'experience': v.get('experience', {}).get('name', '') if isinstance(v.get('experience'), dict) else v.get('experience', ''),
            'schedule': v.get('schedule', {}).get('name', '') if isinstance(v.get('schedule'), dict) else v.get('schedule', ''),
            'has_salary': bool(v.get('salary')),
            'salary': v.get('salary', {})
        }
        vacancies_list.append(vacancy_info)

    # Логирование
    log_dir = 'logs'
    os.makedirs(log_dir, exist_ok=True)
    log_path = os.path.join(log_dir, 'filters.log')

    with open(log_path, 'a', encoding='utf-8') as log_file:
        log_file.write("\n=== Новый анализ ===\n")
        log_file.write(f"Время: {datetime.now()}\n")
        log_file.write(f"Фильтры из формы: {filters}\n")
        log_file.write(f"Сгенерированные параметры: {used_filter_params}\n")
        log_file.write(f"Кол-во полученных вакансий: {len(filtered_vacancies)}\n")
        if not summary_df.empty:
            blocks = summary_df['Блок'].unique().tolist()
            log_file.write(f"Блоки статистики: {blocks}\n")
        else:
            log_file.write("Блоки статистики: –\n")

    # Рендер
    return render_template('analysis.html',
                           data=filtered_vacancies,
                           vacancies_list=vacancies_list,
                           summary_df=summary_df,
                           visualizations=visualizations,
                           filters=filters)

@api_bp.route('/clear_cache', methods=['POST'])
def clear_cache():
    return jsonify({"status": "ok", "message": "Кэш очищен"})

@api_bp.route('/export/<export_type>', methods=['POST'])
def export(export_type):
    from flask import make_response
    import pandas as pd
    import io
    import json

    data = request.form.get("data")
    if not data:
        return redirect(url_for("api.index"))

    parsed_data = json.loads(data)
    
    # Создаем различные датафреймы для экспорта
    analytics_data = []
    
    # 1. Информация о запросе
    if 'filters' in parsed_data:
        filters_df = pd.DataFrame([{
            'Параметр': 'Текстовый запрос',
            'Значение': parsed_data.get('filters', {}).get('text', 'Не указан')
        }, {
            'Параметр': 'Регион',
            'Значение': parsed_data.get('filters', {}).get('region', 'Все регионы')
        }, {
            'Параметр': 'Дата запроса',
            'Значение': pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S')
        }, {
            'Параметр': 'Всего найдено вакансий',
            'Значение': parsed_data.get('total_count', 0)
        }])
        analytics_data.append(('Общая информация', filters_df))
    
    # 2. Статистика зарплат
    if 'salary_stats' in parsed_data:
        salary_stats = parsed_data.get('salary_stats', {})
        salary_df = pd.DataFrame([
            {'Показатель': 'Минимальная зарплата', 'Значение': salary_stats.get('min', 'Н/Д')},
            {'Показатель': 'Максимальная зарплата', 'Значение': salary_stats.get('max', 'Н/Д')},
            {'Показатель': 'Средняя зарплата', 'Значение': salary_stats.get('mean', 'Н/Д')},
            {'Показатель': 'Медианная зарплата', 'Значение': salary_stats.get('median', 'Н/Д')}
        ])
        analytics_data.append(('Статистика зарплат', salary_df))
    
    # 3. Распределение по опыту
    if 'experience_dist' in parsed_data:
        exp_dist = parsed_data.get('experience_dist', {})
        exp_df = pd.DataFrame([
            {'Опыт': key, 'Количество вакансий': value} 
            for key, value in exp_dist.items()
        ])
        analytics_data.append(('Распределение по опыту', exp_df))
    
    # 4. Распределение по регионам
    if 'region_dist' in parsed_data:
        region_dist = parsed_data.get('region_dist', {})
        region_df = pd.DataFrame([
            {'Регион': key, 'Количество вакансий': value} 
            for key, value in region_dist.items()
        ])
        analytics_data.append(('Распределение по регионам', region_df))
    
    # 5. Топ навыков
    if 'skills' in parsed_data:
        skills = parsed_data.get('skills', {})
        skills_df = pd.DataFrame([
            {'Навык': key, 'Количество упоминаний': value} 
            for key, value in skills.items()
        ]).sort_values('Количество упоминаний', ascending=False)
        analytics_data.append(('Топ навыков', skills_df))
    
    # 6. Вакансии (ограниченный список)
    if 'vacancies' in parsed_data:
        vacancies = parsed_data.get('vacancies', [])
        if vacancies:
            # Преобразуем зарплаты в читаемый формат
            for v in vacancies:
                if v.get('has_salary') and v.get('salary'):
                    salary = v['salary']
                    if salary.get('from') and salary.get('to'):
                        v['salary_display'] = f"{salary['from']} - {salary['to']} {salary.get('currency', '')}"
                    elif salary.get('from'):
                        v['salary_display'] = f"от {salary['from']} {salary.get('currency', '')}"
                    elif salary.get('to'):
                        v['salary_display'] = f"до {salary['to']} {salary.get('currency', '')}"
                else:
                    v['salary_display'] = 'Не указана'
                    
            # Создаем DataFrame из списка вакансий
            vac_df = pd.DataFrame([{
                'Название': v.get('name', ''),
                'Компания': v.get('company', ''),
                'Локация': v.get('location', ''),
                'Опыт': v.get('experience', ''),
                'Зарплата': v.get('salary_display', ''),
                'Дата публикации': v.get('published_at', '')
            } for v in vacancies])
            analytics_data.append(('Список вакансий', vac_df))

    output = io.BytesIO()
    if export_type == 'csv':
        # CSV экспорт (создаем простой csv файл)
        combined_df = pd.DataFrame()
        for sheet_name, df in analytics_data:
            if not df.empty:
                # Добавляем заголовок секции
                header_df = pd.DataFrame([{'': f'=== {sheet_name} ==='}])
                # Объединяем в один DataFrame с разделителями
                combined_df = pd.concat([combined_df, header_df, df, pd.DataFrame([{'': ''}])], ignore_index=True)
                
        # Экспортируем в CSV
        combined_df.to_csv(output, index=False)
        mime = 'text/csv'
        ext = 'csv'
    elif export_type == 'excel':
        # Excel экспорт с несколькими вкладками
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            for i, (sheet_name, df) in enumerate(analytics_data):
                if not df.empty:
                    df.to_excel(writer, sheet_name=sheet_name, index=False)
                    
        mime = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        ext = 'xlsx'
    elif export_type == 'pdf':
        from matplotlib.backends.backend_pdf import PdfPages
        from matplotlib import pyplot as plt
        
        with PdfPages(output) as pdf:
            plt.figure(figsize=(11, 8.5))
            plt.suptitle('Анализ IT-вакансий', fontsize=16, y=0.98)
            plt.figtext(0.5, 0.94, 'Отчет создан: ' + pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S'), 
                       ha='center', fontsize=10, style='italic')
            
            # Параметры запроса
            if analytics_data and len(analytics_data) > 0:
                info_df = analytics_data[0][1]
                plt.figtext(0.1, 0.85, 'Параметры поиска:', fontsize=12, weight='bold')
                y_pos = 0.8
                for _, row in info_df.iterrows():
                    plt.figtext(0.1, y_pos, f"{row['Параметр']}: {row['Значение']}", fontsize=10)
                    y_pos -= 0.04
            
            plt.axis('off')
            pdf.savefig()
            plt.close()
            
            # Добавляем остальные таблицы
            for sheet_name, df in analytics_data[1:]:
                if not df.empty:
                    fig, ax = plt.subplots(figsize=(11, 8.5))
                    ax.axis('off')
                    plt.suptitle(sheet_name, fontsize=14, y=0.98)
                    
                    # Отображаем таблицу
                    table = ax.table(
                        cellText=df.values,
                        colLabels=df.columns,
                        loc='center',
                        cellLoc='center',
                        colColours=["#4e73df"] * len(df.columns)
                    )
                    table.auto_set_font_size(False)
                    table.set_fontsize(9)
                    table.scale(1, 1.5)
                    
                    pdf.savefig(fig)
                    plt.close(fig)
            
        mime = 'application/pdf'
        ext = 'pdf'
    else:
        return redirect(url_for("api.index"))

    output.seek(0)
    response = make_response(output.read())
    response.headers["Content-Disposition"] = f"attachment; filename=analytics_export.{ext}"
    response.headers["Content-type"] = mime
    return response
