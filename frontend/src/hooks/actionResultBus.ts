/**
 * Module-level event bus for `action_result` websocket payloads.
 *
 * The websocket lives at the top of the React tree and emits at most one
 * inbound `action_result` per executed action. Components scattered across
 * the tree (e.g. WardrobePage) want to react to those results — refreshing
 * caches, surfacing toasts — without having to be a child of the socket
 * provider.
 *
 * A native `EventTarget` is the lightest possible pub/sub: no Redux churn,
 * no React Query dependency, no module-graph cycles. Subscribe with
 * `useActionResult(handler)` and the hook handles add/remove around
 * StrictMode-friendly cleanup.
 */

import { useEffect } from 'react';
import type { ActionResultPayload } from './types';

const bus = new EventTarget();
const EVENT_NAME = 'action-result';

/**
 * Dispatch an `action_result` payload to every subscribed listener.
 *
 * The websocket message handler is the only intended caller — components
 * should not invoke this directly.
 */
export function emitActionResult(payload: ActionResultPayload): void {
  bus.dispatchEvent(new CustomEvent<ActionResultPayload>(EVENT_NAME, { detail: payload }));
}

/**
 * Subscribe a handler to incoming `action_result` payloads.
 *
 * The handler reference is captured in the dependency array, so callers
 * should memoize via `useCallback` (or keep it stable some other way) to
 * avoid resubscribing on every render.
 */
export function useActionResult(handler: (payload: ActionResultPayload) => void): void {
  useEffect(() => {
    const listener = (event: Event): void => {
      const custom = event as CustomEvent<ActionResultPayload>;
      handler(custom.detail);
    };
    bus.addEventListener(EVENT_NAME, listener);
    return () => bus.removeEventListener(EVENT_NAME, listener);
  }, [handler]);
}
