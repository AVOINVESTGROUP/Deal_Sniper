from pydantic import BaseModel, Field
from typing import List, Optional

class ListingItem(BaseModel):
    """Pydantic-модель исходного объявления с веб-ресурса."""
    title: str = Field(..., description="Название объявления")
    price: float = Field(..., description="Текущая цена в AED")
    location: str = Field(..., description="Локация (город / район в ОАЭ)")
    source: str = Field(..., description="Источник автомобильного объявления (например, Dubizzle)")
    url: str = Field(..., description="Ссылка на объявление")
    raw_description: str = Field(..., description="Текстовое описание автомобиля")
    image_urls: List[str] = Field(default=[], description="Список ссылок на изображения автомобиля")
    vin: Optional[str] = Field(None, description="VIN-номер автомобиля (если применим)")

class DealEvaluation(BaseModel):
    """Pydantic-модель оценки автомобильного объявления ИИ-агентом."""
    is_deal: bool = Field(..., description="Является ли предложение выгодной сделкой с дисконтом")
    discount_percent: float = Field(..., description="Процент скидки от рыночной стоимости")
    estimated_market_price: float = Field(..., description="Оценочная рыночная стоимость аналогичного объекта в ОАЭ в AED")
    potential_profit_aed: float = Field(..., description="Потенциальная чистая прибыль в AED")
    repair_estimate_aed: float = Field(..., description="Ориентировочная стоимость ремонта в AED (в автосервисах Al Quoz)")
    reasoning: str = Field(..., description="Краткое обоснование оценки ИИ")
    deal_score: int = Field(..., description="Оценка привлекательности сделки (от 1 до 10)")
