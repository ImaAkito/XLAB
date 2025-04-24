import plotly.express as px
from collections import defaultdict
import numpy as np
from currency_converter import CurrencyConverter
from plotly.graph_objs import Scatter, Layout, Figure
from plotly.offline import plot
from app.api import geo
import pandas as pd
import plotly.graph_objs as go
from wordcloud import WordCloud
from io import BytesIO
import base64


def generate_all_visualizations(vacancies, filters):
    visualizations = {}
    summary_blocks = []

    # --- Интеграция с CurrencyConverter ---
    converter = CurrencyConverter()
    target_currency = filters.get('currency', 'BYN')
    converted_vacancies = []
    for v in vacancies:
        v_copy = v.copy()
        salary = v_copy.get('salary')
        if salary and (salary.get('from') or salary.get('to')):
            from_val = salary.get('from')
            to_val = salary.get('to')
            currency = salary.get('currency', 'BYN')
            if from_val:
                v_copy['salary']['from'] = converter.convert(from_val, currency, target_currency)
            if to_val:
                v_copy['salary']['to'] = converter.convert(to_val, currency, target_currency)
            v_copy['salary']['currency'] = target_currency
        converted_vacancies.append(v_copy)
    # --- конец интеграции ---

    # Определяем выбранный город (если только один)
    selected_city = None
    if filters.get('region') and isinstance(filters['region'], list) and len(filters['region']) == 1:
        selected_city = filters['region'][0]
    elif filters.get('area') and isinstance(filters['area'], list) and len(filters['area']) == 1:
        selected_city = filters['area'][0]
    elif filters.get('region') and isinstance(filters['region'], str):
        selected_city = filters['region']
    elif filters.get('area') and isinstance(filters['area'], str):
        selected_city = filters['area']

    # Преобразуем id города в название, если это id
    if selected_city and selected_city.isdigit():
        from app.api.geo import get_area_name
        selected_city = get_area_name(selected_city)

    map_data = geo.get_map_data(converted_vacancies, selected_city=selected_city)
    import json
    visualizations["map_data"] = json.dumps(map_data, ensure_ascii=False)
    region_stats = geo.get_region_aggregates(converted_vacancies)

    visualizations["display_currency"] = target_currency

    if region_stats["count"]:
        df_count = pd.DataFrame({
            "Регион": [geo.get_area_name(rid) for rid in region_stats["count"].keys()],
            "Кол-во вакансий": list(region_stats["count"].values())
        })
        fig = px.bar(df_count, x="Регион", y="Кол-во вакансий", title="Вакансии по регионам")
        visualizations["salary_by_region_chart_count"] = fig.to_html(full_html=False)

    if region_stats["mean"]:
        df_mean = pd.DataFrame({
            "Регион": [geo.get_area_name(rid) for rid, val in region_stats["mean"].items() if val is not None],
            "Средняя зарплата": [val for val in region_stats["mean"].values() if val is not None]
        })
        fig = px.bar(df_mean, x="Регион", y="Средняя зарплата", title="Средняя зарплата по регионам")
        visualizations["salary_by_region_chart_mean"] = fig.to_html(full_html=False)

    if region_stats["median"]:
        df_median = pd.DataFrame({
            "Регион": [geo.get_area_name(rid) for rid, val in region_stats["median"].items() if val is not None],
            "Медианная зарплата": [val for val in region_stats["median"].values() if val is not None]
        })
        fig = px.bar(df_median, x="Регион", y="Медианная зарплата", title="Медианная зарплата по регионам")
        visualizations["salary_by_region_chart_median"] = fig.to_html(full_html=False)

    # Блок 1: Общая характеристика
    general_vis, general_summary = generate_general_block(converted_vacancies, filters)
    visualizations.update(general_vis)
    summary_blocks.append(general_summary)

    # Блок 2: Зарплаты
    salary_vis, salary_summary = generate_salary_block(converted_vacancies)
    visualizations.update(salary_vis)
    summary_blocks.append(salary_summary)

    # Блок 3: Опыт, занятость, график
    exp_vis, exp_summary = generate_experience_block(converted_vacancies)
    visualizations.update(exp_vis)
    summary_blocks.append(exp_summary)

    # Блок 4: Навыки
    skill_vis, skill_summary = generate_skills_block(converted_vacancies, filters)
    visualizations.update(skill_vis)
    summary_blocks.append(skill_summary)

    # Блок 5: Работодатели
    emp_vis, emp_summary = generate_employers_block(converted_vacancies)
    visualizations.update(emp_vis)
    summary_blocks.append(emp_summary)

    print(f"[DEBUG] Визуализации: {list(visualizations.keys())}")

    # Объединение всех статистик
    summary_df = pd.concat(summary_blocks, ignore_index=True)
    return visualizations, summary_df


