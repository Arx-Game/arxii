/**
 * StandoffCard: the pre-round standoff (#4145). Per group it shows what the party has
 * learned (face-down tiles for what is still hidden, revealed cause and drives), the
 * viewer's own angles, the approaches to press, the terms to name, a Read control and
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
import type { DispatchResult } from '@/combat/types';
import type { SoulfrayWarningData } from '@/scenes/actionTypes';
import type { components } from '@/generated/api';
import { cn } from '@/lib/utils';

import { MoraleStateChip } from './MoraleStateChip';
import './standoff.css';

type StandoffView = components['schemas']['StandoffView'];
type ApproachView = components['schemas']['ApproachView'];
type GroupView = components['schemas']['GroupView'];
type TermsView = components['schemas']['TermsView'];
type DisplayTechnique = components['schemas']['DisplayTechnique'];

type Fire = (key: string, kwargs?: Record<string, unknown>) => void;
type Display = (kwargs: Record<string, unknown>) => Promise<DispatchResult | null>;

/** The Soulfray warning a refused display carries; the press may be re-sent accepting it. */
function soulfrayWarningOf(result: DispatchResult | null): SoulfrayWarningData | null {
  const warning = result?.data?.soulfray_warning;
  return warning ? (warning as SoulfrayWarningData) : null;
}

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
const ANGLE_PREFIX = 'angle:';

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
  if (focus.startsWith(ANGLE_PREFIX)) {
    return {
      group_id: groupId,
      focus_kind: 'faction_rule',
      focus_faction_rule_id: Number(focus.slice(ANGLE_PREFIX.length)),
    };
  }
  return { group_id: groupId };
}

