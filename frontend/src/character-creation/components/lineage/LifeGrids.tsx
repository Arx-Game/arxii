/**
 * The life as an accordion (#4874, slice 9 of #4813; the beats library of #4124, the
 * grids of #4395), built against the approved demo.
 *
 * One fold per stage the Beginning offers (a struck stage is simply absent): a closed
 * stage shows its heading and how many of its beats are answered, or Unknown; the open
 * stage shows its sections, one open at a time, each a beat whose answers are the
 * `backgrounds` chapter's offers through `ChapterOffers` as a grid of cards, grouped
 * under headings when the answers carry a group, priced as signed numbers, every term
 * on a card's mechanics line a click that opens its definition. A closed section shows
 * its answers, or the beat's own prompt in plain text when nothing is picked. Next
 * closes a section and opens the one below; the last Next opens the next stage.
 *
 * Unknown is a mark on the stage: it sets every beat of the stage unknown in one save
 * and folds the sections away. A pick can be marked secret; on a one-of row a secret
 * pick opens the Cover story box and the next click on another card sets that card as
 * the cover (the public sheet shows it in the secret's place). A person card takes the
 * figure's name once picked. Every stage ends on Description (Optional), one paragraph
 * saved to `draft_data.stage_descriptions`.
 *
 * The draft's state per beat lives at `draft_data.beats[<beat_id>]` (taken, unknown,
 * line, `secret_offer_ids`, `cover_offer_id`, `figures`); the whole map is sent on every
 * change (the server merges `draft_data` by top-level key), and the `backgrounds` offers
 * are refetched after, since an unknown mark is what closes a beat's answers. Fold state
 * is local and never saved.
 *
 * The ledger rail beside the life lists the purse and every pick under its stage with
 * its signed price. Every life ends on the Recent History box (#4830) and the life so far
 * in one paragraph. A beginning that strikes every stage (the Sleeper) has an empty pool;
 * its `struck_stages_text` stands where the stage rows would be, over that box.
 */

import { useQueryClient } from '@tanstack/react-query';
import { useMemo, useState } from 'react';
import { useDraftDistinctions } from '@/hooks/useDistinctions';
import {
  characterCreationKeys,
  useDraftBeats,
  useDraftOffers,
  useUpdateDraft,
} from '../../queries';
import {
  FIGURE_NAME_MAX_LENGTH,
  LIFE_GRID_LABELS,
  LIFE_STAGE_ORDER,
  RECENT_HISTORY_MAX_LENGTH,
  STAGE_DESCRIPTION_MAX_LENGTH,
  type BeatPoolEntry,
  type CGExplanations,
  type CharacterDraft,
  type DraftBeatState,
  type VisibleOffer,
} from '../../types';
import { ChapterOffers } from '../offers/ChapterOffers';

interface Props {
  draft: CharacterDraft;
  copy: CGExplanations | undefined;
}

/** One pick on a beat as the summaries, the rail and the testament read it. */
interface Pick {
  offer: VisibleOffer;
  rank: number;
  secret: boolean;
  /** The points the pick moves: negative when the world pays. */
  cost: number;
}

/** The pick line beside a beat's name: the allowance the years lived give, or any; a
 * one-of row says nothing (ruled 2026-10-25: no "pick one"). */
function pickLine(beat: BeatPoolEntry, copy: CGExplanations | undefined): string {
  if (beat.allowance === null) return copy?.beats_pick_any ?? 'pick any';
  if (beat.allowance_is_points) {
    // Career points (#4829): one at nineteen, one more every five years to fifty-nine;
    // a point buys a card or a rank on one.
    return (
      copy?.beats_pick_points ?? '{n} career points: one at 19 and one more every five years, to 59'
    ).replace('{n}', String(beat.allowance));
  }
  if (beat.allowance === 1) return '';
  return (copy?.beats_pick_up_to ?? 'pick up to {n}; an older character takes more').replace(
    '{n}',
    String(beat.allowance)
  );
}

/** A signed total for a summary or the rail: `+N` when the world pays, `−N` when you do. */
function Signed({ cost }: { cost: number }) {
  if (cost === 0) return null;
  return cost < 0 ? (
    <span className="award">{`+${-cost}`}</span>
  ) : (
    <span className="cost">{`−${cost}`}</span>
  );
}