# Пример: Общая характеристика
def generate_general_block(vacancies, filters):
    rows = []
    visualizations = {}

    count = len(vacancies)
    rows.append(["Общая характеристика", "Всего вакансий", count])

    # График публикаций по датам
    dates = [v.get("published_at")[:10] for v in vacancies if v.get("published_at")]
    if dates:
        df = pd.DataFrame(dates, columns=["date"])
        df["date"] = pd.to_datetime(df["date"])
        hist = df.groupby("date").size().reset_index(name="count")
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=hist["date"],
            y=hist["count"],
            mode='lines+markers',
            name='Количество вакансий',
            marker=dict(color='#4e73df'),
            line=dict(color='#4e73df', width=2)
        ))
        fig.update_layout(
            title='Публикация вакансий по дням',
            xaxis_title='Дата',
            yaxis_title='Количество вакансий',
            showlegend=False,
            height=400
        )
        visualizations["publications_chart"] = fig.to_html(full_html=False)

    # Круговая диаграмма по регионам
    fig_html = generate_regions_chart(vacancies)
    if fig_html:
        visualizations["regions_chart"] = fig_html

    # Данные для карты
    map_points = []
    for v in vacancies:
        addr = v.get("address", {})
        lat, lng = addr.get("lat"), addr.get("lng")
        if lat and lng:
            point = {
                "lat": lat,
                "lng": lng,
                "title": v.get("name"),
                "employer": v.get("employer", {}).get("name"),
                "salary": v.get("salary"),
            }
            map_points.append(point)
    if map_points:
        import json
        visualizations['map_data'] = json.dumps(map_points, ensure_ascii=False)

    return visualizations, pd.DataFrame(rows, columns=["Блок", "Метр", "Значение"])


