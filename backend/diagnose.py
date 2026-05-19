"""
Sentinel AI — Deep Chat Pipeline Diagnostic

Делает прямые вызовы на каждом шаге pipeline отдельно,
чтобы точно увидеть где висит.

Запуск (требует backend на :8000 + MCP-серверы на :8101-8103):
    python diagnose_chat.py
"""
import sys, time, json, urllib.request, urllib.error

BASE = "http://localhost:8000"

def t0():
    return time.time()

def elapsed(start):
    return int((time.time() - start) * 1000)

def post(url, body, timeout=120):
    req = urllib.request.Request(
        url, data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"}, method="POST"
    )
    return urllib.request.urlopen(req, timeout=timeout)

def get(url, timeout=10):
    return urllib.request.urlopen(url, timeout=timeout)


print("=" * 60)
print("  Sentinel AI — Deep Chat Pipeline Diagnostic")
print("=" * 60)

# ── 0. Backend doesn't even respond? ─────────────────────────
print("\n[0] Backend / endpoint health")
try:
    s = t0()
    r = get(f"{BASE}/", timeout=3)
    print(f"  [OK] GET / responds in {elapsed(s)}ms")
except Exception as e:
    print(f"  [FAIL] GET / — {e}")
    sys.exit(1)

# ── 1. MCP direct call (mcp_routes endpoint) ─────────────────
print("\n[1] Direct MCP call (no LLM, no RAG)")
try:
    s = t0()
    r = post(f"{BASE}/api/mcp/call", {
        "server": "hr", "tool": "get_mrp", "arguments": {"year": 2026}
    }, timeout=15)
    d = json.loads(r.read())
    print(f"  Response in {elapsed(s)}ms")
    print(f"  ok={d.get('ok')}, latency={d.get('latency_ms')}ms")
    if d.get("data"):
        print(f"  data: {d['data']}")
except Exception as e:
    print(f"  [FAIL] {e}")

# ── 2. MCP heuristic (no HTTP, no MCP servers) ───────────────
print("\n[2] Importing heuristic check (mcp_integration module)")
try:
    sys.path.insert(0, ".")
    from mcp_integration import heuristic_tool_calls
    for q in ["Что говорит статья 84 ТК РК?",
              "Какой МРП в 2026 году?",
              "Сколько дней отпуска у педагога?"]:
        calls = heuristic_tool_calls(q)
        print(f"  '{q[:50]}...' → {len(calls)} calls: {[(c['server'], c['tool']) for c in calls]}")
except Exception as e:
    print(f"  [FAIL] {e}")

# ── 3. Chat WITHOUT mcp/web/rerank — minimal ─────────────────
print("\n[3] Chat WITHOUT mcp/web/rerank (should be FAST)")
try:
    s = t0()
    r = post(f"{BASE}/api/kb/chat/fast/v2", {
        "question":   "Hello world test",
        "session_id": "diag1",
        "use_cache":  False,
        "rerank":     False,
        "use_web":    False,
        "use_mcp":    False,
    }, timeout=30)
    d = json.loads(r.read())
    print(f"  Total: {elapsed(s)}ms, server reported: {d.get('latency_ms')}ms")
    print(f"  Mode: {d.get('mode')}, flags: {d.get('flags')}")
except urllib.error.HTTPError as e:
    print(f"  [FAIL] HTTP {e.code}: {e.read()[:200]}")
except Exception as e:
    print(f"  [FAIL after {elapsed(s)}ms] {e}")

# ── 4. Chat WITH MCP but no web ──────────────────────────────
print("\n[4] Chat WITH MCP, NO web/rerank")
try:
    s = t0()
    r = post(f"{BASE}/api/kb/chat/fast/v2", {
        "question":   "Что говорит статья 84 ТК РК?",
        "session_id": "diag2",
        "use_cache":  False,
        "rerank":     False,
        "use_web":    False,
        "use_mcp":    True,
    }, timeout=60)
    d = json.loads(r.read())
    print(f"  Total: {elapsed(s)}ms, server reported: {d.get('latency_ms')}ms")
    print(f"  Mode: {d.get('mode')}")
    print(f"  MCP tools used: {d.get('mcp_tools_used')}")
    print(f"  Flags: {d.get('flags')}")
    print(f"  Answer preview: {d.get('answer', '')[:200]}...")
except urllib.error.HTTPError as e:
    print(f"  [FAIL] HTTP {e.code}: {e.read()[:200]}")
except Exception as e:
    print(f"  [FAIL after {elapsed(s)}ms] {e}")

# ── 5. Chat with all features ────────────────────────────────
print("\n[5] Chat with ALL features (no cache)")
try:
    s = t0()
    r = post(f"{BASE}/api/kb/chat/fast/v2", {
        "question":   "Какой МРП в 2026 году?",
        "session_id": "diag3",
        "use_cache":  False,
        "rerank":     True,
        "use_web":    True,
        "use_mcp":    True,
    }, timeout=120)
    d = json.loads(r.read())
    print(f"  Total: {elapsed(s)}ms")
    print(f"  Mode: {d.get('mode')}, MCP: {d.get('mcp_tools_used')}")
    print(f"  Flags: {d.get('flags')}")
except urllib.error.HTTPError as e:
    print(f"  [FAIL] HTTP {e.code}: {e.read()[:200]}")
except Exception as e:
    print(f"  [FAIL after {elapsed(s)}ms] {e}")

print()
print("=" * 60)
print("  ANALYSIS")
print("=" * 60)
print("""
Если шаг [1] (MCP direct) — быстро (<2s), значит MCP ОК.
Если шаг [2] (heuristic) — показывает calls, значит routing ОК.
Если шаг [3] (no features) — быстро, значит pipeline сам по себе ОК.
Если шаг [4] (MCP only, no rerank) — работает, значит проблема в reranker/web.
Если шаг [5] виснет — почти точно reranker качается, либо web search висит.

Если шаг [4] показывает Mode='rag_mcp' и MCP tools используются:
   → бэкенд работает правильно, проблема во фронте (кэш)
Если шаг [4] показывает Mode='rag' без MCP:
   → проблема в chat_fast_v2.py (старая версия?)
""")