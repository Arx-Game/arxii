/**
 * The life as folds (#4874, slice 9 of #4813; the beats library of #4124, the grids of
 * #4395), built against the approved demo.
 *
 * One fold per stage the Beginning offers (a struck stage is simply absent), and inside
 * it one fold per beat, a section. The page opens with every stage and every section
 * expanded (owner ruling 2026-11-16, #5160: "everything should start as expanded"), and
 * each fold opens and closes by itself: the demo's one-open-at-a-time accordion is gone.
 * A closed stage shows its heading and how many of its beats are answered, or Unknown.
 * An open section shows its beat's answers, the `backgrounds` chapter's offers through
 * `ChapterOffers` as a grid of cards, grouped under headings when the answers carry a
 * group, priced as signed numbers, every term on a card's mechanics line showing its
 * definition on hover. A closed section shows its answers, or the beat's own prompt in
 * plain text when nothing is picked. A section has no Next of its own (#5201, owner ruling
 * 2026-11-18): the fold arrow at its heading closes it, and the page's Next is the only
 * Next. The life ends on its last stage, with no count line and no paragraph of the
 * picks under it; the right-hand panel already lists the picks and the points.
 *
 * Every section's grid ends on an Amnesiac card (#5102): no cost, not a distinction,
 * its text a staff copy row. Picking it marks that one beat unknown, which drops its
 * picks and closes its other cards, so the grid then shows the Amnesiac card alone,
 * selected; picking it again brings the cards back. A stage every one of whose sections
 * is Amnesiac reads Unknown. A pick can be marked secret; on a one-of row a secret
 * pick opens the Cover story box and the next click on another card sets that card as
 * the cover (the public sheet shows it in the secret's place). A person card takes the
 * figure's name once picked. The page holds no free text about the life as a whole: the
 * Background is one box on Final Touches (#5178, owner ruling 2026-11-17), which replaced
 * the Background Notes each stage ended on and the Recent History box.
 *
 * The draft's state per beat lives at `draft_data.beats[<beat_id>]` (taken, unknown,
 * line, `secret_offer_ids`, `cover_offer_id`, `figures`); the whole map is sent on every
 * change (the server merges `draft_data` by top-level key), and the `backgrounds` offers
 * are refetched after, since an unknown mark is what closes a beat's answers. Fold state
 * is local and never saved.
 *
 * The life's choices are listed in the chapter's right-hand panel, under the "CG
 * selections" every stage shows, each pick under its stage with its signed price (#5148).
 * Every life ends on the life so far in one paragraph. A beginning that strikes every
 * stage (the Sleeper) has an empty pool; its `struck_stages_text` stands where the stage
 * rows would be, with nothing to fill in.
 */

