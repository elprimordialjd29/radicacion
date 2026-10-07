// Monitoreo del servidor (solo administradores).
import { worker } from './_auth.js';
import { requiere } from './_usuarios.js';

export default async function handler(req, res) {
  res.setHeader('Cache-Control', 'no-store');
  if (!(await requiere(req, res, 'admin_usuarios'))) return;
  try {
    const r = await worker('/monitor');
    const t = await r.text();
    return res.status(r.status).setHeader('Content-Type', 'application/json; charset=utf-8').send(t);
  } catch (e) {
    return res.status(502).json({ error: 'El servidor no respondió: ' + (e.message || e) });
  }
}