# Пример: Зарплаты
def generate_salary_block(vacancies):
    rows = []
    salary_data = []
    experience_salary = {}
    region_salary = {}
    region_count = {}
    region_mean = {}
    region_median = {}

    print(f"[DEBUG] Анализ зарплат: получено {len(vacancies)} вакансий")
    vacancies_with_salary = 0

    for v in vacancies:
        s = v.get("salary")
        if not s:
            continue
        from_val = s.get("from")
        to_val = s.get("to")
        if from_val and to_val:
            avg_salary = (from_val + to_val) / 2
        elif from_val:
            avg_salary = from_val
        elif to_val:
            avg_salary = to_val
        else:
            continue
        salary_data.append(avg_salary)
        vacancies_with_salary += 1

        # По опыту
        exp = v.get("experience")
        if exp:
            if isinstance(exp, dict):
                exp = exp.get("name") or str(exp)
            experience_salary.setdefault(exp, []).append(avg_salary)
            
        # По региону
        area = v.get("area", {})
        region = area.get("name")
        if region:
            region_salary.setdefault(region, []).append(avg_salary)
            region_count[region] = region_count.get(region, 0) + 1
    
    print(f"[DEBUG] Найдено {vacancies_with_salary} вакансий с указанной зарплатой")
    print(f"[DEBUG] Собраны данные о зарплатах по опыту: {len(experience_salary)} категорий")

    if not salary_data:
        return {}, pd.DataFrame()

    s_series = pd.Series(salary_data)
    rows.extend([
        ["Анализ зарплат", "Мин. зарплата", s_series.min()],
        ["Анализ зарплат", "Макс. зарплата", s_series.max()],
        ["Анализ зарплат", "Средняя зарплата", s_series.mean()],
        ["Анализ зарплат", "Медианная зарплата", s_series.median()],
    ])

    visualizations = {}

    # Гистограмма зарплат
    fig_hist = px.histogram(s_series, nbins=20, title="Гистограмма зарплат")
    fig_hist.update_layout(showlegend=False)  # скрываем 'variable = 0'
    visualizations["salary_histogram"] = fig_hist.to_html(full_html=False)

    # Barplot min/median/mean/max
    stats_data = [s_series.min(), s_series.median(), s_series.mean(), s_series.max()]
    labels = ['Минимальная', 'Медиана', 'Средняя', 'Максимальная']
    fig_stats = go.Figure()
    fig_stats.add_trace(go.Bar(
        x=labels,
        y=stats_data,
        text=[f"{x:.0f}" for x in stats_data],
        textposition='auto',
        marker=dict(color=['#36b9cc', '#1cc88a', '#f6c23e', '#e74a3b'])
    ))
    fig_stats.update_layout(
        title='Статистика зарплат',
        yaxis_title='Зарплата',
        height=400
    )
    visualizations["salary_stats_chart"] = fig_stats.to_html(full_html=False)

    # Barplot по регионам (медианная, средняя, количество)
    if region_salary:
        for region, vals in region_salary.items():
            region_mean[region] = np.mean(vals)
            region_median[region] = np.median(vals)
        # Медианная
        df_median = pd.DataFrame({
            "region": list(region_median.keys()),
            "median": list(region_median.values())
        }).sort_values(by="median", ascending=False)
        fig_median = go.Figure()
        fig_median.add_trace(go.Bar(
            x=df_median["region"],
            y=df_median["median"],
            marker=dict(color="#4e73df"),
            text=[f"{x:.0f}" for x in df_median["median"]],
            textposition='auto'
        ))
        fig_median.update_layout(
            title='Медианная зарплата по регионам',
            xaxis_title='Регион',
            yaxis_title='Медианная зарплата',
            height=450
        )
        visualizations["salary_by_region_chart_median"] = fig_median.to_html(full_html=False)
        # Средняя
        df_mean = pd.DataFrame({
            "region": list(region_mean.keys()),
            "mean": list(region_mean.values())
        }).sort_values(by="mean", ascending=False)
        fig_mean = go.Figure()
        fig_mean.add_trace(go.Bar(
            x=df_mean["region"],
            y=df_mean["mean"],
            marker=dict(color="#36b9cc"),
            text=[f"{x:.0f}" for x in df_mean["mean"]],
            textposition='auto'
        ))
        fig_mean.update_layout(
            title='Средняя зарплата по регионам',
            xaxis_title='Регион',
            yaxis_title='Средняя зарплата',
            height=450
        )
        visualizations["salary_by_region_chart_mean"] = fig_mean.to_html(full_html=False)
        # Количество
        df_count = pd.DataFrame({
            "region": list(region_count.keys()),
            "count": list(region_count.values())
        }).sort_values(by="count", ascending=False)
        fig_count = go.Figure()
        fig_count.add_trace(go.Bar(
            x=df_count["region"],
            y=df_count["count"],
            marker=dict(color="#f6c23e"),
            text=df_count["count"],
            textposition='auto'
        ))
        fig_count.update_layout(
            title='Количество вакансий по регионам',
            xaxis_title='Регион',
            yaxis_title='Количество вакансий',
            height=450
        )
        visualizations["salary_by_region_chart_count"] = fig_count.to_html(full_html=False)

    # Barplot по опыту (медиана и средняя)
    if experience_salary and len(experience_salary) >= 2:
        print(f"[DEBUG] Создание диаграмм зарплаты по опыту. Категории опыта: {list(experience_salary.keys())}")
        
        # Сортируем категории опыта по логическому порядку
        def sort_experience(exp_name):
            exp_order = {
                'Нет опыта': 0,
                'От 1 года до 3 лет': 1,
                'От 3 до 6 лет': 2,
                'Более 6 лет': 3
            }
            return exp_order.get(exp_name, 999)
            
        sorted_exp_items = sorted(experience_salary.items(), key=lambda x: sort_experience(x[0]))
        exp_labels = [item[0] for item in sorted_exp_items]
        
        try:
            exp_medians = [np.median(experience_salary[exp]) for exp in exp_labels]
            exp_means = [np.mean(experience_salary[exp]) for exp in exp_labels]
            print(f"[DEBUG] Данные для диаграмм: медианы={exp_medians}, средние={exp_means}")
            
            # Медиана
            fig_exp_median = go.Figure()
            fig_exp_median.add_trace(go.Bar(
                x=exp_labels,
                y=exp_medians,
                marker=dict(color="#4e73df"),
                text=[f"{x:.0f}" for x in exp_medians],
                textposition='auto'
            ))
            fig_exp_median.update_layout(
                title='Медианная зарплата по опыту работы',
                xaxis_title='Опыт работы',
                yaxis_title='Зарплата',
                height=400
            )
            visualizations["salary_by_experience_median"] = fig_exp_median.to_html(full_html=False)
            print(f"[DEBUG] Создана диаграмма медианной зарплаты: длина HTML={len(visualizations['salary_by_experience_median'])}")
            
            # Средняя
            fig_exp_mean = go.Figure()
            fig_exp_mean.add_trace(go.Bar(
                x=exp_labels,
                y=exp_means,
                marker=dict(color="#e74a3b"),
                text=[f"{x:.0f}" for x in exp_means],
                textposition='auto'
            ))
            fig_exp_mean.update_layout(
                title='Средняя зарплата по опыту работы',
                xaxis_title='Опыт работы',
                yaxis_title='Зарплата',
                height=400
            )
            visualizations["salary_by_experience_mean"] = fig_exp_mean.to_html(full_html=False)
            print(f"[DEBUG] Создана диаграмма средней зарплаты: длина HTML={len(visualizations['salary_by_experience_mean'])}")
        except Exception as e:
            print(f"[ERROR] Ошибка при создании диаграмм зарплат по опыту: {str(e)}")
            # Проверяем данные более детально
            for exp, salaries in experience_salary.items():
                print(f"[DEBUG] Опыт '{exp}': {len(salaries)} зарплат, данные: {salaries[:5]}{'...' if len(salaries) > 5 else ''}")
    else:
        print(f"[DEBUG] Недостаточно данных для создания диаграмм зарплат по опыту: {len(experience_salary)} категорий")
        if experience_salary:
            print(f"[DEBUG] Доступные категории: {list(experience_salary.keys())}")

    return visualizations, pd.DataFrame(rows, columns=["Блок", "Метр", "Значение"])

