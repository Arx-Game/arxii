/**
 * The life as grids by stage (#4395, the beats library of #4124).
 *
 * One block per stage the Beginning offers (a struck stage is simply absent); each beat
 * is a grid of its answers, the `backgrounds` chapter's offers for that beat through
 * `ChapterOffers`, picked straight from the cards: a one-of beat swaps, an age-scaled
 * beat allows one more per decade (its allowance comes with the entry), any-that-apply
 * takes any. A line of the player's own sits under a beat once something is picked, and
 * the unknown mark keeps the beat while closing its answers.
 *
 * The draft's state per beat lives at `draft_data.beats[<beat_id>]`; the whole map is
 * sent on every change (the server merges `draft_data` by top-level key), and the
 * `backgrounds` offers are refetched after, since an unknown mark is what closes a
 * beat's answers.
 */

import { useQueryClient } from '@tanstack/react-query';
import { useMemo } from 'react';
import { useDraftDistinctions } from '@/hooks/useDistinctions';
import { characterCreationKeys, useDraftBeats, useUpdateDraft } from '../../queries';
import {
  LIFE_GRID_LABELS,
  LIFE_STAGE_ORDER,
  type BeatPoolEntry,
  type CGExplanations,
  type CharacterDraft,
  type DraftBeatState,
} from '../../types';
import { ChapterOffers } from '../offers/ChapterOffers';

interface Props {
  draft: CharacterDraft;
  copy: CGExplanations | undefined;
}

/** The pick line beside a beat's name: one, any, or the allowance the years lived give. */
function pickLine(beat: BeatPoolEntry, copy: CGExplanations | undefined): string {
  if (beat.allowance === null) return copy?.beats_pick_any ?? 'pick any';
  if (beat.allowance === 1) return copy?.beats_pick_one ?? 'pick one';
  return (copy?.beats_pick_up_to ?? 'pick up to {n}; an older character takes more').replace(
    '{n}',
    String(beat.allowance)
  );
}

export function LifeGrids({ draft, copy }: Props) {
  const { data: beats, isLoading } = useDraftBeats(draft.id);
  const { data: draftDistinctions } = useDraftDistinctions(draft.id);
  const updateDraft = useUpdateDraft();
  const queryClient = useQueryClient();

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

  const picked = useMemo(() => {
    const ids = new Set<number>();
    for (const entry of draftDistinctions ?? []) {
      if (entry.rank > 0) for (const id of entry.offer_ids) if (typeof id === 'number') ids.add(id);
    }
    return ids;
  }, [draftDistinctions]);

  if (isLoading || !beats || beats.length === 0) return null;

  const states = draft.draft_data.beats ?? {};

  const save = async (next: Record<string, DraftBeatState>) => {
    await updateDraft.mutateAsync({ draftId: draft.id, data: { draft_data: { beats: next } } });
    await queryClient.invalidateQueries({ queryKey: characterCreationKeys.draftBeats(draft.id) });
    await queryClient.invalidateQueries({
      queryKey: characterCreationKeys.draftOffers(draft.id, 'backgrounds'),
    });
  };
  const patch = (beat: BeatPoolEntry, change: DraftBeatState) => {
    const next: Record<string, DraftBeatState> = { ...states };
    const key = String(beat.beat_id);
    next[key] = { ...(next[key] ?? {}), ...change };
    void save(next);
  };

  const hasPick = (beat: BeatPoolEntry) => beat.answer_offer_ids.some((id) => picked.has(id));
  const takenCount = beats.filter((b) => b.taken || hasPick(b)).length;
  const budget = draft.cg_points_spent + draft.cg_points_remaining;
  const foot = (copy?.beats_foot ?? '{taken} taken, {spent} of {budget} points spent')
    .replace('{taken}', String(takenCount))
    .replace('{spent}', String(draft.cg_points_spent))
    .replace('{budget}', String(budget));

  return (
    <div className="life">
      {LIFE_STAGE_ORDER.map((stage) => {
        const pool = byStage.get(stage) ?? [];
        if (pool.length === 0) return null;
        const label = LIFE_GRID_LABELS[stage] ?? stage;
        return (
          <section key={stage} className="life-stage" aria-label={label}>
            <h3 className="section-h">{copy?.[`life_${stage}_heading`] ?? label}</h3>
            {pool.map((beat) => {
              const lineLabel = (copy?.beats_line_label ?? '{name}, in your words').replace(
                '{name}',
                beat.name
              );
              return (
                <article key={beat.beat_id} className="life-beat" aria-label={beat.name}>
                  <div className="stage-h">
                    <h4 className="section-h">{beat.name}</h4>
                    {!beat.unknown && <span className="pick">{pickLine(beat, copy)}</span>}
                  </div>
                  <p className="beat-prompt">{beat.prompt}</p>
                  {!beat.unknown && (
                    <ChapterOffers
                      draft={draft}
                      chapter="backgrounds"
                      filter={(o) => o.opener_key === `beat:${beat.beat_id}`}
                      showOpener={false}
                      showClosed={false}
                      firstLook={false}
                      layout="grid"
                      exclusive={beat.allowance === 1}
                      maxPicks={beat.allowance}
                      syncErrorHint={copy?.offers_sync_error}
                      wordPerRank={copy?.offers_word_per_rank}
                      wordSpent={copy?.offers_word_spent}
                      wordAwards={copy?.offers_word_awards}
                    />
                  )}
                  {!beat.unknown && (hasPick(beat) || beat.line) && (
                    <div className="field">
                      <label htmlFor={`beat-${beat.beat_id}-line`}>{lineLabel}</label>
                      <input
                        id={`beat-${beat.beat_id}-line`}
                        type="text"
                        maxLength={200}
                        defaultValue={beat.line}
                        onBlur={(e) => {
                          if (e.target.value !== beat.line) patch(beat, { line: e.target.value });
                        }}
                      />
                    </div>
                  )}
                  <div className="beat-foot">
                    <button
                      type="button"
                      className="entry-mark"
                      aria-pressed={beat.unknown}
                      aria-label={`${copy?.beats_unknown_word ?? 'Unknown'}: ${beat.name}`}
                      onClick={() => patch(beat, { unknown: !beat.unknown })}
                    >
                      <span className="mark-box" aria-hidden="true">
                        {beat.unknown ? '\u2713' : ''}
                      </span>
                      {copy?.beats_unknown_word ?? 'Unknown'}
                    </button>
                  </div>
                </article>
              );
            })}
          </section>
        );
      })}
      <div className="life-foot">
        <span>{foot}</span>
      </div>
    </div>
  );
}
