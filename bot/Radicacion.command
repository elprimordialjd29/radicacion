#!/bin/zsh
cd "$(dirname "$0")"
echo "=== SIE Dusakawi · Seguimiento de radicación Cápita ==="
echo "Escribe los meses (ej: enero febrero) o 'todos':"
read "meses?> "
if [[ "$meses" == "todos" ]]; then
  .venv/bin/python sie_bot.py --todos
else
  .venv/bin/python sie_bot.py ${=meses}
fi
echo; read "?Presiona Enter para cerrar…"
