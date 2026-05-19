"""
Sentinel AI / hr MCP Server

Custom MCP server that provides HR computations for Kazakhstan labor law.

Exposes 5 tools:
  • get_mrp(year)                — Месячный расчётный показатель (МРП)
  • get_min_wage(year)            — Минимальная зарплата (МЗП)
  • calculate_vacation_days       — Расчёт дней отпуска по категории
  • calculate_severance           — Расчёт выходного пособия
  • get_indexed_amount            — Перевести значение в МРП в тенге

Run modes:
  python -m mcp_servers.hr.server --transport stdio
  python -m mcp_servers.hr.server --transport http --port 8102
"""
from __future__ import annotations

import logging
import time
from typing import Dict, Any

from mcp_servers import (
    MCPServer, ToolSchema, ToolResult,
    serve, make_arg_parser, setup_logging,
)
from . import bridge, mock_data

logger = logging.getLogger("mcp.hr")

# Простой кэш для live данных (TTL 1 час)
_CACHE: Dict[str, tuple[float, Any]] = {}
_CACHE_TTL = 3600


def _cache_get(key: str):
    item = _CACHE.get(key)
    if item is None:
        return None
    ts, val = item
    if time.time() - ts > _CACHE_TTL:
        _CACHE.pop(key, None)
        return None
    return val


def _cache_set(key: str, val):
    _CACHE[key] = (time.time(), val)


