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

const cuerpo = (req) => (typeof req.body === 'string' ? JSON.parse(req.body || '{}') : (req.body || {}));

async function login(req, res) {
  if (req.method !== 'POST') return res.status(405).json({ error: 'Usa POST' });
  if (!process.env.SESSION_SECRET) return res.status(503).json({ error: 'Falta SESSION_SECRET en Vercel' });
  const body = cuerpo(req);
  const usuario = normalizarUsuario(body.usuario);
  const usuarios = await cargarUsuarios();
  const u = usuarios[usuario];
  if (!u || !u.activo || !verificarClave(body.clave || '', u.clave)) {
    await new Promise((r) => setTimeout(r, 700)); // frena intentos repetidos
    return res.status(401).json({ error: 'Usuario o clave incorrectos.' });
  }
  u.ultimoIngreso = new Date().toISOString();
  await guardarUsuarios(usuarios);
  const token = await firmar({ u: usuario, exp: Math.floor(Date.now() / 1000) + DURACION });
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
  await guardarUsuarios(ctx.usuarios);
  return res.status(200).json({ ok: true });
}

const ACCIONES = { login, logout, sesion, clave };

export default async function handler(req, res) {
  res.setHeader('Cache-Control', 'no-store');
  const accion = ACCIONES[req.query.accion];
  if (!accion) return res.status(404).json({ error: 'Acción desconocida' });
  return accion(req, res);
}
