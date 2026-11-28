/**
 * What the Glimpse's CG components share that is not a component (#5292): the parts'
 * names and the draft's memory state. Read by `GlimpseAxes`, `GlimpseSection` and the
 * Gift stage's side panel.
 */

import type { GlimpseTagOption } from '@/magic/components/glimpse/glimpseTypes';
import type { CharacterDraft, GlimpseMemory } from '../../types';

// `AXIS_STEPS` never carries a SENSORY entry (GlimpseAxes never renders a
// field for it, same as GlimpseFlow), but `GlimpseTagOption['axis']` is the
// full 7-member union; both maps carry an unreachable SENSORY entry purely
// to satisfy `Record<GlimpseTagOption['axis'], string>`. The axis name is
// the fallback behind a `glimpse_axis_<axis>_chip` copy key (mirrors
// `GlimpseTagAxis`'s own choice labels in `world.magic.constants`, the
// authoritative source this literal must not drift from). The key keeps the
// name it had when the axis name was a chip beside the question, so a row
// staff already edited still applies now that the name is the heading.
export const AXIS_DISPLAY_NAME: Record<GlimpseTagOption['axis'], string> = {
  TRIGGER: 'Trigger',
  CHOOSING: 'The Choosing',
  REFLECTION: 'The Reflection',
  TONE: 'Tone',
  CONSEQUENCE: 'Consequence',
  WITNESS: 'Witness & Secrecy',
  SENSORY: '',
};

/** The draft's memory state as the server reads it: a no-memory beginning overrides. */
export function draftGlimpseMemory(draft: CharacterDraft): GlimpseMemory {
  if (draft.selected_beginnings?.no_glimpse_memory) return 'no_memory';
  return draft.draft_data.glimpse_memory ?? 'remembered';
}
