import { createHash } from 'node:crypto';
import { test, expect, type Page } from '@playwright/test';

test.describe('authenticated idle liveness soak', () => {
  test('keeps the authenticated game socket open for the bounded interval', async ({ page }) => {
    if (process.env.LIVENESS_SOAK_ENABLE !== '1') {
      test.skip(true, 'live soak is opt-in; fixture tests are not acceptance evidence');
    }

    const baseURL = safeBaseURL(required('LIVENESS_SOAK_BASE_URL'));
    const username = required('LIVENESS_SOAK_USERNAME');
    const password = required('LIVENESS_SOAK_PASSWORD');
    const deploymentRevision = required('LIVENESS_DEPLOYMENT_REVISION');
    const seconds = boundedSeconds(process.env.LIVENESS_SOAK_SECONDS ?? '600');
    const gamePath = process.env.LIVENESS_SOAK_GAME_PATH ?? '/game';
    const config = {
      base_url: baseURL,
      game_path: gamePath,
      seconds,
      browser: 'chromium',
      headless: true,
    };
    const configId =
      process.env.LIVENESS_CONFIG_ID ??
      createHash('sha256').update(JSON.stringify(config)).digest('hex').slice(0, 16);

    await installSocketRecorder(page);
    const startedAt = new Date().toISOString();
    await page.goto(new URL('/login', baseURL).toString());
    await page.locator('input[type="text"]').first().fill(username);
    await page.locator('input[type="password"]').fill(password);
    await page.getByRole('button', { name: /log in/i }).click();
    await expect(page).not.toHaveURL(/\/login(?:$|[?/#])/);

    await page.goto(new URL(gamePath, baseURL).toString());
    await expect(page.getByText('In world', { exact: true })).toBeVisible({ timeout: 30_000 });
    const soakStarted = Date.now();
    while (Date.now() - soakStarted < seconds * 1000) {
      await page.waitForTimeout(Math.min(5_000, seconds * 1000 - (Date.now() - soakStarted)));
    }

    const sockets = await page.evaluate(() => window.__livenessSockets ?? []);
    const report = {
      schema: 'arxii.liveness.browser.v1',
      revision: deploymentRevision,
      config_id: configId,
      configuration: config,
      started_at: startedAt,
      ended_at: new Date().toISOString(),
      elapsed_seconds: Number(((Date.now() - soakStarted) / 1000).toFixed(3)),
      sockets,
      status: sockets.some((socket) => socket.close_count > 0) ? 'failed' : 'passed',
      manual_reconnect_required: sockets.some((socket) => socket.close_count > 0),
    };
    // The report contains only counters and close metadata. It intentionally
    // excludes credentials, cookies, URLs with query strings, and frame data.
    console.log(`LIVENESS_RESULT ${JSON.stringify(report)}`);
    expect(sockets.length, 'authenticated game path must open a WebSocket').toBeGreaterThan(0);
    expect(
      sockets.every((socket) => socket.close_count === 0),
      'no authenticated socket may close during the idle bound'
    ).toBe(true);
  });
});

interface SocketRecord {
  opened_at_ms: number;
  open_count: number;
  close_count: number;
  close_codes: number[];
  clean_closes: number;
  sent_frames: number;
  received_frames: number;
  errors: number;
}

declare global {
  interface Window {
    __livenessSockets?: SocketRecord[];
  }
}

async function installSocketRecorder(page: Page): Promise<void> {
  await page.addInitScript(() => {
    const sockets: SocketRecord[] = [];
    window.__livenessSockets = sockets;
    const NativeWebSocket = window.WebSocket;
    class RecordingWebSocket extends NativeWebSocket {
      private readonly record: SocketRecord;

      constructor(url: string | URL, protocols?: string | string[]) {
        if (protocols === undefined) super(url);
        else super(url, protocols);
        this.record = {
          opened_at_ms: performance.now(),
          open_count: 0,
          close_count: 0,
          close_codes: [],
          clean_closes: 0,
          sent_frames: 0,
          received_frames: 0,
          errors: 0,
        };
        sockets.push(this.record);
        this.addEventListener('open', () => {
          this.record.open_count += 1;
        });
        this.addEventListener('message', () => {
          this.record.received_frames += 1;
        });
        this.addEventListener('error', () => {
          this.record.errors += 1;
        });
        this.addEventListener('close', (event) => {
          this.record.close_count += 1;
          this.record.close_codes.push(event.code);
          if (event.wasClean) this.record.clean_closes += 1;
        });
      }

      override send(data: string | ArrayBufferLike | Blob | ArrayBufferView): void {
        this.record.sent_frames += 1;
        super.send(data);
      }
    }
    window.WebSocket = RecordingWebSocket;
  });
}

function required(name: string): string {
  const value = process.env[name];
  if (!value) throw new Error(`${name} must be supplied outside the repository`);
  return value;
}

function safeBaseURL(value: string): string {
  const parsed = new URL(value);
  if (parsed.username || parsed.password || parsed.search || parsed.hash) {
    throw new Error(
      'LIVENESS_SOAK_BASE_URL must not contain credentials, query strings, or fragments'
    );
  }
  return parsed.toString();
}

function boundedSeconds(value: string): number {
  const seconds = Number(value);
  if (!Number.isFinite(seconds) || seconds <= 0 || seconds > 3600) {
    throw new Error('LIVENESS_SOAK_SECONDS must be > 0 and <= 3600');
  }
  return seconds;
}
