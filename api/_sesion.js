// Sesión firmada (HMAC-SHA256) en una cookie HttpOnly. Funciona en Edge (middleware) y en Node (API).
const enc = new TextEncoder();
const dec = new TextDecoder();
export const COOKIE = 'rad_sesion';
export const DURACION = 12 * 3600; // 12 horas

const b64u = (bytes) => btoa(String.fromCharCode(...new Uint8Array(bytes)))
  .replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
const deB64u = (s) => {
  s = s.replace(/-/g, '+').replace(/_/g, '/');
  while (s.length % 4) s += '=';
  return Uint8Array.from(atob(s), (c) => c.charCodeAt(0));
};
const clave = () => crypto.subtle.importKey('raw', enc.encode(process.env.SESSION_SECRET || ''),
  { name: 'HMAC', hash: 'SHA-256' }, false, ['sign', 'verify']);

export async function firmar(payload) {
  const datos = b64u(enc.encode(JSON.stringify(payload)));
  const firma = await crypto.subtle.sign('HMAC', await clave(), enc.encode(datos));
  return `${datos}.${b64u(firma)}`;
}

export async function verificar(token) {
  if (!token || !process.env.SESSION_SECRET) return null;
  const [datos, firma] = token.split('.');
  if (!datos || !firma) return null;
  try {
    const ok = await crypto.subtle.verify('HMAC', await clave(), deB64u(firma), enc.encode(datos));
    if (!ok) return null;
    const p = JSON.parse(dec.decode(deB64u(datos)));
    return p.exp && p.exp > Date.now() / 1000 ? p : null;
  } catch {
    return null;
  }
}

export function leerCookie(header, nombre = COOKIE) {
  const m = (header || '').match(new RegExp(`(?:^|;\\s*)${nombre}=([^;]+)`));
  return m ? decodeURIComponent(m[1]) : null;
}

export const cookieSesion = (token) =>
  `${COOKIE}=${encodeURIComponent(token)}; Path=/; HttpOnly; Secure; SameSite=Lax; Max-Age=${DURACION}`;
export const cookieBorrar = () => `${COOKIE}=; Path=/; HttpOnly; Secure; SameSite=Lax; Max-Age=0`;
