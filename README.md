# Radicasión — seguimiento de radicación de contratos cápita

Automatiza la consulta de **Gestión de Cuentas Médicas → Consulta Recepción** en el
SIE de Dusakawi EPSI. Para cada contrato capitado (RS y RC) identifica **qué periodos están
radicados y cuáles faltan**, descarga los **soportes RIPS** y calcula el mes con las **fechas de
atención que trae el RIPS**. Lo publica en un **tablero web** con usuarios y permisos.

Versión actual: **0.12.3** (ver [CHANGELOG.md](CHANGELOG.md)).

```
 Usuarios ──► radicacion.vercel.app (Vercel)                    VPS Contabo (worker)
              index.html · login.html                           nginx :8443 ─► FastAPI :8092
              middleware.js (sesión firmada)   x-token          ├─ cola de consultas (reintentos)
              api/*.js  ───────────────────────────────────────►├─ bot/sie_bot.py (Playwright) ─► SIE
                                                                 ├─ soportes RIPS (datos de pacientes)
                                                                 ├─ dashboard.json · usuarios.json
                                                                 └─ seguridad.db (intentos, alertas)
 Timer 12:00 m y 12:00 a. m. (hora Colombia) ─► consulta completa programada
```

- **El repositorio es público.** Aquí solo va código. Credenciales, listado de contratos,
  soportes RIPS, historial, usuarios y Excel están fuera del repo (`.gitignore`) y viven en el servidor.
- Los soportes RIPS contienen datos de pacientes: **se quedan en el servidor** y solo se entregan
  a usuarios con permiso «Descargar RIPS».

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
| [docs/USO.md](docs/USO.md) | Tablero (pestañas, descargas, unificado, reporte) y comandos del bot |
| [docs/VERCEL.md](docs/VERCEL.md) | Proyecto en Vercel, variables, límite de funciones y seguridad |
| [docs/SERVIDOR.md](docs/SERVIDOR.md) | Worker en el VPS: servicio, reintentos, alertas, claves, actualización |
| [docs/ARQUITECTURA.md](docs/ARQUITECTURA.md) | Flujo, reglas de negocio, formato de datos |
| [CHANGELOG.md](CHANGELOG.md) | Historial de versiones |
