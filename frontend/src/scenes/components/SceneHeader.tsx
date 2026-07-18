import { useState, useEffect, useMemo } from 'react';
import { useForm } from 'react-hook-form';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useAppSelector } from '@/store/hooks';
import { useMyRosterEntriesQuery } from '@/roster/queries';
import { useDispatchPlayerAction } from '@/combat/queries';
import { SceneDetail, updateScene, finishScene } from '../queries';
import { useAvailableActionsQuery } from '../actionQueries';
import type { PlayerAction } from '../actionTypes';
import type { SceneRoundState } from '../types';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { SubmitButton } from '@/components/SubmitButton';
import { RoundSettingsDialog } from './RoundSettingsDialog';
import { Badge } from '@/components/ui/badge';
import { useEncounterForScene } from '@/combat/queries';

interface Props {
  scene?: SceneDetail;
  onRefresh?: () => void;
}

/**
 * Grant GM control (#2113) — the web face of `scene gm <name>`.
 *
 * Dispatches the `grant_scene_gm` registry action through the same generic
 * available-actions seam `set_the_stage` uses (SceneTacticalMap). Rendered
 * only for scene owners on an active scene; the backend Action re-checks
 * `actor_can_administer_scene` and the target's GMProfile, so this control is
 * a convenience, never the gate.
 */
function GrantSceneGMControl() {
  const [targetName, setTargetName] = useState('');
  const [feedback, setFeedback] = useState<string | null>(null);

  const activeCharacterName = useAppSelector((state) => state.game.active);
  const { data: myRosterEntries = [] } = useMyRosterEntriesQuery();
  const characterId = useMemo(
    () => myRosterEntries.find((e) => e.name === activeCharacterName)?.character_id ?? null,
    [myRosterEntries, activeCharacterName]
  );

  const { data: actionsData } = useAvailableActionsQuery(characterId);
  const availableActions: PlayerAction[] = actionsData?.results ?? [];
  const grantAction =
    availableActions.find(
      (a) => a.ref.backend === 'registry' && a.ref.registry_key === 'grant_scene_gm'
    ) ?? null;

  const { mutateAsync: dispatchAction, isPending } = useDispatchPlayerAction(characterId ?? 0);

  if (!grantAction || characterId === null) return null;

  const submit = () => {
    const name = targetName.trim();
    if (!name) return;
    dispatchAction({ ref: grantAction.ref, kwargs: { target_name: name } })
      .then((result) => {
        setFeedback(result.message ?? `GM status granted to ${name}.`);
        setTargetName('');
      })
      .catch((err: unknown) =>
        setFeedback(err instanceof Error ? err.message : 'Could not grant GM status.')
      );
  };

  return (
    <div className="mb-2" data-testid="grant-scene-gm">
      <div className="flex items-center gap-2">
        <Input
          className="h-8 w-48"
          placeholder="Character name"
          value={targetName}
          onChange={(e) => setTargetName(e.target.value)}
          aria-label="Grant GM target character name"
        />
        <Button size="sm" variant="outline" onClick={submit} disabled={isPending}>
          Grant GM
        </Button>
      </div>
      {feedback && <p className="mt-1 text-xs text-muted-foreground">{feedback}</p>}
    </div>
  );
}

/**
 * Round-state badge (#2158) — read-only round number and status, visible to
 * every scene participant, not just the GM. Mirrors the round state
 * `RoundSettingsDialog` lets the GM edit, but is rendered unconditionally.
 */
function formatRoundStatus(status: string): string {
  return status
    .split('_')
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(' ');
}

function RoundStateBadge({ activeRound }: { activeRound: SceneRoundState | null }) {
  if (activeRound === null) {
    return null;
  }
  return (
    <span className="rounded bg-muted px-2 py-1 text-xs text-muted-foreground">
      Round {activeRound.round_number} · {formatRoundStatus(activeRound.status)}
    </span>
  );
}

export function SceneHeader({ scene, onRefresh }: Props) {
  const [editing, setEditing] = useState(false);
  const qc = useQueryClient();
  const { register, handleSubmit, reset } = useForm<{ name: string; description: string }>({
    defaultValues: { name: scene?.name ?? '', description: scene?.description ?? '' },
  });
  useEffect(() => {
    reset({ name: scene?.name ?? '', description: scene?.description ?? '' });
  }, [scene, reset]);
  const { data: activeEncounter } = useEncounterForScene(scene?.id ?? 0);
  const save = useMutation({
    mutationFn: (values: { name: string; description: string }) =>
      updateScene(String(scene?.id), values),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['scene', String(scene?.id)] });
      setEditing(false);
    },
  });
  const end = useMutation({
    mutationFn: () => finishScene(String(scene?.id)),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['scene', String(scene?.id)] });
      qc.invalidateQueries({ queryKey: ['scenes'] });
    },
  });

  if (!scene) return null;

  if (editing) {
    return (
      <form onSubmit={handleSubmit((values) => save.mutate(values))} className="mb-4 space-y-2">
        <div className="space-y-1">
          <label htmlFor="name" className="text-sm font-medium">
            Name
          </label>
          <Input id="name" {...register('name')} />
        </div>
        <div className="space-y-1">
          <label htmlFor="description" className="text-sm font-medium">
            Description
          </label>
          <Textarea id="description" {...register('description')} />
        </div>
        <div className="flex gap-2">
          <SubmitButton size="sm" isLoading={save.isPending}>
            Save
          </SubmitButton>
          <Button size="sm" variant="secondary" onClick={() => setEditing(false)}>
            Cancel
          </Button>
        </div>
      </form>
    );
  }

  return (
    <div>
      <h1 className="mb-2 text-xl font-bold">{scene.name}</h1>
      {activeEncounter != null && (
        // #2197: combat now renders in-scene (CombatRail on this same page),
        // so this is a plain status indicator, not a navigation link — a
        // link to this scene from this scene would be self-referential.
        <Badge
          variant="destructive"
          className="mb-2 inline-block text-xs"
          data-testid="scene-header-combat-badge"
        >
          In Combat
        </Badge>
      )}
      <p className="mb-4">{scene.description}</p>
      {(scene.is_owner || scene.is_active) && (
        <div className="mb-2 flex gap-2">
          {scene.is_owner && (
            <>
              <Button size="sm" onClick={() => setEditing(true)}>
                Edit
              </Button>
              {scene.is_active && (
                <SubmitButton
                  size="sm"
                  variant="destructive"
                  onClick={() => end.mutate()}
                  isLoading={end.isPending}
                  type="button"
                >
                  End Scene
                </SubmitButton>
              )}
            </>
          )}
          {scene.is_active && (
            <Button size="sm" variant="outline" onClick={() => onRefresh?.()}>
              Refresh
            </Button>
          )}
          <RoundStateBadge activeRound={scene.active_round} />
          <RoundSettingsDialog scene={scene} />
        </div>
      )}
      {scene.is_owner && scene.is_active && <GrantSceneGMControl />}
      {scene.is_active && (
        <p className="mb-4 text-xs text-muted-foreground">
          Auto-refreshes every minute while active
        </p>
      )}
    </div>
  );
}
