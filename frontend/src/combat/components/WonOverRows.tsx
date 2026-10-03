/**
 * WonOverRows — the won-over opponents on the outcome rail (#4091).
 *
 * Renders one row per `AftermathDigest.won_over` entry: who was won over, the
 * condition's own name (plus a stage bar + "Fond, stage 2 of 3" when staged),
 * the hold's own time line, and whichever of Bind as companion / Settle /
 * Take into service / Send away this viewer's per-row flags (`can_bind`/
 * `can_settle`/`can_take_into_service`/`can_send_away`) allow. Strike first
 * is never a button here — it is a muted hint line pointing at the real
 * action (casting a hostile technique at the NPC through the ordinary
 * targeting surfaces).
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
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { PersonaAvatar } from '@/components/PersonaAvatar';
import { PersonaMenu } from '@/scenes/components/PersonaMenu';
import { createActionRequest } from '@/scenes/actionQueries';
import { combatKeys, useDispatchPlayerAction } from '@/combat/queries';
import { isDispatchFailure } from '@/combat/types';
import { useCompanionArchetypes } from '@/companions/queries';
import { useCharacterGifts } from '@/magic/queries';
import { cn } from '@/lib/utils';
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

function genericFailureMessage(action: string): string {
  return `Could not ${action}.`;
}

function errorMessage(err: unknown, action: string): string {
  return err instanceof Error ? err.message : genericFailureMessage(action);
}

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

/** A row-level verb fallback ("Charmed"/"Turned"/"Calmed") for when the
 * condition itself isn't visible to this viewer; the condition's own `name`
 * (e.g. "Enthralled") is preferred whenever it's present. */
function capitalize(value: string): string {
  return value.length > 0 ? value[0].toUpperCase() + value.slice(1) : value;
}

/** The charmer's persona name alone, stripped from `source_label`'s
 * "<name>'s <technique>" shape (`_source_label`, `world/combat/won_over.py`) —
 * a label with no technique suffix is already just the name. */
function charmerPersonaName(row: WonOverRow): string {
  const marker = "'s ";
  const index = row.source_label.indexOf(marker);
  return index === -1 ? row.source_label : row.source_label.slice(0, index);
}

/** Small dot row for a staged condition's progress, after the demo's
 * `.stagebar` (no existing stage-progress component was found to reuse). */
function StageBar({ current, total }: { current: number; total: number }) {
  return (
    <span className="inline-flex gap-0.5" aria-hidden="true" data-testid="won-over-stage-bar">
      {Array.from({ length: total }, (_, index) => (
        <span
          key={index}
          className={cn('h-1.5 w-3 rounded-sm', index < current ? 'bg-primary' : 'bg-muted')}
        />
      ))}
    </span>
  );
}

/** The hold's own time line as a pill — amber-leaning (`accent`, the
 * Arx realm's gold hue) for an open-ended rounds hold, `primary` for a
 * concretely-timed one. Reuses the existing `Badge` component/tokens; no new
 * CSS. */
