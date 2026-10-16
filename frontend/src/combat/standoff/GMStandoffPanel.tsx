/**
 * GMStandoffPanel (#4354): the GM's view of a standoff in the combat GM tab.
 * Per group it shows the profile the players have to read out of it (cause,
 * drives, morale), the force comparison, which faction rules match whom, and
 * the Shake / Steady morale control. A pending cause proposal is decided from
 * the GM prompt queue; this panel only points at it. Edits the placement made over
 * the creature template (#4361) are marked, and each faction rule names where it
 * came from (the template, its organization, a parent, a society).
 */

import { useState } from 'react';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { useStandoffMorale } from '@/combat/queries';
import type { components } from '@/generated/api';

import { MoraleStateChip } from './MoraleStateChip';

type GMStandoffView = components['schemas']['GMStandoffView'];
type GMGroupView = components['schemas']['GMGroupView'];

/** True when the party's effective force beats the group's by the cause margin. */
function partyOutweighs(group: GMGroupView): boolean {
  return group.effective_party_force * 100 > group.group_force * (100 + group.cause_margin_percent);
}

function readLabel(rule: GMGroupView['faction_rules'][number]): string {
  if (rule.matched_by.length === 0) return '';
  return rule.revealed ? 'yes' : 'no';
}

/** The "edited here" mark beside a value a placement changed over its template. */
function EditedMark({ text = 'edited here' }: { text?: string }) {
  return <span className="font-mono text-[10px] text-violet-700 dark:text-violet-300">{text}</span>;
}

function fmt(n: number): string {
  return String(Math.round(n));
}

const MORALE_ORDER = ['steady', 'falter', 'break'] as const;
const MORALE_WORD: Record<string, string> = {
  steady: 'steady',
  falter: 'faltering',
  break: 'broken',
};

/** "moves them one state: steady to faltering", or why it cannot move. */
export function moraleStepGloss(direction: 'shake' | 'steady', state: string): string {
  const at = MORALE_ORDER.indexOf(state as (typeof MORALE_ORDER)[number]);
  const to = direction === 'shake' ? at + 1 : at - 1;
  if (at < 0 || to < 0 || to >= MORALE_ORDER.length) {
    return direction === 'shake' ? 'already broken' : 'already steady';
  }
  return `moves them one state: ${MORALE_WORD[state]} to ${MORALE_WORD[MORALE_ORDER[to]]}`;
}

function MoraleControl({ encounterId, group }: { encounterId: number; group: GMGroupView }) {
  const [direction, setDirection] = useState<'shake' | 'steady' | null>(null);
  const [reason, setReason] = useState('');
  const morale = useStandoffMorale(encounterId);

  function close() {
    setDirection(null);
    setReason('');
    morale.reset();
  }

  function submit() {
    if (direction === null || reason.trim() === '') return;
    morale.mutate(
      { group_id: group.group_id, direction, reason: reason.trim() },
      { onSuccess: close }
    );
  }

  return (
    <div className="flex flex-col gap-2">
      <div className="flex flex-wrap items-center gap-2">
        <Button type="button" size="sm" variant="outline" onClick={() => setDirection('shake')}>
          Shake
        </Button>
        <Button type="button" size="sm" variant="outline" onClick={() => setDirection('steady')}>
          Steady
        </Button>
        <span className="text-xs text-muted-foreground">one morale step, reason required</span>
      </div>
      {direction !== null && (
        <div
          className="flex flex-col gap-2 rounded-md border border-primary/50 bg-primary/5 p-2 text-sm"
          data-testid="standoff-morale-confirm"
        >
          <span className="font-semibold">
            {direction === 'shake' ? 'Shake' : 'Steady'} {group.name}
          </span>
          <Input
            aria-label="Reason (required)"
            placeholder="Reason (required)"
            value={reason}
            onChange={(e) => setReason(e.target.value)}
          />
          {morale.error && (
            <p role="alert" className="text-xs text-destructive">
              {morale.error.message}
            </p>
          )}
          <div className="flex gap-2">
            <Button
              type="button"
              size="sm"
              disabled={reason.trim() === '' || morale.isPending}
              onClick={submit}
            >
              {direction === 'shake' ? 'Shake' : 'Steady'}
            </Button>
            <Button type="button" size="sm" variant="ghost" onClick={close}>
              Cancel
            </Button>
            <span className="self-center text-xs text-muted-foreground">
              {moraleStepGloss(direction, group.morale_state)}
            </span>
          </div>
        </div>
      )}
    </div>
  );
}

