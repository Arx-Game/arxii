/**
 * GMAdjudicationPanel — the web home for the GM adjudication toolkit (#3070).
 *
 * Before this panel, the only way to call a check, hand out an award, apply a
 * condition, or place a situation/challenge from the browser was to type
 * `gm ...` into the scene composer — which poses it to the room as IC text
 * instead of running the action. This panel dispatches the SAME
 * prerequisite-gated REGISTRY actions telnet's `gm`/`setsituation` commands
 * already use (`gm_invoke_check`, `gm_award_progression`, `gm_apply_condition`,
 * `set_situation`, `place_challenge`, `summon_player` — #3071,
 * `gm_trigger_dramatic_beat` — #3387) directly over the generic REST dispatch seam
 * (`useDispatchPlayerAction` -> `POST /api/actions/characters/{id}/dispatch/`),
 * mirroring `PersonaContextMenu.tsx`'s `challenge`/`identify` items — these
 * actions carry no `ActionTemplate`, so they never appear in the generic
 * `get_player_actions` listing.
 *
 * Visibility is gated on `scene.viewer_can_gm` alone (staff, the scene's own
 * GM, or its owner) — the same client-readable signal `HighlightReel`'s
 * `canGm` prop and `RoundSettingsDialog` already gate on. No client-side GM
 * *trust tier* check exists or should exist: `gm_invoke_check` requires SENIOR,
 * the rest JUNIOR, but inventing a tier-probe API here was explicitly out of
 * scope — a below-tier GM simply sees the backend's refusal message surface
 * via toast, same as any other prerequisite failure.
 *
 * Targets are the scene's own participants (`scene.personas`), keyed by
 * `character_sheet` — a `CharacterSheet`'s pk equals its owning `ObjectDB`'s
 * pk (shared-pk O2O), so that id is exactly what `gm_invoke_check`/
 * `gm_award_progression`/`gm_apply_condition`/`summon_player`'s `target` kwarg
 * expects (resolved server-side by `_resolve_gm_target`, `actions/definitions/
 * gm_adjudication.py`). `set_situation`/`place_challenge` act on the GM's own
 * room instead (`target_type=SELF`) and so have no target picker. Summon can
 * only reach a scene participant from this picker today (#3071) — an
 * arbitrary off-scene target needs a global character-search affordance this
 * panel doesn't have yet; telnet's `gm summon <character>` has no such limit.
 */

import { useMemo, useState } from 'react';
import { toast } from 'sonner';
import { useAppSelector } from '@/store/hooks';
import { useMyRosterEntriesQuery } from '@/roster/queries';
import { useDispatchPlayerAction } from '@/combat/queries';
import { isDispatchFailure } from '@/combat/types';
import type { DispatchResult } from '@/combat/types';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Label } from '@/components/ui/label';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import type { SceneDetail, ScenePersona } from '../types';
import {
  useCheckTypeCatalog,
  useConditionTemplateCatalog,
  useSituationTemplateCatalog,
  useChallengeTemplateCatalog,
} from '@/gm-adjudication/queries';
import { AWARD_KINDS, DIFFICULTY_BANDS } from '@/gm-adjudication/types';
import type { AwardKind, DifficultyBand } from '@/gm-adjudication/types';

const SELECT_CLASS =
  'flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm focus:outline-none focus:ring-1 focus:ring-ring disabled:cursor-not-allowed disabled:opacity-50';

function reportResult(result: DispatchResult, fallbackSuccess: string): void {
  if (isDispatchFailure(result)) {
    toast.error(result.message ?? 'The action was refused.');
    return;
  }
  toast.success(result.message ?? fallbackSuccess);
}

// ---------------------------------------------------------------------------
// Participant picker — shared by the target-taking tabs (Check/Award/Condition)
// ---------------------------------------------------------------------------

interface ParticipantPickerProps {
  personas: ScenePersona[];
  targetCharacterId: number | null;
  onChange: (characterId: number | null) => void;
}

