// Descarga de RIPS para el evaluador externo (sin sesión, con token compartido).
// Misma lógica que /api/rips pero protegida por token en vez de sesión.
import { worker } from './_auth.js';

export const config = { maxDuration: 60 };

const TOKEN = process.env.EVALUAR_TOKEN || 'DUSAKAWI-RIPS-2026';
const ORIGIN = 'https://evaluacion-rips-2026.vercel.app';

function cors(req, res) {
  const origin = req.headers.origin || '';
  if (origin === ORIGIN || origin.endsWith('.vercel.app') || origin.includes('localhost')) {
    res.setHeader('Access-Control-Allow-Origin', origin);
    res.setHeader('Vary', 'Origin');
  }
  res.setHeader('Access-Control-Allow-Methods', 'GET, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'x-token, Content-Type');
}

export default async function handler(req, res) {
  cors(req, res);
  if (req.method === 'OPTIONS') return res.status(204).end();
  if (req.method !== 'GET') return res.status(405).json({ error: 'Solo GET' });

  const tok = req.headers['x-token'] || req.query.token || '';
  if (tok !== TOKEN) return res.status(401).json({ error: 'Token inválido' });

  const { contrato = '', anio = '', mes = '', regimen = '', formato = 'txt', por = 'capita' } = req.query;
  const qs = new URLSearchParams({ contrato, anio, mes, regimen, formato, por });
  try {
    const r = await worker('/rips?' + qs.toString(), { signal: AbortSignal.timeout(55000) });
    if (!r.ok) {
      const t = await r.text();
      let msg = 'RIPS no disponible';
      try { msg = JSON.parse(t).detail || msg; } catch {}
      return res.status(r.status).send(msg);
    }
    const buf = Buffer.from(await r.arrayBuffer());
    res.setHeader('Content-Type', r.headers.get('content-type') || 'application/octet-stream');
    res.setHeader('Content-Disposition', r.headers.get('content-disposition') || 'attachment');
    res.setHeader('Cache-Control', 'no-store');
    return res.status(200).send(buf);
  } catch (e) {
    return res.status(502).send('El servidor de consultas no respondió: ' + (e.message || e));
  }
}