function GroupBox({ encounterId, group }: { encounterId: number; group: GMGroupView }) {
  const total = group.effective_party_force + group.group_force;
  const partyPct = total > 0 ? (group.effective_party_force / total) * 100 : 50;
  return (
    <div
      className="flex min-w-0 flex-col gap-2 rounded-md border border-border bg-card p-3"
      data-testid="gm-standoff-group"
    >
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <span className="font-display text-sm font-semibold">{group.name}</span>
        <span className="flex flex-wrap items-center gap-1 text-xs text-muted-foreground">
          {group.state === 'proposed' && (
            <span className="rounded bg-violet-500/15 px-1 py-0.5 text-[10px] text-violet-700 dark:text-violet-300">
              proposed
            </span>
          )}
          {group.emboldened_bands > 0 && (
            <span className="rounded bg-destructive/15 px-1 py-0.5 text-[10px] text-destructive">
              emboldened
            </span>
          )}
          <MoraleStateChip state={group.morale_state} />
          <span>
            {group.is_named_npc ? 'named NPC' : `x${group.member_count}`} · {group.state}
          </span>
        </span>
      </div>

      <dl className="grid grid-cols-[max-content_minmax(0,1fr)] gap-x-3 gap-y-1 text-[13px]">
        <dt className="text-muted-foreground">Cause</dt>
        <dd>
          <b>{group.cause}</b>{' '}
          {group.cause_fires ? (
            <span className="text-xs text-destructive">fires: {group.cause_reason}</span>
          ) : (
            <span className="text-xs text-emerald-700 dark:text-emerald-300">
              holds: will not attack first
            </span>
          )}
          {group.cause_revealed && (
            <span className="text-xs text-muted-foreground"> · read by the party</span>
          )}
          {group.cause_edited && (
            <>
              {' '}
              <EditedMark />
            </>
          )}
        </dd>
        <dt className="text-muted-foreground">Drives</dt>
        <dd>
          {group.drives.length === 0
            ? 'none'
            : group.drives.map((d, i) => (
                <span key={`${d.label}-${i}`}>
                  {i > 0 && ' · '}
                  {d.label}, {d.strength}{' '}
                  {d.edited && (
                    <>
                      <EditedMark />{' '}
                    </>
                  )}
                  <span className="text-xs text-muted-foreground">
                    {d.revealed ? 'read' : 'unread'}
                  </span>
                </span>
              ))}
        </dd>
        {group.affiliation && (
          <>
            <dt className="text-muted-foreground">Affiliation</dt>
            <dd>
              {group.affiliation}{' '}
              {group.affiliation_edited && <EditedMark text="set on this line" />}
            </dd>
          </>
        )}
        <dt className="text-muted-foreground">Speaks</dt>
        <dd data-testid="gm-standoff-speaks">
          {group.speaks.length === 0 ? 'no language' : group.speaks.join(', ')}
        </dd>
        {group.regards.length > 0 && (
          <>
            <dt className="text-muted-foreground">Regard</dt>
            <dd data-testid="gm-standoff-regard">
              {group.regards.map((r, i) => (
                <span key={r.participant}>
                  {i > 0 && ' · '}
                  {r.participant}: {r.label} ({r.regard}){' '}
                  <span className="text-xs text-muted-foreground">NPC regard</span>
                </span>
              ))}
            </dd>
          </>
        )}
        <dt className="text-muted-foreground">Morale</dt>
        <dd>
          {group.members.length === 0
            ? 'none'
            : group.members.map((m, i) => (
                <span key={m.opponent_id}>
                  {i > 0 && ', '}
                  {m.name} {m.morale} ({m.morale_state})
                </span>
              ))}
        </dd>
      </dl>

      <div className="flex flex-col gap-1 text-xs">
        <span>
          Force: party {fmt(group.effective_party_force)}, them {fmt(group.group_force)}.
          {partyOutweighs(group) && ' Party outweighs them.'}
        </span>
        <div
          className="flex h-2 overflow-hidden rounded-full bg-muted"
          aria-hidden="true"
          data-testid="standoff-force-bar"
        >
          <i className="block h-full bg-primary" style={{ width: `${partyPct}%` }} />
          <i className="block h-full bg-destructive" style={{ width: `${100 - partyPct}%` }} />
        </div>
      </div>

      {group.faction_rules.length > 0 && (
        <table className="w-full border-collapse text-xs">
          <thead>
            <tr className="text-left text-[10px] uppercase tracking-wide text-muted-foreground">
              <th className="py-1 pr-2 font-medium">Faction rule</th>
              <th className="py-1 pr-2 font-medium">From</th>
              <th className="py-1 pr-2 font-medium">Matches</th>
              <th className="py-1 font-medium">Read</th>
            </tr>
          </thead>
          <tbody>
            {group.faction_rules.map((r) => (
              <tr key={r.faction_rule_id} className="border-t border-border align-top">
                <td className="py-1 pr-2">{r.label}</td>
                <td className="py-1 pr-2 text-muted-foreground">{r.source}</td>
                <td className="py-1 pr-2">
                  {r.matched_by.length > 0 ? r.matched_by.join(', ') : 'nobody'}
                </td>
                <td className="py-1">{readLabel(r)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {group.pending_prompt_id === null && group.last_decision && (
        <p className="text-xs text-muted-foreground" data-testid="standoff-last-decision">
          Last decision: {group.last_decision}
        </p>
      )}

      {group.pending_prompt_id !== null && (
        <p className="rounded-md border border-violet-500/40 bg-violet-500/10 px-2 py-1 text-xs">
          The cause fires: {group.proposal_reason} Decide it in the GM prompts.
        </p>
      )}

      {group.has_morale && <MoraleControl encounterId={encounterId} group={group} />}
    </div>
  );
}

export function GMStandoffPanel({
  encounterId,
  standoff,
}: {
  encounterId: number;
  standoff: GMStandoffView;
}) {
  return (
    <div
      className="flex flex-col gap-2 rounded-md border border-border bg-card p-3"
      data-testid="gm-standoff-panel"
    >
      <div className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
        Standoff
      </div>
      {standoff.groups.map((g) => (
        <GroupBox key={g.group_id} encounterId={encounterId} group={g} />
      ))}
      <span className="text-xs text-muted-foreground">
        In the standoff: {standoff.participants.join(', ')}.
      </span>
    </div>
  );
}