# Пример: Опыт и график
def generate_experience_block(vacancies):
    rows = []
    visualizations = {}

    experience = defaultdict(int)
    employment = defaultdict(int)
    schedule = defaultdict(int)

    print(f"[DEBUG] Анализ опыта работы: получено {len(vacancies)} вакансий")

    for v in vacancies:
        if v.get("experience"):
            exp = v.get("experience")
            if isinstance(exp, dict):
                exp = exp.get("name") or str(exp)
            experience[exp] += 1
            
        if v.get("employment"):
            emp = v.get("employment")
            if isinstance(emp, dict):
                emp = emp.get("name") or str(emp)
            employment[emp] += 1
            
        if v.get("schedule"):
            sch = v.get("schedule")
            if isinstance(sch, dict):
                sch = sch.get("name") or str(sch)
            schedule[sch] += 1

    print(f"[DEBUG] Собраны данные по опыту: {dict(experience)}")

    # Barplot по опыту (горизонтальный, сортировка)
    if experience and len(experience) >= 3:
        def sort_experience(exp_name):
            exp_order = {
                'Нет опыта': 0,
                'От 1 года до 3 лет': 1,
                'От 3 до 6 лет': 2,
                'Более 6 лет': 3
            }
            return exp_order.get(exp_name, 999)
        exp_items = sorted(experience.items(), key=lambda x: sort_experience(x[0]))
        exp_labels = [item[0] for item in exp_items]
        exp_counts = [item[1] for item in exp_items]
        fig = go.Figure()
        fig.add_trace(go.Bar(
            y=exp_labels,
            x=exp_counts,
            marker=dict(color="#4e73df"),
            text=exp_counts,
            textposition='auto',
            orientation='h'
        ))
        fig.update_layout(
            title='Распределение вакансий по опыту работы',
            xaxis_title='Количество вакансий',
            height=400
        )
        visualizations["experience_chart"] = fig.to_html(full_html=False)
        print(f"[DEBUG] Создана диаграмма опыта (bar): длина HTML = {len(visualizations['experience_chart'])}")
        
        # Добавляем новую круговую диаграмму
        fig_pie = go.Figure()
        fig_pie.add_trace(go.Pie(
            labels=exp_labels,
            values=exp_counts,
            textinfo='percent+label',
            marker=dict(colors=px.colors.qualitative.Set3),
            hole=0.4
        ))
        fig_pie.update_layout(
            title='Распределение вакансий по опыту работы (pie)',
            height=400
        )
        visualizations["experience_pie_chart"] = fig_pie.to_html(full_html=False)
        print(f"[DEBUG] Создана диаграмма опыта (pie): длина HTML = {len(visualizations['experience_pie_chart'])}")
    else:
        print(f"[DEBUG] Недостаточно данных для диаграммы опыта: {len(experience)} категорий (нужно минимум 3)")

    # Pie по графику работы
    if schedule and len(schedule) >= 2:
        schedule_labels = list(schedule.keys())
        schedule_counts = list(schedule.values())
        fig = go.Figure()
        fig.add_trace(go.Pie(
            labels=schedule_labels,
            values=schedule_counts,
            textinfo='percent+label',
            marker=dict(colors=px.colors.qualitative.Set3)
        ))
        fig.update_layout(
            title='Распределение по графику работы',
            height=400
        )
        visualizations["schedule_chart"] = fig.to_html(full_html=False)
        print(f"[DEBUG] Создана диаграмма графика работы: длина HTML = {len(visualizations['schedule_chart'])}")
    else:
        print(f"[DEBUG] Недостаточно данных для диаграммы графика работы: {len(schedule)} категорий (нужно минимум 2)")

    # Barplot по типу занятости
    if employment and len(employment) >= 2:
        employment_labels = list(employment.keys())
        employment_counts = list(employment.values())
        fig = go.Figure()
        fig.add_trace(go.Bar(
            x=employment_labels,
            y=employment_counts,
            marker=dict(color="#36b9cc"),
            text=employment_counts,
            textposition='auto'
        ))
        fig.update_layout(
            title='Распределение по типу занятости',
            xaxis_title='Тип занятости',
            yaxis_title='Количество вакансий',
            height=400
        )
        visualizations["employment_chart"] = fig.to_html(full_html=False)
        print(f"[DEBUG] Создана диаграмма занятости: длина HTML = {len(visualizations['employment_chart'])}")
    else:
        print(f"[DEBUG] Недостаточно данных для диаграммы занятости: {len(employment)} категорий (нужно минимум 2)")
    
    print(f"[DEBUG] Итого создано диаграмм: {len(visualizations)}")
    return visualizations, pd.DataFrame(rows, columns=["Блок", "Метр", "Значение"])

