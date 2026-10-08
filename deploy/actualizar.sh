#!/bin/bash
# Actualiza el servidor con la última versión del repo y reinicia el worker.
set -e
cd /opt/radicacion
git pull -q --ff-only
bot/.venv/bin/pip install -q -r bot/requirements.txt fastapi "uvicorn[standard]"
cp deploy/radicacion-worker.service deploy/radicacion-programada.service deploy/radicacion-programada.timer /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now radicacion-programada.timer >/dev/null 2>&1
systemctl restart radicacion-worker
sleep 2
systemctl is-active radicacion-worker
