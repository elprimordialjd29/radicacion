#!/bin/bash
# Actualiza el servidor con la última versión del repo y reinicia el worker.
set -e
cd /opt/radicacion
git pull -q --ff-only
bot/.venv/bin/pip install -q -r bot/requirements.txt fastapi "uvicorn[standard]"
systemctl restart radicacion-worker
sleep 2
systemctl is-active radicacion-worker
