/**
 * Stage 10: Final Touches, the Actor's Sheet (#3621).
 *
 * Three questions about what the character does; directly under them, this
 * chapter's own offered distinctions (`ChapterOffers chapter="actors_sheet"`,
 * #3675 Task 15) - the personality-flavored ones each prompt answers, in
 * place of the retired Distinctions stage; then the goals, numbered within
 * short term and long term with the points purse at the head; who wants the
 * character to fail, a person priced by their power or a group by its reach
 * at one of four degrees, awarding CG points; and The Introductions, three
 * white journals in the character's own voice, each with a Skip door. Nothing
 * here blocks finalize. Everything is held locally and saved in one PATCH when
 * the player leaves the stage. Copy comes from CG explanation rows; the
 * in-code twins below are the fallbacks and must stay identical to the seeds
 * (`world/seeds/character_creation.py`).
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  ChapterLeaf,
  ChoiceRow,
  Entry,
  EntryDoors,
  EntryList,
  Field,
  InstrumentFrame,
  InstrumentGroup,
  Marginalia,
  Note,
  RecordRail,
} from '../folio';
import { useGoalDomains } from '../goals';
import { ChapterOffers } from './offers/ChapterOffers';
import { useCGExplanations, useUpdateDraft } from '../queries';
import type {
  CharacterDraft,
  DraftEnemy,
  DraftGoal,
  DraftIntroductions,
  EnemyOffer,
  GoalHorizon,
} from '../types';
import { Stage } from '../types';

interface FinalTouchesStageProps {
  draft: CharacterDraft;
  onRegisterBeforeLeave?: (check: () => Promise<boolean>) => (() => void) | void;
}

interface KeyedGoal {
  key: number;
  goal: DraftGoal;
}

const BASE_GOAL_POINTS = 30;

/** The three questions, in order: draft_data key, copy key stem, fallback prompt, example. */
const QUESTIONS: ReadonlyArray<{
  key: 'never_do' | 'protect' | 'fear';
  copy: string;
  prompt: string;
  example: string;
}> = [
  {
    key: 'never_do',
    copy: 'finaltouches_never_do',
    prompt: 'What would you never do?',
    example: 'Ex. Betray a secret. Break a vow. Make a pun.',
  },
  {
    key: 'protect',
    copy: 'finaltouches_protect',
    prompt: 'What would you protect at all costs?',
    example: 'Ex. Family. Party members. My fortune. My stunning good looks.',
  },
  {
    key: 'fear',
    copy: 'finaltouches_fear',
    prompt: 'What are you deathly afraid of?',
    example:
      'Ex. Being trapped in an unending boring conversation. Drowning. Social ruin. Turtles.',
  },
];

const HORIZONS: ReadonlyArray<{ value: GoalHorizon; copy: string; label: string }> = [
  { value: 'short_term', copy: 'finaltouches_short_term_heading', label: 'Short term goals' },
  { value: 'long_term', copy: 'finaltouches_long_term_heading', label: 'Long term goals' },
];

/** The four degrees, in order; labels mirror `EnemyDegree` on the server. */
const DEGREES: ReadonlyArray<{ value: string; label: string; gloss: string }> = [
  { value: 'annoyed', label: 'They want you annoyed', gloss: 'Watched, followed, reminded.' },
  {
    value: 'thwarted',
    label: 'They want you thwarted',
    gloss: 'Kept from doing what you came to do.',
  },
  {
    value: 'ruined',
    label: 'They want you ruined',
    gloss: 'Name, position, friends, gone. Dead, if that is what it takes.',
  },
  {
    value: 'destroy',
    label: 'They will relentlessly try to destroy you',
    gloss: 'A nemesis. They will not stop, and they will not be quiet about it.',
  },
];

const POWER_TIERS: ReadonlyArray<{ value: string; label: string }> = [
  { value: 'quiescent', label: 'Quiescent' },
  { value: 'prospect', label: 'Prospect' },
  { value: 'potential', label: 'Potential' },
  { value: 'puissant', label: 'Puissant' },
  { value: 'true', label: 'True' },
  { value: 'grand', label: 'Grand' },
];

const REACH_LABELS: Record<string, string> = {
  household: 'A household',
  house: 'A house or company',
  society: 'A society or church',
  realm: 'A realm',
};

