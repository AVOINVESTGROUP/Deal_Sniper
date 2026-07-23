import os
import sqlite3
from datetime import datetime

class DealDatabase:
    """Модуль локальной базы данных SQLite для дедупликации и истории объявлений."""
    
    def __init__(self, db_path: str = "data/deals.db") -> None:
        self.db_path = db_path
        # Создаем каталог базы данных, если его нет
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self.init_db()
        
    def init_db(self) -> None:
        """Инициализирует таблицу seen_listings в SQLite."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS seen_listings (
                    url TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    is_deal INTEGER DEFAULT 0,
                    deal_score INTEGER DEFAULT 0,
                    alert_sent INTEGER DEFAULT 0
                )
            """)
            conn.commit()
            
    def is_seen(self, url: str) -> bool:
        """Проверяет, было ли объявление уже обработано."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT 1 FROM seen_listings WHERE url = ?", (url,))
            return cursor.fetchone() is not None
            
    def add_seen(self, url: str, is_deal: bool = False, deal_score: int = 0, alert_sent: bool = False) -> None:
        """Добавляет объявление в базу данных."""
        now = datetime.utcnow().isoformat()
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR IGNORE INTO seen_listings (url, created_at, is_deal, deal_score, alert_sent)
                VALUES (?, ?, ?, ?, ?)
            """, (url, now, int(is_deal), deal_score, int(alert_sent)))
            conn.commit()
            
    def mark_alert_sent(self, url: str) -> None:
        """Помечает отправку уведомления в Telegram как успешную."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE seen_listings SET alert_sent = 1 WHERE url = ?", (url,))
            conn.commit()
