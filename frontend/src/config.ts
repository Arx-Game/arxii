export const SITE_NAME = 'Arx II';

// WebSocket configuration
//
// VITE_WS_PORT is a dev-only escape hatch (e.g. pointing at a locally-run
// portal on a non-default port). Leave it unset in production: Caddy
// reverse-proxies `/ws/*` on the standard site origin/port to the
// localhost-bound Evennia portal (see roles/caddy/templates/Caddyfile.j2),
// so no explicit port is needed there. `undefined` here signals
// getWebSocketUrl to fall through to that same-origin behavior.
export const WS_PORT = import.meta.env.VITE_WS_PORT
  ? Number(import.meta.env.VITE_WS_PORT)
  : undefined;

// Legacy local-dev default: Django/Twisted web server on 4001, Evennia
// portal websocket on 4002, both on localhost with no reverse proxy in
// front.
const LEGACY_DEV_WS_PORT = 4002;

/**
 * Resolve the URL to open the game WebSocket connection against.
 *
 * - `VITE_WS_PORT` explicitly set -> `${protocol}://${hostname}:${port}/ws/game/`
 *   (dev override).
 * - Otherwise, page served over https -> same-origin, no explicit port:
 *   `wss://${host}/ws/game/`. Caddy's `@ws path /ws/*` route proxies this to
 *   the portal.
 * - Otherwise (plain http, e.g. local dev without the override) -> legacy
 *   `:4002` dev default.
 *
 * Takes a `Location`-shaped object (not `typeof window.location` directly)
 * so it's trivially unit-testable without mocking `window.location`.
 */
type SocketLocation = Pick<Location, 'protocol' | 'hostname' | 'host'>;

export function getWebSocketUrl(location: SocketLocation): string {
  const isSecure = location.protocol === 'https:';
  const wsProtocol = isSecure ? 'wss' : 'ws';

  if (WS_PORT !== undefined) {
    return `${wsProtocol}://${location.hostname}:${WS_PORT}/ws/game/`;
  }
  if (isSecure) {
    return `wss://${location.host}/ws/game/`;
  }
  return `${wsProtocol}://${location.hostname}:${LEGACY_DEV_WS_PORT}/ws/game/`;
}
