/**
 * Shared exit-edge pairing for map canvases (#670, #2449) — turns directed
 * exits between rooms into one React Flow edge per room pair.
 */

export interface ExitRecord {
  id: number;
  name: string;
  from_room_id: number;
  to_room_id: number;
}

export interface ExitEdge {
  /** Stable per room pair: `exit-<lowRoomId>-<highRoomId>`. */
  id: string;
  source: number;
  target: number;
  /** Exit leaving `source` toward `target` (if any). */
  there: ExitRecord | null;
  /** Exit leaving `target` back toward `source` (if any). */
  back: ExitRecord | null;
}

/**
 * Pair directed exits into one edge per room pair. A one-way exit still
 * yields an edge (its `back` stays null).
 */
export function exitEdges(exits: ExitRecord[]): ExitEdge[] {
  const edges = new Map<string, ExitEdge>();
  for (const exit of exits) {
    const [low, high] = [
      Math.min(exit.from_room_id, exit.to_room_id),
      Math.max(exit.from_room_id, exit.to_room_id),
    ];
    const id = `exit-${low}-${high}`;
    let edge = edges.get(id);
    if (!edge) {
      edge = { id, source: exit.from_room_id, target: exit.to_room_id, there: null, back: null };
      edges.set(id, edge);
    }
    if (exit.from_room_id === edge.source) {
      edge.there = edge.there ?? exit;
    } else {
      edge.back = edge.back ?? exit;
    }
  }
  return [...edges.values()];
}
