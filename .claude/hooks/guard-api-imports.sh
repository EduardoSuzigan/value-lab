#!/usr/bin/env bash
# PreToolUse (Edit|Write): impede libs pesadas na read-API (api/, backend/app/api/).
# exit 2 = NEGA a edição. Reforça a rule api-light.md de forma determinística.
# Hooks executam com SUAS credenciais — revise antes de habilitar.
set -euo pipefail
payload="$(cat)"
printf '%s' "$payload" | python3 -c '
import sys, json, re
try:
    d = json.load(sys.stdin)
except Exception:
    sys.exit(0)
ti = d.get("tool_input", {})
path = (ti.get("file_path") or ti.get("path") or "").replace("\\", "/")
content = ti.get("content") or ti.get("new_string") or ti.get("new_str") or ""
in_api = ("/api/" in path) or path.startswith("api/")
if not in_api:
    sys.exit(0)
forbidden = ("scipy", "sklearn", "numpy", "statsmodels")
hit = [m for m in forbidden if re.search(r"^\s*(import|from)\s+%s\b" % m, content, re.M)]
if hit:
    sys.stderr.write(
        "Bloqueado: a read-API deve ser leve (sem %s). Mova matematica/modelo para "
        "app/domain ou app/services. Ver .claude/rules/api-light.md\n" % ", ".join(hit))
    sys.exit(2)
sys.exit(0)
'
