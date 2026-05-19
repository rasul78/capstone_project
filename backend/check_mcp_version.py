"""
check_mcp_version.py — verify backend/mcp_integration.py is the latest version.
"""
from pathlib import Path
import sys

p = Path("mcp_integration.py")
if not p.exists():
    print("Run from backend/ directory. mcp_integration.py not found.")
    sys.exit(1)

text = p.read_text(encoding="utf-8")

print("=" * 50)
print("  mcp_integration.py version check")
print("=" * 50)

has_fallback = "Fallback: hardcoded param names" in text
print(f"  Fallback table:                {'[OK]' if has_fallback else '[MISSING]'}")

has_extra_vacation = '"отпуск у"' in text and '"отпуск для"' in text
print(f"  Expanded vacation keywords:    {'[OK]' if has_extra_vacation else '[MISSING]'}")

if has_fallback and has_extra_vacation:
    print()
    print("Latest version installed. Tests should pass.")
    print("If they still fail, clear cache:")
    print("  Remove-Item -Recurse -Force __pycache__")
else:
    print()
    print("OLD version of mcp_integration.py installed.")
    print("Replace backend/mcp_integration.py with the latest")
    print("download, then run:")
    print("  Remove-Item -Recurse -Force __pycache__")
    print("  python -m pytest tests/test_mcp_integration.py -v")