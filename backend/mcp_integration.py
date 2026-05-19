"""
Sentinel AI — MCP Integration Layer

Расширяет chat_fast_v2 pipeline шагом «MCP enrichment»:
  rewrite → retrieve → hybrid → rerank →
      ↓ (NEW)
   suggest_mcp_servers(query)
      ↓
   parallel: call_mcp_tools(...)
      ↓
   build_context(rag + web + MCP results)
      ↓
   LLM synthesis

Также реализует LLM-driven tool selection:
  Если эвристика routing не сработала, спросим у Groq:
  «Какие MCP-инструменты применимы к этому вопросу?»
"""
from __future__ import annotations

import json
import asyncio
import logging
from typing import List, Dict, Any, Optional

from mcp_client import mcp_registry, suggest_servers

logger = logging.getLogger("sentinel.mcp_integration")


# ════════════════════════════════════════════════════════════════════
# Step 1: эвристика + LLM-driven tool selection
# ════════════════════════════════════════════════════════════════════

# Сопоставление "когда что вызывать" — для эвристики без LLM
HEURISTIC_TOOL_HINTS = {
    "legal_rk.search_law": [
        "что говорит закон", "по закону рк", "законодательство",
        "штраф", "санкция", "наказание",
    ],
    "legal_rk.get_article": [
        "статья", "ст.", "ст ",
    ],
    "hr.get_mrp": [
        "мрп", "месячный расчётный", "месячный расчетный",
    ],
    "hr.get_min_wage": [
        "мзп", "минимальная зарплата", "минималка",
    ],
    "hr.calculate_vacation_days": [
        "сколько дней отпуска", "отпуск дней", "дней отпуска",
        "отпуск у", "отпуск для", "продолжительность отпуска",
    ],
    "hr.calculate_severance": [
        "выходное пособие", "компенсация при увольнении",
    ],
    "hr.get_indexed_amount": [
        "вычет в мрп", "перевести мрп", "мрп в тенге",
    ],
    "docs.search_documents": [
        "наша политика", "у нас в компании", "корпоративный документ",
    ],
}


def heuristic_tool_calls(query: str) -> List[Dict[str, Any]]:
    """
    Эвристика: какие MCP tools имеет смысл вызвать.
    Возвращает [{"server": "hr", "tool": "get_mrp", "extracted_args": {...}}].
    """
    q = query.lower()
    calls = []

    # Сначала — какие сервера триггерятся
    suggested = suggest_servers(query)

    # Потом — какие конкретно tools
    for full_name, keywords in HEURISTIC_TOOL_HINTS.items():
        server, tool = full_name.split(".", 1)
        if server not in suggested:
            continue
        if any(kw in q for kw in keywords):
            calls.append({
                "server":         server,
                "tool":           tool,
                "extracted_args": _extract_args(query, server, tool),
            })

    return calls


def _extract_args(query: str, server: str, tool: str) -> Dict[str, Any]:
    """Простая извлекалка аргументов из query через regex."""
    import re
    q = query.lower()
    args: Dict[str, Any] = {}

    # Год
    if "year" in _tool_args(server, tool):
        m = re.search(r"\b(20\d{2})\b", q)
        if m:
            args["year"] = int(m.group(1))
        else:
            from datetime import datetime
            args["year"] = datetime.now().year

    # Номер статьи
    if tool == "get_article":
        m = re.search(r"стать[яю и]\s*(\d{1,4})", q)
        if m:
            args["article_number"] = m.group(1)
        # Код кодекса
        for code in ["ук рк", "гк рк", "тк рк", "коап"]:
            if code in q:
                args["code"] = code
                break

    # Категория отпуска
    if tool == "calculate_vacation_days":
        for cat in ["педагог", "вредные", "инвалид", "несовершеннолетний", "северный"]:
            if cat in q:
                args["category"] = (
                    "вредные_условия" if cat == "вредные"
                    else "инвалид_1_2_гр" if cat == "инвалид"
                    else "северный_регион" if cat == "северный"
                    else cat
                )
                break

    # Поисковый запрос
    if tool in ("search_law", "search_documents"):
        args["query"] = query[:300]

    # mrp_count
    if tool == "get_indexed_amount":
        m = re.search(r"(\d+)\s*мрп", q)
        if m:
            args["mrp_count"] = int(m.group(1))

    return args


def _tool_args(server: str, tool: str) -> List[str]:
    """Возвращает имена параметров tool из schema (если сервер healthy).

    Если registry не инициализирован, использует хардкод-fallback —
    чтобы arg-extraction работала в unit-тестах и при cold start."""
    # Live lookup
    if server in mcp_registry.clients:
        schema = mcp_registry.clients[server].tools.get(tool, {})
        props = schema.get("inputSchema", {}).get("properties", {})
        if props:
            return list(props.keys())
    # Fallback: hardcoded param names for known tools
    fallback = {
        ("hr", "get_mrp"):                    ["year"],
        ("hr", "get_min_wage"):               ["year"],
        ("hr", "calculate_vacation_days"):    ["category", "extra_days"],
        ("hr", "calculate_severance"):        ["average_monthly_salary", "reason"],
        ("hr", "get_indexed_amount"):         ["mrp_count", "year"],
        ("legal_rk", "search_law"):           ["query", "limit"],
        ("legal_rk", "get_article"):          ["code", "article_number"],
        ("legal_rk", "fetch_law_page"):       ["url"],
        ("legal_rk", "list_codes"):           [],
        ("docs", "search_documents"):         ["query", "top_k"],
        ("docs", "list_documents"):           ["category", "limit"],
        ("docs", "get_document"):             ["doc_id"],
        ("docs", "get_kb_stats"):             [],
    }
    return fallback.get((server, tool), [])


