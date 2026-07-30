/**
 * Module-level event bus for `hazard_prompt` websocket payloads (#2846).
 *
 * Mirrors `actionResultBus`: the websocket handler emits, the mounted
 * `HazardPromptNotifier` subscribes and renders the response card. A native
 * `EventTarget` keeps this free of Redux churn and module-graph cycles.
 */

import { useEffect } from 'react';
import type { HazardPromptPayload } from './types';

const bus = new EventTarget();
const EVENT_NAME = 'hazard-prompt';

/** Websocket message handler is the only intended caller. */
export function emitHazardPrompt(payload: HazardPromptPayload): void {
  bus.dispatchEvent(new CustomEvent<HazardPromptPayload>(EVENT_NAME, { detail: payload }));
}

/** Subscribe a (memoized) handler to incoming hazard prompts. */
export function useHazardPrompt(handler: (payload: HazardPromptPayload) => void): void {
  useEffect(() => {
    const listener = (event: Event): void => {
      const custom = event as CustomEvent<HazardPromptPayload>;
      handler(custom.detail);
    };
    bus.addEventListener(EVENT_NAME, listener);
    return () => bus.removeEventListener(EVENT_NAME, listener);
  }, [handler]);
}