export function StandoffCard({ standoff, encounterId, characterId }: StandoffCardProps) {
  const queryClient = useQueryClient();
  const { mutateAsync, isPending } = useDispatchPlayerAction(characterId);
  const [focusByGroup, setFocusByGroup] = useState<Record<number, string>>({});

  async function run(
    key: string,
    kwargs: Record<string, unknown> = {}
  ): Promise<DispatchResult | null> {
    try {
      const result = await mutateAsync(registryRef(key, kwargs));
      const message = result.message ?? '';
      // A Soulfray refusal is shown by the display picker, with its accept control.
      const warned = soulfrayWarningOf(result) !== null;
      if (isDispatchFailure(result)) {
        if (!warned) toast.error(message || 'That did not work.', TOAST_OPTIONS);
      } else if (message) {
        toast.success(message, TOAST_OPTIONS);
      }
      return result;
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'That did not work.');
      return null;
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

      {standoff.angles.length > 0 && (
        <div
          className="rounded-md border border-primary/40 bg-primary/10 px-3 py-2"
          data-testid="standoff-angles"
        >
          <p className="text-[10px] font-semibold uppercase tracking-wide text-primary">
            Your angle here
          </p>
          {standoff.angles.map((angle) => {
            const unread =
              (groupById.get(angle.group_id)?.revealed_faction_rules.length ?? 0) === 0;
            return (
              <div
                key={`${angle.group_id}-${angle.faction_rule_id}`}
                className="mt-1 flex flex-col items-start gap-1.5 text-sm"
              >
                <p className="min-w-0">
                  <b>{angle.text}</b>
                  {unread ? (
                    <span className="text-muted-foreground">
                      {' '}
                      How, you don&apos;t know yet. A read could tell you.
                    </span>
                  ) : null}
                </p>
                {angle.shared ? (
                  <Badge variant="secondary">Shared</Badge>
                ) : (
                  <Button
                    size="sm"
                    variant="outline"
                    disabled={isPending}
                    onClick={() =>
                      fire('standoff_share_angle', {
                        group_id: angle.group_id,
                        faction_rule_id: angle.faction_rule_id,
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

      {standoff.shared_angles.map((angle) => (
        <p
          key={`shared-${angle.group_id}-${angle.faction_rule_id}`}
          className="rounded-md border border-border bg-card px-3 py-1.5 text-sm"
        >
          {angle.text}
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
          display={(kwargs) => run('standoff_press', kwargs)}
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
  fire: Fire;
  display: Display;
}

function GroupSection({
  group,
  standoff,
  focus,
  onFocusChange,
  disabled,
  fire,
  display,
}: GroupSectionProps) {
  const approaches = standoff.approaches.filter((a) => a.group_id === group.group_id);
  const terms = standoff.terms.filter((t) => t.group_id === group.group_id);
  const angles = standoff.angles.filter((s) => s.group_id === group.group_id);
  const [chosenTermsId, setChosenTermsId] = useState<number | null>(null);
  const chosenTerms = terms.find((t) => t.terms_id === chosenTermsId) ?? null;
  const isOpen = group.state === 'open';
  const wasRead =
    group.cause !== null || group.drives.length > 0 || group.revealed_faction_rules.length > 0;
  const selectId = `standoff-focus-${group.group_id}`;

  return (
    <div className="standoff-row" data-testid="standoff-group">
      <div className="flex min-w-0 flex-col gap-2 rounded-md border border-border bg-card p-3">
        <div className="flex items-baseline justify-between gap-2">
          <span className="font-display text-sm font-semibold">{group.name}</span>
          <span className="text-xs text-muted-foreground">x{group.member_count}</span>
        </div>
        {(group.morale_state !== 'steady' || group.emboldened || group.state === 'proposed') && (
          <div className="flex flex-wrap items-center gap-1">
            <MoraleStateChip state={group.morale_state} />
            {(group.emboldened || group.state === 'proposed') && (
              <span
                data-testid="standoff-group-chip"
                className="rounded bg-destructive/15 px-1 py-0.5 text-[10px] text-destructive"
              >
                {[
                  group.emboldened ? 'emboldened' : null,
                  group.state === 'proposed' ? 'deciding' : null,
                ]
                  .filter(Boolean)
                  .join(', ')}
              </span>
            )}
          </div>
        )}

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
        {group.revealed_faction_rules.map((line) => (
          <p key={line} className="text-xs text-muted-foreground">
            {line}
          </p>
        ))}
        {group.revealed_faction_rules.length === 0 && angles.length > 0 && (
          <p className="text-xs text-muted-foreground" data-testid="standoff-matters-hint">
            Something about one of you matters to them.
          </p>
        )}
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
              {angles.map((angle) => (
                <SelectItem
                  key={angle.faction_rule_id}
                  value={`${ANGLE_PREFIX}${angle.faction_rule_id}`}
                >
                  {angle.text}
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
          <ApproachButton
            key={approach.approach_id}
            approach={approach}
            groupId={group.group_id}
            techniques={standoff.display_techniques}
            disabled={disabled || !isOpen}
            fire={fire}
            display={display}
          />
        ))}

        {terms.length > 0 && (
          <TermsSection
            terms={terms}
            ease={group.terms_ease}
            moraleState={group.morale_state}
            moraleEase={group.terms_morale_ease}
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

interface ApproachButtonProps {
  approach: ApproachView;
  groupId: number;
  techniques: DisplayTechnique[];
  disabled: boolean;
  fire: Fire;
  display: Display;
}

function ApproachButton({
  approach,
  groupId,
  techniques,
  disabled,
  fire,
  display,
}: ApproachButtonProps) {
  const [picking, setPicking] = useState(false);
  const [techniqueId, setTechniqueId] = useState<string>('');
  const [soulfray, setSoulfray] = useState<SoulfrayWarningData | null>(null);
  const needsTechnique = approach.casts_technique;
  const noTechnique = needsTechnique && techniques.length === 0;
  const refused = approach.refusal !== '';
  // A picked technique's skill joins the roll, so its own grade replaces the approach's.
  const pickedGrade = approach.technique_grades.find((g) => String(g.technique_id) === techniqueId);
  const shownGrade = pickedGrade ?? approach;
  const pressKwargs = { group_id: groupId, approach_id: approach.approach_id };

  function onPress() {
    if (needsTechnique) {
      setPicking((open) => !open);
      return;
    }
    fire('standoff_press', pressKwargs);
  }

  return (
    <div className="flex flex-col gap-1.5">
      <Button
        variant="outline"
        disabled={disabled || noTechnique || refused}
        data-testid={approach.hits_revealed_drive ? 'standoff-approach-hit' : undefined}
        className={cn(
          'h-auto w-full justify-between gap-2 whitespace-normal py-2 text-left hover:bg-muted hover:text-foreground focus-visible:ring-2',
          approach.hits_revealed_drive && 'border-accent shadow-[inset_3px_0_0_hsl(var(--accent))]'
        )}
        onClick={onPress}
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
                  lever.is_angle ? 'text-primary' : 'text-foreground'
                )}
              >
                {lever.text}
              </span>
            ))
          )}
        </span>
        <Grade value={shownGrade.grade} label={shownGrade.grade_label} />
      </Button>
      {refused && <Refusal text={approach.refusal} />}
      {noTechnique && (
        <span className="text-xs text-muted-foreground">No technique to display</span>
      )}
      {picking && needsTechnique && !noTechnique && (
        <div
          className="flex flex-col gap-1.5 rounded-md border border-primary/50 bg-primary/5 p-2"
          data-testid="standoff-technique-picker"
        >
          <Select value={techniqueId} onValueChange={setTechniqueId}>
            <SelectTrigger aria-label="Technique to display" className="h-auto min-h-8 w-full">
              <SelectValue placeholder="Choose a technique" />
            </SelectTrigger>
            <SelectContent>
              {techniques.map((t) => (
                <SelectItem key={t.technique_id} value={String(t.technique_id)}>
                  {t.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          {soulfray ? (
            <div
              data-testid="standoff-soulfray-gate"
              className={cn(
                'rounded-md border p-2',
                soulfray.has_death_risk
                  ? 'border-red-500 bg-red-950/50'
                  : 'border-amber-500 bg-amber-950/50'
              )}
            >
              <p
                className={cn(
                  'text-xs font-bold',
                  soulfray.has_death_risk ? 'text-red-400' : 'text-amber-400'
                )}
              >
                {soulfray.has_death_risk ? 'DANGER: ' : ''}Soulfray Warning: {soulfray.stage_name}
              </p>
              <p className="mb-2 text-xs text-gray-300">{soulfray.stage_description}</p>
              <div className="flex gap-2">
                <Button size="sm" variant="outline" onClick={() => setSoulfray(null)}>
                  Cancel
                </Button>
                <Button
                  size="sm"
                  disabled={disabled}
                  onClick={() => {
                    fire('standoff_press', {
                      ...pressKwargs,
                      technique_id: Number(techniqueId),
                      confirm_soulfray_risk: true,
                    });
                    setSoulfray(null);
                    setPicking(false);
                  }}
                >
                  Accept the risk
                </Button>
              </div>
            </div>
          ) : (
            <Button
              size="sm"
              disabled={disabled || techniqueId === ''}
              onClick={async () => {
                const result = await display({
                  ...pressKwargs,
                  technique_id: Number(techniqueId),
                });
                const warning = soulfrayWarningOf(result);
                if (warning) {
                  setSoulfray(warning);
                } else {
                  setPicking(false);
                }
              }}
            >
              Display
            </Button>
          )}
        </div>
      )}
    </div>
  );
}

/** Why the language gate closes an approach or terms to this character (#4373). */
function Refusal({ text }: { text: string }) {
  return (
    <span className="text-xs text-destructive" data-testid="standoff-refusal">
      {text}
    </span>
  );
}

interface TermsSectionProps {
  terms: TermsView[];
  ease: number;
  moraleState: string;
  moraleEase: number;
  disabled: boolean;
  chosen: TermsView | null;
  onChoose: (termsId: number | null) => void;
  onSpin: (terms: TermsView) => void;
}

function TermsSection({
  terms,
  ease,
  moraleState,
  moraleEase,
  disabled,
  chosen,
  onChoose,
  onSpin,
}: TermsSectionProps) {
  return (
    <div className="flex flex-col gap-1.5">
      <p className="text-xs text-muted-foreground">
        Name your terms.{' '}
        {ease === 0
          ? 'Each successful press makes this easier.'
          : `${plural(ease, 'step', 'steps')} easier so far.`}
      </p>
      {moraleEase > 0 && (
        <p className="text-xs text-muted-foreground" data-testid="standoff-terms-morale-ease">
          {moraleState === 'break' ? 'Broken' : 'Faltering'}: {moraleEase} more{' '}
          {moraleEase === 1 ? 'step' : 'steps'} easier
        </p>
      )}
      {terms.map((term) => (
        <div key={term.terms_id} className="flex flex-col gap-1">
          <Button
            variant="outline"
            disabled={disabled || term.refusal !== ''}
            aria-pressed={chosen?.terms_id === term.terms_id}
            className={cn(
              'h-auto w-full justify-between gap-2 whitespace-normal py-2 text-left hover:bg-muted hover:text-foreground focus-visible:ring-2',
              chosen?.terms_id === term.terms_id && 'border-primary'
            )}
            onClick={() => onChoose(term.terms_id)}
          >
            <span>
              {term.name}
              {term.critical_label ? (
                <span className="block text-xs text-muted-foreground">
                  On a critical: {term.critical_label}
                </span>
              ) : null}
              {term.levers.map((lever) => (
                <span key={lever.text} className="block text-xs font-normal italic">
                  {lever.text}
                </span>
              ))}
            </span>
            <Grade value={term.grade} label={term.grade_label} />
          </Button>
          {term.refusal !== '' && <Refusal text={term.refusal} />}
        </div>
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
