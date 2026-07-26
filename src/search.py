"""Детерминированный русско-английский разбор пользовательского запроса автомобиля."""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal

from src.domain.ids import canonical_hash
from src.domain.models import SavedSearch, UserSettings

KNOWN_MAKES = {
    "toyota",
    "lexus",
    "nissan",
    "infiniti",
    "bmw",
    "mercedes",
    "audi",
    "porsche",
    "land rover",
    "ford",
    "chevrolet",
    "honda",
    "mazda",
    "mitsubishi",
    "hyundai",
    "kia",
    "tesla",
}


@dataclass(frozen=True, slots=True)
class ParsedSearch:
    settings: UserSettings
    recognized: list[str]
    unknown: list[str]


def parse_search(query: str, user_id: int, language_code: str = "en") -> ParsedSearch:
    """Извлекает только явно указанные параметры и возвращает неизвестные слова."""
    normalized = " ".join(query.strip().split())
    lowered = normalized.casefold()
    settings = UserSettings(user_id=user_id, language_code=language_code)
    recognized: list[str] = []
    consumed: set[str] = set()

    make = next((value for value in KNOWN_MAKES if value in lowered), None)
    if make:
        settings.makes = [make.title()]
        recognized.append(f"make={make.title()}")
        consumed.update(make.split())

    budget_match = re.search(
        r"(?:budget|max|up to|до|бюджет)\s*[:=]?\s*([\d\s,]+)\s*(?:aed|дирхам)?",
        lowered,
    )
    if budget_match:
        value = _number(budget_match.group(1))
        if value > 0:
            settings.max_budget_aed = Decimal(value)
            recognized.append(f"budget={value} AED")

    year_range = re.search(r"\b(19\d{2}|20\d{2})\s*[-–]\s*(19\d{2}|20\d{2})\b", lowered)
    if year_range:
        settings.min_year = int(year_range.group(1))
        settings.max_year = int(year_range.group(2))
        recognized.append(f"years={settings.min_year}-{settings.max_year}")
    else:
        year = re.search(r"(?:from|от|year|год)\s*(19\d{2}|20\d{2})", lowered)
        if year:
            settings.min_year = int(year.group(1))
            recognized.append(f"year_from={settings.min_year}")

    mileage = re.search(
        r"(?:mileage|пробег)\s*[:=]?\s*(?:до|up to|max)?\s*([\d\s,]+)\s*(?:km|км)?",
        lowered,
    )
    if mileage:
        settings.max_mileage_km = _number(mileage.group(1))
        recognized.append(f"mileage<={settings.max_mileage_km} km")

    profit = re.search(r"(?:profit|прибыль)\s*[:=]?\s*([\d\s,]+)", lowered)
    if profit:
        settings.min_profit_aed = Decimal(_number(profit.group(1)))
        recognized.append(f"profit>={settings.min_profit_aed} AED")

    roi = re.search(r"(?:roi|рентабельность)\s*[:=]?\s*(\d+(?:[.,]\d+)?)", lowered)
    if roi:
        settings.min_roi_percent = Decimal(roi.group(1).replace(",", "."))
        recognized.append(f"ROI>={settings.min_roi_percent}%")

    if "gcc" in lowered:
        settings.specifications = ["GCC"]
        recognized.append("specification=GCC")
        consumed.add("gcc")

    parameter_words = {
        "budget",
        "max",
        "up",
        "to",
        "до",
        "бюджет",
        "aed",
        "дирхам",
        "from",
        "от",
        "year",
        "год",
        "mileage",
        "пробег",
        "km",
        "км",
        "profit",
        "прибыль",
        "roi",
        "рентабельность",
    }
    unknown = [
        token
        for token in re.findall(r"[a-zа-яё]+", lowered)
        if token not in parameter_words and token not in consumed and not token.isdigit()
    ]
    return ParsedSearch(settings=settings, recognized=recognized, unknown=unknown)


def build_saved_search(query: str, parsed: ParsedSearch) -> SavedSearch:
    search_id = canonical_hash(
        "saved-search/v1",
        {
            "user_id": parsed.settings.user_id,
            "query": query.strip(),
            "filters": parsed.settings.model_dump(mode="json"),
        },
    )[:20]
    return SavedSearch(
        search_id=search_id,
        user_id=parsed.settings.user_id,
        query_text=query.strip(),
        filters=parsed.settings,
        enabled=False,
    )


def _number(raw: str) -> int:
    digits = re.sub(r"\D", "", raw)
    return int(digits or 0)
