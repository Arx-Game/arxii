/**
 * StandoffCard: the pre-round standoff (#4145). Per group it shows what the party has
 * learned (face-down tiles for what is still hidden, revealed cause and drives), the
 * viewer's own sparks, the approaches to press, the terms to name, a Read control and
 * a Fight button. Every control dispatches a registry action and then refreshes the
 * encounter so the card redraws from the server's view.
 */

import { useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { combatKeys, useDispatchPlayerAction } from '@/combat/queries';
import { registryRef } from '@/combat/duels/DuelChallengeControls';
import { isDispatchFailure } from '@/combat/types';
import type { components } from '@/generated/api';

type StandoffView = components['schemas']['StandoffView'];
type GroupView = components['schemas']['GroupView'];

export interface StandoffCardProps {
  standoff: StandoffView;
  encounterId: number;
  characterId: number;
}

// A read can learn several things at once, one per line.
const TOAST_OPTIONS = { className: 'whitespace-pre-line' };

const NO_FOCUS = 'none';
const FOCUS_CAUSE = 'cause';
const FOCUS_DRIVE = 'drive';
const SPARK_PREFIX = 'spark:';

function readKwargs(groupId: number, focus: string): Record<string, unknown> {
  if (focus === FOCUS_CAUSE) return { group_id: groupId, focus_kind: 'cause' };
  if (focus === FOCUS_DRIVE) return { group_id: groupId, focus_kind: 'drive' };
  if (focus.startsWith(SPARK_PREFIX)) {
    return {
      group_id: groupId,
      focus_kind: 'regard',
      focus_regard_rule_id: Number(focus.slice(SPARK_PREFIX.length)),
    };
  }
  return { group_id: groupId };
}

export function StandoffCard({ standoff, encounterId, characterId }: StandoffCardProps) {
  const queryClient = useQueryClient();
  const { mutateAsync, isPending } = useDispatchPlayerAction(characterId);
  const [focusByGroup, setFocusByGroup] = useState<Record<number, string>>({});

  async function run(key: string, kwargs: Record<string, unknown> = {}) {
    try {
      const result = await mutateAsync(registryRef(key, kwargs));
      const message = result.message ?? '';
      if (isDispatchFailure(result)) {
        toast.error(message || 'That did not work.', TOAST_OPTIONS);
      } else if (message) {
        toast.success(message, TOAST_OPTIONS);
      }
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'That did not work.');
    } finally {
      await queryClient.invalidateQueries({ queryKey: combatKeys.encounter(encounterId) });
    }
  }

  function fire(key: string, kwargs: Record<string, unknown> = {}) {
    run(key, kwargs).catch(() => {});
  }

  return (
    <section
      className="flex flex-col gap-3 rounded-md border border-border bg-muted/30 p-3"
      data-testid="standoff-card"
    >
      <h3 className="font-display text-sm font-bold tracking-wide text-foreground">Standoff</h3>

      {standoff.sparks.length > 0 && (
        <div
          className="rounded-md border border-primary/40 bg-primary/10 px-3 py-2"
          data-testid="standoff-sparks"
        >
          <p className="text-[10px] font-semibold uppercase tracking-wide text-primary">
            Your spark here
          </p>
          {standoff.sparks.map((spark) => (
            <div
              key={`${spark.group_id}-${spark.regard_rule_id}`}
              className="mt-1 flex items-center justify-between gap-2 text-sm"
            >
              <span>{spark.text}</span>
              {spark.shared ? (
                <Badge variant="secondary">Shared</Badge>
              ) : (
                <Button
                  size="sm"
                  variant="outline"
                  disabled={isPending}
                  onClick={() =>
                    fire('standoff_share_spark', {
                      group_id: spark.group_id,
                      regard_rule_id: spark.regard_rule_id,
                    })
                  }
                >
                  Share with the party
                </Button>
              )}
            </div>
          ))}
        </div>
      )}

      {standoff.shared_sparks.map((spark) => (
        <p
          key={`shared-${spark.group_id}-${spark.regard_rule_id}`}
          className="rounded-md border border-border bg-card px-3 py-1.5 text-sm"
        >
          {spark.text}
        </p>
      ))}

      {standoff.groups.map((group) => (
        <GroupSection
          key={group.group_id}
          group={group}
          standoff={standoff}
          focus={focusByGroup[group.group_id] ?? NO_FOCUS}
          onFocusChange={(value) =>
            setFocusByGroup((prev) => ({ ...prev, [group.group_id]: value }))
          }
          disabled={isPending}
          fire={fire}
        />
      ))}

      <Button
        variant="destructive"
        disabled={isPending}
        onClick={() => fire('standoff_fight')}
        data-testid="standoff-fight"
      >
        Fight
      </Button>
    </section>
  );
}

