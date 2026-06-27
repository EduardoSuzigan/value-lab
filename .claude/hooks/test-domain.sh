#!/usr/bin/env bash
# PostToolUse (Edit|Write): se um arquivo do domínio mudou, roda os testes do domínio.
# Reforça "toda mudança no domínio precisa de teste". Seguro (não bloqueia).
set -euo pipefail
payload="$(cat)"
file="$(printf '%s' "$payload" | python3 -c 'import sys,json;ti=json.load(sys.stdin).get("tool_input",{});print(ti.get("file_path") or ti.get("path") or "")' 2>/dev/null || true)"
case "${file//\\//}" in
  *backend/app/domain/*.py)
    command -v pytest >/dev/null 2>&1 || exit 0
    ( cd backend 2>/dev/null && pytest -q tests/domain 2>&1 | tail -n 20 ) \
      || echo "⚠ testes do domínio falharam ou ainda não existem (Fase 0)."
    ;;
esac
exit 0
