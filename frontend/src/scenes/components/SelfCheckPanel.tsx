/**
 * SelfCheckPanel — the player-facing roll picker (#3295).
 *
 * Any player can roll an authored CheckType on themselves, publicly, in a
 * scene: search the catalog, pick a DifficultyChoice band (never a free
 * integer — the "self-picked difficulty is theater" ruling), and dispatch
 * `scene_self_check` (`actions/definitions/scene_checks.py`) over the generic
 * REST dispatch seam, mirroring `GMAdjudicationPanel.tsx`'s `CallCheckTab`.
 * The result broadcasts to the room via the scene interaction pipeline
 * (Narrator-voiced OUTCOME line) — this panel only reports success/failure to
 * the roller via toast, exactly like the GM panel's tabs.
 *
 * The empty-result state offers "Propose a check" (Decision 4 in the spec):
 * when the catalog has nothing fitting, a player proposes a new CheckType
 * instead of inventing one — this dispatches `propose_check_type`, landing in
 * the staff inbox. It never creates a live catalog row.
 */

import { useMemo, useState } from 'react';
import { toast } from 'sonner';
import { useAppSelector } from '@/store/hooks';
import { useMyRosterEntriesQuery } from '@/roster/queries';
import { useDispatchPlayerAction } from '@/combat/queries';
import { isDispatchFailure } from '@/combat/types';
import type { DispatchResult } from '@/combat/types';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Label } from '@/components/ui/label';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Button } from '@/components/ui/button';
import { usePlayerCheckTypeCatalog } from '@/checks/queries';
import { DIFFICULTY_BANDS } from '@/checks/types';
import type { DifficultyBand } from '@/checks/types';

const SELECT_CLASS =
  'flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm focus:outline-none focus:ring-1 focus:ring-ring disabled:cursor-not-allowed disabled:opacity-50';

function reportResult(result: DispatchResult, fallbackSuccess: string): void {
  if (isDispatchFailure(result)) {
    toast.error(result.message ?? 'The check was refused.');
    return;
  }
  toast.success(result.message ?? fallbackSuccess);
}

function ProposeCheckForm({
  characterId,
  initialName,
}: {
  characterId: number;
  initialName: string;
}) {
  const [proposedName, setProposedName] = useState(initialName);
  const [intent, setIntent] = useState('');
  const [situationText, setSituationText] = useState('');
  const [suggestedTraitsText, setSuggestedTraitsText] = useState('');
  const dispatch = useDispatchPlayerAction(characterId);

  const canSubmit =
    proposedName.trim() !== '' &&
    intent.trim() !== '' &&
    situationText.trim() !== '' &&
    !dispatch.isPending;

  function handleSubmit() {
    if (!canSubmit) return;
    dispatch
      .mutateAsync({
        ref: { backend: 'registry', registry_key: 'propose_check_type' },
        kwargs: {
          proposed_name: proposedName,
          intent,
          situation_text: situationText,
          suggested_traits_text: suggestedTraitsText,
        },
      })
      .then((result) => {
        reportResult(result, 'Proposal sent to staff.');
        if (!isDispatchFailure(result)) {
          setProposedName('');
          setIntent('');
          setSituationText('');
          setSuggestedTraitsText('');
        }
      })
      .catch(() => toast.error('Could not send the proposal.'));
  }

  return (
    <div className="space-y-2 rounded-md border border-dashed p-3" data-testid="propose-check-form">
      <p className="text-xs text-muted-foreground">
        Nothing in the catalog fits? Propose a new check — staff review it, they never auto-create
        it.
      </p>
      <Input
        placeholder="Check name"
        value={proposedName}
        onChange={(e) => setProposedName(e.target.value)}
        data-testid="propose-check-name"
      />
      <Textarea
        placeholder="What is this check meant to cover?"
        value={intent}
        onChange={(e) => setIntent(e.target.value)}
        rows={2}
        data-testid="propose-check-intent"
      />
      <Textarea
        placeholder="The situation it would serve"
        value={situationText}
        onChange={(e) => setSituationText(e.target.value)}
        rows={2}
        data-testid="propose-check-situation"
      />
      <Input
        placeholder="Suggested stat + skill (optional)"
        value={suggestedTraitsText}
        onChange={(e) => setSuggestedTraitsText(e.target.value)}
        data-testid="propose-check-traits"
      />
      <Button
        size="sm"
        disabled={!canSubmit}
        onClick={handleSubmit}
        data-testid="propose-check-submit"
      >
        {dispatch.isPending ? 'Sending…' : 'Propose a check'}
      </Button>
    </div>
  );
}

interface SelfCheckPanelProps {
  className?: string;
}

export function SelfCheckPanel({ className }: SelfCheckPanelProps) {
  const activeCharacterName = useAppSelector((state) => state.game.active);
  const { data: myRosterEntries = [] } = useMyRosterEntriesQuery();
  const characterId = useMemo(
    () => myRosterEntries.find((e) => e.name === activeCharacterName)?.character_id ?? null,
    [myRosterEntries, activeCharacterName]
  );

  const [search, setSearch] = useState('');
  const [checkTypeId, setCheckTypeId] = useState<number | null>(null);
  const [difficulty, setDifficulty] = useState<DifficultyBand>('normal');
  const { data: checkTypes = [] } = usePlayerCheckTypeCatalog(
    search,
    characterId,
    characterId !== null
  );
  const dispatch = useDispatchPlayerAction(characterId ?? 0);

  if (characterId === null) {
    return null;
  }

  const canSubmit = checkTypeId !== null && !dispatch.isPending;

  function handleSubmit() {
    if (!canSubmit) return;
    dispatch
      .mutateAsync({
        ref: { backend: 'registry', registry_key: 'scene_self_check' },
        kwargs: { check_type_ref: checkTypeId, difficulty },
      })
      .then((result) => reportResult(result, 'Check rolled.'))
      .catch(() => toast.error('Could not roll that check.'));
  }

  return (
    <Card className={className} data-testid="self-check-panel">
      <CardHeader>
        <CardTitle className="text-base">Roll a Check</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="space-y-1">
          <Label htmlFor="self-check-search">Check</Label>
          <Input
            id="self-check-search"
            placeholder="Search the check catalog…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
          <select
            className={SELECT_CLASS}
            value={checkTypeId ?? ''}
            onChange={(e) => setCheckTypeId(e.target.value ? Number(e.target.value) : null)}
            data-testid="self-check-type-select"
          >
            <option value="">Select a check…</option>
            {checkTypes.map((ct) => (
              <option key={ct.id} value={ct.id}>
                {ct.name}
                {ct.trait_summary ? ` (${ct.trait_summary})` : ''}
              </option>
            ))}
          </select>
        </div>
        <div className="space-y-1">
          <Label htmlFor="self-check-difficulty">Difficulty</Label>
          <select
            id="self-check-difficulty"
            className={SELECT_CLASS}
            value={difficulty}
            onChange={(e) => setDifficulty(e.target.value as DifficultyBand)}
          >
            {DIFFICULTY_BANDS.map((band) => (
              <option key={band.value} value={band.value}>
                {band.label}
              </option>
            ))}
          </select>
        </div>
        <Button disabled={!canSubmit} onClick={handleSubmit} data-testid="self-check-submit">
          {dispatch.isPending ? 'Rolling…' : 'Roll Check'}
        </Button>
        {search.trim() !== '' && checkTypes.length === 0 && (
          <ProposeCheckForm characterId={characterId} initialName={search} />
        )}
      </CardContent>
    </Card>
  );
}
