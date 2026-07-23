import os
import urllib.parse
import httpx
from src.models import ListingItem, DealEvaluation

class TelegramNotifier:
    """Модуль отправки уведомлений о выгодных сделках в Telegram."""
    
    def __init__(self) -> None:
        self.bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
        self.chat_id = os.getenv("TELEGRAM_CHAT_ID")
        self.rate = float(os.getenv("AED_TO_USD_RATE", "3.6725"))
        
    async def send_deal_alert(self, item: ListingItem, eval_res: DealEvaluation) -> bool:
        """Отправляет красивое структурированное HTML-сообщение в Telegram."""
        if not self.bot_token or not self.chat_id:
            # Если ключи не настроены, логируем в консоль
            print(f"[Notifier MOCK] Telegram не настроен. Пропускаем отправку для: {item.title}")
            return True
            
        # Расчет в USD
        price_usd = item.price / self.rate
        market_usd = eval_res.estimated_market_price / self.rate
        profit_usd = eval_res.potential_profit_aed / self.rate
        repair_usd = eval_res.repair_estimate_aed / self.rate
        
        # Генерация ссылки в WhatsApp (заглушка номера перекупщика/продавца)
        message_text = f"Привет! Интересует объявление: {item.title} ({item.url})"
        encoded_text = urllib.parse.quote(message_text)
        whatsapp_url = f"https://wa.me/971500000000?text={encoded_text}"
        
        # Форматирование сообщения
        html_content = (
            f"🚨 <b>БЫСТРАЯ СДЕЛКА! Оценка: {eval_res.deal_score}/10</b> 🚨\n"
            f"<b>Название:</b> {item.title}\n"
            f"<b>Источник:</b> {item.source} | <b>Локация:</b> {item.location}\n\n"
            f"💰 <b>Цена предложения:</b> {item.price:,.0f} AED (~${price_usd:,.0f} USD)\n"
            f"📊 <b>Рыночная стоимость:</b> {eval_res.estimated_market_price:,.0f} AED (~${market_usd:,.0f} USD)\n"
            f"🛠️ <b>Оценка ремонта (Al Quoz):</b> {eval_res.repair_estimate_aed:,.0f} AED (~${repair_usd:,.0f} USD)\n"
            f"🔥 <b>Дисконт:</b> {eval_res.discount_percent:.1f}%\n"
            f"💵 <b>Потенциальная прибыль:</b> <b>{eval_res.potential_profit_aed:,.0f} AED</b> (~${profit_usd:,.0f} USD)\n\n"
            f"📝 <b>Анализ ИИ:</b> {eval_res.reasoning}\n\n"
            f"🔗 <a href='{item.url}'>Открыть объявление</a>\n"
            f"💬 <a href='{whatsapp_url}'>Связаться в WhatsApp</a>"
        )
        
        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        payload = {
            "chat_id": self.chat_id,
            "text": html_content,
            "parse_mode": "HTML",
            "disable_web_page_preview": False
        }
        
        async with httpx.AsyncClient() as client:
            response = await client.post(url, json=payload, timeout=10)
            if response.status_code == 200:
                return True
            else:
                print(f"Ошибка отправки в Telegram: {response.status_code} - {response.text}")
                return False
