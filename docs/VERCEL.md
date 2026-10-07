# Publicar el dashboard en Vercel

## 1. Importar el repo
1. https://vercel.com/new → **Import** `chuvanegas/radicasion`.
2. Framework Preset: **Other**. No necesita build command ni output directory.
3. Deploy.

## 2. Crear el almacenamiento (Blob privado)
Proyecto → **Storage** → **Create** → **Blob** → conectarlo al proyecto.
Vercel agrega la variable `BLOB_READ_WRITE_TOKEN` automáticamente.

## 3. Variables de entorno
Proyecto → **Settings → Environment Variables** (Production):

| Variable | Valor |
|---|---|
| `SESSION_SECRET` | Texto aleatorio largo para firmar las sesiones (`openssl rand -hex 32`) |
| `SUBIR_TOKEN` | Un texto largo y aleatorio. Es el mismo que va en `bot/.env` como `SIE_DASHBOARD_TOKEN` |

Para generar un token: `openssl rand -hex 32`

Después de agregar las variables: **Deployments → Redeploy**.

## 4. Conectar el bot
En `bot/.env`:
```
SIE_DASHBOARD_URL=https://<tu-proyecto>.vercel.app
SIE_DASHBOARD_TOKEN=<el mismo SUBIR_TOKEN>
```

Cada `git push` a `main` vuelve a desplegar el dashboard. Los **datos** no dependen de
los deploys: viven en el Blob y se actualizan cada vez que corre el bot.

## Seguridad
- `middleware.js` exige una sesión válida (cookie firmada) en todo, excepto `/login`, `/api/login`, `/api/logout` y `/api/subir`.
- Usuarios y permisos en `radicacion/usuarios.json` (Blob privado, claves con scrypt). Primer ingreso: `admin` / `admin123` → cambiarla.
- `/api/subir` solo acepta peticiones con el header `x-token` correcto.
- El Blob es **privado**: solo se lee desde `/api/datos`, que está detrás de la clave.
- `X-Robots-Tag: noindex` evita que los buscadores indexen el sitio.
