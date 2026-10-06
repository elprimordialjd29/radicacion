#!/bin/bash
# Consulta automática (la lanza radicacion-programada.timer a las 12:00 m y 12:00 a. m. hora Colombia).
# Todos los contratos · RS y RC · meses de enero al mes actual del año en curso (hora Colombia).
# Entra a la misma cola del worker: se ve en el dashboard como usuario "programada".
set -euo pipefail
ENV=/opt/radicacion/bot/.env
TOKEN=$(grep '^WORKER_TOKEN=' "$ENV" | cut -d= -f2-)
ANIO=$(TZ=America/Bogota date +%Y)
MES=$(TZ=America/Bogota date +%-m)
MESES=$(seq -s, 1 "$MES")
curl -fsS -H "x-token: $TOKEN" -H "Content-Type: application/json" \
  -d "{\"anio\": $ANIO, \"meses\": [$MESES], \"contratos\": [], \"regimenes\": [\"RS\",\"RC\"], \"usuario\": \"programada\"}" \
  http://127.0.0.1:8092/consultas
echo