# Пример: Навыки
def generate_skills_block(vacancies, filters):
    rows = []
    visualizations = []
    all_skills = []

    for v in vacancies:
        skills = v.get("key_skills") or []
        for s in skills:
            if isinstance(s, str):
                all_skills.append(s)
            elif isinstance(s, dict) and "name" in s:
                all_skills.append(s["name"])

    print(f"[DEBUG] Собрано навыков всего: {len(all_skills)}")

    if len(all_skills) < 5:
        print("[DEBUG] Недостаточно навыков для анализа")
        return {}, pd.DataFrame()

    skill_counts = pd.Series(all_skills).value_counts()
    rows.append(["Навыки", "Всего уникальных", skill_counts.size])
    top_skills = skill_counts.head(20)

    fig = go.Figure()
    fig.add_trace(go.Bar(
        y=top_skills.index.tolist(),
        x=top_skills.values.tolist(),
        marker=dict(color="#4e73df"),
        text=top_skills.values.tolist(),
        textposition='auto',
        orientation='h'
    ))
    fig.update_layout(
        title='Топ-20 востребованных навыков',
        xaxis_title='Количество упоминаний',
        height=600,
        margin=dict(l=100, r=20, t=60, b=50)
    )
    visualizations_dict = {}
    visualizations_dict["top_skills_chart"] = fig.to_html(full_html=False)

    wordcloud = WordCloud(width=800, height=400, background_color='white', colormap='viridis')\
        .generate_from_frequencies(skill_counts)

    buf = BytesIO()
    wordcloud.to_image().save(buf, format="PNG")
    data = base64.b64encode(buf.getvalue()).decode("utf-8")
    visualizations_dict["skills_wordcloud"] = data

    print(f"[DEBUG] Визуализации навыков добавлены: {list(visualizations_dict.keys())}")
    return visualizations_dict, pd.DataFrame(rows, columns=["Блок", "Метр", "Значение"])


