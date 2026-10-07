// POST {actual, nueva} → cambia la clave propia.
import { requiere, guardarUsuarios, verificarClave, hash } from './_usuarios.js';

export default async function handler(req, res) {
  if (req.method !== 'POST') return res.status(405).json({ error: 'Usa POST' });
  const ctx = await requiere(req, res);
  if (!ctx) return;
  const body = typeof req.body === 'string' ? JSON.parse(req.body || '{}') : (req.body || {});
  if (!verificarClave(body.actual || '', ctx.yo.clave)) return res.status(400).json({ error: 'La clave actual no es correcta.' });
  if (String(body.nueva || '').length < 8) return res.status(400).json({ error: 'La nueva clave debe tener al menos 8 caracteres.' });
  ctx.yo.clave = hash(body.nueva);
  ctx.yo.debeCambiar = false;
  await guardarUsuarios(ctx.usuarios);
  return res.status(200).json({ ok: true });
}
