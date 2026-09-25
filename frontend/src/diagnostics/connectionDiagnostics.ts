/**
 * Local-only connection diagnostics for alpha investigations.
 *
 * This module is deliberately independent from React and Redux. It is imported
 * by the socket module before a socket can be constructed. Only the small,
 * allowlisted event schema below can reach IndexedDB or an export. In
 * particular, callers never pass character/account data, payloads, commands,
 * or close reasons to this recorder.
 */

export const DIAGNOSTIC_SCHEMA_VERSION = 1;
const TAB_STORAGE_KEY = 'arx-diagnostics-tab-v1';
const RUN_STORAGE_KEY = 'arx-diagnostics-run-v1';
const PREFERENCE_KEY = 'arx-diagnostics-enabled-v1';
const DB_NAME = 'arx-connection-diagnostics-v1';
const STORE_NAME = 'events';
const MAX_EVENTS = 1000;
const MAX_BYTES = 256 * 1024;
const MAX_AGE_MS = 24 * 60 * 60 * 1000;
const TIMER_GAP_MS = 5 * 60 * 1000;
const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;
const OPAQUE_ID_RE = /^v1-[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;

type Primitive = string | number | boolean | null;
export type DiagnosticKind =
  | 'page_start'
  | 'visibility_change'
  | 'online_change'
  | 'timer_gap'
  | 'pagehide'
  | 'capture_enabled'
  | 'user_marker'
  | 'storage_failure'
  | 'socket_attempt'
  | 'socket_constructed'
  | 'socket_open'
  | 'socket_error'
  | 'socket_close'
  | 'frame_received'
  | 'readiness'
  | 'reconnect_scheduled'
  | 'reconnect_fired'
  | 'reconnect_cancelled'
  | 'reconnect_exhausted'
  | 'local_close_intent'
  | 'dropped_events';

export interface DiagnosticEvent {
  schemaVersion: 1;
  kind: DiagnosticKind;
  sequence: number;
  wallTime: string;
  elapsedMs: number;
  releaseSha: string;
  deploymentChannel: 'alpha' | 'production' | 'rehearsal' | 'development';
  browserFamily: string;
  browserMajor: number | null;
  platform: 'windows' | 'macos' | 'linux' | 'android' | 'ios' | 'other' | null;
  timezoneOffsetMinutes: number;
  serverClockDeltaMs: number | null;
  runId: string;
  tabId: string;
  socketAlias?: string;
  generation?: number;
  details: Record<string, Primitive>;
}

export interface DiagnosticSnapshot {
  schemaVersion: 1;
  releaseSha: string;
  deploymentChannel: DiagnosticEvent['deploymentChannel'];
  runId: string | null;
  tabId: string;
  captureEnabled: boolean;
  events: DiagnosticEvent[];
  droppedEvents: number;
  storageAvailable: boolean;
}

const EVENT_KINDS = new Set<DiagnosticKind>([
  'page_start',
  'visibility_change',
  'online_change',
  'timer_gap',
  'pagehide',
  'capture_enabled',
  'user_marker',
  'storage_failure',
  'socket_attempt',
  'socket_constructed',
  'socket_open',
  'socket_error',
  'socket_close',
  'frame_received',
  'readiness',
  'reconnect_scheduled',
  'reconnect_fired',
  'reconnect_cancelled',
  'reconnect_exhausted',
  'local_close_intent',
  'dropped_events',
]);
const SAFE_FRAME_TYPES = new Set([
  'text',
  'logged_in',
  'vn_message',
  'message_reaction',
  'commands',
  'room_state',
  'scene',
  'command_error',
  'puppet_changed',
  'action_result',
  'interaction',
  'roulette_result',
  'battle_state',
  'kudos_received',
  'mail_arrived',
  'hazard_prompt',
  'request_room_state',
  'state_resync',
  'state_resync_error',
  'character_died',
  'estate_settlement_opened',
  'oob',
  'webclient_options',
  'unknown',
]);
const SAFE_ENUMS: Record<string, Set<string>> = {
  visibility: new Set(['visible', 'hidden']),
  direction: new Set(['incoming', 'outgoing']),
  parseOutcome: new Set(['parsed', 'malformed_json', 'unexpected_shape']),
  reason: new Set([
    'disconnect',
    'disconnect_all',
    'logout',
    'account_switch',
    'page_resume',
    'teardown',
  ]),
  readiness: new Set([
    'account_fetch_ok',
    'account_fetch_failed',
    'socket_open',
    'correlation_sent',
    'correlation_ack',
    'puppet_requested',
    'puppet_confirmed',
    'draft_reconciliation_start',
    'draft_reconciliation_result',
    'room_state_accepted',
    'redux_connected',
    'lifecycle_entering',
    'lifecycle_reconnecting',
    'composer_ready',
  ]),
};

function safeChannel(value: unknown): DiagnosticEvent['deploymentChannel'] {
  return value === 'alpha' ||
    value === 'production' ||
    value === 'rehearsal' ||
    value === 'development'
    ? value
    : 'production';
}
function randomUuid(): string {
  try {
    const value = globalThis.crypto?.randomUUID();
    if (value && UUID_RE.test(value)) return value;
  } catch {
    /* private mode can deny crypto; use a non-secret fallback */
  }
  const bytes = new Uint8Array(16);
  if (globalThis.crypto?.getRandomValues) globalThis.crypto.getRandomValues(bytes);
  bytes[6] = (bytes[6] & 0x0f) | 0x40;
  bytes[8] = (bytes[8] & 0x3f) | 0x80;
  const hex = [...bytes].map((byte) => byte.toString(16).padStart(2, '0')).join('');
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-4${hex.slice(13, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
}
function opaqueId(): string {
  return `v1-${randomUuid()}`;
}
function storageGet(storage: Storage | undefined, key: string): string | null {
  if (!storage) return null;
  try {
    return storage.getItem(key);
  } catch {
    return null;
  }
}
function storageSet(storage: Storage | undefined, key: string, value: string): void {
  try {
    storage?.setItem(key, value);
  } catch {
    /* persistence is best effort */
  }
}
function storageRemove(storage: Storage | undefined, key: string): void {
  try {
    storage?.removeItem(key);
  } catch {
    /* persistence is best effort */
  }
}
function validOpaque(value: string | null): value is string {
  return value !== null && OPAQUE_ID_RE.test(value);
}
function browserInfo(): {
  family: string;
  major: number | null;
  platform: DiagnosticEvent['platform'];
} {
  const userAgent = typeof navigator === 'undefined' ? '' : navigator.userAgent.toLowerCase();
  const match = userAgent.match(/(edg|edge|opr|chrome|firefox|safari)\/(\d+)/);
  let family = 'other';
  let major: number | null = null;
  if (match) {
    family = match[1] === 'edg' || match[1] === 'edge' ? 'edge' : match[1];
    major = Number(match[2]);
  }
  let platform: DiagnosticEvent['platform'] = 'other';
  if (/android/.test(userAgent)) platform = 'android';
  else if (/iphone|ipad|ios/.test(userAgent)) platform = 'ios';
  else if (/windows/.test(userAgent)) platform = 'windows';
  else if (/mac os/.test(userAgent)) platform = 'macos';
  else if (/linux/.test(userAgent)) platform = 'linux';
  return { family, major: Number.isSafeInteger(major) ? major : null, platform };
}
function releaseSha(): string {
  const value = import.meta.env.VITE_RELEASE_SHA;
  return typeof value === 'string' && /^[a-f0-9]{7,64}$/i.test(value)
    ? value.toLowerCase()
    : 'unknown';
}
function eventBytes(event: DiagnosticEvent): number {
  return JSON.stringify(event).length;
}

/** A module-level recorder. React components only control this object. */
export class ConnectionDiagnostics {
  private readonly tabId: string;
  private runId: string | null;
  private enabled: boolean;
  private events: DiagnosticEvent[] = [];
  private pending: DiagnosticEvent[] = [];
  private dropped = 0;
  private sequence = 0;
  private startedAt = typeof performance === 'undefined' ? 0 : performance.now();
  private lastElapsed = 0;
  private restored = false;
  private storageAvailable = typeof indexedDB !== 'undefined';
  private db: IDBDatabase | null = null;
  private writeQueue: Promise<void> = Promise.resolve();
  private listeners = new Set<() => void>();
  private snapshotCache: DiagnosticSnapshot | null = null;
  private sockets = new Map<string, { alias: string; generation: number; localIntent?: string }>();
  private nextSocketNumber = 1;

  constructor() {
    const session = typeof sessionStorage === 'undefined' ? undefined : sessionStorage;
    const existingTab = storageGet(session, TAB_STORAGE_KEY);
    this.tabId = validOpaque(existingTab) ? existingTab : opaqueId();
    storageSet(session, TAB_STORAGE_KEY, this.tabId);
    this.runId = validOpaque(storageGet(session, RUN_STORAGE_KEY))
      ? storageGet(session, RUN_STORAGE_KEY)
      : null;
    const preference = storageGet(
      typeof localStorage === 'undefined' ? undefined : localStorage,
      PREFERENCE_KEY
    );
    const channel = safeChannel(import.meta.env.VITE_DEPLOYMENT_CHANNEL);
    this.enabled = preference === null ? channel === 'alpha' : preference === 'true';
    if (this.enabled && !this.runId) this.createRunId();
    void this.restore();
    this.record('page_start');
    if (typeof document !== 'undefined')
      document.addEventListener('visibilitychange', () =>
        this.record('visibility_change', { visibility: document.visibilityState })
      );
    if (typeof window !== 'undefined') {
      window.addEventListener('online', () => this.record('online_change', { online: true }));
      window.addEventListener('offline', () => this.record('online_change', { online: false }));
      window.addEventListener('pagehide', () => this.record('pagehide'));
    }
  }

  subscribe(listener: () => void): () => void {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }
  private notify(): void {
    this.snapshotCache = null;
    this.listeners.forEach((listener) => listener());
  }
  isEnabled(): boolean {
    return this.enabled;
  }
  getTabId(): string {
    return this.tabId;
  }
  getSnapshot(): DiagnosticSnapshot {
    if (!this.snapshotCache) {
      this.snapshotCache = {
        schemaVersion: 1,
        releaseSha: releaseSha(),
        deploymentChannel: safeChannel(import.meta.env.VITE_DEPLOYMENT_CHANNEL),
        runId: this.runId,
        tabId: this.tabId,
        captureEnabled: this.enabled,
        events: [...this.events],
        droppedEvents: this.dropped,
        storageAvailable: this.storageAvailable,
      };
    }
    return this.snapshotCache;
  }
  async ready(): Promise<void> {
    while (!this.restored) await new Promise<void>((resolve) => setTimeout(resolve, 0));
  }

  setEnabled(enabled: boolean): void {
    this.enabled = enabled;
    storageSet(
      typeof localStorage === 'undefined' ? undefined : localStorage,
      PREFERENCE_KEY,
      String(enabled)
    );
    if (!enabled) {
      this.clear();
      this.runId = null;
      this.sockets.clear();
      storageRemove(
        typeof sessionStorage === 'undefined' ? undefined : sessionStorage,
        RUN_STORAGE_KEY
      );
      return;
    }
    if (!this.runId) this.createRunId();
    this.record('capture_enabled');
    this.notify();
  }
  clear(): void {
    this.events = [];
    this.pending = [];
    this.dropped = 0;
    this.sequence = 0;
    if (this.db && this.runId) {
      const run = this.runId;
      this.writeQueue = this.writeQueue.then(
        () =>
          new Promise<void>((resolve) => {
            try {
              const db = this.db;
              if (!db) {
                resolve();
                return;
              }
              const request = db
                .transaction(STORE_NAME, 'readwrite')
                .objectStore(STORE_NAME)
                .openCursor();
              request.onsuccess = () => {
                const cursor = request.result;
                if (!cursor) {
                  resolve();
                  return;
                }
                const value = cursor.value as DiagnosticEvent & { key?: string };
                if (value.tabId === this.tabId && value.runId === run) cursor.delete();
                cursor.continue();
              };
              request.onerror = () => resolve();
            } catch {
              resolve();
            }
          })
      );
    }
    this.notify();
  }
  newRun(): void {
    this.clear();
    this.sockets.clear();
    this.nextSocketNumber = 1;
    this.runId = opaqueId();
    storageSet(
      typeof sessionStorage === 'undefined' ? undefined : sessionStorage,
      RUN_STORAGE_KEY,
      this.runId
    );
    this.record('capture_enabled');
  }
  marker(): void {
    this.record('user_marker');
  }
  async exportReport(): Promise<{ json: string; summary: string; filename: string }> {
    await this.ready();
    const snapshot = this.getSnapshot();
    const report = JSON.stringify(snapshot, null, 2);
    const first = snapshot.events[0]?.wallTime ?? new Date().toISOString();
    const coarseTime = first.slice(0, 16).replace(/[-:T]/g, '').replace(/\..*/, '');
    const safeRun = snapshot.runId?.slice(0, 15) ?? 'none';
    const summary = `Arx connection diagnostics schema ${snapshot.schemaVersion}. Capture ${snapshot.captureEnabled ? 'enabled' : 'disabled'}. ${snapshot.events.length} events, ${report.length} bytes, ${snapshot.droppedEvents} dropped. Review before sharing through the private incident path; do not post publicly.`;
    return {
      json: report,
      summary,
      filename: `arx-connection-diagnostics-${coarseTime}-${safeRun}.json`,
    };
  }
  async download(): Promise<void> {
    const report = await this.exportReport();
    if (typeof document === 'undefined') return;
    const url = URL.createObjectURL(new Blob([report.json], { type: 'application/json' }));
    const link = document.createElement('a');
    link.href = url;
    link.download = report.filename;
    link.click();
    setTimeout(() => URL.revokeObjectURL(url), 0);
  }
  socketStarted(identity: string, generation: number): string | null {
    if (!this.enabled || !this.runId) return null;
    const existing = this.sockets.get(identity);
    const alias = existing?.alias ?? `socket-${this.nextSocketNumber++}`;
    this.sockets.set(identity, { alias, generation });
    this.record('socket_constructed', {}, alias, generation);
    return alias;
  }
  localClose(
    identity: string,
    generation: number,
    reason:
      | 'disconnect'
      | 'disconnect_all'
      | 'logout'
      | 'account_switch'
      | 'page_resume'
      | 'teardown'
  ): void {
    const socket = this.sockets.get(identity);
    if (!socket || socket.generation !== generation) return;
    socket.localIntent = reason;
    this.record('local_close_intent', { reason }, socket.alias, generation);
  }
  socketClosed(identity: string, generation: number, code: number, wasClean: boolean): void {
    const socket = this.sockets.get(identity);
    if (!socket || socket.generation !== generation) return;
    this.record(
      'socket_close',
      {
        code: Number.isInteger(code) && code >= 0 && code <= 4999 ? code : 0,
        wasClean,
        ...(socket.localIntent ? { reason: socket.localIntent } : {}),
      },
      socket.alias,
      generation
    );
    this.sockets.delete(identity);
  }
  frame(
    type: unknown,
    parseOutcome: 'parsed' | 'malformed_json' | 'unexpected_shape',
    generation?: number
  ): void {
    const socket = [...this.sockets.values()].find((item) => item.generation === generation);
    const messageType = typeof type === 'string' && SAFE_FRAME_TYPES.has(type) ? type : 'unknown';
    this.record(
      'frame_received',
      { direction: 'incoming', messageType, parseOutcome },
      socket?.alias,
      generation
    );
  }
  readiness(name: string, generation?: number): void {
    this.record(
      'readiness',
      { readiness: SAFE_ENUMS.readiness.has(name) ? name : 'lifecycle_entering' },
      this.aliasForGeneration(generation),
      generation
    );
  }
  reconnect(
    kind: 'reconnect_scheduled' | 'reconnect_fired' | 'reconnect_cancelled' | 'reconnect_exhausted',
    details: Record<string, Primitive> = {},
    generation?: number
  ): void {
    this.record(kind, details, this.aliasForGeneration(generation), generation);
  }
  record(
    kind: DiagnosticKind,
    details: Record<string, Primitive> = {},
    socketAlias?: string,
    generation?: number
  ): void {
    if (!this.enabled || !this.runId || !EVENT_KINDS.has(kind)) return;
    const now =
      typeof performance === 'undefined' ? this.lastElapsed : performance.now() - this.startedAt;
    if (this.lastElapsed && now - this.lastElapsed > TIMER_GAP_MS && kind !== 'timer_gap')
      this.append('timer_gap', { gapMs: Math.min(Math.round(now - this.lastElapsed), 2147483647) });
    this.lastElapsed = now;
    socketAlias = socketAlias ?? this.aliasForGeneration(generation);
    const event: DiagnosticEvent = {
      schemaVersion: 1,
      kind,
      sequence: ++this.sequence,
      wallTime: new Date().toISOString(),
      elapsedMs: Math.max(0, Math.round(now)),
      releaseSha: releaseSha(),
      deploymentChannel: safeChannel(import.meta.env.VITE_DEPLOYMENT_CHANNEL),
      browserFamily: browserInfo().family,
      browserMajor: browserInfo().major,
      platform: browserInfo().platform,
      timezoneOffsetMinutes: new Date().getTimezoneOffset(),
      serverClockDeltaMs: null,
      runId: this.runId,
      tabId: this.tabId,
      ...(socketAlias
        ? { socketAlias: /^socket-[1-9][0-9]{0,5}$/.test(socketAlias) ? socketAlias : undefined }
        : {}),
      ...(Number.isInteger(generation) && (generation as number) >= 0 ? { generation } : {}),
      details: this.sanitizeDetails(kind, details),
    };
    this.appendEvent(event);
  }
  private aliasForGeneration(generation?: number): string | undefined {
    return [...this.sockets.values()].find((item) => item.generation === generation)?.alias;
  }
  private sanitizeDetails(
    kind: DiagnosticKind,
    details: Record<string, Primitive>
  ): Record<string, Primitive> {
    const allowed: Record<DiagnosticKind, string[]> = {
      page_start: [],
      visibility_change: ['visibility'],
      online_change: ['online'],
      timer_gap: ['gapMs'],
      pagehide: [],
      capture_enabled: [],
      user_marker: [],
      storage_failure: ['code'],
      socket_attempt: ['attempt', 'outcome'],
      socket_constructed: [],
      socket_open: [],
      socket_error: [],
      socket_close: ['code', 'wasClean', 'reason'],
      frame_received: ['direction', 'messageType', 'parseOutcome'],
      readiness: ['readiness'],
      reconnect_scheduled: ['attempt', 'delayMs'],
      reconnect_fired: ['attempt'],
      reconnect_cancelled: [],
      reconnect_exhausted: ['attempt'],
      local_close_intent: ['reason'],
      dropped_events: ['count'],
    };
    const out: Record<string, Primitive> = {};
    for (const key of allowed[kind]) {
      const value = details[key];
      if (key === 'messageType')
        out[key] = typeof value === 'string' && SAFE_FRAME_TYPES.has(value) ? value : 'unknown';
      else if (
        key === 'visibility' ||
        key === 'direction' ||
        key === 'parseOutcome' ||
        key === 'reason' ||
        key === 'readiness'
      )
        out[key] = typeof value === 'string' && SAFE_ENUMS[key]?.has(value) ? value : 'unknown';
      else if (typeof value === 'number' && Number.isFinite(value))
        out[key] = Math.max(-2147483648, Math.min(2147483647, Math.round(value)));
      else if (typeof value === 'boolean') out[key] = value;
      else if (typeof value === 'string' && value.length <= 32 && /^[a-z0-9_.-]+$/i.test(value))
        out[key] = value;
    }
    return out;
  }
  private append(kind: DiagnosticKind, details: Record<string, Primitive>): void {
    this.record(kind, details);
  }
  private appendEvent(event: DiagnosticEvent): void {
    if (!this.restored) this.pending.push(event);
    else this.events.push(event);
    this.evict();
    if (this.restored && this.db) this.persist(event);
    this.notify();
  }
  private evict(): void {
    const target = this.restored ? this.events : this.pending;
    const cutoff = Date.now() - MAX_AGE_MS;
    while (
      target.length &&
      (target.length > MAX_EVENTS ||
        target[0].sequence < 1 ||
        Date.parse(target[0].wallTime) < cutoff ||
        target.reduce((sum, event) => sum + eventBytes(event), 0) > MAX_BYTES)
    ) {
      target.shift();
      this.dropped += 1;
    }
  }
  private createRunId(): void {
    this.runId = opaqueId();
    storageSet(
      typeof sessionStorage === 'undefined' ? undefined : sessionStorage,
      RUN_STORAGE_KEY,
      this.runId
    );
  }
  private async restore(): Promise<void> {
    if (!this.enabled || !this.runId || !this.storageAvailable) {
      this.restored = true;
      return;
    }
    try {
      this.db = await this.openDb();
      const loaded = await this.load();
      const queued = this.pending;
      this.events = loaded;
      this.sequence = loaded.reduce((max, event) => Math.max(max, event.sequence), 0);
      this.pending = [];
      queued.forEach((event) => {
        const next = { ...event, sequence: ++this.sequence };
        this.events.push(next);
        this.persist(next);
      });
      this.evict();
    } catch {
      this.storageAvailable = false;
      this.db = null;
      this.events = this.pending;
      this.pending = [];
      this.dropped += 1;
    }
    this.restored = true;
    this.notify();
  }
  private openDb(): Promise<IDBDatabase> {
    return new Promise((resolve, reject) => {
      const request = indexedDB.open(DB_NAME, 1);
      request.onupgradeneeded = () => {
        if (!request.result.objectStoreNames.contains(STORE_NAME))
          request.result.createObjectStore(STORE_NAME, { keyPath: 'key' });
      };
      request.onsuccess = () => resolve(request.result);
      request.onerror = () => reject(request.error);
    });
  }
  private load(): Promise<DiagnosticEvent[]> {
    return new Promise((resolve, reject) => {
      if (!this.db || !this.runId) return resolve([]);
      const request = this.db.transaction(STORE_NAME, 'readonly').objectStore(STORE_NAME).getAll();
      request.onsuccess = () => {
        const values = (request.result as Array<DiagnosticEvent & { key?: string }>).filter(
          (event) =>
            event.tabId === this.tabId && event.runId === this.runId && event.schemaVersion === 1
        );
        values.sort((a, b) => a.sequence - b.sequence);
        resolve(values.map(({ key: _key, ...event }) => event));
      };
      request.onerror = () => reject(request.error);
    });
  }
  private persist(event: DiagnosticEvent): void {
    if (!this.db) return;
    const value = { ...event, key: `${this.tabId}/${event.runId}/${event.sequence}` };
    this.writeQueue = this.writeQueue.then(
      () =>
        new Promise<void>((resolve) => {
          try {
            const db = this.db;
            if (!db) {
              resolve();
              return;
            }
            const request = db
              .transaction(STORE_NAME, 'readwrite')
              .objectStore(STORE_NAME)
              .put(value);
            request.onsuccess = () => resolve();
            request.onerror = () => {
              this.storageAvailable = false;
              resolve();
            };
          } catch {
            this.storageAvailable = false;
            resolve();
          }
        })
    );
  }
}

export const connectionDiagnostics = new ConnectionDiagnostics();
export const diagnosticPreferenceKey = PREFERENCE_KEY;
export const diagnosticLimits = {
  maxEvents: MAX_EVENTS,
  maxBytes: MAX_BYTES,
  maxAgeMs: MAX_AGE_MS,
} as const;
