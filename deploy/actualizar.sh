#!/bin/bash
# Actualiza el servidor con la última versión del repo y reinicia el worker.
set -e
cd /opt/radicacion
git pull -q --ff-only
bot/.venv/bin/pip install -q -r bot/requirements.txt fastapi "uvicorn[standard]"
cp deploy/radicacion-worker.service deploy/radicacion-programada.service deploy/radicacion-programada.timer /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now radicacion-programada.timer >/dev/null 2>&1
# no reiniciar en medio de una consulta al SIE: esperar hasta 60 min a que termine (o usar --forzar)
T=$(grep '^WORKER_TOKEN=' bot/.env | cut -d= -f2-)
if [ "${1:-}" != "--forzar" ]; then
  for i in $(seq 1 120); do
    C=$(curl -s -m 5 -H "x-token: $T" http://127.0.0.1:8092/salud | python3 -c "import sys,json; print(json.load(sys.stdin).get('corriendo') or '')" 2>/dev/null)
    [ -z "$C" ] && break
    [ "$i" = 1 ] && echo "Hay una consulta en curso ($C): espero a que termine antes de reiniciar…"
    sleep 30
  done
fi
systemctl restart radicacion-worker
sleep 2
systemctl is-active radicacion-worker
