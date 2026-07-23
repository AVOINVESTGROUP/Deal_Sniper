import os
import json
import google.generativeai as genai
from src.models import ListingItem, DealEvaluation

class GeminiEvaluator:
    """Класс для оценки привлекательности сделок с помощью Gemini 1.5 Flash."""
    
    def __init__(self) -> None:
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("Переменная окружения GEMINI_API_KEY не задана.")
        
        genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel("gemini-1.5-flash")
    
    async def evaluate_listing(self, item: ListingItem) -> DealEvaluation:
        """
        Асинхронная экспресс-оценка автомобильного объявления с использованием Gemini API.
        Возвращает структурированный DealEvaluation.
        """
        prompt = f"""
        Выступай в роли эксперта по оценке б/у автомобилей на рынке ОАЭ (Дубай, Абу-Даби).
        Проведи экспресс-анализ следующего автомобильного объявления с фиксированной ценой:
        
        Название: {item.title}
        Текущая цена (AED): {item.price}
        Локация: {item.location}
        Источник: {item.source}
        Ссылка: {item.url}
        VIN: {item.vin or "Не указан"}
        Описание: {item.raw_description}
        
        Инструкции по оценке:
        1. Оцени рыночную стоимость аналогичного исправного объекта в ОАЭ.
        2. Если в описании есть намеки на повреждения, ДТП или необходимость ремонта, предположи стоимость ремонта в промышленных зонах (например, автосервисах Al Quoz в Дубае).
        3. Рассчитай процент скидки (discount_percent) относительно рыночной стоимости.
        4. Рассчитай потенциальную чистую прибыль (potential_profit_aed) = Рыночная цена - Текущая цена - Стоимость ремонта.
        5. Поставь оценку (deal_score) от 1 до 10.
        6. Определи выгодность (is_deal) - True, если discount_percent >= 15% и deal_score >= 7.
        """
        
        # Вызов Gemini API с поддержкой Structured Output
        response = self.model.generate_content(
            prompt,
            generation_config=genai.GenerationConfig(
                response_mime_type="application/json",
                response_schema=DealEvaluation
            )
        )
        
        # Десериализация ответа
        data = json.loads(response.text)
        return DealEvaluation(**data)
