import requests
import logging
from datetime import datetime
from functools import lru_cache

class CurrencyConverter:

    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.base_currency = 'BYN'
        
        # Фиксированные курсы валют (на случай недоступности API)
        self.fallback_rates = {
            'BYN': 1.0,
            'USD': 3.22,  # ~3.22 BYN за 1 USD
            'EUR': 3.48,  # ~3.48 BYN за 1 EUR
            'RUB': 0.034,  # ~0.034 BYN за 1 RUB (3.4 BYN за 100 RUB)
            'RUR': 0.034,  # Alias для российского рубля (идентичен RUB)
            'KZT': 0.0072,  # Казахстанский тенге
            'UZS': 0.00026,  # Узбекский сум
            'KGS': 0.036,  # Киргизский сом
        }

        self.rates = {}
        self.last_update = None
        self.update_rates()
    
    @lru_cache(maxsize=1)
    def update_rates(self, force=False):
        try:
            # Можно использовать API НБРБ или другие открытые API для курсов валют
            # Пример: https://www.nbrb.by/api/exrates/rates?periodicity=0
            response = requests.get('https://www.nbrb.by/api/exrates/rates?periodicity=0')
            
            if response.status_code != 200:
                self.logger.warning(f"Не удалось получить курсы валют. Код: {response.status_code}")
                return self.fallback_rates
                
            rates_data = response.json()

            rates = {self.base_currency: 1.0}
            
            for rate in rates_data:
                currency = rate.get('Cur_Abbreviation')
                if currency in ['USD', 'EUR', 'RUB', 'KZT', 'UZS', 'KGS']:
                    scale = rate.get('Cur_Scale', 1)
                    value = rate.get('Cur_OfficialRate', 0)
                    
                    if value > 0:
                        rates[currency] = value / scale
                    else:
                        rates[currency] = self.fallback_rates.get(currency, 1.0)

            if 'RUB' in rates:
                rates['RUR'] = rates['RUB']
            else:
                rates['RUB'] = self.fallback_rates.get('RUB', 1.0)
                rates['RUR'] = rates['RUB']
                
            self.logger.info(f"Курсы валют обновлены: {rates}")
            self.rates = rates
            self.last_update = datetime.now()
            return rates
            
        except Exception as e:
            self.logger.error(f"Ошибка при обновлении курсов валют: {e}")
            self.rates = self.fallback_rates
            return self.fallback_rates
    
    def convert(self, amount, from_currency, to_currency):
        if amount is None or amount == 0:
            return 0

        from_currency = from_currency.upper() if from_currency else self.base_currency
        to_currency = to_currency.upper() if to_currency else self.base_currency

        if from_currency == 'RUR':
            from_currency = 'RUB'
        if to_currency == 'RUR':
            to_currency = 'RUB'

        if from_currency == to_currency:
            return amount

        rates = self.rates if self.rates else self.update_rates()

        if from_currency not in rates:
            self.logger.warning(f"Курс для {from_currency} не найден, использую запасное значение")
            from_rate = self.fallback_rates.get(from_currency, 1.0)
        else:
            from_rate = rates[from_currency]
            
        if to_currency not in rates:
            self.logger.warning(f"Курс для {to_currency} не найден, использую запасное значение")
            to_rate = self.fallback_rates.get(to_currency, 1.0)
        else:
            to_rate = rates[to_currency]

        if to_currency == 'BYN':
            converted_amount = amount * from_rate
        elif from_currency == 'BYN':
            converted_amount = amount / to_rate
        else:
            converted_amount = amount * from_rate / to_rate
        
        return round(converted_amount, 2)
    
    def convert_all(self, data, target_currency='BYN'):
        result = data.copy()

        result['display_currency'] = target_currency

        if 'salary_stats' in result:
            for key in ['min', 'max', 'mean', 'median']:
                result['salary_stats'][key] = self.convert(
                    result['salary_stats'][key],
                    self.base_currency,
                    target_currency
                )

        if 'salary_histogram' in result:
            result['salary_histogram']['bins'] = [
                self.convert(edge, self.base_currency, target_currency)
                for edge in result['salary_histogram']['bins']
            ]

        if 'salary_by_region' in result:
            for region_data in result['salary_by_region']:
                region_data['mean'] = self.convert(
                    region_data['mean'],
                    self.base_currency,
                    target_currency
                )
                region_data['median'] = self.convert(
                    region_data['median'],
                    self.base_currency,
                    target_currency
                )

        if 'salary_by_experience' in result:
            for exp_data in result['salary_by_experience']:
                exp_data['mean'] = self.convert(
                    exp_data['mean'], 
                    self.base_currency, 
                    target_currency
                )
                exp_data['median'] = self.convert(
                    exp_data['median'], 
                    self.base_currency, 
                    target_currency
                )

        if 'top_employers_detailed' in result:
            for employer_data in result['top_employers_detailed']:
                if 'avg_salary' in employer_data:
                    employer_data['avg_salary'] = self.convert(
                        employer_data['avg_salary'],
                        self.base_currency,
                        target_currency
                    )

        if 'coordinates' in result:
            for coord in result['coordinates']:
                if coord.get('salary'):
                    salary = coord['salary']
                    
                    if salary.get('from'):
                        salary['from'] = self.convert(
                            salary['from'],
                            salary.get('currency', self.base_currency),
                            target_currency
                        )
                        
                    if salary.get('to'):
                        salary['to'] = self.convert(
                            salary['to'],
                            salary.get('currency', self.base_currency),
                            target_currency
                        )
                        
                    salary['currency'] = target_currency
        
        return result 
