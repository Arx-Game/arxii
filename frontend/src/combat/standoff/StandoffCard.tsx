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
import { cn } from '@/lib/utils';

import './standoff.css';

type StandoffView = components['schemas']['StandoffView'];
type GroupView = components['schemas']['GroupView'];
type TermsView = components['schemas']['TermsView'];

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

const GRADE_TONES: Record<string, string> = {
  easy: 'text-emerald-700 dark:text-emerald-300',
  moderate: 'text-amber-700 dark:text-amber-400',
  hard: 'text-red-700 dark:text-red-400',
  very_hard: 'text-red-700 dark:text-red-400',
};
const GRADE_FALLBACK_TONE = 'text-muted-foreground';

function Grade({ value, label }: { value: string; label: string }) {
  if (!label) return null;
  return (
    <span
      data-testid="standoff-grade"
      className={cn('shrink-0 font-mono text-xs', GRADE_TONES[value] ?? GRADE_FALLBACK_TONE)}
    >
      {label}
    </span>
  );
}

function plural(count: number, one: string, many: string): string {
  return `${count} ${count === 1 ? one : many}`;
}

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

  const groupById = new Map(standoff.groups.map((g) => [g.group_id, g]));

  return (
    <section
      className="standoff-card flex flex-col gap-3 rounded-md border border-border bg-muted/30 p-3"
      data-testid="standoff-card"
    >
      <h3 className="font-display text-sm font-bold tracking-wide text-foreground">
        Standoff
        {standoff.place ? (
          <span className="font-normal text-muted-foreground"> at {standoff.place}</span>
        ) : null}
      </h3>

      {standoff.sparks.length > 0 && (
        <div
          className="rounded-md border border-primary/40 bg-primary/10 px-3 py-2"
          data-testid="standoff-sparks"
        >
          <p className="text-[10px] font-semibold uppercase tracking-wide text-primary">
            Your spark here
          </p>
          {standoff.sparks.map((spark) => {
            const unread = (groupById.get(spark.group_id)?.revealed_regard.length ?? 0) === 0;
            return (
              <div
                key={`${spark.group_id}-${spark.regard_rule_id}`}
                className="mt-1 flex flex-col items-start gap-1.5 text-sm"
              >
                <p className="min-w-0">
                  <b>{spark.text}</b>
                  {unread ? (
                    <span className="text-muted-foreground">
                      {' '}
                      How, you don&apos;t know yet. A read could tell you.
                    </span>
                  ) : null}
                </p>
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
            );
          })}
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
        variant="outline"
        disabled={isPending}
        onClick={() => fire('standoff_fight')}
        data-testid="standoff-fight"
        className="h-auto w-full justify-between border-destructive py-2 text-destructive hover:bg-muted hover:text-destructive focus-visible:ring-2"
      >
        <span>Fight</span>
        <span className="text-xs font-normal">starts round one</span>
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
  const [chosenTermsId, setChosenTermsId] = useState<number | null>(null);
  const chosenTerms = terms.find((t) => t.terms_id === chosenTermsId) ?? null;
  const isOpen = group.state === 'open';
  const wasRead =
    group.cause !== null || group.drives.length > 0 || group.revealed_regard.length > 0;
  const selectId = `standoff-focus-${group.group_id}`;

  return (
    <div className="standoff-row" data-testid="standoff-group">
      <div className="flex min-w-0 flex-col gap-2 rounded-md border border-border bg-card p-3">
        <div className="flex items-baseline justify-between gap-2">
          <span className="font-display text-sm font-semibold">{group.name}</span>
          <span className="text-xs text-muted-foreground">x{group.member_count}</span>
        </div>

        <div className="flex flex-wrap gap-2" role="group" aria-label="What is known">
          {group.cause !== null && (
            <div
              data-testid="standoff-cause-tile"
              className="standoff-tile flex flex-col items-center justify-center gap-1 rounded-md border-2 border-dashed border-destructive bg-card p-1.5 text-center text-xs"
            >
              <b className="font-display text-[13px]">{group.cause}</b>
              <span className="font-mono text-[10px] text-muted-foreground">cause</span>
              {group.cause_gloss ? (
                <span className="text-[10px] text-muted-foreground">{group.cause_gloss}</span>
              ) : null}
            </div>
          )}
          {group.drives.map((drive) => (
            <div
              key={drive.label}
              className="standoff-tile flex flex-col items-center justify-center gap-1 rounded-md border-2 border-accent bg-card p-1.5 text-center text-xs"
            >
              <b className="font-display text-[13px]">{drive.label}</b>
              <span className="font-mono text-[10px] text-muted-foreground">{drive.strength}</span>
            </div>
          ))}
          {Array.from({ length: group.hidden_count }, (_, i) => (
            <div
              key={`hidden-${i}`}
              data-testid="standoff-facedown-tile"
              role="img"
              aria-label="Hidden, not yet read"
              className="standoff-facedown flex items-center justify-center rounded-md font-display text-2xl"
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
      </div>

      <div className="flex min-w-0 flex-col gap-1.5">
        <div className="flex flex-col gap-1.5 rounded-md border border-border bg-card p-2">
          <label htmlFor={selectId} className="text-[10px] uppercase text-muted-foreground">
            Look for
          </label>
          <Select value={focus} onValueChange={onFocusChange}>
            <SelectTrigger id={selectId} className="h-auto min-h-8 w-full py-1 text-left">
              <span className="min-w-0 flex-1 truncate">
                <SelectValue />
              </span>
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
          <Button
            size="sm"
            variant="outline"
            disabled={disabled || !isOpen || group.hidden_count === 0}
            className="h-auto w-full justify-between gap-2 whitespace-normal py-2 text-left hover:bg-muted hover:text-foreground focus-visible:ring-2"
            onClick={() => fire('standoff_read', readKwargs(group.group_id, focus))}
          >
            <span className="flex min-w-0 flex-col">
              <span>{wasRead ? 'Read them again' : 'Read them'}</span>
              {group.read_check ? (
                <span className="text-xs font-normal text-muted-foreground">
                  {group.read_check} · reveals by success level
                </span>
              ) : null}
            </span>
            <Grade value={group.read_grade} label={group.read_grade_label} />
          </Button>
        </div>

        {approaches.map((approach) => (
          <Button
            key={approach.approach_id}
            variant="outline"
            disabled={disabled || !isOpen}
            data-testid={approach.hits_revealed_drive ? 'standoff-approach-hit' : undefined}
            className={cn(
              'h-auto w-full justify-between gap-2 whitespace-normal py-2 text-left hover:bg-muted hover:text-foreground focus-visible:ring-2',
              approach.hits_revealed_drive &&
                'border-accent shadow-[inset_3px_0_0_hsl(var(--accent))]'
            )}
            onClick={() =>
              fire('standoff_press', {
                group_id: group.group_id,
                approach_id: approach.approach_id,
              })
            }
          >
            <span className="flex min-w-0 flex-col">
              <span>{approach.name}</span>
              <span className="text-xs font-normal text-muted-foreground">
                {approach.check_caption}
              </span>
              {approach.levers.length === 0 ? (
                <span className="text-xs font-normal text-muted-foreground">no known lever</span>
              ) : (
                approach.levers.map((lever) => (
                  <span
                    key={lever.text}
                    className={cn(
                      'text-xs font-normal italic',
                      lever.is_spark ? 'text-primary' : 'text-foreground'
                    )}
                  >
                    {lever.text}
                  </span>
                ))
              )}
            </span>
            <Grade value={approach.grade} label={approach.grade_label} />
          </Button>
        ))}

        {terms.length > 0 && (
          <TermsSection
            terms={terms}
            ease={group.terms_ease}
            disabled={disabled || !isOpen}
            chosen={chosenTerms}
            onChoose={(id) => setChosenTermsId(id)}
            onSpin={(t) => {
              fire('standoff_terms', { group_id: group.group_id, terms_id: t.terms_id });
              setChosenTermsId(null);
            }}
          />
        )}
      </div>
    </div>
  );
}

interface TermsSectionProps {
  terms: TermsView[];
  ease: number;
  disabled: boolean;
  chosen: TermsView | null;
  onChoose: (termsId: number | null) => void;
  onSpin: (terms: TermsView) => void;
}

function TermsSection({ terms, ease, disabled, chosen, onChoose, onSpin }: TermsSectionProps) {
  return (
    <div className="flex flex-col gap-1.5">
      <p className="text-xs text-muted-foreground">
        Name your terms.{' '}
        {ease === 0
          ? 'Each successful press makes this easier.'
          : `${plural(ease, 'step', 'steps')} easier so far.`}
      </p>
      {terms.map((term) => (
        <Button
          key={term.terms_id}
          variant="outline"
          disabled={disabled}
          aria-pressed={chosen?.terms_id === term.terms_id}
          className={cn(
            'h-auto w-full justify-between gap-2 whitespace-normal py-2 text-left hover:bg-muted hover:text-foreground focus-visible:ring-2',
            chosen?.terms_id === term.terms_id && 'border-primary'
          )}
          onClick={() => onChoose(term.terms_id)}
        >
          <span>{term.name}</span>
          <Grade value={term.grade} label={term.grade_label} />
        </Button>
      ))}
      {chosen !== null && (
        <div
          className="flex flex-col gap-2 rounded-md border border-primary/50 bg-primary/5 p-2"
          data-testid="standoff-terms-confirm"
        >
          {chosen.description ? <p className="text-sm">{chosen.description}</p> : null}
          <div className="flex flex-wrap gap-2">
            <Button size="sm" disabled={disabled} onClick={() => onSpin(chosen)}>
              Spin for &quot;{chosen.name}&quot;
            </Button>
            <Button size="sm" variant="outline" onClick={() => onChoose(null)}>
              Keep pressing
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
