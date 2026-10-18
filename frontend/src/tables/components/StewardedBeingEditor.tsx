/**
 * StewardedBeingEditor (#4333 slice 4): the table GM writes a stewarded
 * being's pledge types and its answers, tier by tier.
 *
 * The same fields and tier limits as the staff Answer builder: fact text and a
 * fact clue on Success and Critical Success only; a follow-up clue on Partial
 * Success and above. Clues come only from the being's catalogue (the clues its
 * answers already link; staff create clues). Cost pools are picked from the
 * existing list.
 */

import { useEffect, useMemo, useState } from 'react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import {
  useSaveAnswer,
  useSavePledge,
  useSaveSacrificeLine,
  useStewardAnswers,
} from '../beingsQueries';
import type { StewardAnswer, StewardedBeing, StewardPledge } from '../types';

const FACT_MIN_LEVEL = 1;
const FOLLOW_UP_MIN_LEVEL = 0;
const NEW_PLEDGE = 'new';

const selectClass = 'h-9 w-full rounded-md border border-input bg-transparent px-3 text-sm';

function Field({
  label,
  children,
  rule,
}: {
  label: string;
  children: React.ReactNode;
  rule?: string;
}) {
  return (
    <label className="grid gap-1 text-sm">
      <span className="font-medium">{label}</span>
      {children}
      {rule && (
        <span className="text-xs text-muted-foreground">
          <b>Rule:</b> {rule}
        </span>
      )}
    </label>
  );
}

function ErrorLine({ error }: { error: Error | null }) {
  if (!error) return null;
  return (
    <p role="alert" className="text-sm text-destructive">
      {error.message}
    </p>
  );
}

// ---------------------------------------------------------------------------
// Pledge type
// ---------------------------------------------------------------------------

function PledgeForm({
  being,
  pledge,
  onSaved,
}: {
  being: StewardedBeing;
  pledge: StewardPledge | null;
  onSaved: (id: number) => void;
}) {
  const save = useSavePledge();
  const [name, setName] = useState(pledge?.name ?? '');
  const [description, setDescription] = useState(pledge?.description ?? '');
  const [target, setTarget] = useState(String(pledge?.favor_target ?? 10));
  const [weeks, setWeeks] = useState(String(pledge?.span_weeks ?? 1));
  const [rite, setRite] = useState(
    String(pledge?.closing_rite ?? being.closing_rites[0]?.id ?? '')
  );

  return (
    <form
      aria-label="Pledge type"
      className="space-y-3"
      onSubmit={(e) => {
        e.preventDefault();
        save.mutate(
          {
            pledgeId: pledge?.id,
            body: {
              being: being.id,
              name: name.trim(),
              description,
              favor_target: Number(target),
              span_weeks: Number(weeks),
              closing_rite: Number(rite),
            },
          },
          { onSuccess: (row) => onSaved(row.id) }
        );
      }}
    >
      <h3 className="font-semibold">Pledge type</h3>
      <Field label="Name">
        <Input value={name} onChange={(e) => setName(e.target.value)} />
      </Field>
      <Field label="Description">
        <Textarea value={description} onChange={(e) => setDescription(e.target.value)} />
      </Field>
      <div className="flex flex-wrap items-center gap-2 text-sm">
        <label htmlFor={`target-${being.id}`} className="font-medium">
          Favor target
        </label>
        <Input
          id={`target-${being.id}`}
          className="w-20"
          type="number"
          min={1}
          value={target}
          onChange={(e) => setTarget(e.target.value)}
        />
        <label htmlFor={`weeks-${being.id}`} className="text-muted-foreground">
          within
        </label>
        <Input
          id={`weeks-${being.id}`}
          className="w-16"
          type="number"
          min={1}
          value={weeks}
          onChange={(e) => setWeeks(e.target.value)}
        />
        <span className="text-muted-foreground">
          {Number(weeks) === 1 ? 'game week' : 'game weeks'}
        </span>
      </div>
      <Field label="Closing rite">
        <select className={selectClass} value={rite} onChange={(e) => setRite(e.target.value)}>
          {being.closing_rites.map((row) => (
            <option key={row.id} value={String(row.id)}>
              {row.name}
            </option>
          ))}
        </select>
      </Field>
      <div className="flex justify-end">
        <Button type="submit" disabled={save.isPending || !name.trim() || !rite}>
          Save pledge type
        </Button>
      </div>
      <ErrorLine error={save.error} />
    </form>
  );
}

// ---------------------------------------------------------------------------
// Answer at one tier
// ---------------------------------------------------------------------------

interface AnswerDraft {
  delay_text: string;
  answer_text: string;
  fact_text: string;
  fact_clue: string;
  cost_text: string;
  cost_pool: string;
  follow_up_text: string;
  follow_up_clue: string;
  onlooker_line: string;
}

