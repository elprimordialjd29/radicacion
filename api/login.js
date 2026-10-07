// POST {usuario, clave} → cookie de sesión (12 h).
import { firmar, cookieSesion, DURACION } from './_sesion.js';
import { cargarUsuarios, guardarUsuarios, verificarClave, publico, normalizarUsuario } from './_usuarios.js';

export default async function handler(req, res) {
  if (req.method !== 'POST') return res.status(405).json({ error: 'Usa POST' });
  if (!process.env.SESSION_SECRET) return res.status(503).json({ error: 'Falta SESSION_SECRET en Vercel' });
  const body = typeof req.body === 'string' ? JSON.parse(req.body || '{}') : (req.body || {});
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
  res.setHeader('Cache-Control', 'no-store');
  return res.status(200).json({ ok: true, usuario: publico(u) });
}
