#!/usr/bin/env bash
# PostToolUse (Edit|Write): formata Python com ruff. Seguro (não bloqueia).
# Hooks executam com SUAS credenciais — revise antes de habilitar.
set -euo pipefail
# Usa o venv do backend (uv/venv) se existir; senão, o ruff do PATH.
_root="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
[ -d "$_root/backend/.venv/bin" ] && PATH="$_root/backend/.venv/bin:$PATH"
payload="$(cat)"
file="$(printf '%s' "$payload" | python3 -c 'import sys,json;ti=json.load(sys.stdin).get("tool_input",{});print(ti.get("file_path") or ti.get("path") or "")' 2>/dev/null || true)"
[ -z "$file" ] && exit 0
case "${file//\\//}" in
  *.py)
    command -v ruff >/dev/null 2>&1 || exit 0
    ruff check --fix "$file" >/dev/null 2>&1 || true
    ruff format "$file" >/dev/null 2>&1 || true
    ;;
esac
exit 0