function ParticipantPicker({ personas, targetCharacterId, onChange }: ParticipantPickerProps) {
  const withCharacter = personas.filter((p) => p.character_sheet != null);
  return (
    <div className="space-y-1">
      <Label htmlFor="gm-adjudication-target">Target</Label>
      <select
        id="gm-adjudication-target"
        className={SELECT_CLASS}
        value={targetCharacterId ?? ''}
        onChange={(e) => onChange(e.target.value ? Number(e.target.value) : null)}
        data-testid="gm-adjudication-target-select"
      >
        <option value="">Select a participant…</option>
        {withCharacter.map((p) => (
          <option key={p.id} value={p.character_sheet as number}>
            {p.name}
          </option>
        ))}
      </select>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Call Check tab
// ---------------------------------------------------------------------------

interface TabProps {
  characterId: number;
  targetCharacterId: number | null;
}

function CallCheckTab({ characterId, targetCharacterId }: TabProps) {
  const [search, setSearch] = useState('');
  const [checkTypeId, setCheckTypeId] = useState<number | null>(null);
  const [difficulty, setDifficulty] = useState<DifficultyBand>('normal');
  const [shiftKind, setShiftKind] = useState<'' | 'edge' | 'setback'>('');
  const [shiftReason, setShiftReason] = useState('');
  const { data: checkTypes = [] } = useCheckTypeCatalog(search, true);
  const dispatch = useDispatchPlayerAction(characterId);

  const canSubmit = targetCharacterId !== null && checkTypeId !== null && !dispatch.isPending;

  function handleSubmit() {
    if (!canSubmit) return;
    const kwargs: Record<string, unknown> = {
      target: targetCharacterId,
      check_type_ref: checkTypeId,
      difficulty,
    };
    if (shiftKind === 'edge') kwargs.edge_reason = shiftReason;
    if (shiftKind === 'setback') kwargs.setback_reason = shiftReason;
    dispatch
      .mutateAsync({ ref: { backend: 'registry', registry_key: 'gm_invoke_check' }, kwargs })
      .then((result) => reportResult(result, 'Check invoked.'))
      .catch(() => toast.error('Could not invoke the check.'));
  }

  return (
    <div className="space-y-3" data-testid="gm-adjudication-check-tab">
      <div className="space-y-1">
        <Label htmlFor="gm-check-search">Check</Label>
        <Input
          id="gm-check-search"
          placeholder="Search the check catalog…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
        <select
          className={SELECT_CLASS}
          value={checkTypeId ?? ''}
          onChange={(e) => setCheckTypeId(e.target.value ? Number(e.target.value) : null)}
          data-testid="gm-check-type-select"
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
        <Label htmlFor="gm-check-difficulty">Difficulty</Label>
        <select
          id="gm-check-difficulty"
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
      <div className="space-y-1">
        <Label htmlFor="gm-check-shift">Shift</Label>
        <select
          id="gm-check-shift"
          className={SELECT_CLASS}
          value={shiftKind}
          onChange={(e) => setShiftKind(e.target.value as '' | 'edge' | 'setback')}
        >
          <option value="">No shift</option>
          <option value="edge">Edge (one band easier)</option>
          <option value="setback">Setback (one band harder)</option>
        </select>
        {shiftKind !== '' && (
          <Input
            placeholder="Why?"
            value={shiftReason}
            onChange={(e) => setShiftReason(e.target.value)}
            data-testid="gm-check-shift-reason"
          />
        )}
      </div>
      <Button disabled={!canSubmit} onClick={handleSubmit} data-testid="gm-check-submit">
        {dispatch.isPending ? 'Invoking…' : 'Invoke Check'}
      </Button>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Call For Check tab (#3295) — JUNIOR+ GM, room-visible prompt, targets answer
// themselves. Distinct from Call Check above (SENIOR-only ad-hoc invocation,
// #2118): this never rolls anything itself.
// ---------------------------------------------------------------------------

function CallForCheckTab({
  characterId,
  personas,
}: {
  characterId: number;
  personas: ScenePersona[];
}) {
  const [search, setSearch] = useState('');
  const [checkTypeId, setCheckTypeId] = useState<number | null>(null);
  const [difficulty, setDifficulty] = useState<DifficultyBand>('normal');
  const [targetIds, setTargetIds] = useState<number[]>([]);
  const { data: checkTypes = [] } = useCheckTypeCatalog(search, true);
  const dispatch = useDispatchPlayerAction(characterId);

  const withCharacter = personas.filter((p) => p.character_sheet != null);
  const canSubmit = checkTypeId !== null && targetIds.length > 0 && !dispatch.isPending;

  function toggleTarget(id: number) {
    setTargetIds((prev) => (prev.includes(id) ? prev.filter((t) => t !== id) : [...prev, id]));
  }

  function handleSubmit() {
    if (!canSubmit) return;
    dispatch
      .mutateAsync({
        ref: { backend: 'registry', registry_key: 'call_for_check' },
        kwargs: { check_type_ref: checkTypeId, difficulty, targets: targetIds },
      })
      .then((result) => reportResult(result, 'Check called.'))
      .catch(() => toast.error('Could not call that check.'));
  }

  return (
    <div className="space-y-3" data-testid="gm-adjudication-callforcheck-tab">
      <div className="space-y-1">
        <Label htmlFor="gm-callforcheck-search">Check</Label>
        <Input
          id="gm-callforcheck-search"
          placeholder="Search the check catalog…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
        <select
          className={SELECT_CLASS}
          value={checkTypeId ?? ''}
          onChange={(e) => setCheckTypeId(e.target.value ? Number(e.target.value) : null)}
          data-testid="gm-callforcheck-type-select"
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
        <Label htmlFor="gm-callforcheck-difficulty">Difficulty</Label>
        <select
          id="gm-callforcheck-difficulty"
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
      <div className="space-y-1">
        <Label>Targets</Label>
        <div className="space-y-1 rounded-md border p-2" data-testid="gm-callforcheck-targets">
          {withCharacter.map((p) => (
            <label key={p.id} className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={targetIds.includes(p.character_sheet as number)}
                onChange={() => toggleTarget(p.character_sheet as number)}
              />
              {p.name}
            </label>
          ))}
        </div>
      </div>
      <Button disabled={!canSubmit} onClick={handleSubmit} data-testid="gm-callforcheck-submit">
        {dispatch.isPending ? 'Calling…' : 'Call For Check'}
      </Button>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Award tab
// ---------------------------------------------------------------------------

function AwardTab({ characterId, targetCharacterId }: TabProps) {
  const [kind, setKind] = useState<AwardKind>('xp');
  const [amount, setAmount] = useState('');
  const [description, setDescription] = useState('');
  const [traitRef, setTraitRef] = useState('');
  const [orgRef, setOrgRef] = useState('');
  const [techniqueRef, setTechniqueRef] = useState('');
  const dispatch = useDispatchPlayerAction(characterId);

  const canSubmit = targetCharacterId !== null && !dispatch.isPending;

  function handleSubmit() {
    if (!canSubmit) return;
    const kwargs: Record<string, unknown> = {
      target: targetCharacterId,
      award_type: kind,
      description: description || undefined,
    };
    if (kind === 'xp' || kind === 'development') kwargs.amount = Number(amount);
    if (kind === 'development' || kind === 'stat') kwargs.trait_ref = traitRef;
    if (kind === 'favor_token') kwargs.org_ref = orgRef;
    if (kind === 'technique') kwargs.technique_ref = techniqueRef;
    dispatch
      .mutateAsync({ ref: { backend: 'registry', registry_key: 'gm_award_progression' }, kwargs })
      .then((result) => reportResult(result, 'Award granted.'))
      .catch(() => toast.error('Could not grant the award.'));
  }

  return (
    <div className="space-y-3" data-testid="gm-adjudication-award-tab">
      <div className="space-y-1">
        <Label htmlFor="gm-award-kind">Award kind</Label>
        <select
          id="gm-award-kind"
          className={SELECT_CLASS}
          value={kind}
          onChange={(e) => setKind(e.target.value as AwardKind)}
        >
          {AWARD_KINDS.map((k) => (
            <option key={k.value} value={k.value}>
              {k.label}
            </option>
          ))}
        </select>
      </div>
      {(kind === 'xp' || kind === 'development') && (
        <div className="space-y-1">
          <Label htmlFor="gm-award-amount">Amount</Label>
          <Input
            id="gm-award-amount"
            type="number"
            min={1}
            value={amount}
            onChange={(e) => setAmount(e.target.value)}
          />
        </div>
      )}
      {(kind === 'development' || kind === 'stat') && (
        <div className="space-y-1">
          <Label htmlFor="gm-award-trait">Trait</Label>
          <Input
            id="gm-award-trait"
            placeholder="Trait name"
            value={traitRef}
            onChange={(e) => setTraitRef(e.target.value)}
          />
        </div>
      )}
      {kind === 'favor_token' && (
        <div className="space-y-1">
          <Label htmlFor="gm-award-org">Organization</Label>
          <Input
            id="gm-award-org"
            placeholder="Organization name"
            value={orgRef}
            onChange={(e) => setOrgRef(e.target.value)}
          />
        </div>
      )}
      {kind === 'technique' && (
        <div className="space-y-1">
          <Label htmlFor="gm-award-technique">Technique</Label>
          <Input
            id="gm-award-technique"
            placeholder="Technique name"
            value={techniqueRef}
            onChange={(e) => setTechniqueRef(e.target.value)}
          />
        </div>
      )}
      <div className="space-y-1">
        <Label htmlFor="gm-award-description">Description</Label>
        <Input
          id="gm-award-description"
          placeholder="Why this award?"
          value={description}
          onChange={(e) => setDescription(e.target.value)}
        />
      </div>
      <Button disabled={!canSubmit} onClick={handleSubmit} data-testid="gm-award-submit">
        {dispatch.isPending ? 'Granting…' : 'Grant Award'}
      </Button>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Condition tab
// ---------------------------------------------------------------------------

function ConditionTab({ characterId, targetCharacterId }: TabProps) {
  const [conditionName, setConditionName] = useState('');
  const [severity, setSeverity] = useState('');
  const [durationRounds, setDurationRounds] = useState('');
  const [note, setNote] = useState('');
  const { data: conditions = [] } = useConditionTemplateCatalog(true);
  const dispatch = useDispatchPlayerAction(characterId);

  const canSubmit = targetCharacterId !== null && conditionName !== '' && !dispatch.isPending;
  const canQuickApply = targetCharacterId !== null && !dispatch.isPending;

  function handleSubmit() {
    if (!canSubmit) return;
    const kwargs: Record<string, unknown> = {
      target: targetCharacterId,
      condition_ref: conditionName,
      note: note || undefined,
    };
    if (severity) kwargs.severity = Number(severity);
    if (durationRounds) kwargs.duration_rounds = Number(durationRounds);
    dispatch
      .mutateAsync({ ref: { backend: 'registry', registry_key: 'gm_apply_condition' }, kwargs })
      .then((result) => reportResult(result, 'Condition applied.'))
      .catch(() => toast.error('Could not apply the condition.'));
  }

  // Quick Edge/Setback (#3387) — one-click round-scoped nudge. Dispatches the
  // same gm_apply_condition seam with only target/condition_ref set, letting
  // severity/duration fall back to the authored template defaults.
  function quickApply(name: 'Edge' | 'Setback') {
    if (!canQuickApply) return;
    dispatch
      .mutateAsync({
        ref: { backend: 'registry', registry_key: 'gm_apply_condition' },
        kwargs: { target: targetCharacterId, condition_ref: name },
      })
      .then((result) => reportResult(result, `${name} applied.`))
      .catch(() => toast.error(`Could not apply ${name}.`));
  }

  return (
    <div className="space-y-3" data-testid="gm-adjudication-condition-tab">
      <div className="flex gap-2">
        <Button
          variant="outline"
          disabled={!canQuickApply}
          onClick={() => quickApply('Edge')}
          data-testid="gm-condition-quick-edge"
        >
          Quick Edge
        </Button>
        <Button
          variant="outline"
          disabled={!canQuickApply}
          onClick={() => quickApply('Setback')}
          data-testid="gm-condition-quick-setback"
        >
          Quick Setback
        </Button>
      </div>
      <div className="space-y-1">
        <Label htmlFor="gm-condition-select">Condition</Label>
        <select
          id="gm-condition-select"
          className={SELECT_CLASS}
          value={conditionName}
          onChange={(e) => setConditionName(e.target.value)}
          data-testid="gm-condition-select"
        >
          <option value="">Select a condition…</option>
          {conditions.map((c) => (
            <option key={c.id} value={c.name}>
              {c.name}
            </option>
          ))}
        </select>
      </div>
      <div className="space-y-1">
        <Label htmlFor="gm-condition-severity">Severity (optional)</Label>
        <Input
          id="gm-condition-severity"
          type="number"
          min={1}
          value={severity}
          onChange={(e) => setSeverity(e.target.value)}
        />
      </div>
      <div className="space-y-1">
        <Label htmlFor="gm-condition-duration">Duration in rounds (optional)</Label>
        <Input
          id="gm-condition-duration"
          type="number"
          min={1}
          value={durationRounds}
          onChange={(e) => setDurationRounds(e.target.value)}
        />
      </div>
      <div className="space-y-1">
        <Label htmlFor="gm-condition-note">Note</Label>
        <Input
          id="gm-condition-note"
          placeholder="Narration only — never a mechanical effect"
          value={note}
          onChange={(e) => setNote(e.target.value)}
        />
      </div>
      <Button disabled={!canSubmit} onClick={handleSubmit} data-testid="gm-condition-submit">
        {dispatch.isPending ? 'Applying…' : 'Apply Condition'}
      </Button>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Situation / Challenge placement tab — acts on the GM's own room, no target
// ---------------------------------------------------------------------------

function SituationTab({ characterId }: { characterId: number }) {
  const [placementKind, setPlacementKind] = useState<'situation' | 'challenge'>('situation');
  const [situationId, setSituationId] = useState<number | null>(null);
  const [challengeId, setChallengeId] = useState<number | null>(null);
  const [targetObjectName, setTargetObjectName] = useState('');
  const [shiftKind, setShiftKind] = useState<'' | 'edge' | 'setback'>('');
  const [shiftReason, setShiftReason] = useState('');
  const { data: situations = [] } = useSituationTemplateCatalog(placementKind === 'situation');
  const { data: challenges = [] } = useChallengeTemplateCatalog(placementKind === 'challenge');
  const dispatch = useDispatchPlayerAction(characterId);

  const canSubmit =
    !dispatch.isPending &&
    (placementKind === 'situation'
      ? situationId !== null
      : challengeId !== null && targetObjectName.trim() !== '');

  function handleSubmit() {
    if (!canSubmit) return;
    if (placementKind === 'situation') {
      dispatch
        .mutateAsync({
          ref: { backend: 'registry', registry_key: 'set_situation' },
          kwargs: { situation_template_id: situationId },
        })
        .then((result) => reportResult(result, 'Situation placed.'))
        .catch(() => toast.error('Could not place the situation.'));
      return;
    }
    const kwargs: Record<string, unknown> = {
      challenge_template_id: challengeId,
      target_object_name: targetObjectName.trim(),
    };
    if (shiftKind === 'edge') kwargs.edge_reason = shiftReason;
    if (shiftKind === 'setback') kwargs.setback_reason = shiftReason;
    dispatch
      .mutateAsync({ ref: { backend: 'registry', registry_key: 'place_challenge' }, kwargs })
      .then((result) => reportResult(result, 'Challenge placed.'))
      .catch(() => toast.error('Could not place the challenge.'));
  }

  return (
    <div className="space-y-3" data-testid="gm-adjudication-situation-tab">
      <div className="space-y-1">
        <Label htmlFor="gm-placement-kind">Placement kind</Label>
        <select
          id="gm-placement-kind"
          className={SELECT_CLASS}
          value={placementKind}
          onChange={(e) => setPlacementKind(e.target.value as 'situation' | 'challenge')}
        >
          <option value="situation">Whole Situation</option>
          <option value="challenge">Single Challenge</option>
        </select>
      </div>
      {placementKind === 'situation' ? (
        <div className="space-y-1">
          <Label htmlFor="gm-situation-select">Situation</Label>
          <select
            id="gm-situation-select"
            className={SELECT_CLASS}
            value={situationId ?? ''}
            onChange={(e) => setSituationId(e.target.value ? Number(e.target.value) : null)}
            data-testid="gm-situation-select"
          >
            <option value="">Select a situation…</option>
            {situations.map((s) => (
              <option key={s.id} value={s.id}>
                {s.name}
              </option>
            ))}
          </select>
        </div>
      ) : (
        <>
          <div className="space-y-1">
            <Label htmlFor="gm-challenge-select">Challenge</Label>
            <select
              id="gm-challenge-select"
              className={SELECT_CLASS}
              value={challengeId ?? ''}
              onChange={(e) => setChallengeId(e.target.value ? Number(e.target.value) : null)}
              data-testid="gm-challenge-select"
            >
              <option value="">Select a challenge…</option>
              {challenges.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                </option>
              ))}
            </select>
          </div>
          <div className="space-y-1">
            <Label htmlFor="gm-challenge-target-name">What embodies it</Label>
            <Input
              id="gm-challenge-target-name"
              placeholder="e.g. the barred gate"
              value={targetObjectName}
              onChange={(e) => setTargetObjectName(e.target.value)}
            />
          </div>
          <div className="space-y-1">
            <Label htmlFor="gm-challenge-shift">Shift</Label>
            <select
              id="gm-challenge-shift"
              className={SELECT_CLASS}
              value={shiftKind}
              onChange={(e) => setShiftKind(e.target.value as '' | 'edge' | 'setback')}
            >
              <option value="">No shift</option>
              <option value="edge">Edge (one band easier)</option>
              <option value="setback">Setback (one band harder)</option>
            </select>
            {shiftKind !== '' && (
              <Input
                placeholder="Why?"
                value={shiftReason}
                onChange={(e) => setShiftReason(e.target.value)}
              />
            )}
          </div>
        </>
      )}
      <Button disabled={!canSubmit} onClick={handleSubmit} data-testid="gm-situation-submit">
        {dispatch.isPending
          ? 'Placing…'
          : placementKind === 'situation'
            ? 'Place Situation'
            : 'Place Challenge'}
      </Button>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Dramatic Beat tab (#3387) — SENIOR-gated manual apply_dramatic_surge trigger.
// Server-side Prerequisite enforces the trust tier; the tab itself carries no
// client-side gate, mirroring every other tab in this panel.
// ---------------------------------------------------------------------------

function DramaticBeatTab({ characterId, targetCharacterId }: TabProps) {
  const [reason, setReason] = useState('');
  const dispatch = useDispatchPlayerAction(characterId);

  const canSubmit = targetCharacterId !== null && reason.trim() !== '' && !dispatch.isPending;

  function handleSubmit() {
    if (!canSubmit) return;
    dispatch
      .mutateAsync({
        ref: { backend: 'registry', registry_key: 'gm_trigger_dramatic_beat' },
        kwargs: { target: targetCharacterId, reason: reason.trim() },
      })
      .then((result) => reportResult(result, 'The spotlight turns.'))
      .catch(() => toast.error('Could not trigger the dramatic beat.'));
  }

  return (
    <div className="space-y-3" data-testid="gm-adjudication-dramaticbeat-tab">
      <p className="text-xs text-muted-foreground">
        Manually spotlights a dramatic beat on the selected participant (Senior GM+). A stated
        reason is required and is kept as staff provenance — never broadcast to the room.
      </p>
      <div className="space-y-1">
        <Label htmlFor="gm-dramaticbeat-reason">Reason</Label>
        <Input
          id="gm-dramaticbeat-reason"
          placeholder="Why does this moment escalate?"
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          data-testid="gm-dramaticbeat-reason"
        />
      </div>
      <Button disabled={!canSubmit} onClick={handleSubmit} data-testid="gm-dramaticbeat-submit">
        {dispatch.isPending ? 'Triggering…' : 'Trigger Dramatic Beat'}
      </Button>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Summon tab (#3071)
// ---------------------------------------------------------------------------

function SummonTab({ characterId, targetCharacterId }: TabProps) {
  const dispatch = useDispatchPlayerAction(characterId);
  const canSubmit = targetCharacterId !== null && !dispatch.isPending;

  function handleSubmit() {
    if (!canSubmit) return;
    dispatch
      .mutateAsync({
        ref: { backend: 'registry', registry_key: 'summon_player' },
        kwargs: { target: targetCharacterId },
      })
      .then((result) => reportResult(result, 'Invitation sent — they must accept to be moved.'))
      .catch(() => toast.error('Could not summon that character.'));
  }

  return (
    <div className="space-y-3" data-testid="gm-adjudication-summon-tab">
      <p className="text-xs text-muted-foreground">
        Invites the selected participant to your current scene room. They must accept
        (consent-prompted) before they are moved.
      </p>
      <Button disabled={!canSubmit} onClick={handleSubmit} data-testid="gm-summon-submit">
        {dispatch.isPending ? 'Sending…' : 'Summon'}
      </Button>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Panel shell
// ---------------------------------------------------------------------------

interface GMAdjudicationPanelProps {
  scene: SceneDetail | undefined;
}

export function GMAdjudicationPanel({ scene }: GMAdjudicationPanelProps) {
  const activeCharacterName = useAppSelector((state) => state.game.active);
  const { data: myRosterEntries = [] } = useMyRosterEntriesQuery();
  const characterId = useMemo(
    () => myRosterEntries.find((e) => e.name === activeCharacterName)?.character_id ?? null,
    [myRosterEntries, activeCharacterName]
  );
  const [targetCharacterId, setTargetCharacterId] = useState<number | null>(null);

  if (!scene?.viewer_can_gm || characterId === null) {
    return null;
  }

  const personas = scene.personas ?? [];

  return (
    <Card data-testid="gm-adjudication-panel">
      <CardHeader>
        <CardTitle className="text-base">GM Tools</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <ParticipantPicker
          personas={personas}
          targetCharacterId={targetCharacterId}
          onChange={setTargetCharacterId}
        />
        <Tabs defaultValue="check">
          <TabsList>
            <TabsTrigger value="check" data-testid="gm-tab-check">
              Call Check
            </TabsTrigger>
            <TabsTrigger value="callforcheck" data-testid="gm-tab-callforcheck">
              Call For Check
            </TabsTrigger>
            <TabsTrigger value="award" data-testid="gm-tab-award">
              Award
            </TabsTrigger>
            <TabsTrigger value="condition" data-testid="gm-tab-condition">
              Condition
            </TabsTrigger>
            <TabsTrigger value="situation" data-testid="gm-tab-situation">
              Situation
            </TabsTrigger>
            <TabsTrigger value="dramaticbeat" data-testid="gm-tab-dramaticbeat">
              Dramatic Beat
            </TabsTrigger>
            <TabsTrigger value="summon" data-testid="gm-tab-summon">
              Summon
            </TabsTrigger>
          </TabsList>
          <TabsContent value="check">
            <CallCheckTab characterId={characterId} targetCharacterId={targetCharacterId} />
          </TabsContent>
          <TabsContent value="callforcheck">
            <CallForCheckTab characterId={characterId} personas={personas} />
          </TabsContent>
          <TabsContent value="award">
            <AwardTab characterId={characterId} targetCharacterId={targetCharacterId} />
          </TabsContent>
          <TabsContent value="condition">
            <ConditionTab characterId={characterId} targetCharacterId={targetCharacterId} />
          </TabsContent>
          <TabsContent value="situation">
            <SituationTab characterId={characterId} />
          </TabsContent>
          <TabsContent value="dramaticbeat">
            <DramaticBeatTab characterId={characterId} targetCharacterId={targetCharacterId} />
          </TabsContent>
          <TabsContent value="summon">
            <SummonTab characterId={characterId} targetCharacterId={targetCharacterId} />
          </TabsContent>
        </Tabs>
      </CardContent>
    </Card>
  );
}