# ════════════════════════════════════════════════════════════════════
# Step 2: параллельный вызов MCP tools
# ════════════════════════════════════════════════════════════════════

async def execute_mcp_calls(calls: List[Dict[str, Any]], timeout: float = 10.0
                            ) -> List[Dict[str, Any]]:
    """Параллельно вызывает все указанные tools. Возвращает результаты."""
    if not calls:
        return []

    async def _one(call):
        result = await mcp_registry.call(
            call["server"], call["tool"], call.get("extracted_args", {})
        )
        return {
            "server":     call["server"],
            "tool":       call["tool"],
            "args":       call.get("extracted_args", {}),
            "ok":         result.ok,
            "data":       result.data,
            "text":       result.text,
            "error":      result.error,
            "latency_ms": result.latency_ms,
        }

    try:
        results = await asyncio.wait_for(
            asyncio.gather(*[_one(c) for c in calls]),
            timeout=timeout
        )
    except asyncio.TimeoutError:
        logger.warning(f"[mcp_integration] timeout for {len(calls)} calls")
        return []

    return results


# ════════════════════════════════════════════════════════════════════
# Step 3: форматирование результатов для LLM-контекста
# ════════════════════════════════════════════════════════════════════

def format_mcp_results_for_llm(results: List[Dict[str, Any]]) -> str:
    """Преобразует MCP-результаты в красивый текст для добавления в контекст LLM."""
    if not results:
        return ""

    lines = ["", "🔧 РЕЗУЛЬТАТЫ ИЗ ВНЕШНИХ MCP-ИНСТРУМЕНТОВ:"]

    for i, r in enumerate(results, 1):
        if not r["ok"]:
            lines.append(f"\n[Tool {i}: {r['server']}.{r['tool']}] ❌ {r['error']}")
            continue

        data = r.get("data")
        if not data:
            # Если data не было, используем raw text (но он обычно тот же JSON)
            text = r.get("text", "")
            if text:
                lines.append(f"\n[Tool {i}: {r['server']}.{r['tool']}]\n{text[:800]}")
            continue

        # Структурированный data — форматируем читаемо
        lines.append(f"\n[Tool {i}: {r['server']}.{r['tool']}] "
                     f"({r['latency_ms']}ms)")

        if isinstance(data, dict):
            # Если есть explanation — берём его (для calc-инструментов)
            if "explanation" in data:
                lines.append(f"  {data['explanation']}")
                if "law_reference" in data:
                    lines.append(f"  Источник: {data['law_reference']}")

            # Если статья закона
            elif "article" in data:
                a = data["article"]
                lines.append(f"  {a.get('code')} ст.{a.get('article_number')}: "
                             f"{a.get('title')}")
                lines.append(f"  {a.get('text', '')[:500]}")

            # Если значение МРП/МЗП
            elif "value" in data and "unit" in data:
                lines.append(f"  {data.get('name', 'Значение')}: "
                             f"{data['value']:,} {data['unit']} ({data.get('year', '')})")

            # Если результаты поиска
            elif "results" in data:
                lines.append(f"  Найдено: {data.get('count', len(data['results']))}")
                for j, item in enumerate(data["results"][:3], 1):
                    title = item.get("title") or item.get("doc_name") or "?"
                    snippet = (item.get("snippet") or item.get("chunk_preview")
                               or item.get("text") or "")
                    lines.append(f"  {j}. {title}: {snippet[:200]}")

            # Generic fallback — компактный JSON
            else:
                lines.append(f"  {json.dumps(data, ensure_ascii=False)[:500]}")

    return "\n".join(lines)


# ════════════════════════════════════════════════════════════════════
# Step 4: главный entry point — enrichment функция
# ════════════════════════════════════════════════════════════════════

async def enrich_with_mcp(query: str, max_tools: int = 3,
                          timeout: float = 8.0) -> Dict[str, Any]:
    """
    Главный entry point: даёт строку для добавления в LLM-контекст
    и список tools которые были вызваны (для tracing/UI).
    """
    if not mcp_registry._initialized:
        logger.warning("[mcp_integration] registry не инициализирован")
        return {"text": "", "tools_used": [], "results": []}

    # 1. Эвристика
    calls = heuristic_tool_calls(query)[:max_tools]
    if not calls:
        return {"text": "", "tools_used": [], "results": []}

    logger.info(f"[mcp_integration] query='{query[:50]}' → calls={[(c['server'], c['tool']) for c in calls]}")

    # 2. Параллельный вызов
    results = await execute_mcp_calls(calls, timeout=timeout)

    # 3. Форматирование
    text = format_mcp_results_for_llm(results)
    tools_used = [f"{r['server']}.{r['tool']}" for r in results if r["ok"]]

    return {
        "text":       text,
        "tools_used": tools_used,
        "results":    results,
    }