export function LifeGrids({ draft, copy }: Props) {
  const { data: beats, isLoading } = useDraftBeats(draft.id);
  const { data: offersData } = useDraftOffers(draft.id, 'backgrounds');
  const { data: draftDistinctions } = useDraftDistinctions(draft.id);
  const updateDraft = useUpdateDraft();
  const queryClient = useQueryClient();
  // Fold state (#4874), never saved: `undefined` is the default (the first stage, its
  // first section), `null` is folded shut.
  const [openStage, setOpenStage] = useState<string | null | undefined>(undefined);
  const [openBeat, setOpenBeat] = useState<number | null | undefined>(undefined);

  const byStage = useMemo(() => {
    const groups = new Map<string, BeatPoolEntry[]>();
    for (const stage of LIFE_STAGE_ORDER) groups.set(stage, []);
    for (const beat of beats ?? []) {
      const list = groups.get(beat.life_stage) ?? [];
      list.push(beat);
      groups.set(beat.life_stage, list);
    }
    return groups;
  }, [beats]);

  const rankByOffer = useMemo(() => {
    const ranks = new Map<number, number>();
    for (const entry of draftDistinctions ?? []) {
      if (entry.rank > 0)
        for (const id of entry.offer_ids) if (typeof id === 'number') ranks.set(id, entry.rank);
    }
    return ranks;
  }, [draftDistinctions]);

  const offerById = useMemo(() => {
    const map = new Map<number, VisibleOffer>();
    for (const offer of offersData?.offers ?? []) map.set(offer.offer_id, offer);
    return map;
  }, [offersData]);

  if (isLoading || !beats) return null;

  const states = draft.draft_data.beats ?? {};
  const stateOf = (beat: BeatPoolEntry): DraftBeatState => states[String(beat.beat_id)] ?? {};
  const firstName = draft.draft_data.first_name?.trim() || (copy?.life_name_fallback ?? 'you');
  const named = (text: string) => text.replace(/\{name\}/g, firstName);
  const beginning = draft.selected_beginnings;
  const stages = LIFE_STAGE_ORDER.filter((stage) => (byStage.get(stage) ?? []).length > 0);
  const currentStage = openStage === undefined ? (stages[0] ?? null) : openStage;
  const currentBeat = (stage: string): number | null => {
    const pool = byStage.get(stage) ?? [];
    if (openBeat === undefined) return pool[0]?.beat_id ?? null;
    if (openBeat !== null && pool.some((b) => b.beat_id === openBeat)) return openBeat;
    return null;
  };

  // Every stage struck (#4830, the Sleeper): the pool is empty and the beginning's own
  // text stands where the stage rows would be; until that text is authored, the mockup's
  // fallback line stands there instead. An empty pool for any other reason puts nothing
  // in their place.
  const struckAll =
    beats.length === 0 &&
    beginning !== null &&
    beginning.strikes_childhood &&
    beginning.strikes_youth &&
    beginning.strikes_adulthood;
  const struck = struckAll
    ? beginning.struck_stages_text.trim() ||
      (copy?.life_struck_fallback ??
        'Every stage of this life is struck. What there is to say begins below.')
    : '';
  const recentHistory = draft.draft_data.recent_history ?? '';
  const saveRecentHistory = (value: string) => {
    if (value === recentHistory) return;
    void updateDraft.mutateAsync({
      draftId: draft.id,
      data: { draft_data: { recent_history: value } },
    });
  };
  const recentHistoryBox = (
    <div className="field recent-history">
      <label htmlFor="recent-history">
        {copy?.life_recent_history_label ?? 'Recent History (Optional)'}
      </label>
      <textarea
        id="recent-history"
        rows={3}
        maxLength={RECENT_HISTORY_MAX_LENGTH}
        defaultValue={recentHistory}
        aria-describedby="recent-history-help"
        onBlur={(e) => saveRecentHistory(e.target.value)}
      />
      <span id="recent-history-help" className="hint">
        {copy?.life_recent_history_help ?? 'What you want a GM or another player to pick up.'}
      </span>
    </div>
  );

  if (beats.length === 0) {
    return (
      <div className="life">
        {struck && <p className="absent">{struck}</p>}
        {recentHistoryBox}
      </div>
    );
  }

  const save = async (next: Record<string, DraftBeatState>) => {
    await updateDraft.mutateAsync({ draftId: draft.id, data: { draft_data: { beats: next } } });
    await queryClient.invalidateQueries({ queryKey: characterCreationKeys.draftBeats(draft.id) });
    await queryClient.invalidateQueries({
      queryKey: characterCreationKeys.draftOffers(draft.id, 'backgrounds'),
    });
  };
  const patchBeats = (changes: Map<number, DraftBeatState>) => {
    const next: Record<string, DraftBeatState> = { ...states };
    for (const [beatId, change] of changes) {
      const key = String(beatId);
      next[key] = { ...(next[key] ?? {}), ...change };
    }
    void save(next);
  };
  const patch = (beat: BeatPoolEntry, change: DraftBeatState) =>
    patchBeats(new Map([[beat.beat_id, change]]));

  const picksOf = (beat: BeatPoolEntry): Pick[] => {
    const secret = new Set(stateOf(beat).secret_offer_ids ?? []);
    const picks: Pick[] = [];
    for (const id of beat.answer_offer_ids) {
      const rank = rankByOffer.get(id) ?? 0;
      const offer = offerById.get(id);
      if (rank > 0 && offer)
        picks.push({ offer, rank, secret: secret.has(id), cost: offer.cost_per_rank * rank });
    }
    return picks;
  };
  const isOneOf = (beat: BeatPoolEntry) => beat.allowance === 1 && !beat.allowance_is_points;
  const coverName = (beat: BeatPoolEntry): string => {
    const cover = stateOf(beat).cover_offer_id;
    if (typeof cover === 'number' && offerById.has(cover)) return offerById.get(cover)!.name;
    return isOneOf(beat)
      ? (copy?.life_cover_unremarkable ?? 'Unremarkable')
      : (copy?.life_cover_none ?? 'Nothing shown');
  };
  const pickText = (beat: BeatPoolEntry, pick: Pick): string =>
    pick.offer.name +
    (pick.offer.max_rank > 1 ? ` (rank ${pick.rank})` : '') +
    (pick.secret ? ` (${copy?.life_secret_word ?? 'secret'}; cover: ${coverName(beat)})` : '');
  const summaryOf = (beat: BeatPoolEntry): { text: string; none: boolean; cost: number } => {
    if (beat.unknown) return { text: copy?.beats_unknown_word ?? 'Unknown', none: true, cost: 0 };
    const picks = picksOf(beat);
    if (picks.length === 0) return { text: named(beat.prompt), none: true, cost: 0 };
    return {
      text: picks.map((p) => pickText(beat, p)).join('; '),
      none: false,
      cost: picks.reduce((sum, p) => sum + p.cost, 0),
    };
  };
  const stageUnknown = (pool: BeatPoolEntry[]) => pool.length > 0 && pool.every((b) => b.unknown);

  const setStageUnknown = (pool: BeatPoolEntry[], on: boolean) =>
    patchBeats(new Map(pool.map((b) => [b.beat_id, { unknown: on }])));
  const toggleSecret = (beat: BeatPoolEntry, offerId: number) => {
    const current = stateOf(beat).secret_offer_ids ?? [];
    const next = current.includes(offerId)
      ? current.filter((id) => id !== offerId)
      : [...current, offerId];
    patch(beat, {
      secret_offer_ids: next,
      ...(next.length === 0 && { cover_offer_id: null }),
    });
  };
  const setCover = (beat: BeatPoolEntry, offerId: number | null) =>
    patch(beat, { cover_offer_id: offerId });
  const setFigure = (beat: BeatPoolEntry, offerId: number, name: string) => {
    const figures = { ...(stateOf(beat).figures ?? {}) };
    if (name.trim()) figures[String(offerId)] = name.trim();
    else delete figures[String(offerId)];
    patch(beat, { figures });
  };
  const descriptions = draft.draft_data.stage_descriptions ?? {};
  const saveDescription = (stage: string, value: string) => {
    if ((descriptions[stage] ?? '') === value) return;
    void updateDraft.mutateAsync({
      draftId: draft.id,
      data: { draft_data: { stage_descriptions: { ...descriptions, [stage]: value } } },
    });
  };

  const openSection = (stage: string | null, beatId: number | null | undefined) => {
    setOpenStage(stage);
    setOpenBeat(beatId);
  };
  const toggleStage = (stage: string) =>
    currentStage === stage ? openSection(null, null) : openSection(stage, undefined);
  const next = (stage: string, beat: BeatPoolEntry) => {
    const pool = byStage.get(stage) ?? [];
    const at = pool.findIndex((b) => b.beat_id === beat.beat_id);
    if (at + 1 < pool.length) {
      openSection(stage, pool[at + 1].beat_id);
      return;
    }
    // The last Next of a stage opens the next stage on its first section; the last
    // stage's last Next folds its sections.
    const stageAt = stages.indexOf(stage);
    if (stageAt + 1 < stages.length) openSection(stages[stageAt + 1], undefined);
    else openSection(stage, null);
  };

  const takenCount = beats.filter((b) => b.taken || picksOf(b).length > 0).length;
  const budget = draft.cg_points_spent + draft.cg_points_remaining;
  // The demo's purse: the net points moved, read as Spent when positive and Gained when
  // the world paid more than it took.
  const net = draft.cg_points_spent;
  const spent = Math.max(0, net);
  const gained = Math.max(0, -net);
  const foot = (copy?.beats_foot ?? '{taken} taken, {spent} of {budget} points spent')
    .replace('{taken}', String(takenCount))
    .replace('{spent}', String(draft.cg_points_spent))
    .replace('{budget}', String(budget));
  const told = beats
    .filter((b) => !b.unknown)
    .map((b) => summaryOf(b))
    .filter((s) => !s.none)
    .map((s) => s.text);
  const unknownStages = stages
    .filter((stage) => stageUnknown(byStage.get(stage) ?? []))
    .map(
      (stage) =>
        `${copy?.[`life_${stage}_heading`] ?? LIFE_GRID_LABELS[stage] ?? stage}: ${(
          copy?.beats_unknown_word ?? 'Unknown'
        ).toLowerCase()}`
    );
  const testamentLines = [...unknownStages, ...told];

  const renderSection = (stage: string, beat: BeatPoolEntry) => {
    const open = currentBeat(stage) === beat.beat_id;
    const summary = summaryOf(beat);
    const state = stateOf(beat);
    const picks = picksOf(beat);
    const secretIds = state.secret_offer_ids ?? [];
    const coverMode = isOneOf(beat) && secretIds.length > 0;
    const cover = typeof state.cover_offer_id === 'number' ? state.cover_offer_id : null;
    const pickedIds = new Set(picks.map((p) => p.offer.offer_id));
    const line = pickLine(beat, copy);
    const interceptPick = (offer: VisibleOffer, selected: boolean): boolean => {
      if (!coverMode) return false;
      if (selected) patch(beat, { secret_offer_ids: [], cover_offer_id: null });
      else setCover(beat, cover === offer.offer_id ? null : offer.offer_id);
      return true;
    };
    const unpicked = beat.answer_offer_ids
      .map((id) => offerById.get(id))
      .filter((o): o is VisibleOffer => o !== undefined && !pickedIds.has(o.offer_id));
    // With no cover chosen the row's no-cost card (Unremarkable) stands as the cover.
    const defaultCover = unpicked.find((o) => o.cost_per_rank === 0)?.offer_id ?? null;
    return (
      <article key={beat.beat_id} className="sec" data-open={open} aria-label={beat.name}>
        <button
          type="button"
          className="sec-sum"
          aria-expanded={open}
          onClick={() => openSection(stage, open ? null : beat.beat_id)}
          data-testid={`sec-${beat.beat_id}`}
        >
          <span className="nm">{beat.name}</span>
          <span className="pts">
            <Signed cost={summary.cost} />
          </span>
          <span className={summary.none ? 'ans none' : 'ans'}>{summary.text}</span>
        </button>
        {open && (
          <div className="sec-body">
            <p className="beat-prompt">{named(beat.prompt)}</p>
            {line && <span className="pick">{line}</span>}
            <ChapterOffers
              draft={draft}
              chapter="backgrounds"
              filter={(o) => o.opener_key === `beat:${beat.beat_id}`}
              showOpener={false}
              showClosed={false}
              firstLook={false}
              layout="grid"
              exclusive={isOneOf(beat)}
              maxPicks={beat.allowance}
              pointsPicks={beat.allowance_is_points}
              groupBy={(o) => o.group}
              pricing="signed"
              terms={offersData?.terms ?? []}
              interceptPick={coverMode ? interceptPick : undefined}
              coverOfferId={coverMode ? (cover ?? defaultCover) : null}
              secretOfferIds={secretIds}
              wordSecret={copy?.life_card_secret ?? 'Secret: select a cover story below'}
              wordCover={copy?.life_cover_label ?? 'Cover story'}
              syncErrorHint={copy?.offers_sync_error}
              wordPerRank={copy?.offers_word_per_rank}
              wordSpent={copy?.offers_word_spent}
              wordAwards={copy?.offers_word_awards}
            />
            {picks.length > 0 && (
              <div className="beat-foot">
                {picks.map((pick) => (
                  <button
                    key={pick.offer.offer_id}
                    type="button"
                    className="entry-mark secret-mark"
                    aria-pressed={pick.secret}
                    onClick={() => toggleSecret(beat, pick.offer.offer_id)}
                  >
                    <span className="mark-box" aria-hidden="true">
                      {pick.secret ? '✓' : ''}
                    </span>
                    {`${copy?.life_secret_label ?? 'Secret'}: ${pick.offer.name}`}
                  </button>
                ))}
              </div>
            )}
            {coverMode && (
              <div className="field cover-box">
                <label>{copy?.life_cover_label ?? 'Cover story'}</label>
                <div className="cover-val">{coverName(beat)}</div>
                <span className="hint">
                  {copy?.life_cover_help ??
                    'A cover story is what will show on your sheet instead of your secret, without any associated penalties or bonuses. If not selected, it defaults to unremarkable. Alternately, a character can create an entirely fictitious alternate persona under Final Touches.'}
                </span>
              </div>
            )}
            {!coverMode && secretIds.length > 0 && (
              <div className="field">
                <label htmlFor={`cover-${beat.beat_id}`}>
                  {copy?.life_cover_label ?? 'Cover story'}
                </label>
                <select
                  id={`cover-${beat.beat_id}`}
                  value={cover ?? ''}
                  onChange={(e) =>
                    setCover(beat, e.target.value === '' ? null : Number(e.target.value))
                  }
                >
                  <option value="">{copy?.life_cover_none ?? 'Nothing shown'}</option>
                  {unpicked.map((o) => (
                    <option key={o.offer_id} value={o.offer_id}>
                      {o.name}
                    </option>
                  ))}
                </select>
                <span className="hint">
                  {copy?.life_cover_help ??
                    'A cover story is what will show on your sheet instead of your secret, without any associated penalties or bonuses. If not selected, it defaults to unremarkable. Alternately, a character can create an entirely fictitious alternate persona under Final Touches.'}
                </span>
              </div>
            )}
            {picks
              .filter((p) => p.offer.asks_figure_name)
              .map((pick) => (
                <div key={pick.offer.offer_id} className="field figure">
                  <label htmlFor={`figure-${pick.offer.offer_id}`}>
                    {(copy?.life_figure_label ?? '{card}: their name').replace(
                      '{card}',
                      pick.offer.name
                    )}
                  </label>
                  <input
                    id={`figure-${pick.offer.offer_id}`}
                    type="text"
                    maxLength={FIGURE_NAME_MAX_LENGTH}
                    defaultValue={state.figures?.[String(pick.offer.offer_id)] ?? ''}
                    onBlur={(e) => {
                      if (e.target.value !== (state.figures?.[String(pick.offer.offer_id)] ?? ''))
                        setFigure(beat, pick.offer.offer_id, e.target.value);
                    }}
                  />
                </div>
              ))}
            <div className="next">
              <button type="button" onClick={() => next(stage, beat)}>
                {copy?.life_next ?? 'Next'}
              </button>
            </div>
          </div>
        )}
      </article>
    );
  };

  const renderStage = (stage: string) => {
    const pool = byStage.get(stage) ?? [];
    const label = copy?.[`life_${stage}_heading`] ?? LIFE_GRID_LABELS[stage] ?? stage;
    const open = currentStage === stage;
    const unknown = stageUnknown(pool);
    const answered = pool.filter((b) => !b.unknown && picksOf(b).length > 0).length;
    const prog = unknown
      ? (copy?.beats_unknown_word ?? 'Unknown')
      : (copy?.life_stage_progress ?? '{answered} of {total}')
          .replace('{answered}', String(answered))
          .replace('{total}', String(pool.length));
    return (
      <section key={stage} className="stage-acc" data-open={open} aria-label={label}>
        <button
          type="button"
          className="stage-sum"
          aria-expanded={open}
          onClick={() => toggleStage(stage)}
        >
          {/* A heading inside a button is phrasing content, so a span carries the role. */}
          <span className="section-h" role="heading" aria-level={3}>
            {label}
          </span>
          <span className="prog">{prog}</span>
        </button>
        {open && (
          <div className="stage-body">
            <div className="beat-foot">
              <button
                type="button"
                className="entry-mark"
                aria-pressed={unknown}
                aria-label={`${copy?.beats_unknown_word ?? 'Unknown'}: ${label}`}
                onClick={() => setStageUnknown(pool, !unknown)}
              >
                <span className="mark-box" aria-hidden="true">
                  {unknown ? '✓' : ''}
                </span>
                {copy?.beats_unknown_word ?? 'Unknown'}
              </button>
              <span className="hint">
                {copy?.life_stage_unknown_help ??
                  'No idea what happened in this part of your life. No memory of it at all.'}
              </span>
            </div>
            {!unknown && pool.map((beat) => renderSection(stage, beat))}
            {!unknown && (
              <div className="field stage-description">
                <label htmlFor={`stage-desc-${stage}`}>
                  {copy?.life_stage_description_label ?? 'Description (Optional)'}
                </label>
                <textarea
                  id={`stage-desc-${stage}`}
                  rows={3}
                  maxLength={STAGE_DESCRIPTION_MAX_LENGTH}
                  defaultValue={descriptions[stage] ?? ''}
                  onBlur={(e) => saveDescription(stage, e.target.value)}
                />
              </div>
            )}
          </div>
        )}
      </section>
    );
  };

  const ledgerRows = stages.map((stage) => {
    const pool = byStage.get(stage) ?? [];
    const label = copy?.[`life_${stage}_heading`] ?? LIFE_GRID_LABELS[stage] ?? stage;
    const rows = stageUnknown(pool)
      ? [{ key: 'unknown', text: copy?.beats_unknown_word ?? 'Unknown', cost: 0 }]
      : pool.flatMap((beat) =>
          picksOf(beat).map((pick) => ({
            key: String(pick.offer.offer_id),
            text:
              pick.offer.name +
              (pick.offer.max_rank > 1 ? ` (rank ${pick.rank})` : '') +
              (pick.secret ? ` (${copy?.life_secret_word ?? 'secret'})` : ''),
            cost: pick.cost,
          }))
        );
    return { stage, label, rows };
  });

  return (
    <div className="leafwrap">
      <div className="life">
        <h2 className="section-h first">{copy?.life_so_far_heading ?? 'Life So Far'}</h2>
        <p className="helper">
          {named(
            copy?.life_so_far_help ??
              'In this stage, distinctions that can be selected that best describes {name}’s life up to now. Advantageous distinctions grant bonuses and cost CG points, disadvantages have penalties but grant CG points.'
          )}
        </p>
        {stages.map(renderStage)}
        {recentHistoryBox}
        <div className="life-foot">
          <span>{foot}</span>
        </div>
        <div className="testament">
          {testamentLines.length > 0
            ? testamentLines.map((line, i) => (
                <span key={line}>
                  {i > 0 && '. '}
                  <b>{line}</b>
                  {i === testamentLines.length - 1 && '.'}
                </span>
              ))
            : (copy?.life_testament_empty ?? 'Nothing written yet.')}
        </div>
      </div>
      <aside className="ledger" aria-label={copy?.life_ledger_heading ?? 'CG points'}>
        <h3>{copy?.life_ledger_heading ?? 'CG points'}</h3>
        <div className="tot">
          <span>{copy?.life_ledger_starting ?? 'Starting'}</span>
          <b>{budget}</b>
        </div>
        <div className="tot">
          <span>{copy?.life_ledger_spent ?? 'Spent'}</span>
          <b>{spent}</b>
        </div>
        <div className="tot">
          <span>{copy?.life_ledger_gained ?? 'Gained'}</span>
          <b>{gained}</b>
        </div>
        <div className="tot">
          <span>{copy?.life_ledger_remaining ?? 'Remaining'}</span>
          <b>{draft.cg_points_remaining}</b>
        </div>
        {ledgerRows.every((s) => s.rows.length === 0) ? (
          <p className="empty">{copy?.life_ledger_empty ?? 'Nothing chosen yet.'}</p>
        ) : (
          ledgerRows
            .filter((s) => s.rows.length > 0)
            .map((s) => (
              <div key={s.stage}>
                <div className="st">{s.label}</div>
                {s.rows.map((row) => (
                  <div key={row.key} className="row">
                    <span>{row.text}</span>
                    <span>
                      <Signed cost={row.cost} />
                    </span>
                  </div>
                ))}
              </div>
            ))
        )}
      </aside>
    </div>
  );
}
