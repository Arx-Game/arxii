/**
 * The beats of a life (#4124): the Backgrounds library as this draft meets it.
 *
 * One block per life stage. A taken beat is an entry: its prompt, its answers as the
 * `backgrounds` chapter's offers for that beat (one-of drawn across, any-that-apply
 * drawn down, through `ChapterOffers`), one optional line, and the unknown mark; the
 * stage's untaken beats sit under it as "add" buttons. Nothing is required: a stage
 * with nothing taken is a quiet one. A Beginning that keeps a beat (`kept`) shows it
 * without a remove.
 *
 * The draft's state per beat lives at `draft_data.beats[<beat_id>]`; the whole map is
 * sent on every change (the server merges `draft_data` by top-level key), and the
 * `backgrounds` offers are refetched after, since taking or removing a beat is what
 * opens or closes its answers.
 */

import { useQueryClient } from '@tanstack/react-query';
import { useMemo } from 'react';
import { characterCreationKeys, useDraftBeats, useUpdateDraft } from '../../queries';
import {
  LIFE_STAGE_LABELS,
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

export function BeatsBlock({ draft, copy }: Props) {
  const { data: beats, isLoading } = useDraftBeats(draft.id);
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

  if (isLoading || !beats || beats.length === 0) return null;

  const states = draft.draft_data.beats ?? {};

  const save = async (next: Record<string, DraftBeatState>) => {
    await updateDraft.mutateAsync({ draftId: draft.id, data: { draft_data: { beats: next } } });
    await queryClient.invalidateQueries({ queryKey: characterCreationKeys.draftBeats(draft.id) });
    await queryClient.invalidateQueries({
      queryKey: characterCreationKeys.draftOffers(draft.id, 'backgrounds'),
    });
  };
  const patch = (beat: BeatPoolEntry, change: DraftBeatState | null) => {
    const next: Record<string, DraftBeatState> = { ...states };
    const key = String(beat.beat_id);
    if (change === null) delete next[key];
    else next[key] = { ...(next[key] ?? {}), ...change };
    void save(next);
  };

  return (
    <div className="beats">
      {LIFE_STAGE_ORDER.map((stage) => {
        const pool = byStage.get(stage) ?? [];
        if (pool.length === 0) return null;
        const taken = pool.filter((b) => b.taken);
        const untaken = pool.filter((b) => !b.taken);
        return (
          <section key={stage} className="beat-stage" aria-label={LIFE_STAGE_LABELS[stage]}>
            <h3 className="section-h">
              {LIFE_STAGE_LABELS[stage] ?? stage}
              {taken.length > 0 && <small> {taken.length}</small>}
            </h3>
            {taken.map((beat) => (
              <article key={beat.beat_id} className="beat-row" aria-label={beat.name}>
                <h4 className="section-h">{beat.name}</h4>
                <p className="beat-prompt">{beat.prompt}</p>
                {!beat.unknown && (
                  <span className="mode">
                    {beat.selection === 'one_of'
                      ? (copy?.beats_mode_one_of ?? 'One of')
                      : (copy?.beats_mode_any ?? 'Any that apply')}
                  </span>
                )}
                {!beat.unknown && (
                  <ChapterOffers
                    draft={draft}
                    chapter="backgrounds"
                    filter={(o) => o.opener_key === `beat:${beat.beat_id}`}
                    showOpener={false}
                    showClosed={false}
                    firstLook={false}
                    exclusive={beat.selection === 'one_of'}
                    syncErrorHint={copy?.offers_sync_error}
                    wordPerRank={copy?.offers_word_per_rank}
                    wordSpent={copy?.offers_word_spent}
                    wordAwards={copy?.offers_word_awards}
                  />
                )}
                {!beat.unknown && (
                  <div className="field">
                    <label htmlFor={`beat-${beat.beat_id}-line`}>
                      {copy?.beats_line_label ?? 'Line'}
                    </label>
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
                    onClick={() => patch(beat, { taken: true, unknown: !beat.unknown })}
                  >
                    <span className="mark-box" aria-hidden="true">
                      {beat.unknown ? '\u2713' : ''}
                    </span>
                    {copy?.beats_unknown_word ?? 'Unknown'}
                  </button>
                  {!beat.kept && (
                    <button type="button" className="btn-quiet" onClick={() => patch(beat, null)}>
                      {copy?.beats_remove_word ?? 'Remove'}
                    </button>
                  )}
                </div>
              </article>
            ))}
            {untaken.length > 0 && (
              <div
                className="beat-pool"
                role="group"
                aria-label={`${copy?.beats_add_word ?? 'Add a beat'}: ${LIFE_STAGE_LABELS[stage] ?? stage}`}
              >
                {untaken.map((beat) => (
                  <button
                    key={beat.beat_id}
                    type="button"
                    onClick={() => patch(beat, { taken: true, unknown: false })}
                  >
                    {beat.name}
                  </button>
                ))}
              </div>
            )}
          </section>
        );
      })}
    </div>
  );
}
