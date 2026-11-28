/**
 * CG mount of the guided Glimpse flow (#2427; three ways in and no CG points,
 * #5292).
 *
 * The state binder around `GlimpseAxes`: draft reads, `updateDraft` writes,
 * and the copy query. It reads the catalog via useGlimpseTags and binds the
 * parts to draft_data keys (glimpse_tag_ids / glimpse_story), persisting
 * through useUpdateDraft on change (same PATCH-merge contract as the funnel
 * steps).
 *
 * Under GiftStage's own `section-h` (which prints the chapter heading, so this
 * mount renders none) sits the owner's paragraph in body text, then the three
 * ways into the Glimpse (owner ruling 2026-11-24, labels verbatim): "Create
 * Glimpse in CG", "Amnesiac, No Memory of Glimpse", "Create Glimpse Post-CG".
 * One is always chosen; a draft that never chose is on the first. The choice
 * and the blackout tick together are `draft_data.glimpse_memory` (the server's
 * `GlimpseMemory`): remembered or blacked out for the first way, no memory for
 * the second, later for the third. With the second or third no part is asked;
 * one line says what the choice means. The answers and the story a player gave
 * stay in the draft, and come back with the first way.
 *
 * A beginning with no memory of the Glimpse (`no_glimpse_memory`, the
 * Sleeper's) shows no ways and the no-memory line: the server holds such a
 * draft in that state whatever it is sent.
 *
 * "Skip for now" is gone: "Create Glimpse Post-CG" is that choice, recorded.
 *
 * Prose stays on the parent GiftStage's shared react-hook-form instance
 * (`register('glimpse_story')`, passed down — `AnimaCheckStep`'s
 * `ritualNameField` prop is the precedent) so it still saves via
 * `saveFormFields` on stage leave; answers and the way write immediately via
 * `updateDraft`, like `GiftSelector`'s `selected_gift_id`.
 */

import { useState } from 'react';
import type { ChangeEvent } from 'react';
import type { UseFormRegisterReturn } from 'react-hook-form';
import { useCGExplanations, useGlimpseTags, useUpdateDraft } from '../../queries';
import type { CharacterDraft, GlimpseMemory, GlimpseTagOption } from '../../types';
import { GlimpseAxes } from './GlimpseAxes';
import { draftGlimpseMemory } from './glimpseParts';

interface GlimpseSectionProps {
  draft: CharacterDraft;
  /** Registration for the prose field — owned by GiftStage's shared form so a
   * single beforeLeave save covers ritual name + motif + glimpse. */
  glimpseProseField: UseFormRegisterReturn<'glimpse_story'>;
}

/** The three ways into the Glimpse; `now` covers remembered and blacked out. */
type GlimpseWay = 'now' | 'none' | 'later';

const WAYS: { way: GlimpseWay; copyKey: string; fallback: string }[] = [
  { way: 'now', copyKey: 'glimpse_way_now', fallback: 'Create Glimpse in CG' },
  { way: 'none', copyKey: 'glimpse_way_none', fallback: 'Amnesiac, No Memory of Glimpse' },
  { way: 'later', copyKey: 'glimpse_way_later', fallback: 'Create Glimpse Post-CG' },
];

const WAY_OF: Record<GlimpseMemory, GlimpseWay> = {
  remembered: 'now',
  blacked_out: 'now',
  no_memory: 'none',
  later: 'later',
};

// The owner's paragraph for The Glimpse (ruling 2026-11-23), without its last
// sentence: that sentence says skipping the Glimpse grants CG points, which the
// ruling of 2026-11-24 ended, and its replacement is the owner's to write. A copy row
// under `glimpse_intro` replaces the whole paragraph.
const GLIMPSE_INTRO_FALLBACK =
  "The Glimpse is the often traumatic event that begins a character's magical awakening, " +
  'catching a glimpse of who they might one day become if they survive to fully grow into ' +
  'their power. Usually happening during moments of great emotional turmoil or ' +
  'life-threatening danger, the character instinctively uses magic and gains access to their ' +
  'Gift. Since this can be character defining, a player has the option of skipping this in CG ' +
  'and defining it later. Or, in the case of characters like Sleepers, may have no memory of ' +
  'this.';