function TimePill({ row }: { row: WonOverRow }) {
  const holds = row.holds_until_settled || !row.condition?.expires_at;
  return (
    <Badge
      variant="outline"
      className={holds ? 'border-accent text-accent' : 'border-primary text-primary'}
    >
      {timeLeftText(row)}
    </Badge>
  );
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

  const { data: archetypes } = useCompanionArchetypes(bindOpen);
  const { data: gifts } = useCharacterGifts(characterId, bindOpen);

  const [serviceOpen, setServiceOpen] = useState(false);
  const [roleContext, setRoleContext] =
    useState<(typeof ROLE_CONTEXT_OPTIONS)[number]['value']>('contact');

  function invalidateAfterAction() {
    // No encounterId is threaded this far down; combatKeys.all is a prefix
    // match (React Query), so it covers combatKeys.encounter(...) along with
    // everything else CombatTurnPanel reads.
    queryClient.invalidateQueries({ queryKey: combatKeys.all }).catch(() => {});
  }

  function dispatchRegistryAction(
    registryKey: string,
    kwargs: Record<string, unknown>,
    actionLabel: string
  ) {
    dispatch.mutate(
      { ref: { backend: 'registry', registry_key: registryKey }, kwargs },
      {
        onSuccess: (result) => {
          if (isDispatchFailure(result)) {
            toast.error(result.message ?? genericFailureMessage(actionLabel));
            return;
          }
          if (result.message) toast.success(result.message);
          invalidateAfterAction();
        },
        onError: (err) => toast.error(errorMessage(err, actionLabel)),
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
    onError: (err) => toast.error(errorMessage(err, 'settle this')),
  });

  const canSubmitBind = archetypeId !== '' && giftId !== '' && bindName.trim() !== '';

  function handleBindSubmit() {
    if (!canSubmitBind) return;
    dispatchRegistryAction(
      'promote_summon',
      {
        combat_opponent_id: row.opponent_id,
        archetype_id: Number(archetypeId),
        gift_id: Number(giftId),
        name: bindName.trim(),
      },
      'bind them as a companion'
    );
    setBindOpen(false);
    setArchetypeId('');
    setGiftId('');
    setBindName('');
  }

  function handleTakeIntoServiceSubmit() {
    if (row.persona_id == null) return;
    dispatchRegistryAction(
      'charm_asset',
      { target_persona_id: row.persona_id, role_context: roleContext },
      'take them into service'
    );
    setServiceOpen(false);
  }

  function handleSendAway() {
    dispatchRegistryAction('send_away', { combat_opponent_id: row.opponent_id }, 'send them away');
  }

  function handleSettle() {
    settleMutation.mutate();
  }

  // Ruling R2: a nameless row never shows Settle or the Strike-first hint,
  // regardless of its own can_settle flag (computed from the opponent's
  // state alone, not from namelessness). Settle is a scene action request, so
  // it also needs a scene to post to (#4091 final review).
  const showSettle = row.can_settle && !row.nameless && sceneId != null;
  const showStrikeFirstHint = !row.nameless;
  // A nameless row someone else charmed: still bindable in principle, just
  // not by this viewer.
  const showCharmerNote = row.nameless && !row.can_bind;

  const conditionLabel = row.condition?.name ?? capitalize(row.verb);
  const hasStages = row.condition?.total_stages != null && row.condition?.stage_order != null;

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
            <span className="text-xs text-foreground">{conditionLabel}</span>
            {hasStages && (
              <>
                <StageBar
                  current={row.condition!.stage_order!}
                  total={row.condition!.total_stages!}
                />
                <span className="text-[11px] text-muted-foreground">
                  {row.condition!.stage_name ? `${row.condition!.stage_name}, ` : ''}
                  stage {row.condition!.stage_order} of {row.condition!.total_stages}
                </span>
              </>
            )}
            <span className="text-[11px] text-muted-foreground">by {row.source_label}</span>
          </div>
          <div className="flex items-center gap-1.5 text-[11px] text-muted-foreground">
            <TimePill row={row} />
            {row.condition?.total_stages != null && <span>fading: strength {row.strength}</span>}
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

          {showCharmerNote && (
            // PLACEHOLDER copy (review round 1, item 6) — not authored prose.
            <p
              className="text-[11px] italic text-muted-foreground"
              data-testid={`won-over-charmer-note-${row.opponent_id}`}
            >
              only {charmerPersonaName(row)} can bind it
            </p>
          )}

          {bindOpen && (
            <div
              className="flex flex-wrap items-end gap-1.5 pt-1"
              data-testid={`won-over-bind-form-${row.opponent_id}`}
            >
              <label className="flex flex-col gap-0.5 text-[10px] text-muted-foreground">
                Archetype
                <Select value={archetypeId} onValueChange={setArchetypeId}>
                  <SelectTrigger className="h-8 w-36 text-xs">
                    <SelectValue placeholder="Choose archetype" />
                  </SelectTrigger>
                  <SelectContent>
                    {(archetypes ?? []).map((archetype) => (
                      <SelectItem key={archetype.id} value={String(archetype.id)}>
                        {archetype.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </label>
              <label className="flex flex-col gap-0.5 text-[10px] text-muted-foreground">
                Gift
                <Select value={giftId} onValueChange={setGiftId}>
                  <SelectTrigger className="h-8 w-36 text-xs">
                    <SelectValue placeholder="Choose gift" />
                  </SelectTrigger>
                  <SelectContent>
                    {(gifts ?? []).map((gift) => (
                      <SelectItem key={gift.gift_detail.id} value={String(gift.gift_detail.id)}>
                        {gift.gift_detail.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </label>
              <Input
                aria-label="Companion name"
                placeholder="Name"
                value={bindName}
                onChange={(e) => setBindName(e.target.value)}
                className="h-8 w-32 text-xs"
              />
              <Button
                type="button"
                size="sm"
                disabled={!canSubmitBind}
                onClick={handleBindSubmit}
                data-testid={`won-over-bind-confirm-${row.opponent_id}`}
              >
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
              <Button
                type="button"
                size="sm"
                onClick={handleTakeIntoServiceSubmit}
                data-testid={`won-over-service-confirm-${row.opponent_id}`}
              >
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
