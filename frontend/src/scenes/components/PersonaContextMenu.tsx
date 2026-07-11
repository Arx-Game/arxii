import { type ReactNode, useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuSub,
  DropdownMenuSubContent,
  DropdownMenuSubTrigger,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { Ban, HeartPulse, Swords, VolumeX, Zap, ScrollText } from 'lucide-react';
import { useAppSelector } from '@/store/hooks';
import { useMyRosterEntriesQuery } from '@/roster/queries';
import { useDispatchPlayerAction, combatKeys } from '@/combat/queries';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { useCreateBlock, useCreateMute } from '@/social/queries';
import { createActionRequest, fetchAvailableActions } from '../actionQueries';
import type { ActionAttachmentInfo, PlayerAction } from '../actionTypes';
import type { SceneDetail } from '../types';
import { WhisperReceiverPicker } from './WhisperReceiverPicker';
import { TreatActionPanel } from '@/conditions/components/TreatActionPanel';
import { GiveMissionDialog } from './GiveMissionDialog';

/** The whisper action awaiting a recipient choice (#907). */
interface PendingWhisper {
  actionKey: string;
  techniqueId?: number;
}

// Unmet prerequisite: shown disabled with its reason instead of omitted
// (mirrors ActionPanel.tsx's disabled-button pattern, #2158). No delivery
// submenu — the action can't be fired regardless. Shared by both the direct-
// execute list and the "Attach to Pose" list below.
function disabledActionItem(action: PlayerAction, key: string) {
  return (
    <button
      key={key}
      type="button"
      disabled
      title={action.prerequisite_reasons.join('; ')}
      className="flex w-full cursor-not-allowed select-none items-center gap-2 rounded-sm px-2 py-1.5 text-left text-sm opacity-50 outline-none"
    >
      <Zap className="mr-2 h-4 w-4" />
      {action.display_name}
    </button>
  );
}

interface Props {
  personaId: number;
  personaName: string;
  sceneId: string;
  children: ReactNode;
  onAttachAction?: (action: ActionAttachmentInfo) => void;
}

export function PersonaContextMenu({
  personaId,
  personaName,
  sceneId,
  children,
  onAttachAction,
}: Props) {
  const queryClient = useQueryClient();

  // Resolve the active character name to its numeric ObjectDB pk to look up
  // the correct cache key (which ActionAttachment populates as ['available-actions', characterId]).
  const activeCharacterName = useAppSelector((state) => state.game.active);
  const { data: myRosterEntries = [] } = useMyRosterEntriesQuery();
  const characterId = useMemo(
    () => myRosterEntries.find((e) => e.name === activeCharacterName)?.character_id ?? null,
    [myRosterEntries, activeCharacterName]
  );

  // Fetch directly (mirrors ActionPanel.tsx) rather than reading the cache
  // opportunistically — the menu must populate even if ActionPanel/ActionAttachment
  // hasn't been opened yet this session (#2158).
  const { data } = useQuery({
    queryKey: ['available-actions', characterId],
    queryFn: () => fetchAvailableActions(characterId!),
    enabled: characterId !== null,
  });

  // #907: present scene personas (excluding the target) are the extra-listener
  // pool. Read from the already-loaded scene cache; empty if not yet present.
  const scene = queryClient.getQueryData<SceneDetail>(['scene', sceneId]);
  const whisperCandidates = useMemo(
    () => (scene?.personas ?? []).filter((p) => p.id !== personaId),
    [scene, personaId]
  );

  // #1181: outgoing duel-challenge affordance. Resolve the target persona to know
  // whether it's the viewer's own character (hide for self) and whether it has
  // opted out of social targeting (mirror the backend consent gate).
  const targetPersona = useMemo(
    () => (scene?.personas ?? []).find((p) => p.id === personaId) ?? null,
    [scene, personaId]
  );
  const isSelfTarget = characterId !== null && targetPersona?.character_sheet === characterId;
  // Require the target persona to be resolved from scene data: without it we know
  // neither its character (self check) nor its opt-out state, so don't offer the duel.
  const canChallenge =
    characterId !== null &&
    targetPersona !== null &&
    !isSelfTarget &&
    targetPersona.allow_social_actions !== false;

  // Challenge dispatches via the registry path (the action carries no ActionTemplate,
  // so it's absent from the available-actions list) with the target persona id.
  const { mutateAsync: dispatchChallenge, isPending: isChallengePending } = useDispatchPlayerAction(
    characterId ?? 0
  );

  const [pendingWhisper, setPendingWhisper] = useState<PendingWhisper | null>(null);

  // #1278 — block/mute. The viewer's own face in this scene is the blocker persona; a block needs
  // it (mute doesn't). You can block/mute any resolved persona but your own.
  const blockerPersonaId = useMemo(
    () => (scene?.personas ?? []).find((p) => p.character_sheet === characterId)?.id ?? null,
    [scene, characterId]
  );
  const canModerate = targetPersona !== null && !isSelfTarget;
  const createMute = useCreateMute();
  const createBlock = useCreateBlock();
  const [blockDialogOpen, setBlockDialogOpen] = useState(false);
  const [blockReason, setBlockReason] = useState('');
  const [treatDialogOpen, setTreatDialogOpen] = useState(false);
  const [giveMissionOpen, setGiveMissionOpen] = useState(false);

  // Reuse the already-loaded scene data for the GM check (#2050).
  const canGiveMission = scene?.viewer_can_gm ?? false;

  function submitBlock() {
    if (blockerPersonaId === null || blockReason.trim() === '') {
      return;
    }
    createBlock.mutate(
      { blocker_persona: blockerPersonaId, blocked_persona: personaId, reason: blockReason.trim() },
      {
        onSettled: () => {
          setBlockDialogOpen(false);
          setBlockReason('');
        },
      }
    );
  }

  const performAction = useMutation({
    mutationFn: (params: {
      action_key: string;
      target_persona_id: number;
      technique_id?: number;
      delivery?: string;
      delivery_receiver_ids?: number[];
    }) => createActionRequest(sceneId, params),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['scene-messages', sceneId] });
      queryClient.invalidateQueries({ queryKey: ['pending-requests', sceneId] });
    },
  });

  // Show every targeted action, including unmet-prerequisite ones — rendered
  // disabled with their reason below, not silently omitted (mirrors ActionPanel, #2158).
  const targetedActions: PlayerAction[] = data?.results ?? [];

  // Treat affordance (#1486): available for any non-self target once the viewer's
  // character is resolved.  The discovery endpoint gates candidates server-side,
  // so the menu item is always offered for eligible targets; an empty candidate
  // list renders an inline "No treatable conditions." message in the dialog.
  const canTreat = characterId !== null && !isSelfTarget;

  // The menu is worth showing if there are targeted actions, a challenge, treat,
  // or block/mute.
  if (targetedActions.length === 0 && !canChallenge && !canTreat && !canModerate) {
    return <>{children}</>;
  }

  function handleChallenge() {
    dispatchChallenge({
      ref: { backend: 'registry', registry_key: 'challenge' },
      kwargs: { target: personaId },
    })
      .then(() => queryClient.invalidateQueries({ queryKey: combatKeys.duelChallengesAll() }))
      .catch(() => {});
  }

  return (
    <>
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <button className="cursor-pointer font-medium hover:underline">{children}</button>
        </DropdownMenuTrigger>
        <DropdownMenuContent>
          <DropdownMenuLabel>Actions on {personaName}</DropdownMenuLabel>
          <DropdownMenuSeparator />
          {canChallenge && (
            <>
              <DropdownMenuItem
                disabled={isChallengePending}
                data-testid="challenge-to-duel-item"
                onClick={handleChallenge}
              >
                <Swords className="mr-2 h-4 w-4" />
                Challenge to a duel
              </DropdownMenuItem>
              {targetedActions.length > 0 && <DropdownMenuSeparator />}
            </>
          )}
          {/* Direct execute: fires the action immediately via REST, independent of
            any pose in the composer. This is a "quick action" path. The submenu
            picks the audience (#903); the plain "Default" entry sends NO delivery
            so the backend's template default stays the single fallback authority. */}
          {targetedActions.map((action) => {
            const stableKey = `${action.ref.backend}-${action.ref.challenge_instance_id ?? ''}-${action.ref.approach_id ?? ''}-${action.ref.registry_key ?? ''}`;
            if (!action.prerequisite_met) {
              return disabledActionItem(action, stableKey);
            }
            const techniqueId = action.ref.technique_id ?? undefined;
            const actionKey =
              action.ref.registry_key ??
              action.action_template?.name.toLowerCase() ??
              action.display_name.toLowerCase();
            const fire = (delivery?: string) =>
              performAction.mutate({
                action_key: actionKey,
                target_persona_id: personaId,
                technique_id: techniqueId,
                delivery,
              });
            const defaultDelivery = action.action_template?.default_delivery ?? 'pose';
            return (
              <DropdownMenuSub key={stableKey}>
                <DropdownMenuSubTrigger disabled={performAction.isPending}>
                  <Zap className="mr-2 h-4 w-4" />
                  {action.display_name}
                </DropdownMenuSubTrigger>
                <DropdownMenuSubContent>
                  <DropdownMenuItem disabled={performAction.isPending} onClick={() => fire()}>
                    Default ({defaultDelivery.replace('_', ' ')})
                  </DropdownMenuItem>
                  <DropdownMenuItem disabled={performAction.isPending} onClick={() => fire('pose')}>
                    Openly (whole room)
                  </DropdownMenuItem>
                  <DropdownMenuItem
                    disabled={performAction.isPending}
                    onClick={() => fire('whisper')}
                  >
                    Subtly (target only)
                  </DropdownMenuItem>
                  {whisperCandidates.length > 0 && (
                    <DropdownMenuItem
                      disabled={performAction.isPending}
                      onClick={() => setPendingWhisper({ actionKey, techniqueId })}
                    >
                      Subtly (choose listeners…)
                    </DropdownMenuItem>
                  )}
                  <DropdownMenuItem
                    disabled={performAction.isPending}
                    onClick={() => fire('table_talk')}
                  >
                    At your table
                  </DropdownMenuItem>
                </DropdownMenuSubContent>
              </DropdownMenuSub>
            );
          })}
          {/* Attach to Pose: stores the action in the composer so it is submitted
            alongside the next pose. Visually separated from the direct execute items. */}
          {onAttachAction && targetedActions.length > 0 && (
            <>
              <DropdownMenuSeparator />
              <DropdownMenuLabel className="text-xs">Attach to Pose</DropdownMenuLabel>
              {targetedActions.map((action) => {
                const stableKey = `attach-${action.ref.backend}-${action.ref.challenge_instance_id ?? ''}-${action.ref.approach_id ?? ''}-${action.ref.registry_key ?? ''}`;
                if (!action.prerequisite_met) {
                  return disabledActionItem(action, stableKey);
                }
                const techniqueId = action.ref.technique_id ?? undefined;
                const actionKey =
                  action.ref.registry_key ??
                  action.action_template?.name.toLowerCase() ??
                  action.display_name.toLowerCase();
                return (
                  <DropdownMenuItem
                    key={stableKey}
                    onClick={() =>
                      onAttachAction({
                        actionKey,
                        name: action.display_name,
                        target: personaName,
                        requiresTarget: true,
                        techniqueId,
                        targetPersonaId: personaId,
                      })
                    }
                  >
                    <Zap className="mr-2 h-4 w-4" />
                    {action.display_name}
                  </DropdownMenuItem>
                );
              })}
            </>
          )}
          {canModerate && (
            <>
              <DropdownMenuSeparator />
              <DropdownMenuItem
                disabled={createMute.isPending}
                data-testid="mute-persona-item"
                onClick={() =>
                  createMute.mutate({ muted_persona: personaId, mute_ic: true, mute_ooc: true })
                }
              >
                <VolumeX className="mr-2 h-4 w-4" />
                Mute
              </DropdownMenuItem>
              <DropdownMenuItem
                disabled={blockerPersonaId === null}
                data-testid="block-persona-item"
                onClick={() => setBlockDialogOpen(true)}
              >
                <Ban className="mr-2 h-4 w-4" />
                Block…
              </DropdownMenuItem>
            </>
          )}
          {canTreat && (
            <>
              <DropdownMenuSeparator />
              <DropdownMenuItem
                data-testid="treat-persona-item"
                onClick={() => setTreatDialogOpen(true)}
              >
                <HeartPulse className="mr-2 h-4 w-4" />
                Treat…
              </DropdownMenuItem>
            </>
          )}
          {canGiveMission && (
            <>
              <DropdownMenuSeparator />
              <DropdownMenuItem
                data-testid="give-mission-item"
                onClick={() => setGiveMissionOpen(true)}
              >
                <ScrollText className="mr-2 h-4 w-4" />
                Give mission…
              </DropdownMenuItem>
            </>
          )}
        </DropdownMenuContent>
      </DropdownMenu>
      <Dialog open={blockDialogOpen} onOpenChange={setBlockDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Block {personaName}?</DialogTitle>
            <DialogDescription>
              You won't see or be targeted by them. Unblocking takes a full cron cycle to clear, so
              this is deliberate — a reason is required and goes to staff.
            </DialogDescription>
          </DialogHeader>
          <Textarea
            value={blockReason}
            onChange={(e) => setBlockReason(e.target.value)}
            placeholder="Why are you blocking them?"
            data-testid="block-reason-input"
          />
          <DialogFooter>
            <Button variant="outline" onClick={() => setBlockDialogOpen(false)}>
              Cancel
            </Button>
            <Button
              variant="destructive"
              disabled={createBlock.isPending || blockReason.trim() === ''}
              onClick={submitBlock}
              data-testid="confirm-block-button"
            >
              Block
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
      <Dialog open={treatDialogOpen} onOpenChange={setTreatDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Offer treatment to {personaName}</DialogTitle>
            <DialogDescription>
              Offer to treat one of their conditions or alterations. They will be asked to accept
              before anything takes effect.
            </DialogDescription>
          </DialogHeader>
          <TreatActionPanel sceneId={sceneId} targetPersonaId={personaId} />
          <DialogFooter>
            <Button variant="outline" onClick={() => setTreatDialogOpen(false)}>
              Close
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
      <WhisperReceiverPicker
        open={pendingWhisper !== null}
        onClose={() => setPendingWhisper(null)}
        targetName={personaName}
        candidates={whisperCandidates}
        onConfirm={(receiverIds) => {
          if (pendingWhisper !== null) {
            performAction.mutate({
              action_key: pendingWhisper.actionKey,
              target_persona_id: personaId,
              technique_id: pendingWhisper.techniqueId,
              delivery: 'whisper',
              // Include the target so it still hears, plus the chosen listeners.
              delivery_receiver_ids: [personaId, ...receiverIds],
            });
          }
          setPendingWhisper(null);
        }}
      />
      <GiveMissionDialog
        open={giveMissionOpen}
        onOpenChange={setGiveMissionOpen}
        targetPersonaId={personaId}
        targetPersonaName={personaName}
      />
    </>
  );
}
