import { afterEach, describe, expect, it, vi } from 'vitest';
import { ConnectionDiagnostics } from './connectionDiagnostics';

describe('ConnectionDiagnostics', () => {
  afterEach(() => {
    localStorage.clear();
    sessionStorage.clear();
    vi.restoreAllMocks();
  });

  it('stores only allowlisted values and never close reasons or socket identities', async () => {
    const recorder = new ConnectionDiagnostics();
    recorder.setEnabled(true);
    recorder.socketStarted('Lady Secret <script>', 4);
    recorder.localClose('Lady Secret <script>', 4, 'disconnect');
    recorder.socketClosed('Lady Secret <script>', 4, 1006, false);
    recorder.frame('player prose and cookie=secret', 'parsed', 4);
    recorder.record(
      'frame_received',
      {
        direction: 'incoming',
        messageType: 'Bearer password=secret',
        parseOutcome: 'parsed',
      },
      'not-a-safe-alias',
      4
    );
    await recorder.ready();
    const serialized = JSON.stringify(recorder.getSnapshot());
    expect(serialized).not.toContain('Lady Secret');
    expect(serialized).not.toContain('script');
    expect(serialized).not.toContain('secret');
    expect(recorder.getSnapshot().events.at(-1)?.details).toMatchObject({
      direction: 'incoming',
      messageType: 'unknown',
      parseOutcome: 'parsed',
    });
    expect(recorder.getSnapshot().events.some((event) => event.socketAlias === 'socket-1')).toBe(
      true
    );
  });

  it('uses a per-tab opaque run and rotates it only for a new run', async () => {
    const recorder = new ConnectionDiagnostics();
    recorder.setEnabled(true);
    await recorder.ready();
    const first = recorder.getSnapshot().runId;
    expect(first).toMatch(/^v1-[0-9a-f-]+$/);
    recorder.newRun();
    expect(recorder.getSnapshot().runId).not.toBe(first);
    expect(
      recorder.getSnapshot().events.every((event) => event.runId === recorder.getSnapshot().runId)
    ).toBe(true);
  });

  it('disabling capture removes the active run and leaves no tombstone', async () => {
    const recorder = new ConnectionDiagnostics();
    recorder.setEnabled(true);
    recorder.record('user_marker');
    recorder.setEnabled(false);
    await recorder.ready();
    expect(recorder.getSnapshot().captureEnabled).toBe(false);
    expect(recorder.getSnapshot().runId).toBeNull();
    expect(recorder.getSnapshot().events).toHaveLength(0);
  });
});