// PLACEHOLDER: Apostate rewrite. Plain statements of what each choice does.
const NO_MEMORY_LINE_FALLBACK =
  'Nothing of the Glimpse is asked. The character holds the card that marks it as a mystery, ' +
  'and each part gives its bonus when a story returns the memory.';
const LATER_LINE_FALLBACK =
  'The Glimpse is written from the character sheet after character creation, and each part ' +
  'gives its bonus then.';

/**
 * The memory state a click on a way saves. The first way keeps a blackout already
 * ticked (the tick itself is below, among the parts) and otherwise reads remembered.
 */
function memoryForWay(way: GlimpseWay, current: GlimpseMemory): GlimpseMemory {
  if (way === 'none') return 'no_memory';
  if (way === 'later') return 'later';
  return WAY_OF[current] === 'now' ? current : 'remembered';
}

export function GlimpseSection({ draft, glimpseProseField }: GlimpseSectionProps) {
  const updateDraft = useUpdateDraft();
  const { data: tags } = useGlimpseTags(draft.selected_path?.id);
  const { data: copy } = useCGExplanations();

  // Prose is uncontrolled from RHF's point of view (no `value` on a register
  // return) so this local copy exists purely to give GlimpseAxes a controlled
  // display value that starts from the last-saved draft_data.
  const [prose, setProse] = useState(() => draft.draft_data.glimpse_story ?? '');

  const selectedTagIds = draft.draft_data.glimpse_tag_ids ?? [];
  const memory = draftGlimpseMemory(draft);
  const way = WAY_OF[memory];
  const isForced = draft.selected_beginnings?.no_glimpse_memory ?? false;

  const saveMemory = (next: GlimpseMemory) => {
    if (next === memory) return;
    updateDraft.mutate({ draftId: draft.id, data: { draft_data: { glimpse_memory: next } } });
  };

  const handleChangeAxis = (axis: GlimpseTagOption['axis'], tagIds: number[]) => {
    if (!tags) return;
    const axisTagIds = new Set(tags.filter((tag) => tag.axis === axis).map((tag) => tag.id));
    const otherAxisSelections = selectedTagIds.filter((id) => !axisTagIds.has(id));
    updateDraft.mutate({
      draftId: draft.id,
      data: {
        draft_data: {
          glimpse_tag_ids: [...otherAxisSelections, ...tagIds],
        },
      },
    });
  };

  const handleChangeProse = (text: string) => {
    setProse(text);
    // Manually driving register()'s onChange (rather than attaching its ref)
    // is RHF's documented pattern for wiring a non-native/controlled input —
    // it still updates the form's internal value and dirty state so
    // GiftStage's saveFormFields/getValues() picks up the edit on stage leave.
    glimpseProseField.onChange({
      target: { name: 'glimpse_story', value: text },
      type: 'change',
    } as unknown as ChangeEvent<HTMLTextAreaElement>);
  };

  return (
    <>
      <p className="explain">{copy?.glimpse_intro ?? GLIMPSE_INTRO_FALLBACK}</p>
      {!isForced && (
        <ul className="stances pair oneof ways grid" aria-labelledby="glimpse-heading">
          {WAYS.map((option) => (
            <li key={option.way}>
              <button
                type="button"
                className="stance"
                aria-pressed={way === option.way}
                onClick={() => saveMemory(memoryForWay(option.way, memory))}
              >
                <span className="dot" />
                <span>
                  <b>{copy?.[option.copyKey] ?? option.fallback}</b>
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
      {way === 'none' && (
        <p className="ledger-line">{copy?.glimpse_no_memory_line ?? NO_MEMORY_LINE_FALLBACK}</p>
      )}
      {way === 'later' && (
        <p className="ledger-line">{copy?.glimpse_later_line ?? LATER_LINE_FALLBACK}</p>
      )}
      {way === 'now' && (
        <GlimpseAxes
          tags={tags ?? []}
          selectedTagIds={selectedTagIds}
          copy={copy}
          onChangeAxis={handleChangeAxis}
          blackedOut={memory === 'blacked_out'}
          onChangeBlackedOut={(blackedOut) => saveMemory(blackedOut ? 'blacked_out' : 'remembered')}
          prose={prose}
          onChangeProse={handleChangeProse}
        />
      )}
    </>
  );
}