function draftOf(answer: StewardAnswer | undefined): AnswerDraft {
  return {
    delay_text: answer?.delay_text ?? '',
    answer_text: answer?.answer_text ?? '',
    fact_text: answer?.fact_text ?? '',
    fact_clue: answer?.fact_clue ? String(answer.fact_clue) : '',
    cost_text: answer?.cost_text ?? '',
    cost_pool: answer?.cost_pool ? String(answer.cost_pool) : '',
    follow_up_text: answer?.follow_up_text ?? '',
    follow_up_clue: answer?.follow_up_clue ? String(answer.follow_up_clue) : '',
    onlooker_line: answer?.onlooker_line ?? '',
  };
}

function AnswerForm({
  being,
  pledgeId,
  tier,
  answer,
}: {
  being: StewardedBeing;
  pledgeId: number;
  tier: StewardedBeing['outcome_tiers'][number];
  answer: StewardAnswer | undefined;
}) {
  const save = useSaveAnswer();
  const saveLine = useSaveSacrificeLine();
  const [draft, setDraft] = useState<AnswerDraft>(() => draftOf(answer));
  const [lines, setLines] = useState<Record<number, string>>({});
  useEffect(() => {
    setDraft(draftOf(answer));
    setLines(
      Object.fromEntries((answer?.sacrifice_lines ?? []).map((line) => [line.facet, line.text]))
    );
  }, [answer, tier.id]);
  const carriesFact = tier.success_level >= FACT_MIN_LEVEL;
  const carriesFollowUp = tier.success_level >= FOLLOW_UP_MIN_LEVEL;
  const set = (key: keyof AnswerDraft) => (value: string) =>
    setDraft((current) => ({ ...current, [key]: value }));
  const clueOptions = (
    <>
      <option value="">Clue from {being.name}&apos;s catalogue</option>
      {being.catalogue_clues.map((clue) => (
        <option key={clue.id} value={String(clue.id)}>
          {clue.name}
        </option>
      ))}
    </>
  );

  function submit() {
    const body = {
      being: being.id,
      pledge: pledgeId,
      outcome_tier: tier.id,
      delay_text: draft.delay_text,
      answer_text: draft.answer_text,
      fact_text: carriesFact ? draft.fact_text : '',
      fact_clue: carriesFact && draft.fact_clue ? Number(draft.fact_clue) : null,
      cost_text: draft.cost_text,
      cost_pool: draft.cost_pool ? Number(draft.cost_pool) : null,
      follow_up_text: draft.follow_up_text,
      follow_up_clue: carriesFollowUp && draft.follow_up_clue ? Number(draft.follow_up_clue) : null,
      onlooker_line: draft.onlooker_line,
    };
    save.mutate(
      { answerId: answer?.id, body },
      {
        onSuccess: (saved) => {
          const existing = new Map(
            (answer?.sacrifice_lines ?? []).map((line) => [line.facet, line.id])
          );
          for (const facet of being.favored_facets) {
            const text = (lines[facet.id] ?? '').trim();
            if (!text) continue;
            saveLine.mutate({
              lineId: existing.get(facet.id),
              body: { answer: saved.id, facet: facet.id, text },
            });
          }
        },
      }
    );
  }

  return (
    <form
      aria-label={`Answer · ${tier.name}`}
      className="space-y-3"
      onSubmit={(e) => {
        e.preventDefault();
        submit();
      }}
    >
      <h3 className="mt-2 font-semibold">Answer · {tier.name}</h3>
      <Field label="Delay text">
        <Textarea value={draft.delay_text} onChange={(e) => set('delay_text')(e.target.value)} />
      </Field>
      <Field label="Answer text">
        <Textarea value={draft.answer_text} onChange={(e) => set('answer_text')(e.target.value)} />
      </Field>
      <Field
        label="Fact text and fact clue"
        rule="fact text and fact clue are allowed on Success and Critical Success only."
      >
        <Textarea
          disabled={!carriesFact}
          value={draft.fact_text}
          onChange={(e) => set('fact_text')(e.target.value)}
        />
        <select
          aria-label="Fact clue"
          className={selectClass}
          disabled={!carriesFact}
          value={draft.fact_clue}
          onChange={(e) => set('fact_clue')(e.target.value)}
        >
          {clueOptions}
        </select>
      </Field>
      <Field label="Cost text and cost pool">
        <Textarea value={draft.cost_text} onChange={(e) => set('cost_text')(e.target.value)} />
        <select
          aria-label="Cost pool"
          className={selectClass}
          value={draft.cost_pool}
          onChange={(e) => set('cost_pool')(e.target.value)}
        >
          <option value="">No cost pool</option>
          {being.cost_pools.map((pool) => (
            <option key={pool.id} value={String(pool.id)}>
              {pool.name}
            </option>
          ))}
        </select>
      </Field>
      <Field label="Follow-up text and follow-up clue">
        <Textarea
          value={draft.follow_up_text}
          onChange={(e) => set('follow_up_text')(e.target.value)}
        />
        <select
          aria-label="Follow-up clue"
          className={selectClass}
          disabled={!carriesFollowUp}
          value={draft.follow_up_clue}
          onChange={(e) => set('follow_up_clue')(e.target.value)}
        >
          {clueOptions}
        </select>
      </Field>
      <Field label="Onlooker line">
        <Input value={draft.onlooker_line} onChange={(e) => set('onlooker_line')(e.target.value)} />
      </Field>
      {being.favored_facets.map((facet) => (
        <Field key={facet.id} label={`Sacrifice line, ${facet.name} facet`}>
          <Input
            value={lines[facet.id] ?? ''}
            onChange={(e) => setLines((current) => ({ ...current, [facet.id]: e.target.value }))}
          />
        </Field>
      ))}
      <div className="flex justify-end">
        <Button type="submit" disabled={save.isPending || !draft.delay_text.trim()}>
          Save
        </Button>
      </div>
      <ErrorLine error={save.error ?? saveLine.error} />
    </form>
  );
}

