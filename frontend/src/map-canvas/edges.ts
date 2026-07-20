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

export interface PortalAnchorRecord {
  id: number;
  room_id: number;
  kind_name: string;
  /** The room this anchor's kind is reachable from, if the canvas can resolve one (same-area pairing). Null when no destination is resolvable from this view. */
  destination_room_id: number | null;
}

export interface PortalEdge {
  /** Stable per anchor: `portal-<anchorId>`. */
  id: string;
  source: number;
  target: number;
  kindName: string;
}

/**
 * Turn portal anchors with a resolvable same-area destination into edges —
 * "canvas shows where it leads" (#2451). An anchor with no destination
 * resolvable in this view (e.g. the only anchor of its kind, or its pair is
 * in another area) contributes no edge; it's still visible via the room's
 * detail panel.
 */
export function portalEdges(anchors: PortalAnchorRecord[]): PortalEdge[] {
  return anchors
    .filter((anchor) => anchor.destination_room_id !== null)
    .map((anchor) => ({
      id: `portal-${anchor.id}`,
      source: anchor.room_id,
      target: anchor.destination_room_id as number,
      kindName: anchor.kind_name,
    }));
}
