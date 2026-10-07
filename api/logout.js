import { cookieBorrar } from './_sesion.js';

export default function handler(req, res) {
  res.setHeader('Set-Cookie', cookieBorrar());
  res.setHeader('Cache-Control', 'no-store');
  if (req.method === 'GET') { res.setHeader('Location', '/login'); return res.status(302).end(); }
  return res.status(200).json({ ok: true });
}