// PLACEHOLDER: Apostate rewrite
const HOW_GOALS_WORK =
  'take points from a pool of thirty. During play a goal can be invoked to add its point ' +
  'value as a bonus to a roll, up to twice your total goal points per day. A goal with no ' +
  'points is a note to yourself. Goals are numbered as you add them, so a goal can be named ' +
  'in play. Add more, and change these, from your sheet as the character goes on.';

const ENEMY_INTRO =
  'A person or a group. Offered from your Lineage and your Beginning, or write your own. ' +
  'The price is what the world owes you for carrying them, and the worst of them mark you.';

const PUBLIC_LINE_HINT =
  "The public line. The name, the reach and the price are yours, your GM's and staff's.";

// PLACEHOLDER: Apostate rewrite
const MARK_HINT =
  "Reach is fixed by the group picked; only how badly is the player's choice. The two worst " +
  'degrees mark you with a Distinction, the way a Lineage answer can. A free-written enemy ' +
  'awards one point until staff place them.';

const SCALE_ROWS: Record<'group' | 'person', ReadonlyArray<{ value: string; label: string }>> = {
  group: [
    { value: 'household', label: 'A household' },
    { value: 'house', label: 'A house or company' },
    { value: 'society', label: 'A society or church' },
    { value: 'realm', label: 'A realm' },
  ],
  person: [
    { value: 'quiescent', label: 'Quiescent' },
    { value: 'prospect', label: 'Prospect' },
    { value: 'potential', label: 'Potential' },
    { value: 'puissant', label: 'Puissant' },
    { value: 'true', label: 'True' },
    { value: 'grand', label: 'Grand' },
  ],
};

const INTRODUCTIONS_INTRO =
  'These are optional IC introductions that can be answered IC as another way to help flesh ' +
  'out a character in their past. The First Journal is a white journal in the Great Archive, ' +
  'and would be a reference point to any other character that reads someone’s profile ' +
  'inside the Archive. Each of these count as journals mechanically, and award xp for ' +
  'writing them.';

const FIRST_JOURNAL = {
  institution: 'The Great Archive of Vellichor',
  frame:
    'The Great Archive strives to collect the stories of everyone that ever lived, and to ' +
    'record the journey of those on their Durance. In the First Journal, one responds to ' +
    'three questions in any manner they desire.',
  questions: [
    'What should the world know of you first?',
    'What is a day that made you who you are?',
    'What do you think of the City of Arx?',
  ],
};

const APPLICATION = {
  title: 'An Application to Shroudwatch Academy',
  frame:
    'All throughout the continent of Catenys, all who have their Glimpse and many who just ' +
    'hope for it perform a ritual to write an application to Shroudwatch Academy, burn it, ' +
    'and hope one day to receive word. Alarmingly, some people receive answers to ' +
    'applications they never recall writing at all, even if it seems exactly what they might ' +
    'have written.',
  questions: [
    'What dost thou hope to become?',
    'What are thy talents?',
    'What drives thee to distraction?',
  ],
};

const WHISPERS = {
  title: 'The Whispers - Rumors of Deeds and Misdeeds',
  frame:
    'Rumors of note about the character, and what they consider vile slander and what might ' +
    'be pleasant hyperbole.',
};

const EMPTY_INTRODUCTIONS: DraftIntroductions = {
  first_journal: ['', '', ''],
  application: ['', '', ''],
  whispers: '',
};

function announceText(remaining: number): string {
  return remaining < 0 ? `${Math.abs(remaining)} points over.` : `${remaining} points remain.`;
}

function priceFor(
  tables: CharacterDraft['enemy_price_tables'],
  kind: 'person' | 'group',
  scale: string,
  degree: string
): number {
  return tables[kind]?.[scale]?.[degree] ?? 1;
}

function awardLabel(points: number): string {
  return `Awards ${points} CG ${points === 1 ? 'point' : 'points'}`;
}

/** Which offer the draft's enemy pick is, if any (by kind, group id and name). */
function offerFor(enemy: DraftEnemy | null, offers: EnemyOffer[]): EnemyOffer | undefined {
  if (!enemy) return undefined;
  return offers.find(
    (o) =>
      o.kind === enemy.kind &&
      (enemy.organization_id !== null
        ? o.organization_id === enemy.organization_id &&
          (o.kind === 'group' || o.name === enemy.name)
        : o.organization_id === null && o.name === enemy.name)
  );
}

