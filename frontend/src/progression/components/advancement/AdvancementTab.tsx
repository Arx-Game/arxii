/**
 * AdvancementTab (#3045) — the web home for every SPEND/advance path a
 * player previously had to reach over telnet: skill breakthroughs, class-
 * level unlocks, deliberate skill training, and the Ritual of the Durance.
 *
 * Own-sheet gate: mounted only when `isMyCharacter` (CharacterSheetPage's
 * existing own-tenure gate — same pattern as StatPointPanel/MaturationPanel).
 *
 * Active-puppet caveat: every card here reads/writes through backend views
 * that resolve the acting character via the account's currently PUPPETED
 * character (`request.user.puppet` — `ProgressionUnlockViewSet
 * ._resolve_puppet_sheet`, `TrainingAllocationViewSet._active_puppet`,
 * `DuranceStatusView`/`DuranceConveneView`), not by an id passed from this
 * page. An account with multiple characters could be viewing one character's
 * sheet while a different character is puppeted — mirrors the exact
 * constraint the Locations tab's Ships section already handles
 * (`isActiveCharacter`, CharacterSheetPage.tsx). So this tab is further
 * gated on `isActiveCharacter`, with an explicit message otherwise, rather
 * than silently showing (or worse, letting the player spend against) a
 * different character's advancement state.
 */

import { AlertCircle } from 'lucide-react';
import { BreakthroughsCard } from './BreakthroughsCard';
import { ClassUnlocksCard } from './ClassUnlocksCard';
import { TrainingCard } from './TrainingCard';
import { DuranceCard } from './DuranceCard';

interface AdvancementTabProps {
  characterId: number;
  isActiveCharacter: boolean;
}

export function AdvancementTab({ characterId, isActiveCharacter }: AdvancementTabProps) {
  if (!isActiveCharacter) {
    return (
      <div
        className="flex items-center gap-2 rounded-md border border-amber-500/40 bg-amber-950/20 p-4 text-sm"
        data-testid="advancement-inactive-character-notice"
      >
        <AlertCircle className="h-4 w-4 shrink-0" />
        <p>
          Advancement acts on your currently active character. Switch to this character to manage
          their breakthroughs, unlocks, training, and Durance.
        </p>
      </div>
    );
  }

  return (
    <div className="grid gap-4 md:grid-cols-2" data-testid="advancement-tab">
      <BreakthroughsCard />
      <ClassUnlocksCard />
      <TrainingCard />
      <DuranceCard characterId={characterId} />
    </div>
  );
}
