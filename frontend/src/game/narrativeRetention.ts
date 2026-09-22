import type { InteractionWsPayload } from '@/hooks/types';

/** Adjustable browser guardrails. These are engineering defaults, not product limits. */
export interface NarrativeRetentionLimits {
  maxTemporaryPoses: number;
  maxBodyBytes: number;
  warningRatio: number;
  maxMountedBodies: number;
  maxCachedBodies: number;
}

export const DEFAULT_NARRATIVE_RETENTION_LIMITS: NarrativeRetentionLimits = {
  maxTemporaryPoses: 2_000,
  maxBodyBytes: 20 * 1024 * 1024,
  warningRatio: 0.8,
  maxMountedBodies: 150,
  maxCachedBodies: 500,
};

export interface NarrativeBody {
  content: string;
  line?: string;
}

export interface NarrativeBodyCacheStats {
  entries: number;
  bytes: number;
  warning: boolean;
  evictions: number;
}

function bodyKey(id: number | string, timestamp: string, scene?: number | null): string {
  return `${scene ?? 'none'}:${id}:${timestamp}`;
}

function utf8Bytes(value: string): number {
  if (typeof TextEncoder !== 'undefined') return new TextEncoder().encode(value).byteLength;
  return unescape(encodeURIComponent(value)).length;
}

/**
 * Normalized bounded body cache for websocket pose text.
 *
 * Metadata remains Redux-owned; full text is kept here in insertion-ordered LRU
 * form. The cache is intentionally module-local and account-resettable so it
 * cannot leak through Redux persistence or across logout/account changes.
 */
export class NarrativeBodyCache {
  private readonly entries = new Map<string, { body: NarrativeBody; bytes: number }>();
  private bytes = 0;
  private evictions = 0;

  constructor(
    private readonly limits: NarrativeRetentionLimits = DEFAULT_NARRATIVE_RETENTION_LIMITS
  ) {}

  put(
    payload: Pick<InteractionWsPayload, 'id' | 'timestamp' | 'content' | 'line'> & {
      scene_id?: number | null;
    }
  ): void {
    const key = bodyKey(payload.id, payload.timestamp, payload.scene_id);
    const body = {
      content: payload.content,
      ...(payload.line === undefined ? {} : { line: payload.line }),
    };
    const bytes = utf8Bytes(body.content) + utf8Bytes(body.line ?? '');
    const previous = this.entries.get(key);
    if (previous) this.bytes -= previous.bytes;
    this.entries.delete(key);
    this.entries.set(key, { body, bytes });
    this.bytes += bytes;
    this.trim();
  }

  get(id: number | string, timestamp: string, scene?: number | null): NarrativeBody | undefined {
    const key = bodyKey(id, timestamp, scene);
    const entry = this.entries.get(key);
    if (!entry) return undefined;
    this.entries.delete(key);
    this.entries.set(key, entry);
    return entry.body;
  }

  delete(id: number | string, timestamp: string, scene?: number | null): void {
    const key = bodyKey(id, timestamp, scene);
    const entry = this.entries.get(key);
    if (!entry) return;
    this.entries.delete(key);
    this.bytes -= entry.bytes;
  }

  clear(): void {
    this.entries.clear();
    this.bytes = 0;
    this.evictions = 0;
  }

  stats(): NarrativeBodyCacheStats {
    return {
      entries: this.entries.size,
      bytes: this.bytes,
      warning:
        this.bytes >= this.limits.maxBodyBytes * this.limits.warningRatio ||
        this.entries.size >= this.limits.maxCachedBodies * this.limits.warningRatio,
      evictions: this.evictions,
    };
  }

  private trim(): void {
    while (
      this.entries.size > this.limits.maxCachedBodies ||
      this.bytes > this.limits.maxBodyBytes
    ) {
      const oldest = this.entries.keys().next().value as string | undefined;
      if (!oldest) break;
      const entry = this.entries.get(oldest);
      this.entries.delete(oldest);
      this.bytes -= entry?.bytes ?? 0;
      this.evictions += 1;
    }
  }
}

export const narrativeBodyCache = new NarrativeBodyCache();

export function clearNarrativeBodyCache(): void {
  narrativeBodyCache.clear();
}

export function getNarrativeBody(
  payload: Pick<InteractionWsPayload, 'id' | 'timestamp'> & { scene_id?: number | null }
): NarrativeBody | undefined {
  return narrativeBodyCache.get(payload.id, payload.timestamp, payload.scene_id);
}