class HrMCPServer(MCPServer):
    """MCP-сервер для HR-расчётов по ТК РК."""

    def __init__(self):
        super().__init__("sentinel-hr", "1.0.0")

    def register_tools(self) -> None:

        # ── Tool 1: get_mrp ─────────────────────────────────────
        self.register_tool(
            ToolSchema(
                name="get_mrp",
                description=(
                    "Получить размер Месячного Расчётного Показателя (МРП) РК "
                    "на указанный год. МРП используется в РК для расчёта налогов, "
                    "штрафов, пособий, госпошлин. Например, МРП 2026 = 4 325 тенге."
                ),
                input_schema={
                    "type": "object",
                    "properties": {
                        "year": {
                            "type": "integer",
                            "description": "Год (например, 2026)",
                            "minimum": 2020, "maximum": 2030,
                        },
                    },
                    "required": ["year"],
                },
            ),
            self._tool_get_mrp,
        )

        # ── Tool 2: get_min_wage ────────────────────────────────
        self.register_tool(
            ToolSchema(
                name="get_min_wage",
                description=(
                    "Получить размер Минимальной Заработной Платы (МЗП) РК на год. "
                    "МЗП — установленный законом минимум, ниже которого работодатель "
                    "не вправе платить за полный рабочий месяц. МЗП 2026 = 85 000 тенге."
                ),
                input_schema={
                    "type": "object",
                    "properties": {
                        "year": {
                            "type":    "integer",
                            "minimum": 2020, "maximum": 2030,
                        },
                    },
                    "required": ["year"],
                },
            ),
            self._tool_get_min_wage,
        )

        # ── Tool 3: calculate_vacation_days ─────────────────────
        self.register_tool(
            ToolSchema(
                name="calculate_vacation_days",
                description=(
                    "Рассчитать количество дней оплачиваемого трудового отпуска "
                    "по Трудовому кодексу РК (ст. 88). Базовая норма — 24 календарных дня; "
                    "к ней добавляются бонусы за категорию работника "
                    "(вредные условия, инвалидность, северный регион, педагог)."
                ),
                input_schema={
                    "type": "object",
                    "properties": {
                        "category": {
                            "type": "string",
                            "description": (
                                "Категория работника. Допустимые значения: "
                                "'обычный', 'вредные_условия', 'инвалид_1_2_гр', "
                                "'несовершеннолетний', 'северный_регион', 'педагог'"
                            ),
                            "default": "обычный",
                        },
                        "extra_days": {
                            "type": "integer",
                            "description": "Дополнительные дни по индивидуальному договору",
                            "default": 0, "minimum": 0, "maximum": 60,
                        },
                    },
                    "required": [],
                },
            ),
            self._tool_calculate_vacation,
        )

        # ── Tool 4: calculate_severance ─────────────────────────
        self.register_tool(
            ToolSchema(
                name="calculate_severance",
                description=(
                    "Рассчитать размер выходного пособия при увольнении по ТК РК (ст. 131). "
                    "Принимает среднюю месячную зарплату и причину увольнения. "
                    "Возвращает сумму компенсации в тенге."
                ),
                input_schema={
                    "type": "object",
                    "properties": {
                        "average_monthly_salary": {
                            "type":    "number",
                            "minimum": 0,
                            "description": "Средняя месячная зарплата (тенге)",
                        },
                        "reason": {
                            "type": "string",
                            "description": (
                                "Причина: 'ликвидация', 'сокращение', 'несоответствие', "
                                "'восстановление', 'отказ_перевод', 'соглашение_сторон', "
                                "'по_собственному'"
                            ),
                        },
                    },
                    "required": ["average_monthly_salary", "reason"],
                },
            ),
            self._tool_calculate_severance,
        )

        # ── Tool 5: get_indexed_amount ──────────────────────────
        self.register_tool(
            ToolSchema(
                name="get_indexed_amount",
                description=(
                    "Перевести значение указанное в МРП в тенге для конкретного года. "
                    "Например, налоговый вычет 14 МРП в 2026 году = 14 × 4325 = 60 550 тенге."
                ),
                input_schema={
                    "type": "object",
                    "properties": {
                        "mrp_count": {
                            "type": "number", "minimum": 0,
                            "description": "Сколько МРП (например, 14 или 882)",
                        },
                        "year": {
                            "type":    "integer",
                            "minimum": 2020, "maximum": 2030,
                            "description": "Год для расчёта",
                        },
                    },
                    "required": ["mrp_count", "year"],
                },
            ),
            self._tool_get_indexed_amount,
        )

    # ─── Handlers ──────────────────────────────────────────────

    async def _tool_get_mrp(self, args: Dict[str, Any]) -> ToolResult:
        year = int(args.get("year") or 0)
        if not year:
            return ToolResult.error("year is required")

        # Сначала пробуем cache, потом live, потом mock
        ck = f"mrp:{year}"
        if cached := _cache_get(ck):
            return ToolResult.json(cached, cache_hit=True)

        # Live только для текущего/прошлого года (чтобы не дёргать API лишний раз)
        from datetime import datetime
        current_year = datetime.now().year
        if year >= current_year - 1:
            live, src = await bridge.fetch_current_mrp_mzp()
            if live and live.get("mrp") and live.get("year") == year:
                payload = {
                    "year": year, "value": live["mrp"], "unit": "тенге",
                    "name": "Месячный расчётный показатель (МРП)",
                    "source": "live_fetch", "live_url": live.get("url"),
                }
                _cache_set(ck, payload)
                return ToolResult.json(payload, cache_hit=False, source="live_fetch")

        # Mock fallback
        mock = mock_data.get_mrp(year)
        if not mock:
            return ToolResult.error(
                f"МРП для {year} года недоступен. "
                f"Доступные годы: {mock_data.list_available_years()['mrp_years']}"
            )
        _cache_set(ck, mock)
        return ToolResult.json(mock, cache_hit=False, source="mock_fallback")

    async def _tool_get_min_wage(self, args: Dict[str, Any]) -> ToolResult:
        year = int(args.get("year") or 0)
        if not year:
            return ToolResult.error("year is required")

        ck = f"mzp:{year}"
        if cached := _cache_get(ck):
            return ToolResult.json(cached, cache_hit=True)

        from datetime import datetime
        current_year = datetime.now().year
        if year >= current_year - 1:
            live, src = await bridge.fetch_current_mrp_mzp()
            if live and live.get("mzp") and live.get("year") == year:
                payload = {
                    "year": year, "value": live["mzp"], "unit": "тенге",
                    "name": "Минимальная заработная плата (МЗП)",
                    "source": "live_fetch", "live_url": live.get("url"),
                }
                _cache_set(ck, payload)
                return ToolResult.json(payload, cache_hit=False, source="live_fetch")

        mock = mock_data.get_min_wage(year)
        if not mock:
            return ToolResult.error(
                f"МЗП для {year} года недоступен. "
                f"Доступные годы: {mock_data.list_available_years()['mzp_years']}"
            )
        _cache_set(ck, mock)
        return ToolResult.json(mock, cache_hit=False, source="mock_fallback")

    async def _tool_calculate_vacation(self, args: Dict[str, Any]) -> ToolResult:
        category = (args.get("category") or "обычный").strip().lower()
        extra    = int(args.get("extra_days") or 0)

        if category not in mock_data.VACATION_BONUS:
            return ToolResult.error(
                f"Неизвестная категория '{category}'. "
                f"Допустимые: {list(mock_data.VACATION_BONUS.keys())}"
            )

        base  = mock_data.VACATION_BASE_DAYS
        bonus = mock_data.VACATION_BONUS[category]
        total = base + bonus + extra

        payload = {
            "category":     category,
            "base_days":    base,
            "bonus_days":   bonus,
            "extra_days":   extra,
            "total_days":   total,
            "law_reference": "Трудовой кодекс РК, ст. 88",
            "explanation":  (
                f"Базовая норма {base} дней + {bonus} дней за категорию "
                f"'{category}' + {extra} дополнительных дней = {total} календарных дней"
            ),
            "source": "computed",
        }
        return ToolResult.json(payload)

    async def _tool_calculate_severance(self, args: Dict[str, Any]) -> ToolResult:
        salary = float(args.get("average_monthly_salary") or 0)
        reason = (args.get("reason") or "").strip().lower()

        if salary <= 0:
            return ToolResult.error("average_monthly_salary must be > 0")
        if reason not in mock_data.SEVERANCE_BY_REASON:
            return ToolResult.error(
                f"Неизвестная причина '{reason}'. "
                f"Допустимые: {list(mock_data.SEVERANCE_BY_REASON.keys())}"
            )

        coef = mock_data.SEVERANCE_BY_REASON[reason]
        amount = salary * coef

        payload = {
            "average_monthly_salary": salary,
            "reason":                 reason,
            "coefficient":            coef,
            "severance_amount":       round(amount, 2),
            "currency":               "тенге",
            "law_reference":          "Трудовой кодекс РК, ст. 131",
            "explanation": (
                f"Выходное пособие = {salary:,.0f} × {coef} = {amount:,.0f} тенге "
                f"(основание: {reason})"
            ),
            "source": "computed",
        }
        return ToolResult.json(payload)

    async def _tool_get_indexed_amount(self, args: Dict[str, Any]) -> ToolResult:
        mrp_count = float(args.get("mrp_count") or 0)
        year      = int(args.get("year") or 0)
        if mrp_count <= 0 or not year:
            return ToolResult.error("mrp_count > 0 and year are required")

        mrp_info = mock_data.get_mrp(year)
        if not mrp_info:
            return ToolResult.error(
                f"МРП для {year} года недоступен"
            )

        mrp = mrp_info["value"]
        total = mrp_count * mrp

        payload = {
            "year":      year,
            "mrp_count": mrp_count,
            "mrp_value": mrp,
            "amount":    round(total, 2),
            "currency":  "тенге",
            "explanation": (
                f"{mrp_count} МРП × {mrp:,} тенге = {total:,.0f} тенге ({year} год)"
            ),
            "source": "computed",
        }
        return ToolResult.json(payload)


# ══════════════════════════════════════════════════════════════════
# Entry point
# ══════════════════════════════════════════════════════════════════

def main():
    parser = make_arg_parser(default_port=8102)
    args = parser.parse_args()
    setup_logging(args.log_level)
    server = HrMCPServer()
    serve(server, transport=args.transport, host=args.host, port=args.port)


if __name__ == "__main__":
    main()