export function FinalTouchesStage({ draft, onRegisterBeforeLeave }: FinalTouchesStageProps) {
  const { data: domains, isLoading: domainsLoading, error: domainsError } = useGoalDomains();
  const updateDraft = useUpdateDraft();
  const { data: copy } = useCGExplanations();
  const draftData = draft.draft_data;

  // --- local state: the three answers, the goals, the enemy, the Introductions -------
  const [answers, setAnswers] = useState<Record<'never_do' | 'protect' | 'fear', string>>({
    never_do: draftData.never_do ?? '',
    protect: draftData.protect ?? '',
    fear: draftData.fear ?? '',
  });
  const keyCounterRef = useRef(0);
  const [keyedGoals, setKeyedGoals] = useState<KeyedGoal[]>(() =>
    (draftData.goals ?? []).map((goal) => ({
      key: keyCounterRef.current++,
      goal: { ...goal, horizon: goal.horizon ?? 'short_term' },
    }))
  );
  const [enemy, setEnemy] = useState<DraftEnemy | null>(draftData.enemy ?? null);
  const [enemyKind, setEnemyKind] = useState<'person' | 'group'>(draftData.enemy?.kind ?? 'group');
  const [intros, setIntros] = useState<DraftIntroductions>({
    ...EMPTY_INTRODUCTIONS,
    ...(draftData.introductions ?? {}),
  });
  const [openIntros, setOpenIntros] = useState<Record<string, boolean>>(() => ({
    first_journal: (draftData.introductions?.first_journal ?? []).some((a) => a.trim() !== ''),
    application: (draftData.introductions?.application ?? []).some((a) => a.trim() !== ''),
    whispers: (draftData.introductions?.whispers ?? '').trim() !== '',
  }));
  const [announce, setAnnounce] = useState('');

  const goals = useMemo(() => keyedGoals.map((kg) => kg.goal), [keyedGoals]);
  const usedPoints = goals.reduce((sum, g) => sum + g.points, 0);
  const remaining = BASE_GOAL_POINTS - usedPoints;

  // --- save on leave -------------------------------------------------------------
  const payloadRef = useRef({ answers, goals, enemy, intros });
  payloadRef.current = { answers, goals, enemy, intros };
  const hasChangesRef = useRef(false);
  useEffect(() => {
    const current = JSON.stringify(payloadRef.current);
    const server = JSON.stringify({
      answers: {
        never_do: draftData.never_do ?? '',
        protect: draftData.protect ?? '',
        fear: draftData.fear ?? '',
      },
      goals: (draftData.goals ?? []).map((g) => ({ ...g, horizon: g.horizon ?? 'short_term' })),
      enemy: draftData.enemy ?? null,
      intros: { ...EMPTY_INTRODUCTIONS, ...(draftData.introductions ?? {}) },
    });
    hasChangesRef.current = current !== server;
  }, [answers, goals, enemy, intros, draftData]);

  const save = useCallback(async () => {
    if (!hasChangesRef.current) return true;
    const { answers: a, goals: g, enemy: e, intros: i } = payloadRef.current;
    try {
      await updateDraft.mutateAsync({
        draftId: draft.id,
        data: { draft_data: { ...a, goals: g, enemy: e, introductions: i } },
      });
      hasChangesRef.current = false;
      return true;
    } catch (error) {
      console.error('[FinalTouches] Auto-save failed:', error);
      return window.confirm('Failed to save this stage. Discard changes and continue anyway?');
    }
  }, [draft.id, updateDraft]);

  useEffect(() => {
    if (!onRegisterBeforeLeave) return;
    return onRegisterBeforeLeave(save) ?? undefined;
  }, [onRegisterBeforeLeave, save]);

  // --- goals ----------------------------------------------------------------------
  const applyGoals = (next: KeyedGoal[]) => {
    setKeyedGoals(next);
    const used = next.reduce((sum, kg) => sum + kg.goal.points, 0);
    setAnnounce(announceText(BASE_GOAL_POINTS - used));
  };
  const goalsFor = (horizon: GoalHorizon) => keyedGoals.filter((kg) => kg.goal.horizon === horizon);
  const addGoal = (horizon: GoalHorizon) => {
    const domainId = (domains ?? [])[0]?.id ?? 0;
    applyGoals([
      ...keyedGoals,
      {
        key: keyCounterRef.current++,
        goal: { domain_id: domainId, notes: '', points: 0, horizon },
      },
    ]);
  };
  const patchGoal = (key: number, patch: Partial<DraftGoal>) =>
    applyGoals(
      keyedGoals.map((kg) => (kg.key === key ? { key, goal: { ...kg.goal, ...patch } } : kg))
    );
  const removeGoal = (key: number) => applyGoals(keyedGoals.filter((kg) => kg.key !== key));

  // --- enemy ----------------------------------------------------------------------
  const offers = draft.enemy_offers ?? [];
  const chosenOffer = offerFor(enemy, offers);
  const visibleOffers = offers.filter((o) => o.kind === enemyKind);
  const writtenOwn = enemy !== null && enemy.kind === enemyKind && !chosenOffer;
  let scale = '';
  if (enemy) {
    scale = enemy.kind === 'group' ? (chosenOffer?.reach ?? '') : enemy.power_tier;
  }
  const priceAt = (degree: string) =>
    scale
      ? priceFor(draft.enemy_price_tables ?? { group: {}, person: {} }, enemyKind, scale, degree)
      : 1;
  const chooseOffer = (offer: EnemyOffer) =>
    setEnemy({
      kind: offer.kind,
      organization_id: offer.organization_id,
      name: offer.name,
      power_tier: offer.kind === 'person' ? offer.power_tier || (enemy?.power_tier ?? '') : '',
      degree: enemy?.degree ?? '',
      why: enemy?.why ?? '',
      public_line: enemy?.public_line ?? '',
    });
  const writeOwn = () =>
    setEnemy({
      kind: enemyKind,
      organization_id: null,
      name: '',
      power_tier: '',
      degree: enemy?.degree ?? '',
      why: enemy?.why ?? '',
      public_line: enemy?.public_line ?? '',
    });
  const patchEnemy = (patch: Partial<DraftEnemy>) =>
    setEnemy((prev) => (prev ? { ...prev, ...patch } : prev));
  const enemyLine =
    enemy && enemy.degree && (enemy.name || chosenOffer)
      ? `${DEGREES.find((d) => d.value === enemy.degree)?.label ?? enemy.degree}: ${
          chosenOffer?.name ?? enemy.name
        }`
      : undefined;
  const enemyAward = enemy && enemy.degree ? priceAt(enemy.degree) : 0;

  // --- introductions ----------------------------------------------------------------
  const firstJournalOffered = draft.introductions_offered?.first_journal ?? false;
  const firstName = draftData.first_name || 'Your';
  const setIntroAnswer = (kind: 'first_journal' | 'application', index: number, value: string) =>
    setIntros((prev) => {
      const next = [...prev[kind]];
      next[index] = value;
      return { ...prev, [kind]: next };
    });
  const toggleIntro = (kind: string) => setOpenIntros((prev) => ({ ...prev, [kind]: !prev[kind] }));

  if (domainsLoading) {
    return (
      <p className="ledger-line" aria-busy="true">
        Loading goal domains…
      </p>
    );
  }
  if (domainsError) {
    return <p className="ledger-line">The goal domains could not be read. Try again.</p>;
  }

  const rail = (
    <>
      <RecordRail
        rows={[
          { label: 'Origin', value: draft.selected_area?.name },
          { label: 'Path', value: draft.selected_path?.name },
          {
            label: 'Goals',
            value: `${goals.length} goals, ${usedPoints} of ${BASE_GOAL_POINTS} points`,
          },
          {
            label: 'Enemy',
            value: enemyLine ? `${enemyLine} · ${awardLabel(enemyAward)}` : undefined,
          },
        ]}
        ledger="Stage 10 of 11"
      />
      <Marginalia id="note-finaltouches">
        <Note lead="Goals">{copy?.finaltouches_how_note ?? HOW_GOALS_WORK}</Note>
        <Note lead="Enemy">{copy?.finaltouches_enemy_public_line_hint ?? PUBLIC_LINE_HINT}</Note>
      </Marginalia>
    </>
  );

  return (
    <ChapterLeaf
      stage={Stage.FINAL_TOUCHES}
      title={copy?.finaltouches_heading ?? "Actor's Sheet"}
      intro={
        copy?.finaltouches_intro ?? 'Questions for the character, to flesh out their motivations.'
      }
      aside={rail}
    >
      <span className="vh" role="status">
        {announce}
      </span>

      {QUESTIONS.map((q) => (
        <Field
          key={q.key}
          id={`actor-${q.key}`}
          label={copy?.[`${q.copy}_prompt`] ?? q.prompt}
          hint={copy?.[`${q.copy}_example`] ?? q.example}
        >
          <textarea
            id={`actor-${q.key}`}
            rows={2}
            value={answers[q.key]}
            onChange={(e) => setAnswers((prev) => ({ ...prev, [q.key]: e.target.value }))}
          />
        </Field>
      ))}

      <ChapterOffers
        draft={draft}
        chapter="actors_sheet"
        heading={copy?.finaltouches_offers_heading ?? 'Is it a hunger'}
        headingTag={copy?.finaltouches_offers_chip ?? 'optional'}
        closedLead={copy?.finaltouches_closed_lead ?? 'Closed by your route'}
        className="conditional"
      />

      <h2 className="section-h">{copy?.finaltouches_goals_heading ?? 'Goals'}</h2>
      <InstrumentFrame
        label="Goals"
        ledger={{
          left: `${goals.length} goals`,
          right: (
            <>
              Points remaining: <b>{remaining}</b> of <b>{BASE_GOAL_POINTS}</b>
              {remaining < 0 && <>, over by {Math.abs(remaining)}</>}
            </>
          ),
          over: remaining < 0,
        }}
      >
        {HORIZONS.map((h) => (
          <InstrumentGroup key={h.value} title={copy?.[h.copy] ?? h.label}>
            {goalsFor(h.value).map((kg, index) => (
              <div className="stat-row goal-row" key={kg.key}>
                <span className="stat-name" aria-hidden="true">
                  {index + 1}.
                </span>
                <Field id={`goal-${kg.key}-notes`} label={`Goal ${index + 1}`}>
                  <input
                    id={`goal-${kg.key}-notes`}
                    type="text"
                    value={kg.goal.notes}
                    onChange={(e) => patchGoal(kg.key, { notes: e.target.value })}
                  />
                </Field>
                <Field id={`goal-${kg.key}-domain`} label="Domain">
                  <select
                    id={`goal-${kg.key}-domain`}
                    value={kg.goal.domain_id}
                    onChange={(e) => patchGoal(kg.key, { domain_id: Number(e.target.value) })}
                  >
                    {(domains ?? []).map((d) => (
                      <option key={d.id} value={d.id}>
                        {d.name}
                      </option>
                    ))}
                  </select>
                </Field>
                <Field id={`goal-${kg.key}-points`} label="Points">
                  <input
                    id={`goal-${kg.key}-points`}
                    type="number"
                    min={0}
                    max={BASE_GOAL_POINTS}
                    value={kg.goal.points}
                    onChange={(e) =>
                      patchGoal(kg.key, {
                        points: Math.max(
                          0,
                          Math.min(BASE_GOAL_POINTS, parseInt(e.target.value, 10) || 0)
                        ),
                      })
                    }
                  />
                </Field>
                <button type="button" className="btn-quiet" onClick={() => removeGoal(kg.key)}>
                  Remove
                </button>
              </div>
            ))}
            <p className="ledger-line">
              <button type="button" className="btn-small" onClick={() => addGoal(h.value)}>
                Add a goal
              </button>
            </p>
          </InstrumentGroup>
        ))}
      </InstrumentFrame>

      <h2 className="section-h">{copy?.finaltouches_enemy_heading ?? 'Who wants you to fail'}</h2>
      <p>{copy?.finaltouches_enemy_intro ?? ENEMY_INTRO}</p>
      <ChoiceRow<'person' | 'group'>
        label="Kind of enemy"
        options={[
          { value: 'person', label: 'A person' },
          { value: 'group', label: 'A group' },
        ]}
        value={enemyKind}
        onChange={(value) => {
          if (value) setEnemyKind(value);
        }}
      />
      <EntryList label="Enemies offered">
        {visibleOffers.map((offer) => {
          const chosen = chosenOffer === offer;
          return (
            <Entry
              key={`${offer.kind}-${offer.organization_id ?? 'x'}-${offer.name}`}
              name={offer.name}
              gloss={offer.why || undefined}
              tag={
                offer.kind === 'group'
                  ? `${REACH_LABELS[offer.reach] ?? offer.reach} · from your ${offer.source === 'lineage' ? 'Lineage' : 'Beginning'}`
                  : `${offer.power_tier ? POWER_TIERS.find((t) => t.value === offer.power_tier)?.label : 'Rate their power'} · from your ${offer.source === 'lineage' ? 'Lineage' : 'Beginning'}`
              }
              chosen={chosen}
              open={chosen}
            >
              <EntryDoors
                chooseLabel="Name them"
                chosen={chosen}
                onChoose={() => chooseOffer(offer)}
                onSetAside={() => setEnemy(null)}
              />
            </Entry>
          );
        })}
        <Entry
          name={enemyKind === 'group' ? 'Another group' : 'Someone else'}
          gloss="write who, and staff place them at review"
          tag="Free-written · priced at review"
          chosen={writtenOwn}
          open={writtenOwn}
        >
          <EntryDoors
            chooseLabel="Write your own"
            chosen={writtenOwn}
            onChoose={writeOwn}
            onSetAside={() => setEnemy(null)}
          />
          {writtenOwn && (
            <Field id="enemy-name" label="Who">
              <input
                id="enemy-name"
                type="text"
                value={enemy?.name ?? ''}
                onChange={(e) => patchEnemy({ name: e.target.value })}
              />
            </Field>
          )}
        </Entry>
      </EntryList>

      {enemy && enemy.kind === enemyKind && (
        <>
          {enemy.kind === 'person' && !chosenOffer?.power_tier && (
            <ChoiceRow<string>
              label="How strong they are"
              options={[...POWER_TIERS]}
              value={enemy.power_tier || null}
              onChange={(value) => patchEnemy({ power_tier: value ?? '' })}
            />
          )}
          <Field id="enemy-why" label={copy?.finaltouches_enemy_why_prompt ?? 'Why'}>
            <textarea
              id="enemy-why"
              rows={3}
              value={enemy.why}
              onChange={(e) => patchEnemy({ why: e.target.value })}
            />
          </Field>
          <div className="field">
            <label id="enemy-degree-label">
              {copy?.finaltouches_enemy_degree_prompt ?? 'How badly'}
            </label>
            <ChoiceRow<string>
              label="How badly"
              labelledBy="enemy-degree-label"
              options={DEGREES.map((d) => {
                const grant = draft.enemy_degree_grants?.[d.value];
                return {
                  value: d.value,
                  label: `${d.label} · ${awardLabel(priceAt(d.value))}${grant ? ` · grants ${grant}` : ''}`,
                  title: d.gloss,
                };
              })}
              value={enemy.degree || null}
              onChange={(value) => patchEnemy({ degree: value ?? '' })}
            />
            <span className="hint">
              {!scale && enemy.kind === 'person' ? 'Rate their power to see the price. ' : ''}
              {copy?.finaltouches_enemy_mark_hint ?? MARK_HINT}
            </span>
          </div>
          <div className="field">
            <label id="enemy-scales-label">
              {copy?.finaltouches_enemy_scales_heading ?? 'The two scales'}
            </label>
            {(['group', 'person'] as const).map((kind) => (
              <table className="price-grid" key={kind} aria-labelledby="enemy-scales-label">
                <thead>
                  <tr>
                    <th scope="col">{kind === 'group' ? 'A group' : 'A person'}</th>
                    {DEGREES.map((d) => (
                      <th scope="col" key={d.value}>
                        {d.value[0].toUpperCase() + d.value.slice(1)}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {SCALE_ROWS[kind].map((row) => (
                    <tr key={row.value}>
                      <th scope="row">{row.label}</th>
                      {DEGREES.map((d) => {
                        const on =
                          enemy.kind === kind && scale === row.value && enemy.degree === d.value;
                        return (
                          <td key={d.value} className={on ? 'on' : undefined}>
                            {priceFor(draft.enemy_price_tables, kind, row.value, d.value)}
                          </td>
                        );
                      })}
                    </tr>
                  ))}
                </tbody>
              </table>
            ))}
          </div>
          <Field
            id="enemy-public-line"
            label={copy?.finaltouches_enemy_public_line_prompt ?? 'As the sheet will say it'}
            hint={copy?.finaltouches_enemy_public_line_hint ?? PUBLIC_LINE_HINT}
          >
            <input
              id="enemy-public-line"
              type="text"
              value={enemy.public_line}
              onChange={(e) => patchEnemy({ public_line: e.target.value })}
            />
          </Field>
        </>
      )}

      <h2 className="section-h">{copy?.introductions_heading ?? 'The Introductions'}</h2>
      <p>{copy?.introductions_intro ?? INTRODUCTIONS_INTRO}</p>

      {firstJournalOffered && (
        <IntroductionBlock
          id="first_journal"
          title={`${firstName}'s First Journal`}
          institution={copy?.first_journal_institution ?? FIRST_JOURNAL.institution}
          frame={copy?.first_journal_frame ?? FIRST_JOURNAL.frame}
          open={openIntros.first_journal}
          onToggle={() => toggleIntro('first_journal')}
        >
          {FIRST_JOURNAL.questions.map((question, index) => (
            <Field
              key={question}
              id={`first-journal-${index}`}
              label={copy?.[`first_journal_q${index + 1}`] ?? question}
            >
              <textarea
                id={`first-journal-${index}`}
                rows={3}
                value={intros.first_journal[index] ?? ''}
                onChange={(e) => setIntroAnswer('first_journal', index, e.target.value)}
              />
            </Field>
          ))}
        </IntroductionBlock>
      )}

      <IntroductionBlock
        id="application"
        title={copy?.application_title ?? APPLICATION.title}
        frame={copy?.application_frame ?? APPLICATION.frame}
        open={openIntros.application}
        onToggle={() => toggleIntro('application')}
      >
        {APPLICATION.questions.map((question, index) => (
          <Field
            key={question}
            id={`application-${index}`}
            label={copy?.[`application_q${index + 1}`] ?? question}
          >
            <textarea
              id={`application-${index}`}
              rows={3}
              value={intros.application[index] ?? ''}
              onChange={(e) => setIntroAnswer('application', index, e.target.value)}
            />
          </Field>
        ))}
      </IntroductionBlock>

      <IntroductionBlock
        id="whispers"
        title={copy?.whispers_title ?? WHISPERS.title}
        frame={copy?.whispers_frame ?? WHISPERS.frame}
        open={openIntros.whispers}
        onToggle={() => toggleIntro('whispers')}
      >
        <Field
          id="whispers-text"
          label="One rumor per line"
          hint="Each line becomes a rumor the city can overhear at its social hubs, and that you or anyone else can spread or hush."
        >
          <textarea
            id="whispers-text"
            rows={4}
            value={intros.whispers}
            onChange={(e) => setIntros((prev) => ({ ...prev, whispers: e.target.value }))}
          />
        </Field>
      </IntroductionBlock>
    </ChapterLeaf>
  );
}

interface IntroductionBlockProps {
  id: string;
  title: string;
  institution?: string;
  frame: string;
  open: boolean;
  onToggle: () => void;
  children: React.ReactNode;
}

/** One Introduction: its title, its frame, and a Skip door that folds the questions away. */
function IntroductionBlock({
  id,
  title,
  institution,
  frame,
  open,
  onToggle,
  children,
}: IntroductionBlockProps) {
  return (
    <section className="introduction" aria-labelledby={`intro-${id}-title`}>
      <div className="entry-act">
        <h3 className="section-h" id={`intro-${id}-title`}>
          {title}
          {institution && <small> · {institution}</small>}
        </h3>
        <button type="button" className="btn-small" aria-pressed={!open} onClick={onToggle}>
          {open ? 'Skip' : 'Write it'}
        </button>
      </div>
      <p className="hint">{frame}</p>
      {open && children}
    </section>
  );
}
