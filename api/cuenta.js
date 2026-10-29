// Cuenta del usuario en UNA sola función (el plan Hobby de Vercel permite máx. 12 funciones).
// vercel.json reescribe las rutas de siempre hacia aquí:
//   POST /api/login   → ingresar            (sin sesión)
//   *    /api/logout  → salir               (sin sesión)
//   GET  /api/sesion  → quién soy y permisos
//   POST /api/clave   → cambiar mi clave
import { firmar, cookieSesion, cookieBorrar, DURACION } from './_sesion.js';
import {
  cargarUsuarios, guardarUsuarios, verificarClave, publico, normalizarUsuario, requiere, hash, PERMISOS, ROLES,
} from './_usuarios.js';
import { evento, bloqueo } from './_seguridad.js';

const cuerpo = (req) => (typeof req.body === 'string' ? JSON.parse(req.body || '{}') : (req.body || {}));

async function login(req, res) {
  if (req.method !== 'POST') return res.status(405).json({ error: 'Usa POST' });
  if (!process.env.SESSION_SECRET) return res.status(503).json({ error: 'Falta SESSION_SECRET en Vercel' });
  const body = cuerpo(req);
  const usuario = normalizarUsuario(body.usuario);
  // demasiados intentos fallidos (5 del usuario o 10 de la IP en 15 min) → bloqueo temporal
  const b = await bloqueo(req, usuario);
  if (b.bloqueado) return res.status(429).json({ error: `Demasiados intentos fallidos. Espera ${b.minutos} min e intenta de nuevo.` });
  const usuarios = await cargarUsuarios();
  const u = usuarios[usuario];
  if (!u || !u.activo || !verificarClave(body.clave || '', u.clave)) {
    const motivo = !u ? `usuario inexistente «${String(body.usuario || '').slice(0, 40)}»` : !u.activo ? 'usuario inactivo' : 'clave errada';
    const r = await evento(req, 'login_fallido', { usuario, detalle: motivo });
    await new Promise((ok) => setTimeout(ok, 700)); // frena intentos repetidos
    if (r?.bloqueado) return res.status(429).json({ error: `Demasiados intentos fallidos. Espera ${r.minutos} min e intenta de nuevo.` });
    return res.status(401).json({ error: 'Usuario o clave incorrectos.' });
  }
  u.ultimoIngreso = new Date().toISOString();
  await guardarUsuarios(usuarios);
  await evento(req, 'login_ok', { usuario, es_admin: (u.permisos || []).includes('admin_usuarios') });
  const token = await firmar({ u: usuario, v: u.sv || 0, exp: Math.floor(Date.now() / 1000) + DURACION });
  res.setHeader('Set-Cookie', cookieSesion(token));
  return res.status(200).json({ ok: true, usuario: publico(u) });
}

function logout(req, res) {
  res.setHeader('Set-Cookie', cookieBorrar());
  if (req.method === 'GET') { res.setHeader('Location', '/login'); return res.status(302).end(); }
  return res.status(200).json({ ok: true });
}

async function sesion(req, res) {
  const ctx = await requiere(req, res);
  if (!ctx) return;
  return res.status(200).json({ usuario: publico(ctx.yo), permisos: PERMISOS, roles: ROLES });
}

async function clave(req, res) {
  if (req.method !== 'POST') return res.status(405).json({ error: 'Usa POST' });
  const ctx = await requiere(req, res);
  if (!ctx) return;
  const body = cuerpo(req);
  if (!verificarClave(body.actual || '', ctx.yo.clave)) return res.status(400).json({ error: 'La clave actual no es correcta.' });
  if (String(body.nueva || '').length < 8) return res.status(400).json({ error: 'La nueva clave debe tener al menos 8 caracteres.' });
  ctx.yo.clave = hash(body.nueva);
  ctx.yo.debeCambiar = false;
  ctx.yo.sv = (ctx.yo.sv || 0) + 1;   // cierra las demás sesiones abiertas con la clave anterior
  await guardarUsuarios(ctx.usuarios);
  res.setHeader('Set-Cookie', cookieSesion(await firmar({ u: ctx.yo.usuario, v: ctx.yo.sv, exp: Math.floor(Date.now() / 1000) + DURACION })));
  return res.status(200).json({ ok: true });
}

const ACCIONES = { login, logout, sesion, clave };

export default async function handler(req, res) {
  res.setHeader('Cache-Control', 'no-store');
  const accion = ACCIONES[req.query.accion];
  if (!accion) return res.status(404).json({ error: 'Acción desconocida' });
  return accion(req, res);
}
