/**
 * Tests for getWebSocketUrl.
 *
 * VITE_WS_PORT is unset in the test env (no .env.test / vitest env override
 * defines it), so WS_PORT is undefined here — exercising the two non-override
 * branches: same-origin wss (production, served over https) and the legacy
 * dev ws default (plain http, no override).
 */
import { describe, it, expect } from 'vitest';
import { getWebSocketUrl, WS_PORT } from './config';

describe('getWebSocketUrl', () => {
  it('has no VITE_WS_PORT override in the test env (precondition for the branches below)', () => {
    expect(WS_PORT).toBeUndefined();
  });

  it('uses same-origin wss with no explicit port when served over https', () => {
    const url = getWebSocketUrl({
      protocol: 'https:',
      hostname: 'play.arxii.example',
      host: 'play.arxii.example',
    });
    expect(url).toBe('wss://play.arxii.example/ws/game/');
  });

  it('keeps the CF/Caddy-facing host:port form when https is served on a non-default port', () => {
    const url = getWebSocketUrl({
      protocol: 'https:',
      hostname: 'play.arxii.example',
      host: 'play.arxii.example:8443',
    });
    expect(url).toBe('wss://play.arxii.example:8443/ws/game/');
  });

  it('falls back to the legacy :4002 dev default over plain http', () => {
    const url = getWebSocketUrl({
      protocol: 'http:',
      hostname: 'localhost',
      host: 'localhost:3000',
    });
    expect(url).toBe('ws://localhost:4002/ws/game/');
  });
});