# Пример: Работодатели
def generate_employers_block(vacancies):
    rows = []
    visualizations = {}
    employers = defaultdict(int)
    salaries = defaultdict(list)

    for v in vacancies:
        emp = v.get("employer", {}).get("name")
        if emp:
            employers[emp] += 1
            s = v.get("salary")
            if s:
                from_val = s.get("from")
                to_val = s.get("to")
                if from_val and to_val:
                    avg = (from_val + to_val) / 2
                elif from_val:
                    avg = from_val
                elif to_val:
                    avg = to_val
                else:
                    avg = None
                if avg is not None:
                    salaries[emp].append(avg)

    emp_counts = pd.DataFrame(employers.items(), columns=["Работодатель", "Кол-во"]).sort_values(by="Кол-во", ascending=False)
    top10 = emp_counts.head(10)
    # Горизонтальный barplot по топ-10 работодателям
    fig1 = go.Figure()
    fig1.add_trace(go.Bar(
        y=top10["Работодатель"],
        x=top10["Кол-во"],
        marker=dict(color="#1cc88a"),
        text=top10["Кол-во"],
        textposition='auto',
        orientation='h'
    ))
    fig1.update_layout(
        title='Топ работодателей по количеству вакансий',
        xaxis_title='Количество вакансий',
        height=500
    )
    visualizations["top_employers_chart"] = fig1.to_html(full_html=False)

    # Средние зарплаты по работодателям (горизонтальный barplot)
    avg_salaries = [(k, sum(v)/len(v)) for k, v in salaries.items() if len(v) >= 2]
    if avg_salaries:
        df_avg = pd.DataFrame(avg_salaries, columns=["Работодатель", "Средняя зарплата"]).sort_values(by="Средняя зарплата", ascending=False).head(10)
        fig2 = go.Figure()
        fig2.add_trace(go.Bar(
            y=df_avg["Работодатель"],
            x=df_avg["Средняя зарплата"],
            marker=dict(color="#f6c23e"),
            text=[f"{x:.0f}" for x in df_avg["Средняя зарплата"]],
            textposition='auto',
            orientation='h'
        ))
        height = max(500, 100 + len(df_avg) * 30)
        fig2.update_layout(
            title='Средняя зарплата по работодателям',
            xaxis_title='Средняя зарплата',
            height=height
        )
        visualizations["employers_salary_chart"] = fig2.to_html(full_html=False)

    return visualizations, pd.DataFrame(rows, columns=["Блок", "Метр", "Значение"])

def generate_publication_chart(vacancies):


    dates = []
    for v in vacancies:
        pub_date = v.get("published_at")
        if pub_date:
            try:
                date_only = pd.to_datetime(pub_date).date()
                dates.append(date_only)
            except Exception:
                continue

    if not dates:
        return None

    df = pd.DataFrame(dates, columns=["date"])
    count_by_day = df.groupby("date").size().reset_index(name="count")

    trace = Scatter(
        x=count_by_day["date"],
        y=count_by_day["count"],
        mode="lines+markers",
        line=dict(color="#3366cc"),
        marker=dict(size=6),
        name="Вакансии"
    )

    layout = Layout(
        title="Публикация вакансий по дням",
        xaxis=dict(title="Дата"),
        yaxis=dict(title="Количество вакансий"),
        height=400
    )

    fig = Figure(data=[trace], layout=layout)
    return plot(fig, output_type="div", include_plotlyjs=False)


# Функция: генерация pie chart по регионам (вакансии по регионам)
def generate_regions_chart(vacancies):
    region_counts = {}
    for v in vacancies:
        area = v.get("area", {})
        region = area.get("name")
        if region:
            region_counts[region] = region_counts.get(region, 0) + 1

    if not region_counts or sum(region_counts.values()) == 0:
        return None

    sorted_regions = sorted(region_counts.items(), key=lambda x: x[1], reverse=True)
    if len(sorted_regions) > 8:
        top_regions = sorted_regions[:8]
        other_count = sum(count for _, count in sorted_regions[8:])
        regions = [region for region, _ in top_regions] + ['Другие']
        counts = [count for _, count in top_regions] + [other_count]
    else:
        regions = [region for region, _ in sorted_regions]
        counts = [count for _, count in sorted_regions]

    total = sum(counts)
    labels = [
        f"{region} ({count} вакансий, {count / total * 100:.1f}%)"
        for region, count in zip(regions, counts)
    ]

    fig = go.Figure()
    fig.add_trace(go.Pie(
        labels=labels,
        values=counts,
        textinfo='none',
        hole=0.4,
        marker=dict(colors=[
            '#4e73df', '#1cc88a', '#36b9cc', '#f6c23e', '#e74a3b', '#858796',
            '#6610f2', '#fd7e14', '#6c757d'
        ])
    ))

    fig.update_layout(
        title='Распределение вакансий по регионам',
        height=400,
        showlegend=True
    )

    return fig.to_html(full_html=False)