interface GroupSectionProps {
  group: GroupView;
  standoff: StandoffView;
  focus: string;
  onFocusChange: (value: string) => void;
  disabled: boolean;
  fire: (key: string, kwargs?: Record<string, unknown>) => void;
}

function GroupSection({
  group,
  standoff,
  focus,
  onFocusChange,
  disabled,
  fire,
}: GroupSectionProps) {
  const approaches = standoff.approaches.filter((a) => a.group_id === group.group_id);
  const terms = standoff.terms.filter((t) => t.group_id === group.group_id);
  const sparks = standoff.sparks.filter((s) => s.group_id === group.group_id);
  const isOpen = group.state === 'open';
  const selectId = `standoff-focus-${group.group_id}`;

  return (
    <div className="flex flex-col gap-2 rounded-md border border-border bg-card p-3">
      <div className="flex items-baseline justify-between gap-2">
        <span className="font-display text-sm font-semibold">{group.name}</span>
        <span className="text-xs text-muted-foreground">x{group.member_count}</span>
      </div>

      <div className="flex flex-wrap gap-2" role="group" aria-label="What is known">
        {group.cause !== null && (
          <div className="rounded border border-primary/50 bg-primary/10 px-2 py-1 text-xs">
            <span className="block text-[10px] uppercase text-muted-foreground">cause</span>
            <b>{group.cause}</b>
          </div>
        )}
        {group.drives.map((drive) => (
          <div
            key={drive.label}
            className="rounded border border-border bg-muted px-2 py-1 text-xs"
          >
            <span className="block text-[10px] uppercase text-muted-foreground">
              {drive.strength}
            </span>
            <b>{drive.label}</b>
          </div>
        ))}
        {Array.from({ length: group.hidden_count }, (_, i) => (
          <div
            key={`hidden-${i}`}
            data-testid="standoff-facedown-tile"
            role="img"
            aria-label="Hidden, not yet read"
            className="flex h-10 w-10 items-center justify-center rounded border border-border bg-foreground/80 text-sm text-background"
          >
            ?
          </div>
        ))}
      </div>
      {group.revealed_regard.map((line) => (
        <p key={line} className="text-xs text-muted-foreground">
          {line}
        </p>
      ))}

      <div className="flex items-end gap-2">
        <div className="flex-1">
          <label htmlFor={selectId} className="text-[10px] uppercase text-muted-foreground">
            Look for
          </label>
          <Select value={focus} onValueChange={onFocusChange}>
            <SelectTrigger id={selectId} className="h-8">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={NO_FOCUS}>Anything</SelectItem>
              <SelectItem value={FOCUS_CAUSE}>Why would they fight?</SelectItem>
              <SelectItem value={FOCUS_DRIVE}>What moves them?</SelectItem>
              {sparks.map((spark) => (
                <SelectItem
                  key={spark.regard_rule_id}
                  value={`${SPARK_PREFIX}${spark.regard_rule_id}`}
                >
                  {spark.text}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <Button
          size="sm"
          disabled={disabled || !isOpen || group.hidden_count === 0}
          onClick={() => fire('standoff_read', readKwargs(group.group_id, focus))}
        >
          Read them
        </Button>
      </div>

      <div className="flex flex-col gap-1">
        {approaches.map((approach) => (
          <Button
            key={approach.approach_id}
            variant="outline"
            disabled={disabled || !isOpen}
            className="h-auto justify-between whitespace-normal py-2 text-left"
            onClick={() =>
              fire('standoff_press', {
                group_id: group.group_id,
                approach_id: approach.approach_id,
              })
            }
          >
            <span className="flex flex-col">
              <span>{approach.name}</span>
              {approach.levers.map((lever) => (
                <span key={lever} className="text-xs font-normal italic text-muted-foreground">
                  {lever}
                </span>
              ))}
            </span>
            <span className="text-xs text-muted-foreground">{approach.grade}</span>
          </Button>
        ))}
      </div>

      {terms.length > 0 && (
        <div className="flex flex-col gap-1">
          <p className="text-xs text-muted-foreground">
            Name your terms. Each successful press makes this easier (ease {group.terms_ease}).
          </p>
          {terms.map((term) => (
            <Button
              key={term.terms_id}
              variant="secondary"
              disabled={disabled || !isOpen}
              className="justify-between"
              onClick={() =>
                fire('standoff_terms', { group_id: group.group_id, terms_id: term.terms_id })
              }
            >
              <span>{term.name}</span>
              <span className="text-xs text-muted-foreground">{term.grade}</span>
            </Button>
          ))}
        </div>
      )}
    </div>
  );
}
