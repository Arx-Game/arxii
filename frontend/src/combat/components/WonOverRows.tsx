/**
 * WonOverRows — the won-over opponents on the outcome rail (#4091).
 *
 * Renders one row per `AftermathDigest.won_over` entry: who was won over, by
 * what verb (charmed/turned/calmed), the hold's own time line, and whichever
 * of Bind as companion / Settle / Take into service / Send away this viewer's
 * per-row flags (`can_bind`/`can_settle`/`can_take_into_service`/
 * `can_send_away`) allow. Strike first is never a button here — it is a
 * muted hint line pointing at the real action (casting a hostile technique
 * at the NPC through the ordinary targeting surfaces).
 *
 * Ruling R2 (demo review): a nameless row offers Bind and Send away only — no
 * Settle, no Strike-first hint — regardless of what the row's own flags say,
 * since `can_settle` is computed from the opponent's state alone and does not
 * itself know about namelessness.
 *
 * Every write here goes through the existing registry-dispatch
 * (`useDispatchPlayerAction`) or scene action-request
 * (`createActionRequest`) pipelines — no new backend endpoint.
 */

import { useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { PersonaAvatar } from '@/components/PersonaAvatar';
import { PersonaMenu } from '@/scenes/components/PersonaMenu';
import { createActionRequest } from '@/scenes/actionQueries';
import { combatKeys, useDispatchPlayerAction } from '@/combat/queries';
import { isDispatchFailure } from '@/combat/types';
import { ConditionBadge } from './ConditionBadge';
import type { components } from '@/generated/api';

export type WonOverRow = components['schemas']['WonOverRow'];

export interface WonOverRowsProps {
  rows: WonOverRow[];
  characterId: number | null;
  sceneId: string | null;
}

const ROLE_CONTEXT_OPTIONS = [
  { value: 'informant', label: 'Informant' },
  { value: 'contact', label: 'Contact' },
  { value: 'personal_favor', label: 'Personal favor' },
] as const;

const SECONDS_PER_HOUR = 3600;
const SECONDS_PER_MINUTE = 60;

/** `holds until settled` for a rounds-measured hold, else `about N hours left`
 * (or minutes, under an hour), mirroring the telnet line's own rounding
 * (`_allegiance_time_text`, `src/flows/object_states/character_state.py`). */
function timeLeftText(row: WonOverRow): string {
  if (row.holds_until_settled || !row.condition?.expires_at) {
    return 'holds until settled';
  }
  const totalSeconds = Math.max(
    (new Date(row.condition.expires_at).getTime() - Date.now()) / 1000,
    0
  );
  if (totalSeconds < SECONDS_PER_HOUR) {
    const minutes = Math.ceil(totalSeconds / SECONDS_PER_MINUTE);
    return `about ${minutes} ${minutes === 1 ? 'minute' : 'minutes'} left`;
  }
  const hours = Math.ceil(totalSeconds / SECONDS_PER_HOUR);
  return `about ${hours} ${hours === 1 ? 'hour' : 'hours'} left`;
}

function WonOverRowItem({
  row,
  characterId,
  sceneId,
}: {
  row: WonOverRow;
  characterId: number | null;
  sceneId: string | null;
}) {
  const queryClient = useQueryClient();
  const dispatch = useDispatchPlayerAction(characterId ?? 0);

  const [bindOpen, setBindOpen] = useState(false);
  const [archetypeId, setArchetypeId] = useState('');
  const [giftId, setGiftId] = useState('');
  const [bindName, setBindName] = useState('');

  const [serviceOpen, setServiceOpen] = useState(false);
  const [roleContext, setRoleContext] =
    useState<(typeof ROLE_CONTEXT_OPTIONS)[number]['value']>('contact');

  function invalidateAfterAction() {
    // No encounterId is threaded this far down; combatKeys.all is a prefix
    // match (React Query), so it covers combatKeys.encounter(...) along with
    // everything else CombatTurnPanel reads.
    queryClient.invalidateQueries({ queryKey: combatKeys.all }).catch(() => {});
  }

  function dispatchRegistryAction(registryKey: string, kwargs: Record<string, unknown>) {
    dispatch.mutate(
      { ref: { backend: 'registry', registry_key: registryKey }, kwargs },
      {
        onSuccess: (result) => {
          if (isDispatchFailure(result)) {
            toast.error(result.message ?? 'That failed.');
            return;
          }
          if (result.message) toast.success(result.message);
          invalidateAfterAction();
        },
      }
    );
  }

  const settleMutation = useMutation({
    mutationFn: () =>
      createActionRequest(sceneId ?? '', {
        action_key: 'settle',
        target_persona_id: row.persona_id ?? undefined,
      }),
    onSuccess: invalidateAfterAction,
  });

  function handleBindSubmit() {
    dispatchRegistryAction('promote_summon', {
      combat_opponent_id: row.opponent_id,
      archetype_id: Number(archetypeId),
      gift_id: Number(giftId),
      name: bindName,
    });
    setBindOpen(false);
    setArchetypeId('');
    setGiftId('');
    setBindName('');
  }

  function handleTakeIntoServiceSubmit() {
    if (row.persona_id == null) return;
    dispatchRegistryAction('charm_asset', {
      target_persona_id: row.persona_id,
      role_context: roleContext,
    });
    setServiceOpen(false);
  }

  function handleSendAway() {
    dispatchRegistryAction('send_away', { combat_opponent_id: row.opponent_id });
  }

  function handleSettle() {
    settleMutation.mutate();
  }

  // Ruling R2: a nameless row never shows Settle or the Strike-first hint,
  // regardless of its own can_settle flag (computed from the opponent's
  // state alone, not from namelessness).
  const showSettle = row.can_settle && !row.nameless;
  const showStrikeFirstHint = !row.nameless;

  const nameNode = (
    <span className="text-xs font-medium text-foreground">
      {row.persona_id != null ? (
        <PersonaMenu personaId={row.persona_id} personaName={row.name}>
          {row.name}
        </PersonaMenu>
      ) : (
        row.name
      )}
    </span>
  );

  return (
    <div
      className="space-y-1.5 rounded-md border border-border bg-muted/30 p-2"
      data-testid={`won-over-row-${row.opponent_id}`}
    >
      <div className="flex items-start gap-2">
        <PersonaAvatar source={{ name: row.name }} size="sm" />
        <div className="flex-1 space-y-1">
          <div className="flex flex-wrap items-center gap-1.5">
            {nameNode}
            {row.nameless && (
              <span className="rounded px-1 text-[10px] text-muted-foreground">nameless</span>
            )}
            {row.condition && <ConditionBadge condition={row.condition} />}
            <span className="rounded bg-primary/10 px-1 text-[10px] text-primary">{row.verb}</span>
            <span className="text-[11px] text-muted-foreground">by {row.source_label}</span>
          </div>
          <div className="text-[11px] text-muted-foreground">
            {timeLeftText(row)}
            {row.condition?.total_stages != null && ` · fading: strength ${row.strength}`}
          </div>

          <div className="flex flex-wrap gap-1.5 pt-0.5">
            {row.can_bind && !bindOpen && (
              <Button
                type="button"
                size="sm"
                variant="default"
                data-testid={`won-over-bind-${row.opponent_id}`}
                onClick={() => setBindOpen(true)}
              >
                Bind as companion
              </Button>
            )}
            {showSettle && (
              <Button
                type="button"
                size="sm"
                variant="outline"
                data-testid={`won-over-settle-${row.opponent_id}`}
                disabled={settleMutation.isPending}
                onClick={handleSettle}
              >
                Settle
              </Button>
            )}
            {row.can_take_into_service && !serviceOpen && (
              <Button
                type="button"
                size="sm"
                variant="default"
                data-testid={`won-over-service-${row.opponent_id}`}
                onClick={() => setServiceOpen(true)}
              >
                Take into service
              </Button>
            )}
            {row.can_send_away && (
              <Button
                type="button"
                size="sm"
                variant="outline"
                data-testid={`won-over-send-away-${row.opponent_id}`}
                disabled={dispatch.isPending}
                onClick={handleSendAway}
              >
                Send away
              </Button>
            )}
          </div>

          {showStrikeFirstHint && (
            <p
              className="text-[11px] italic text-muted-foreground"
              data-testid={`won-over-strike-hint-${row.opponent_id}`}
            >
              Strike first: cast a hostile technique at {row.name}
            </p>
          )}

          {bindOpen && (
            <div
              className="flex flex-wrap items-end gap-1.5 pt-1"
              data-testid={`won-over-bind-form-${row.opponent_id}`}
            >
              <Input
                aria-label="Archetype id"
                placeholder="Archetype id"
                value={archetypeId}
                onChange={(e) => setArchetypeId(e.target.value)}
                className="h-8 w-28 text-xs"
              />
              <Input
                aria-label="Gift id"
                placeholder="Gift id"
                value={giftId}
                onChange={(e) => setGiftId(e.target.value)}
                className="h-8 w-24 text-xs"
              />
              <Input
                aria-label="Companion name"
                placeholder="Name"
                value={bindName}
                onChange={(e) => setBindName(e.target.value)}
                className="h-8 w-32 text-xs"
              />
              <Button type="button" size="sm" onClick={handleBindSubmit}>
                Confirm
              </Button>
              <Button type="button" size="sm" variant="ghost" onClick={() => setBindOpen(false)}>
                Cancel
              </Button>
            </div>
          )}

          {serviceOpen && (
            <div
              className="flex flex-wrap items-end gap-1.5 pt-1"
              data-testid={`won-over-service-form-${row.opponent_id}`}
            >
              <select
                aria-label="Role"
                value={roleContext}
                onChange={(e) =>
                  setRoleContext(e.target.value as (typeof ROLE_CONTEXT_OPTIONS)[number]['value'])
                }
                className="h-8 rounded-md border border-input bg-transparent px-2 text-xs"
              >
                {ROLE_CONTEXT_OPTIONS.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
              <Button type="button" size="sm" onClick={handleTakeIntoServiceSubmit}>
                Confirm
              </Button>
              <Button type="button" size="sm" variant="ghost" onClick={() => setServiceOpen(false)}>
                Cancel
              </Button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export function WonOverRows({ rows, characterId, sceneId }: WonOverRowsProps) {
  if (rows.length === 0) return null;
  return (
    <div className="space-y-1.5" data-testid="won-over-rows">
      {rows.map((row) => (
        <WonOverRowItem
          key={row.opponent_id}
          row={row}
          characterId={characterId}
          sceneId={sceneId}
        />
      ))}
    </div>
  );
}
