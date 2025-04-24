import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import plotly.io as pio
from wordcloud import WordCloud
import numpy as np
import pandas as pd
import json
import base64
from io import BytesIO
import re
from collections import Counter

class Visualizer:
    """Класс для создания визуализаций данных о вакансиях"""
    
    def __init__(self):
        # Настройка цветов для графиков
        self.colors = {
            'primary': '#4e73df',
            'success': '#1cc88a',
            'info': '#36b9cc',
            'warning': '#f6c23e',
            'danger': '#e74a3b',
            'secondary': '#858796',
            'light': '#f8f9fc',
            'dark': '#5a5c69'
        }
        
        # Настройка темы для Plotly
        pio.templates.default = "plotly_white"
        
        # Настройка удаления логотипа Plotly со всех графиков
        self.config = {
            'displayModeBar': False,  # Скрываем панель инструментов
            'displaylogo': False,     # Скрываем логотип Plotly
            'responsive': True,       # Делаем график адаптивным
            'staticPlot': False       # Разрешаем интерактивность
        }
    
    def create_visualizations(self, data, filters):
        """
        Создание всех необходимых визуализаций
        
        Args:
            data (dict): Словарь с данными для визуализации
            filters (dict): Параметры фильтрации
            
        Returns:
            dict: Словарь с HTML-кодом визуализаций
        """
        if data.get('count', 0) == 0:
            return {'no_data': True}
            
        result = {}
        
        # Блок 1: Общая характеристика вакансий
        result.update(self._create_general_info_block(data, filters))
        
        # Блок 2: Анализ зарплат (если есть данные по зарплатам)
        if data.get('has_salary_data', False):
            result.update(self._create_salary_block(data, filters))
        
        # Блок 3: Опыт и график работы
        result.update(self._create_experience_schedule_block(data, filters))
        
        # Блок 4: Навыки
        result.update(self._create_skills_block(data, filters))
        
        # Блок 5: Работодатели
        if data.get('count', 0) >= 5 and 'top_employers' in data:
            result.update(self._create_employers_block(data, filters))
        
        # Блок 6: Технологии (экспериментальный)
        if 'top_skills' in data and len(data['top_skills']) >= 10:
            result.update(self._create_tech_grid_block(data, filters))
        
        # Блок 7: Рейтинг профессий (экспериментальный, если текст не задан)
        if not filters.get('text') and 'keywords' in data:
            result.update(self._create_professions_block(data, filters))
            
        return result
    
    def _create_general_info_block(self, data, filters):
        """Создание блока с общей информацией о вакансиях"""
        result = {}
        
        # График публикаций по дням
        if 'publications_by_day' in data:
            fig = go.Figure()
            dates = list(data['publications_by_day'].keys())
            counts = list(data['publications_by_day'].values())
            
            fig.add_trace(go.Scatter(
                x=dates, 
                y=counts,
                mode='lines+markers',
                name='Количество вакансий',
                marker=dict(color=self.colors['primary']),
                line=dict(color=self.colors['primary'], width=2)
            ))
            
            fig.update_layout(
                title='Публикация вакансий по дням',
                xaxis_title='Дата',
                yaxis_title='Количество вакансий',
                showlegend=False,
                height=400
            )
            
            result['publications_chart'] = pio.to_html(fig, full_html=False, config=self.config)
        
        # Круговая диаграмма по регионам (если выбран один уровень и есть >=2 региона)
        if 'regions' in data and len(data['regions']) >= 2:
            fig = go.Figure()
            
            # Сортируем регионы по количеству вакансий и ограничиваем до 10 самых популярных
            # Остальные группируем в категорию "Другие"
            sorted_regions = sorted(data['regions'].items(), key=lambda x: x[1], reverse=True)
            
            if len(sorted_regions) > 8:
                top_regions = sorted_regions[:8]
                other_count = sum(count for _, count in sorted_regions[8:])
                
                regions = [region for region, _ in top_regions] + ['Другие']
                counts = [count for _, count in top_regions] + [other_count]
                
                # Создаем палитру цветов (8 основных + 1 для "Другие")
                colors = [
                    self.colors['primary'], self.colors['success'], self.colors['info'],
                    self.colors['warning'], self.colors['danger'], self.colors['secondary'],
                    '#6610f2', '#fd7e14', '#6c757d'
                ]
            else:
                regions = [region for region, _ in sorted_regions]
                counts = [count for _, count in sorted_regions]
                
                # Создаем палитру цветов соответствующего размера
                base_colors = [
                    self.colors['primary'], self.colors['success'], self.colors['info'],
                    self.colors['warning'], self.colors['danger'], self.colors['secondary'],
                    '#6610f2', '#fd7e14'
                ]
                colors = base_colors[:len(regions)]
            
            # Создаем улучшенные метки для легенды с количеством и процентами
            total_count = sum(counts)
            custom_labels = []
            for i, region in enumerate(regions):
                percentage = counts[i] / total_count * 100
                custom_labels.append(f"{region} ({counts[i]} вакансий, {percentage:.1f}%)")
            
            fig.add_trace(go.Pie(
                labels=custom_labels,
                values=counts,
                textinfo='none',  # Убираем текст с самого графика
                marker=dict(colors=colors),
                hole=0.4  # Создаем donut chart для современного вида
            ))
            
            fig.update_layout(
                title='Распределение вакансий по регионам',
                height=450,  # Увеличиваем высоту для размещения легенды
                legend=dict(
                    orientation="v",  # Вертикальная ориентация легенды
                    yanchor="middle",
                    y=0.5,
                    xanchor="right",
                    x=1.1,
                    font=dict(size=12)
                )
            )
            
            result['regions_chart'] = pio.to_html(fig, full_html=False, config=self.config)
        
        # Интерактивная карта с координатами вакансий (если есть координаты)
        if 'coordinates' in data and data['coordinates']:
            # Для карты используется Leaflet.js через JavaScript
            # Здесь только подготовка данных для шаблона
            
            # Используем ensure_ascii=False для корректного отображения Unicode
            # Это решит проблему с экранированием кириллических символов в JSON
            result['map_data'] = json.dumps(data['coordinates'], ensure_ascii=False)
        
        return result
    
    def _create_salary_block(self, data, filters):
        """Создание блока с анализом зарплат"""
        result = {}
        currency = data.get('display_currency', 'BYN')
        
        # Гистограмма по зарплатам
        if 'salary_histogram' in data:
            fig = go.Figure()
            
            bin_edges = data['salary_histogram']['bins']
            bin_labels = []
            
            for i in range(len(bin_edges) - 1):
                bin_labels.append(f"{bin_edges[i]:.0f} - {bin_edges[i+1]:.0f}")
            
            fig.add_trace(go.Bar(
                x=bin_labels,
                y=data['salary_histogram']['counts'],
                marker=dict(color=self.colors['primary'])
            ))
            
            fig.update_layout(
                title=f'Распределение зарплат ({currency})',
                xaxis_title='Диапазон зарплат',
                yaxis_title='Количество вакансий',
                height=400
            )
            
            result['salary_histogram'] = pio.to_html(fig, full_html=False, config=self.config)
        
        # Основные статистики по зарплатам
        if 'salary_stats' in data:
            stats = data['salary_stats']
            
            fig = go.Figure()
            
            # Находим максимальную зарплату среди всех вакансий, которая не превышает 20000
            # (если в данных нет зарплат до 20000, то используем минимальную из имеющихся)
            if 'filtered_max_salary' in data:
                # Если есть специально подготовленная отфильтрованная максимальная зарплата
                max_display_salary = data['filtered_max_salary']
            else:
                # Иначе вычисляем на лету максимальную зарплату до 20000
                max_display_salary = stats.get('max', 0)
                if max_display_salary > 20000:
                    max_display_salary = 20000
            
            stats_data = [
                stats.get('min', 0),
                stats.get('median', 0),
                stats.get('mean', 0),
                max_display_salary  # Используем найденное максимальное значение
            ]
            
            labels = ['Минимальная', 'Медиана', 'Средняя', 'Максимальная']
            
            fig.add_trace(go.Bar(
                x=labels,
                y=stats_data,
                text=[f"{x:.0f} {currency}" for x in stats_data],
                textposition='auto',
                marker=dict(color=[
                    self.colors['info'],
                    self.colors['success'],
                    self.colors['warning'],
                    self.colors['danger']
                ])
            ))
            
            fig.update_layout(
                title='Статистика зарплат',
                yaxis_title=f'Зарплата ({currency})',
                height=400
            )
            
            result['salary_stats_chart'] = pio.to_html(fig, full_html=False, config=self.config)
        
        # Boxplot зарплат по регионам
        if 'salary_by_region' in data and len(data['salary_by_region']) >= 2:
            region_data = pd.DataFrame(data['salary_by_region'])
            
            # Сортируем регионы по медианной зарплате для более наглядного отображения
            region_data = region_data.sort_values(by='median', ascending=False)
            
            # График 1: Медианная зарплата по регионам
            fig_median = go.Figure()
            
            fig_median.add_trace(go.Bar(
                x=region_data['region'],
                y=region_data['median'],
                marker=dict(color=self.colors['primary']),
                text=[f"{x:.0f} {currency}" for x in region_data['median']],
                textposition='auto'
            ))
            
            fig_median.update_layout(
                title=f'Медианная зарплата по регионам ({currency})',
                xaxis_title='Регион',
                yaxis_title=f'Медианная зарплата ({currency})',
                height=450
            )
            
            # Добавляем информацию в результат
            result['salary_by_region_chart_median'] = pio.to_html(fig_median, full_html=False, config=self.config)
            
            # График 2: Средняя зарплата по регионам
            fig_mean = go.Figure()
            
            fig_mean.add_trace(go.Bar(
                x=region_data['region'],
                y=region_data['mean'],
                marker=dict(color=self.colors['info']),
                text=[f"{x:.0f} {currency}" for x in region_data['mean']],
                textposition='auto'
            ))
            
            fig_mean.update_layout(
                title=f'Средняя зарплата по регионам ({currency})',
                xaxis_title='Регион',
                yaxis_title=f'Средняя зарплата ({currency})',
                height=450
            )
            
            # Добавляем информацию в результат
            result['salary_by_region_chart_mean'] = pio.to_html(fig_mean, full_html=False, config=self.config)
            
            # График 3: Количество вакансий по регионам
            fig_count = go.Figure()
            
            fig_count.add_trace(go.Bar(
                x=region_data['region'],
                y=region_data['count'],
                marker=dict(color=self.colors['warning']),
                text=region_data['count'],
                textposition='auto'
            ))
            
            fig_count.update_layout(
                title='Количество вакансий по регионам',
                xaxis_title='Регион',
                yaxis_title='Количество вакансий',
                height=450
            )
            
            # Добавляем информацию в результат
            result['salary_by_region_chart_count'] = pio.to_html(fig_count, full_html=False, config=self.config)
        
        # Scatter plot: зарплата vs опыт
        if 'salary_by_experience' in data and len(data['salary_by_experience']) >= 2:
            exp_data = pd.DataFrame(data['salary_by_experience'])
            # Создаем два отдельных графика - для медианы и средней зарплаты
            # Разделим на два графика: медиана и средняя зарплата
            fig_median = go.Figure()
            fig_mean = go.Figure()
            # График медианной зарплаты
            fig_median.add_trace(go.Bar(
                x=exp_data['experience'],
                y=exp_data['median'],
                name='Медиана',
                marker=dict(color=self.colors['primary']),
                text=[f"{x:.0f} {currency}" for x in exp_data['median']],
                textposition='auto'
            ))
            fig_median.update_layout(
                title=f'Медианная зарплата по опыту работы ({currency})',
                xaxis_title='Опыт работы',
                yaxis_title=f'Зарплата ({currency})',
                height=400
            )
            # График средней зарплаты
            fig_mean.add_trace(go.Bar(
                x=exp_data['experience'],
                y=exp_data['mean'],
                name='Средняя',
                marker=dict(color=self.colors['danger']),
                text=[f"{x:.0f} {currency}" for x in exp_data['mean']],
                textposition='auto'
            ))
            fig_mean.update_layout(
                title=f'Средняя зарплата по опыту работы ({currency})',
                xaxis_title='Опыт работы',
                yaxis_title=f'Зарплата ({currency})',
                height=400
            )
            # Сохраняем оба графика по отдельности
            result['salary_by_experience_median'] = pio.to_html(fig_median, full_html=False, config=self.config)
            result['salary_by_experience_mean'] = pio.to_html(fig_mean, full_html=False, config=self.config)
        
        return result
    
    def _create_experience_schedule_block(self, data, filters):
        """Создание блока с анализом опыта и графика работы"""
        result = {}
        
        # Pie chart и Bar chart по опыту работы
        if 'experience' in data and len(data['experience']) >= 3:
            # Сортируем данные по опыту
            exp_items = sorted(data['experience'].items(), key=lambda x: self._sort_experience(x[0]))
            exp_labels = [item[0] for item in exp_items]
            exp_counts = [item[1] for item in exp_items]
            
            # 1. Круговая диаграмма (pie chart)
            fig = go.Figure()
            fig.add_trace(go.Pie(
                labels=exp_labels,
                values=exp_counts,
                textinfo='percent+label',
                marker=dict(colors=px.colors.qualitative.Set3),
                hole=0.4
            ))
            fig.update_layout(
                title='Распределение вакансий по опыту работы',
                height=400
            )
            result['experience_chart'] = pio.to_html(fig, full_html=False, config=self.config)
            
            # 2. Горизонтальная гистограмма (bar chart)
            fig_bar = go.Figure()
            fig_bar.add_trace(go.Bar(
                y=exp_labels,
                x=exp_counts,
                marker=dict(color=self.colors['primary']),
                text=exp_counts,
                textposition='auto',
                orientation='h'
            ))
            fig_bar.update_layout(
                title='Распределение вакансий по опыту работы (кол-во)',
                xaxis_title='Количество вакансий',
                height=400
            )
            result['experience_bar_chart'] = pio.to_html(fig_bar, full_html=False, config=self.config)
            
            print(f"[DEBUG] Созданы диаграммы по опыту: pie={len(result['experience_chart'])}, bar={len(result['experience_bar_chart'])}")
        
        # Bar/pie по графику работы
        if 'schedule' in data and len(data['schedule']) >= 2:
            fig = go.Figure()
            
            schedule_labels = list(data['schedule'].keys())
            schedule_counts = list(data['schedule'].values())
            
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
            
            result['schedule_chart'] = pio.to_html(fig, full_html=False, config=self.config)
        
        # Bar/pie по типу занятости
        if 'employment' in data and len(data['employment']) >= 2:
            fig = go.Figure()
            
            employment_labels = list(data['employment'].keys())
            employment_counts = list(data['employment'].values())
            
            fig.add_trace(go.Bar(
                x=employment_labels,
                y=employment_counts,
                marker=dict(color=self.colors['info']),
                text=employment_counts,
                textposition='auto'
            ))
            
            fig.update_layout(
                title='Распределение по типу занятости',
                xaxis_title='Тип занятости',
                yaxis_title='Количество вакансий',
                height=400
            )
            
            result['employment_chart'] = pio.to_html(fig, full_html=False, config=self.config)
        
        return result
    
    def _create_skills_block(self, data, filters):
        """Создание блока с анализом ключевых навыков"""
        result = {}
        
        # WordCloud (если >10 уникальных ключевых навыков)
        if 'all_skills' in data and len(data['all_skills']) > 10:
            try:
                wordcloud = WordCloud(
                    width=800, 
                    height=400, 
                    background_color='white', 
                    colormap='viridis'
                ).generate_from_frequencies(data['all_skills'])
                
                img = BytesIO()
                wordcloud.to_image().save(img, format='PNG')
                img.seek(0)
                
                result['skills_wordcloud'] = base64.b64encode(img.getvalue()).decode('utf-8')
            except Exception as e:
                print(f"Ошибка при создании облака слов: {e}")
        
        # Barplot топ-20 навыков
        if 'top_skills' in data and len(data['top_skills']) >= 5:
            fig = go.Figure()
            
            skills = list(data['top_skills'].keys())[:20]  # ограничиваем до 20
            counts = list(data['top_skills'].values())[:20]
            
            # Сортируем по убыванию
            skills_sorted = [x for _, x in sorted(zip(counts, skills), reverse=True)]
            counts_sorted = sorted(counts, reverse=True)
            
            fig.add_trace(go.Bar(
                y=skills_sorted,
                x=counts_sorted,
                marker=dict(color=self.colors['primary']),
                text=counts_sorted,
                textposition='auto',
                orientation='h'
            ))
            
            fig.update_layout(
                title='Топ-20 востребованных навыков',
                xaxis_title='Количество вакансий',
                height=600
            )
            
            result['top_skills_chart'] = pio.to_html(fig, full_html=False, config=self.config)
        
        return result
    
    def _create_employers_block(self, data, filters):
        """Создание блока с анализом работодателей"""
        result = {}
        
        # Топ-10 работодателей по количеству вакансий
        if 'top_employers' in data:
            fig = go.Figure()
            
            employers = list(data['top_employers'].keys())
            counts = list(data['top_employers'].values())
            
            # Сортируем по убыванию
            employers_sorted = [x for _, x in sorted(zip(counts, employers), reverse=True)]
            counts_sorted = sorted(counts, reverse=True)
            
            fig.add_trace(go.Bar(
                y=employers_sorted,
                x=counts_sorted,
                marker=dict(color=self.colors['success']),
                text=counts_sorted,
                textposition='auto',
                orientation='h'
            ))
            
            fig.update_layout(
                title='Топ работодателей по количеству вакансий',
                xaxis_title='Количество вакансий',
                height=500
            )
            
            result['top_employers_chart'] = pio.to_html(fig, full_html=False, config=self.config)
        
        # Средняя зарплата по работодателям
        if 'top_employers_detailed' in data:
            # Фильтруем только работодателей с данными о зарплате
            employers_with_salary = [
                e for e in data['top_employers_detailed'] 
                if 'avg_salary' in e
            ]
            
            if len(employers_with_salary) >= 2:
                fig = go.Figure()
                
                employers = [e['name'] for e in employers_with_salary]
                salaries = [e['avg_salary'] for e in employers_with_salary]
                
                # Сортируем по зарплате без ограничения количества
                sorted_data = sorted(zip(salaries, employers), reverse=True)
                salaries_sorted = [s for s, _ in sorted_data]
                employers_sorted = [e for _, e in sorted_data]
                
                currency = data.get('display_currency', 'BYN')
                
                # Добавляем горизонтальную гистограмму для лучшей читаемости
                fig.add_trace(go.Bar(
                    y=employers_sorted,
                    x=salaries_sorted,
                    marker=dict(color=self.colors['warning']),
                    text=[f"{s:.0f} {currency}" for s in salaries_sorted],
                    textposition='auto',
                    orientation='h'
                ))
                
                # Настраиваем высоту графика в зависимости от количества работодателей
                # для обеспечения достаточного пространства
                height = max(500, 100 + len(employers_with_salary) * 30) 
                
                fig.update_layout(
                    title=f'Средняя зарплата по работодателям ({currency})',
                    xaxis_title=f'Средняя зарплата ({currency})',
                    height=height
                )
                
                result['employers_salary_chart'] = pio.to_html(fig, full_html=False, config=self.config)
        
        return result
    
    def _create_tech_grid_block(self, data, filters):
        """Создание блока с визуальным интерактивом по технологиям"""
        result = {}
        
        # Treemap технологий (heatmap / treemap)
        if 'top_skills' in data and len(data['top_skills']) >= 10:
            fig = go.Figure()
            
            skills = list(data['top_skills'].keys())[:30]  # ограничиваем до 30
            counts = list(data['top_skills'].values())[:30]
            
            # Используем только имя для отображения и частоту как значение
            fig.add_trace(go.Treemap(
                labels=skills,
                parents=[""] * len(skills),
                values=counts,
                textinfo="label+value",
                marker=dict(
                    colorscale='Viridis',
                    cmid=np.mean(counts)
                )
            ))
            
            fig.update_layout(
                title='Карта технологий',
                height=600
            )
            
            result['tech_grid_chart'] = pio.to_html(fig, full_html=False, config=self.config)
        
        return result
    
    def _create_professions_block(self, data, filters):
        """Создание блока с рейтингом профессий/направлений"""
        result = {}
        
        # Список популярных IT-профессий для поиска в названиях вакансий
        professions = [
            {"name": "Backend разработчик", "keywords": ["backend", "бэкенд", "back-end", "backend developer"]},
            {"name": "Frontend разработчик", "keywords": ["frontend", "фронтенд", "front-end", "frontend developer"]},
            {"name": "Fullstack разработчик", "keywords": ["fullstack", "full stack", "full-stack", "фулстек"]},
            {"name": "Mobile разработчик", "keywords": ["mobile developer", "мобильный разработчик", "android", "ios", "flutter"]},
            {"name": "Data Scientist", "keywords": ["data scientist", "data science", "дата сайентист"]},
            {"name": "Data Analyst", "keywords": ["data analyst", "аналитик данных", "дата аналитик"]},
            {"name": "QA инженер", "keywords": ["qa", "quality assurance", "тестировщик", "тестирование"]},
            {"name": "DevOps инженер", "keywords": ["devops", "девопс", "sre"]},
            {"name": "Project Manager", "keywords": ["project manager", "менеджер проекта", "проджект менеджер", "pm"]},
            {"name": "Product Manager", "keywords": ["product manager", "продакт менеджер", "продукт менеджер"]},
            {"name": "UX/UI дизайнер", "keywords": ["ux/ui", "ui/ux", "дизайнер интерфейсов"]},
            {"name": "System Administrator", "keywords": ["system administrator", "системный администратор", "сисадмин"]},
            {"name": "Database Administrator", "keywords": ["dba", "database administrator", "администратор баз данных"]},
            {"name": "Machine Learning инженер", "keywords": ["machine learning", "ml engineer", "machine learning engineer"]},
            {"name": "Java разработчик", "keywords": ["java developer", "java разработчик"]},
            {"name": "Python разработчик", "keywords": ["python developer", "python разработчик"]},
            {"name": "C# разработчик", "keywords": ["c# developer", "c# разработчик", ".net developer"]},
            {"name": "JavaScript разработчик", "keywords": ["javascript developer", "js developer", "javascript разработчик"]},
            {"name": "PHP разработчик", "keywords": ["php developer", "php разработчик"]},
            {"name": "Golang разработчик", "keywords": ["golang developer", "golang разработчик", "go developer", "go разработчик"]}
        ]
        
        # Если в data есть данные о вакансиях
        if 'vacancy_names' in data and len(data['vacancy_names']) > 0:
            # Используем данные из списка вакансий
            vacancy_names = data['vacancy_names']
        else:
            # Если нет специального списка имен, создаем новый список
            # с пустыми результатами для демонстрации
            vacancy_names = []
        
        # Счетчик для каждой профессии
        profession_counts = Counter()
        
        # Проходим по всем названиям вакансий
        for vacancy_name in vacancy_names:
            vacancy_name_lower = vacancy_name.lower()
            for profession in professions:
                for keyword in profession["keywords"]:
                    if keyword.lower() in vacancy_name_lower:
                        profession_counts[profession["name"]] += 1
                        break  # Если нашли совпадение по ключевому слову, переходим к следующей вакансии
        
        # Проверяем, есть ли результаты
        if profession_counts:
            # Создаем горизонтальную гистограмму для профессий
            fig = go.Figure()
            
            # Сортируем по убыванию количества
            profession_names = []
            profession_values = []
            
            for name, count in profession_counts.most_common(15):  # Берем top-15 профессий
                profession_names.append(name)
                profession_values.append(count)
            
            # Добавляем горизонтальный bar chart
            fig.add_trace(go.Bar(
                y=profession_names,
                x=profession_values,
                marker=dict(color=self.colors['info']),
                text=profession_values,
                textposition='auto',
                orientation='h'
            ))
            
            fig.update_layout(
                title='Распределение вакансий по профессиям',
                xaxis_title='Количество вакансий',
                height=500
            )
            
            result['professions_chart'] = pio.to_html(fig, full_html=False, config=self.config)
            
            # Создаем круговую диаграмму для топ-7 профессий
            if len(profession_names) >= 5:
                fig_pie = go.Figure()
                
                # Берем топ-7 профессий
                top_names = profession_names[:7]
                top_values = profession_values[:7]
                
                # Если есть еще профессии, добавляем их в категорию "Другие"
                if len(profession_names) > 7:
                    other_sum = sum(profession_values[7:])
                    if other_sum > 0:
                        top_names.append('Другие')
                        top_values.append(other_sum)
                
                fig_pie.add_trace(go.Pie(
                    labels=top_names,
                    values=top_values,
                    textinfo='percent+label',
                    marker=dict(colors=px.colors.qualitative.Set3)
                ))
                
                fig_pie.update_layout(
                    title='Доля различных профессий в вакансиях',
                    height=400
                )
                
                result['professions_pie_chart'] = pio.to_html(fig_pie, full_html=False, config=self.config)
        
        return result
    
    def _sort_experience(self, exp_name):
        """Сортировка опыта работы в правильном порядке"""
        exp_order = {
            'Нет опыта': 0,
            'От 1 года до 3 лет': 1,
            'От 3 до 6 лет': 2,
            'Более 6 лет': 3
        }
        return exp_order.get(exp_name, 999) 