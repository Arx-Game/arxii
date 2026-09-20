/**
 * Frame types the client has no case for (#3933). Recorded here, never shown
 * as a feed diagnostic: an unknown control frame is a protocol gap for a
 * developer to close, not something a player can act on. Type name only; the
 * payload may hold anything and is never kept.
 */
export interface UnknownFrame {
  type: string;
  generation: number;
  at: string;
}

const MAX_UNKNOWN_FRAMES = 50;
const frames: UnknownFrame[] = [];
/**
 * Types already warned about. A protocol gap repeats for every frame of that
 * type, so the console is warned once per type; the record below still keeps
 * every occurrence, which is what tells a developer how often it fires.
 */
const warned = new Set<string>();

export function recordUnknownFrame(type: string, generation: number): void {
  frames.push({ type, generation, at: new Date().toISOString() });
  if (frames.length > MAX_UNKNOWN_FRAMES) frames.splice(0, frames.length - MAX_UNKNOWN_FRAMES);
  if (warned.has(type)) return;
  warned.add(type);
  console.warn(`[socket] unknown frame type: ${type}`);
}

export function recordedUnknownFrames(): readonly UnknownFrame[] {
  return frames;
}

/** Exported ONLY for test beforeEach. */
export function __resetUnknownFramesForTests(): void {
  frames.length = 0;
  warned.clear();
}
