// Protege todo el dashboard con usuario/clave (Basic Auth).
//  - DASHBOARD_USUARIOS="ana:clave1,luis:clave2"  → usuarios con nombre (recomendado)
//  - DASHBOARD_CLAVE="..."                         → una clave compartida (cualquier usuario)
// /api/subir queda fuera: el bot se autentica con su propio token (x-token).
import { next } from '@vercel/functions';

export const config = { matcher: ['/((?!api/subir).*)'] };

function usuarios() {
  const m = new Map();
  for (const par of (process.env.DASHBOARD_USUARIOS || '').split(',')) {
    const i = par.indexOf(':');
    if (i > 0) m.set(par.slice(0, i).trim().toLowerCase(), par.slice(i + 1).trim());
  }
  return m;
}

export default function middleware(request) {
  const lista = usuarios();
  const clave = process.env.DASHBOARD_CLAVE;
  if (!lista.size && !clave) {
    return new Response('Falta configurar DASHBOARD_USUARIOS o DASHBOARD_CLAVE en Vercel', { status: 503 });
  }
  const auth = request.headers.get('authorization') || '';
  if (auth.startsWith('Basic ')) {
    const txt = atob(auth.slice(6));
    const i = txt.indexOf(':');
    const u = txt.slice(0, i).trim().toLowerCase(), p = txt.slice(i + 1);
    if ((lista.size && lista.get(u) === p) || (clave && p === clave)) return next();
  }
  return new Response('Acceso restringido', {
    status: 401,
    headers: { 'WWW-Authenticate': 'Basic realm="Radicacion Capita", charset="UTF-8"' },
  });
}