import { useQueryClient } from '@tanstack/react-query';
import { useEffect, useMemo, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import {
  characterCreationKeys,
  useDraftBeats,
  useDraftOffers,
  useLoadDefaultLife,
  useUpdateDraft,
} from '../../queries';
import { useChapterRail } from '../../folio';
import { useShownPicks } from '../../useShownPicks';
import {
  FIGURE_NAME_MAX_LENGTH,
  LIFE_GRID_LABELS,
  LIFE_STAGE_ORDER,
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

/** The pick line beside a beat's name: the cap an age-scaled beat gives, or any; a
 * one-of row says nothing (ruled 2026-10-25: no "pick one"), and so does a beat that
 * spends career points (#4829), whose own prompt says the allowance. Printing it here
 * too said it twice (owner ruling 2026-10-29: the prompt is "the only thing we say
 * there"; #5331). The copy key `beats_pick_points` is not read. */
function pickLine(beat: BeatPoolEntry, copy: CGExplanations | undefined): string {
  if (beat.allowance === null) return copy?.beats_pick_any ?? 'pick any';
  if (beat.allowance_is_points) return '';
  if (beat.allowance === 1) return '';
  return (copy?.beats_pick_up_to ?? 'pick up to {n}; an older character takes more').replace(
    '{n}',
    String(beat.allowance)
  );
}

/** A fold set with one entry flipped: in if it was out, out if it was in. */
function flipped<T>(set: ReadonlySet<T>, item: T): Set<T> {
  const next = new Set(set);
  if (!next.delete(item)) next.add(item);
  return next;
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
  // The picks and the points on screen (#5141): a save in flight is laid over the saved
  // list, so the list of choices, the foot line and the section summaries move with the
  // click.
  const shown = useShownPicks(draft);
  const rail = useChapterRail();
  const updateDraft = useUpdateDraft();
  const queryClient = useQueryClient();
  // Fold state, never saved: the stages and the sections the player has folded on this
  // visit. Both start empty, so everything starts open (#5160).
  const [foldedStages, setFoldedStages] = useState<ReadonlySet<string>>(() => new Set());
  const [foldedBeats, setFoldedBeats] = useState<ReadonlySet<number>>(() => new Set());
  // The suggested life (#4865): loaded once when the grids first open for a beginning the
  // draft's stamp does not name. The server's stamp is the durable guard (a life the player
  // edited or cleared never reloads); the ref only stops a second call in one mount.
  const loadLife = useLoadDefaultLife(draft.id);
  const loadedForRef = useRef<number | null>(null);
  const beginningId = draft.selected_beginnings?.id ?? null;
  const loadedFor = draft.draft_data.life_loaded_for ?? null;
  const { mutate: loadMutate } = loadLife;
  useEffect(() => {
    if (isLoading || beginningId === null) return;
    if (loadedFor === beginningId || loadedForRef.current === beginningId) return;
    loadedForRef.current = beginningId;
    loadMutate();
  }, [isLoading, beginningId, loadedFor, loadMutate]);

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
    for (const pick of shown.picks) {
      if (pick.rank > 0)
        for (const id of pick.offer_ids) if (typeof id === 'number') ranks.set(id, pick.rank);
    }
    return ranks;
  }, [shown.picks]);

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
  // The Amnesiac card (#5102). Its text is the staff copy row; the default is the line
  // the stage-wide Unknown mark it replaces carried.
  const amnesiacName = copy?.life_amnesiac_name ?? 'Amnesiac';
  const amnesiacText =
    copy?.life_amnesiac_text ??
    'No idea what happened in this part of your life. No memory of it at all.';
  const beginning = draft.selected_beginnings;
  const stages = LIFE_STAGE_ORDER.filter((stage) => (byStage.get(stage) ?? []).length > 0);

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
      (copy?.life_struck_fallback ?? 'Every stage of this life is struck.')
    : '';
  if (beats.length === 0) {
    return struck ? (
      <div className="life">
        <p className="absent">{struck}</p>
      </div>
    ) : null;
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
  // With no cover chosen on a one-of row its no-cost card (Unremarkable) stands as the
  // cover; marking a secret saves it, so finalize holds what the player was shown.
  const defaultCoverOf = (beat: BeatPoolEntry): number | null => {
    const pickedIds = new Set(picksOf(beat).map((p) => p.offer.offer_id));
    const card = beat.answer_offer_ids
      .map((id) => offerById.get(id))
      .find((o) => o !== undefined && !pickedIds.has(o.offer_id) && o.cost_per_rank === 0);
    return card?.offer_id ?? null;
  };
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
    if (beat.unknown) return { text: amnesiacName, none: true, cost: 0 };
    const picks = picksOf(beat);
    if (picks.length === 0) return { text: named(beat.prompt), none: true, cost: 0 };
    return {
      text: picks.map((p) => pickText(beat, p)).join('; '),
      none: false,
      cost: picks.reduce((sum, p) => sum + p.cost, 0),
    };
  };
  const stageUnknown = (pool: BeatPoolEntry[]) => pool.length > 0 && pool.every((b) => b.unknown);

  const toggleSecret = (beat: BeatPoolEntry, offerId: number) => {
    const state = stateOf(beat);
    const current = state.secret_offer_ids ?? [];
    const next = current.includes(offerId)
      ? current.filter((id) => id !== offerId)
      : [...current, offerId];
    const saveDefault =
      next.length > 0 && isOneOf(beat) && typeof state.cover_offer_id !== 'number';
    patch(beat, {
      secret_offer_ids: next,
      ...(next.length === 0 && { cover_offer_id: null }),
      ...(saveDefault && { cover_offer_id: defaultCoverOf(beat) }),
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
  const toggleStage = (stage: string) => setFoldedStages((folded) => flipped(folded, stage));
  const toggleSection = (beat: BeatPoolEntry) =>
    setFoldedBeats((folded) => flipped(folded, beat.beat_id));
  const amnesiacCard = (beat: BeatPoolEntry) => (
    <li>
      <button
        type="button"
        className="stance amnesiac"
        aria-pressed={beat.unknown}
        onClick={() => patch(beat, { unknown: !beat.unknown })}
      >
        <span className={isOneOf(beat) ? 'dot' : 'dot sq'} />
        <span>
          <b>{amnesiacName}</b>
          <span className="g">{amnesiacText}</span>
        </span>
        <span className="price" />
      </button>
    </li>
  );

  const renderSection = (beat: BeatPoolEntry) => {
    const open = !foldedBeats.has(beat.beat_id);
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
    const defaultCover = defaultCoverOf(beat);
    return (
      <article key={beat.beat_id} className="sec" data-open={open} aria-label={beat.name}>
        <button
          type="button"
          className="sec-sum"
          id={`life-sec-${beat.beat_id}`}
          aria-expanded={open}
          onClick={() => toggleSection(beat)}
          data-testid={`sec-${beat.beat_id}`}
        >
          <span className="nm">{beat.name}</span>
          <span className="pts">
            <Signed cost={summary.cost} />
          </span>
          {/* An open section with nothing picked prints its prompt in its body; the
              line does not say it a second time (with every section open on arrival,
              #5160, that was every prompt on the page twice). */}
          {!(open && summary.none) && (
            <span className={summary.none ? 'ans none' : 'ans'}>{summary.text}</span>
          )}
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
              trailing={amnesiacCard(beat)}
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
          </div>
        )}
      </article>
    );
  };

  const renderStage = (stage: string) => {
    const pool = byStage.get(stage) ?? [];
    const label = copy?.[`life_${stage}_heading`] ?? LIFE_GRID_LABELS[stage] ?? stage;
    const open = !foldedStages.has(stage);
    const unknown = stageUnknown(pool);
    const answered = pool.filter((b) => !b.unknown && picksOf(b).length > 0).length;
    const prog = unknown
      ? (copy?.beats_unknown_word ?? 'Unknown')
      : (copy?.life_stage_progress ?? '{answered} of {total}')
          .replace('{answered}', String(answered))
          .replace('{total}', String(pool.length));
    return (
      <section key={stage} className="stage-acc" data-open={open} aria-label={label}>
        {/* The heading wraps the button: a heading may not sit inside a button. */}
        <h3 className="stage-head">
          <button
            type="button"
            className="stage-sum"
            aria-expanded={open}
            onClick={() => toggleStage(stage)}
          >
            <span className="section-h">{label}</span>
            <span className="prog">{prog}</span>
          </button>
        </h3>
        {open && <div className="stage-body">{pool.map((beat) => renderSection(beat))}</div>}
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

  // The life's choices, by life stage, each with its signed price. They stand in the
  // chapter's right-hand panel under the "CG selections" every stage shows (#5148); the
  // points line there is the panel's own, so this list prints no totals.
  const life = copy?.life_so_far_heading ?? 'Life So Far';
  const ledger = (
    <section className="ledger" aria-label={life}>
      <h2 className="rail-label">{life}</h2>
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
    </section>
  );

  return (
    <div className="leafwrap">
      <div className="life">
        <h2 className="section-h first">{copy?.life_so_far_heading ?? 'Life So Far'}</h2>
        <p className="helper">
          {named(
            copy?.life_so_far_help ??
              'In this stage, distinctions can be selected that best describe {name}’s life up to now. Advantageous distinctions grant bonuses and cost CG points, disadvantages have penalties but grant CG points.'
          )}
        </p>
        {stages.map(renderStage)}
      </div>
      {rail ? createPortal(ledger, rail) : ledger}
    </div>
  );
}
