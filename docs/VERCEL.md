# Tablero en Vercel

Proyecto `radicacion` (cuenta elprimordialjd29, plan Hobby), conectado al repo
`elprimordialjd29/radicacion`: cada `git push` a `main` despliega solo. URL: https://radicacion.vercel.app

Vercel solo sirve el tablero y las funciones puente. **Los datos, usuarios y soportes RIPS viven
en el worker del VPS** (desde la v0.10.0 ya no se usa Vercel Blob: en el plan Hobby se suspendió
por exceder la cuota de operaciones).

## Variables de entorno (Production)
| Variable | Valor |
|---|---|
| `SESSION_SECRET` | Texto aleatorio largo para firmar las sesiones (`openssl rand -hex 32`) |
| `WORKER_URL` | `https://evaluador3280.duckdns.org:8443` |
| `WORKER_TOKEN` | El mismo de `bot/.env` del servidor |
| `SUBIR_TOKEN` | Token de `/api/subir` (el bot lo envía como `SIE_DASHBOARD_TOKEN`) |
| `EVALUAR_TOKEN` | Token de `/api/evaluar` y `/api/rips-ext` (evaluador externo) |

Después de cambiar variables: **Deployments → Redeploy**.

## Límite de funciones (Hobby: máx. 12, middleware incluido)
Hoy: `cuenta`, `consultas`, `datos`, `subir`, `excel`, `rips`, `usuarios`, `monitor`, `duplicados`,
`evaluar`, `rips-ext` + `middleware` = 12. Los archivos que empiezan por `_` (`_auth`, `_sesion`,
`_usuarios`, `_blob`, `_seguridad`) son módulos compartidos, no funciones. Login, logout, sesión y
cambio de clave van en `api/cuenta.js`; duplicados y frecuencia de uso en `api/duplicados.js` (rewrites en `vercel.json`). **Antes de agregar una función,
agrupar en una existente.**

## Usuarios y permisos
Permisos: ver reporte, lanzar consultas al SIE, descargar RIPS, descargar reportes, administrar usuarios.

| Rol | Permisos |
|---|---|
| Administrador | Todos |
| Analista | Reporte, consultas al SIE, RIPS, reportes |
| Auditor RIPS | Reporte, RIPS |
| Descarga RIPS (solo tablero) | RIPS |
| Reporte (ver y descargar) | Reporte, reportes |
| Solo consulta | Solo el tablero |

Se crean en el tablero: menú del usuario → **Usuarios y permisos**. Primer ingreso de un usuario
nuevo: debe cambiar la clave.

## Seguridad
- `middleware.js` exige sesión válida (cookie HttpOnly, Secure, SameSite=Lax, 12 h) en todo menos
  `/login`, `/api/login`, `/api/logout`, `/api/subir`, `/api/evaluar` y `/api/rips-ext`
  (estos tres usan token).
- Cada API valida el permiso en el servidor; la interfaz solo oculta lo que no corresponde.
- Las sesiones llevan una versión (`sv`): cambiar la clave, desactivar el usuario o cambiar sus
  permisos cierra sus sesiones abiertas.
- Ingreso: bloqueo de 15 min tras 5 claves erradas del usuario o 10 desde la misma IP (429).
- Intentos sin permiso y tokens inválidos se registran en el worker y avisan por correo; se ven
  en **Servidor → Seguridad** (solo administradores).
- Cabeceras: CSP, HSTS, X-Frame-Options DENY, nosniff, Referrer-Policy, Permissions-Policy, noindex.
