#!/usr/bin/env python3
"""Guarda la clave del SIE (leída de stdin) en bot/.env del servidor y reinicia el worker.
Uso desde tu Mac (la clave no se ve ni queda en el historial):
  read -rs "C?Clave SIE: " && printf %s "$C" | ssh root@SERVIDOR /opt/radicacion/deploy/guardar_clave.py; unset C
"""
import re
import subprocess
import sys
from pathlib import Path

clave = sys.stdin.read().strip()
if not clave:
    sys.exit("No se recibió ninguna clave.")
env = Path(__file__).resolve().parent.parent / "bot" / ".env"
texto = env.read_text(encoding="utf-8")
comilla = '"' if "'" in clave else "'"
linea = f"SIE_CLAVE={comilla}{clave}{comilla}"
texto = re.sub(r"(?m)^SIE_CLAVE=.*$", lambda _: linea, texto) if re.search(r"(?m)^SIE_CLAVE=", texto) \
    else texto.rstrip("\n") + "\n" + linea + "\n"
env.write_text(texto, encoding="utf-8")
env.chmod(0o600)
subprocess.run(["systemctl", "restart", "radicacion-worker"], check=False)
sys.stdout.write("Clave del SIE guardada en el servidor y worker reiniciado.\n")
