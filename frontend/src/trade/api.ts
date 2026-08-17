/**
 * Player<->player negotiated trade API (#2990).
 *
 * Hand-authored, not generated — same reasoning as `@/covenants/api.ts`'s
 * GroupStoryRequest block: this is a brand-new model/serializer/viewset, and
 * regenerating the shared OpenAPI schema on this branch risks colliding with
 * unrelated in-flight branches. Reads hit the read-only `TradeSessionViewSet`
 * directly; every mutation dispatches through the generic action-dispatch
 * endpoint (`POST /api/actions/characters/{id}/dispatch/`, see
 * `@/covenants/api.ts`'s `depositCovenantFunds`) — never a bespoke mutation
 * endpoint here, matching the "all trade mutations go through actions"
 * convention `world/items/trade/views.py` documents.
 */

import { apiFetch } from '@/evennia_replacements/api';
import { parseDispatchBody } from '@/lib/errors';

export type TradeStatus = 'proposed' | 'active' | 'completed' | 'cancelled';

export interface TradeItemStake {
  id: number;
  item_instance: number;
  item_name: string;
  offered_by_sheet: number;
  offered_by_name: string;
  staked_at: string;
}

export interface TradeSession {
  id: number;
  initiator_sheet: number;
  initiator_name: string;
  counterparty_sheet: number;
  counterparty_name: string;
  status: TradeStatus;
  initiator_confirmed: boolean;
  counterparty_confirmed: boolean;
  initiator_coppers: number;
  counterparty_coppers: number;
  item_stakes: TradeItemStake[];
  created_at: string;
  resolved_at: string | null;
}

interface PaginatedTradeSessionList {
  count: number;
  next: string | null;
  previous: string | null;
  results: TradeSession[];
}

const TRADE_SESSIONS_URL = '/api/items/trade-sessions';

/** GET /api/items/trade-sessions/ — the viewer's own open + past trades. */
export async function getTradeSessions(): Promise<TradeSession[]> {
  const res = await apiFetch(`${TRADE_SESSIONS_URL}/`);
  if (!res.ok) throw new Error('Failed to load trade sessions');
  const body = (await res.json()) as TradeSession[] | PaginatedTradeSessionList;
  return Array.isArray(body) ? body : body.results;
}

/** GET /api/items/trade-sessions/{id}/ */
export async function getTradeSession(sessionId: number): Promise<TradeSession> {
  const res = await apiFetch(`${TRADE_SESSIONS_URL}/${sessionId}/`);
  if (!res.ok) throw new Error('Failed to load trade session');
  return res.json() as Promise<TradeSession>;
}

// ---------------------------------------------------------------------------
// Mutations — every one dispatches a REGISTRY action for the actor's own
// character (`actions/definitions/trade.py`).
// ---------------------------------------------------------------------------

async function dispatchTradeAction(
  actorCharacterId: number,
  registryKey: string,
  kwargs: Record<string, unknown>
): Promise<{ message: string; data: Record<string, unknown> | undefined }> {
  const res = await apiFetch(`/api/actions/characters/${actorCharacterId}/dispatch/`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ ref: { backend: 'registry', registry_key: registryKey }, kwargs }),
  });
  const { success, message, data } = await parseDispatchBody(res);
  if (!res.ok || success === false) throw new Error(message ?? 'Trade action failed.');
  return { message: message ?? '', data };
}

/** Propose a trade with a co-located character; returns the new session id. */
export async function proposeTrade(
  actorCharacterId: number,
  targetCharacterId: number
): Promise<number> {
  const { data } = await dispatchTradeAction(actorCharacterId, 'propose_trade', {
    target: targetCharacterId,
  });
  const sessionId = data?.session_id;
  if (typeof sessionId !== 'number') throw new Error('Trade proposed, but no session id returned.');
  return sessionId;
}

export async function acceptTrade(actorCharacterId: number, sessionId: number): Promise<void> {
  await dispatchTradeAction(actorCharacterId, 'accept_trade', { session_id: sessionId });
}

/** Stage `itemInstanceId`'s ObjectDB (game_object) id onto the table. */
export async function stageTradeItem(
  actorCharacterId: number,
  sessionId: number,
  itemGameObjectId: number
): Promise<void> {
  await dispatchTradeAction(actorCharacterId, 'stage_trade_item', {
    session_id: sessionId,
    target: itemGameObjectId,
  });
}

export async function unstageTradeItem(actorCharacterId: number, stakeId: number): Promise<void> {
  await dispatchTradeAction(actorCharacterId, 'unstage_trade_item', { stake_id: stakeId });
}

export async function setTradeCoin(
  actorCharacterId: number,
  sessionId: number,
  amount: number
): Promise<void> {
  await dispatchTradeAction(actorCharacterId, 'set_trade_coin', {
    session_id: sessionId,
    amount,
  });
}

/** Confirm the current offer; the server executes the swap once both sides have. */
export async function confirmTrade(
  actorCharacterId: number,
  sessionId: number
): Promise<{ completed: boolean }> {
  const { data } = await dispatchTradeAction(actorCharacterId, 'confirm_trade', {
    session_id: sessionId,
  });
  return { completed: data?.completed === true };
}

export async function cancelTrade(actorCharacterId: number, sessionId: number): Promise<void> {
  await dispatchTradeAction(actorCharacterId, 'cancel_trade', { session_id: sessionId });
}
