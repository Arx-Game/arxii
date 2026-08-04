/**
 * HazardPromptNotifier — site-wide response card for an environmental hazard
 * prompt (#2846: sunlight bane/allergy today; hazard-generic by payload).
 *
 * Push-driven (no polling): the websocket handler emits `hazard_prompt`
 * payloads onto `hazardPromptBus`; this component — mounted once at the app
 * root alongside `DuelChallengeNotifier` — fires a persistent toast with the
 * character's real options. "Tough It Out" and "Retreat To Safety" are
 * one-click action dispatches (`hazard_endure` / `hazard_retreat` via the
 * normal REST dispatch endpoint); covering up or seeking shade happen through
 * the wardrobe / room surfaces the player already has, so the card only
 * advises them. If the player does nothing, the server-side AFK guard
 * auto-retreats them after the second damage instance — the card says so.
 *
 * Renders nothing itself — `null` always, purely a side-effect component.
 */

import { useCallback, useState } from 'react';
import { toast } from 'sonner';
import { useDispatchPlayerAction } from '@/combat/queries';
import { registryRef } from '@/combat/duels/DuelChallengeControls';
import { isDispatchFailure } from '@/combat/types';
import { useHazardPrompt } from '@/hooks/hazardPromptBus';
import type { HazardPromptPayload } from '@/hooks/types';

interface ToastBodyProps {
  toastId: string | number;
  payload: HazardPromptPayload;
}

function HazardPromptToastBody({ toastId, payload }: ToastBodyProps) {
  const { mutateAsync } = useDispatchPlayerAction(payload.character_id);
  const [isPending, setIsPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handle(actionKey: string) {
    setIsPending(true);
    setError(null);
    try {
      const result = await mutateAsync(registryRef(actionKey));
      if (isDispatchFailure(result)) {
        setError(result.message ?? 'That did not work.');
        return;
      }
      toast.dismiss(toastId);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'That did not work.');
    } finally {
      setIsPending(false);
    }
  }

  return (
    <div
      className="rounded-md border border-orange-500/50 bg-orange-500/10 p-3 shadow-sm"
      data-testid="hazard-prompt-toast"
    >
      <p className="text-sm font-semibold text-foreground">
        {payload.condition_name}
        {payload.stage_name ? `; ${payload.stage_name}` : ''}
      </p>
      <p className="mt-1 text-sm text-foreground">{payload.player_text}</p>
      <p className="mt-1 text-xs text-muted-foreground">
        Cover up or find shade where you are, or choose below. Do nothing, and your instincts will
        carry you to shelter.
      </p>
      <div className="mt-2 flex gap-2">
        <button
          type="button"
          disabled={isPending}
          onClick={() => {
            handle(payload.retreat_action).catch(() => {});
          }}
          data-testid="hazard-toast-retreat-btn"
          className="rounded border border-emerald-500/60 bg-emerald-500/10 px-3 py-1 text-xs font-semibold text-emerald-300 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {isPending ? 'Dispatching…' : 'Retreat To Safety'}
        </button>
        <button
          type="button"
          disabled={isPending}
          onClick={() => {
            handle(payload.endure_action).catch(() => {});
          }}
          data-testid="hazard-toast-endure-btn"
          className="rounded border border-orange-500/60 bg-orange-500/10 px-3 py-1 text-xs font-semibold text-orange-300 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {isPending ? 'Dispatching…' : 'Tough It Out'}
        </button>
      </div>
      {error !== null && (
        <p role="alert" className="mt-2 text-xs text-destructive" data-testid="hazard-toast-error">
          {error}
        </p>
      )}
    </div>
  );
}

export function HazardPromptNotifier() {
  const handler = useCallback((payload: HazardPromptPayload) => {
    toast.custom((toastId) => <HazardPromptToastBody toastId={toastId} payload={payload} />, {
      duration: Infinity,
    });
  }, []);
  useHazardPrompt(handler);
  return null;
}