// ---------------------------------------------------------------------------
// The editor
// ---------------------------------------------------------------------------

export function StewardedBeingEditor({
  being,
  onClose,
}: {
  being: StewardedBeing;
  onClose: () => void;
}) {
  const [pledgeKey, setPledgeKey] = useState<string>(
    being.pledges.length ? String(being.pledges[0].id) : NEW_PLEDGE
  );
  const pledge = being.pledges.find((row) => String(row.id) === pledgeKey) ?? null;
  const tiersHigh = being.outcome_tiers;
  const [tierId, setTierId] = useState<number>(
    tiersHigh.find((tier) => tier.success_level === FACT_MIN_LEVEL)?.id ?? tiersHigh[0]?.id ?? 0
  );
  const { data: answers } = useStewardAnswers(being.id);
  const answer = useMemo(
    () =>
      (answers?.results ?? []).find(
        (row) => row.pledge === pledge?.id && row.outcome_tier === tierId
      ),
    [answers, pledge?.id, tierId]
  );
  const tier = tiersHigh.find((row) => row.id === tierId);
  const covered = new Set(pledge?.covered_tiers ?? []);
  const tiersLow = [...tiersHigh].reverse();

  return (
    <div className="grid gap-4 md:grid-cols-[minmax(0,1.25fr)_minmax(0,1fr)]">
      <div className="space-y-4">
        <div className="flex flex-wrap items-center gap-2">
          <label htmlFor={`pledge-pick-${being.id}`} className="text-sm font-medium">
            Pledge type
          </label>
          <select
            id={`pledge-pick-${being.id}`}
            className={`${selectClass} w-auto`}
            value={pledgeKey}
            onChange={(e) => setPledgeKey(e.target.value)}
          >
            {being.pledges.map((row) => (
              <option key={row.id} value={String(row.id)}>
                {row.name}
              </option>
            ))}
            <option value={NEW_PLEDGE}>New pledge type</option>
          </select>
        </div>
        <PledgeForm
          key={pledgeKey}
          being={being}
          pledge={pledge}
          onSaved={(id) => setPledgeKey(String(id))}
        />
        {pledge && tier && (
          <AnswerForm being={being} pledgeId={pledge.id} tier={tier} answer={answer} />
        )}
        <div className="flex justify-end">
          <Button type="button" variant="outline" onClick={onClose}>
            Close
          </Button>
        </div>
      </div>
      <div className="space-y-4">
        {pledge && (
          <div className="space-y-2 rounded-lg border bg-card p-4">
            <b>Coverage for this pledge type</b>{' '}
            <span className="text-xs text-muted-foreground">(tiers with at least one answer)</span>
            <ul className="grid gap-1 text-sm">
              {tiersLow.map((row) => (
                <li key={row.id}>
                  <button
                    type="button"
                    className="flex w-full justify-between border-b border-dotted py-1 text-left"
                    aria-pressed={row.id === tierId}
                    onClick={() => setTierId(row.id)}
                  >
                    <span>{row.name}</span>
                    <span className={covered.has(row.id) ? 'text-primary' : 'text-destructive'}>
                      {covered.has(row.id) ? 'written' : 'not written'}
                      {row.id === tierId ? ', editing now' : ''}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          </div>
        )}
        <div className="space-y-2 rounded-lg border bg-card p-4">
          <b>{being.name}&apos;s catalogue clues</b>
          {being.catalogue_clues.length > 0 && (
            <ul className="text-sm">
              {being.catalogue_clues.map((clue) => (
                <li key={clue.id}>{clue.name}</li>
              ))}
            </ul>
          )}
          <p className="text-xs text-muted-foreground">
            <b>Rule:</b> the picker lists clues already linked from {being.name}&apos;s answers;
            staff create clues. With none linked, free text goes out without a clue.
          </p>
        </div>
      </div>
    </div>
  );
}
