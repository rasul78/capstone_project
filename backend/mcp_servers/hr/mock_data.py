"""
Sentinel AI / hr MCP — Mock fallback data

Справочник МРП, МЗП и базовых норм трудового права РК на 2020-2026 годы.
Источники: Закон о республиканском бюджете на соответствующий год,
adilet.zan.kz, официальные публикации pro1c.kz, mybuh.kz.
"""
from typing import Dict, Optional


# ── Базовые расчётные показатели РК ──────────────────────────────
# Год: значение в тенге
MRP_BY_YEAR: Dict[int, int] = {
    2020: 2_651,
    2021: 2_917,
    2022: 3_063,
    2023: 3_450,
    2024: 3_692,
    2025: 3_932,
    2026: 4_325,
}

MZP_BY_YEAR: Dict[int, int] = {
    2020: 42_500,
    2021: 42_500,
    2022: 60_000,
    2023: 70_000,
    2024: 85_000,
    2025: 85_000,
    2026: 85_000,
}

MIN_PENSION_BY_YEAR: Dict[int, int] = {
    2024: 57_853,
    2025: 62_771,
    2026: 69_049,
}

LIVING_WAGE_BY_YEAR: Dict[int, int] = {
    2024: 43_407,
    2025: 46_228,
    2026: 50_851,
}


# ── Нормы трудового отпуска по ТК РК ─────────────────────────────
# Минимум = 24 календарных дня (ст. 88 ТК РК)
# Дополнительные дни — за стаж, особые условия и т.п.

VACATION_BASE_DAYS = 24

# Категории работников с особыми правами (упрощённо)
VACATION_BONUS = {
    "обычный":           0,    # стандарт
    "вредные_условия":   6,    # ст. 96 ТК — +6 дней
    "инвалид_1_2_гр":    6,    # +6 дней
    "несовершеннолетний": 6,   # до 18 лет
    "северный_регион":   8,    # за работу в особых климатических условиях
    "педагог":           32,   # ст. 51 Закона "Об образовании" — суммарно 56 дней
}

# ── Выходное пособие при увольнении (ст. 131 ТК) ─────────────────
# Базовый коэффициент: 1 средняя месячная зарплата
SEVERANCE_BASE_MONTHS = 1.0

SEVERANCE_BY_REASON = {
    "ликвидация":           1.0,   # ликвидация работодателя
    "сокращение":           1.0,   # сокращение штата
    "несоответствие":       0.5,   # несоответствие должности (вина работника не доказана)
    "восстановление":       1.0,   # восстановление прежнего работника
    "отказ_перевод":        1.0,   # отказ от перевода в другую местность
    "соглашение_сторон":    0.0,   # по соглашению — без обязательной компенсации
    "по_собственному":      0.0,   # по собственному желанию — без компенсации
}


def get_mrp(year: int) -> Optional[Dict]:
    """Получить МРП на указанный год."""
    if year not in MRP_BY_YEAR:
        return None
    return {
        "year":  year,
        "value": MRP_BY_YEAR[year],
        "unit":  "тенге",
        "name":  "Месячный расчётный показатель (МРП)",
        "source": "mock_fallback",
    }


def get_min_wage(year: int) -> Optional[Dict]:
    """Получить минимальную зарплату (МЗП) на указанный год."""
    if year not in MZP_BY_YEAR:
        return None
    return {
        "year":  year,
        "value": MZP_BY_YEAR[year],
        "unit":  "тенге",
        "name":  "Минимальная заработная плата (МЗП)",
        "source": "mock_fallback",
    }


def get_living_wage(year: int) -> Optional[Dict]:
    if year not in LIVING_WAGE_BY_YEAR:
        return None
    return {
        "year":  year,
        "value": LIVING_WAGE_BY_YEAR[year],
        "unit":  "тенге",
        "name":  "Прожиточный минимум",
        "source": "mock_fallback",
    }


def list_available_years() -> Dict[str, list]:
    return {
        "mrp_years":         sorted(MRP_BY_YEAR.keys()),
        "mzp_years":         sorted(MZP_BY_YEAR.keys()),
        "pension_years":     sorted(MIN_PENSION_BY_YEAR.keys()),
        "living_wage_years": sorted(LIVING_WAGE_BY_YEAR.keys()),
    }