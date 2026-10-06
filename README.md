# Radicasión — seguimiento de radicación de contratos cápita

Automatiza la consulta de **Gestión de Cuentas Médicas → Consulta Recepción** en el
SIE de Dusakawi EPSI. Para cada contrato capitado identifica **qué periodos están
radicados y cuáles faltan**. Publica el resultado en un **dashboard en Vercel**,
protegido con clave.

```
┌──────────────── Tu Mac ────────────────┐        ┌──────────── Vercel ────────────┐
│ bot/sie_bot.py (Playwright)            │        │ index.html  (dashboard)        │
│  1. login SIE                          │  POST  │ api/subir.js ─► Blob PRIVADO   │
│  2. Consulta Recepción por contrato    │ ─────► │ api/datos.js ◄─ Blob           │
│  3. descarga soporte RIPS (hojita)     │ token  │ middleware.js (clave de acceso)│
│  4. periodo = fechas ARCHIVO-CONSULTAS │        └────────────────────────────────┘
│  5. Excel + historial.db + notificación│
└────────────────────────────────────────┘
```

- **El repositorio es público.** Aquí solo va código. Las credenciales, el listado de
  contratos, los soportes RIPS, el historial y los Excel están en `.gitignore` y
  **nunca** se suben.
- Los soportes RIPS contienen datos de pacientes y **se quedan en tu equipo**. Al
  dashboard solo llegan datos agregados por radicación: contrato, recepción, IPS,
  valor, periodo y número de radicación.

## Inicio rápido

```bash
cd bot
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python -m playwright install chromium
cp .env.example .env        # completar usuario, ruta del Excel, URL y token del dashboard
.venv/bin/python sie_bot.py septiembre
```

O haz doble clic en `bot/Radicacion.command`.

## Documentación

| Documento | Contenido |
|---|---|
| [docs/USO.md](docs/USO.md) | Comandos, opciones y cómo leer el Excel y el dashboard |
| [docs/VERCEL.md](docs/VERCEL.md) | Cómo conectar el repo a Vercel, Blob y variables |
| [docs/SERVIDOR.md](docs/SERVIDOR.md) | Worker en el VPS: instalación, servicio, actualización |
| [docs/ARQUITECTURA.md](docs/ARQUITECTURA.md) | Flujo, reglas de negocio, formato de datos |
| [CHANGELOG.md](CHANGELOG.md) | Historial de versiones |
