/**
 * PersonaMenu — the one action menu for "do something to this persona" (#4030).
 *
 * The menu's CONTENT is composed entirely by the server:
 * `GET /api/actions/characters/<characterId>/personas/<personaId>/menu/`
 * (`actions/persona_menu.py`). This component only renders whatever that
 * endpoint returns — no client-side `canX` gating, and no scene cache is read
 * to decide availability. It opens on right-click (a Radix `ContextMenu`,
 * reachable anywhere a persona is rendered) and, optionally, on a left click
 * on its trigger (`leftClick`, today's name-click affordance). It replaces
 * the scene-bound `PersonaContextMenu` and the never-wired `EntityContextMenu`.
 */
import {
  type ComponentType,
  type MouseEventHandler,
  type ReactNode,
  Fragment,
  useMemo,
  useState,
} from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import {
  ContextMenu,
  ContextMenuContent,
  ContextMenuItem,
  ContextMenuLabel,
  ContextMenuSeparator,
  ContextMenuSub,
  ContextMenuSubContent,
  ContextMenuSubTrigger,
  ContextMenuTrigger,
} from '@/components/ui/context-menu';
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
import {
  Award,
  Ban,
  DoorOpen,
  Eye,
  Heart,
  HeartPulse,
  IdCard,
  type LucideIcon,
  Reply,
  ScrollText,
  Shield,
  Swords,
  Umbrella,
  VolumeX,
  Zap,
} from 'lucide-react';
import { useAppSelector } from '@/store/hooks';
import { useMyRosterEntriesQuery } from '@/roster/queries';
import { useDispatchPlayerAction, combatKeys } from '@/combat/queries';
import { isDispatchFailure } from '@/combat/types';
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
import { toast } from 'sonner';
import { PersonaAvatar } from '@/components/PersonaAvatar';
import {
  usePersonaMenuQuery,
  type PersonaMenuData,
  type PersonaMenuItemData,
} from '@/game/persona-menu/personaMenuApi';
import { usePersonaCard } from '@/game/persona-menu/PersonaCardContext';
import { LookDialog } from '@/game/persona-menu/LookDialog';
import { createActionRequest } from '../actionQueries';
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
// execute list and the "Attach to Pose" list below. Not a Radix menu item
// (unchanged from the pre-#4030 component) — it renders identically inside
// either menu.
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

// ---------------------------------------------------------------------------
// MenuKit — the common surface ContextMenu.* and DropdownMenu.* both offer,
// so renderItems() below can draw the same content into either menu.
// ---------------------------------------------------------------------------

interface MenuItemProps {
  children?: ReactNode;
  disabled?: boolean;
  // Radix's ContextMenuItem/DropdownMenuItem both pass an onClick through to
  // an underlying <div>, so the handler receives a MouseEvent<HTMLDivElement>
  // — every caller here ignores it (all pass a plain `() => void`), which is
  // a valid narrower value for this wider handler type.
  onClick?: MouseEventHandler<HTMLDivElement>;
  className?: string;
  title?: string;
}

interface MenuLabelProps {
  children?: ReactNode;
  className?: string;
}

interface MenuSeparatorProps {
  className?: string;
}

interface MenuSubProps {
  children?: ReactNode;
}

interface MenuSubTriggerProps {
  children?: ReactNode;
  disabled?: boolean;
}

interface MenuSubContentProps {
  children?: ReactNode;
}

interface MenuKit {
  Item: ComponentType<MenuItemProps>;
  Label: ComponentType<MenuLabelProps>;
  Separator: ComponentType<MenuSeparatorProps>;
  Sub: ComponentType<MenuSubProps>;
  SubTrigger: ComponentType<MenuSubTriggerProps>;
  SubContent: ComponentType<MenuSubContentProps>;
}

const contextKit: MenuKit = {
  Item: ContextMenuItem,
  Label: ContextMenuLabel,
  Separator: ContextMenuSeparator,
  Sub: ContextMenuSub,
  SubTrigger: ContextMenuSubTrigger,
  SubContent: ContextMenuSubContent,
};

const dropdownKit: MenuKit = {
  Item: DropdownMenuItem,
  Label: DropdownMenuLabel,
  Separator: DropdownMenuSeparator,
  Sub: DropdownMenuSub,
  SubTrigger: DropdownMenuSubTrigger,
  SubContent: DropdownMenuSubContent,
};

// One icon per server item key (#4030). 'look' is drawn separately (always first).
const ITEM_ICONS: Record<string, LucideIcon> = {
  identify: Eye,
  challenge: Swords,
  scene_succor: Umbrella,
  scene_interpose: Shield,
  treat: HeartPulse,
  give_mission: ScrollText,
  // #4091 task 12 left these two items wired with no icon (Task 14 owns
  // frontend). Matches each action's own `icon` metadata (allegiance.py
  // SendAwayAction.icon="door-open", charm_asset.py CharmAssetAction.icon="heart").
  send_away: DoorOpen,
  charm_asset: Heart,
  mute: VolumeX,
  block: Ban,
};

export interface PersonaMenuProps {
  personaId: number;
  personaName: string;
  thumbnailUrl?: string | null;
  children: ReactNode;
  /** When true, `children` also acts as a left-click DropdownMenu trigger (today's name click). */
  leftClick?: boolean;
  /**
   * When false, right-click is left to the caller (#4128: on a pose line the
   * right button is the sorting menu, so the avatar offers only the left-click
   * play menu). Defaults to true: the name's right-click menu as before.
   */
  contextMenu?: boolean;
  /** This pose's own actions (#4128), listed first when the menu opens from a pose. */
  poseActions?: { onReply?: () => void; onKudos?: () => void; kudosDisabled?: boolean };
  onAttachAction?: (action: ActionAttachmentInfo) => void;
}

export function PersonaMenu({
  personaId,
  personaName,
  thumbnailUrl,
  children,
  leftClick = false,
  contextMenu = true,
  poseActions,
  onAttachAction,
}: PersonaMenuProps) {
  const queryClient = useQueryClient();

  // Resolve the active character name to its numeric ObjectDB pk (mirrors the
  // pre-#4030 component) — the character whose menu this is.
  const activeCharacterName = useAppSelector((state) => state.game.active);
  const { data: myRosterEntries = [] } = useMyRosterEntriesQuery();
  const characterId = useMemo(
    () => myRosterEntries.find((e) => e.name === activeCharacterName)?.character_id ?? null,
    [myRosterEntries, activeCharacterName]
  );

  const [open, setOpen] = useState(false);
  const { data, isLoading } = usePersonaMenuQuery(characterId, personaId, open);

  const items: PersonaMenuItemData[] = data?.items ?? [];
  const groups: PersonaMenuData['groups'] = data?.groups ?? [];
  const lookItem = items.find((i) => i.key === 'look');
  const lookAvailable = lookItem?.available ?? true;
  const lookReason = lookItem?.reason ?? '';

  // #4030: the server is the only source of scene identity now — no sceneId
  // prop, and the scene cache is read only when the server says one exists.
  const sceneId = data?.scene_id != null ? String(data.scene_id) : null;
  const sceneCache =
    sceneId !== null ? queryClient.getQueryData<SceneDetail>(['scene', sceneId]) : undefined;

  // #907: present scene personas (excluding the target) are the extra-listener pool.
  const whisperCandidates = useMemo(
    () => (sceneCache?.personas ?? []).filter((p) => p.id !== personaId),
    [sceneCache, personaId]
  );

  // The server's scene_actions carry the generated PlayerAction shape, which
  // drifts from the hand-written frontend/src/scenes/actionTypes.ts PlayerAction
  // this delivery-submenu/Attach-to-Pose code (moved unchanged from the
  // pre-#4030 component) was written against — e.g. position_target_shape is a
  // narrow string union there vs a bare `string` here. Typing scene_actions
  // with the hand-written PlayerAction keeps that code working as-is.
  const sceneActions = (data?.scene_actions ?? []) as unknown as PlayerAction[];

  const [pendingWhisper, setPendingWhisper] = useState<PendingWhisper | null>(null);
  const [blockDialogOpen, setBlockDialogOpen] = useState(false);
  const [blockReason, setBlockReason] = useState('');
  const [treatDialogOpen, setTreatDialogOpen] = useState(false);
  const [giveMissionOpen, setGiveMissionOpen] = useState(false);
  const [lookOpen, setLookOpen] = useState(false);
  const [lookText, setLookText] = useState('');
  const [lookLoading, setLookLoading] = useState(false);

  const personaCard = usePersonaCard();
  const createMute = useCreateMute();
  const createBlock = useCreateBlock();

  const { mutateAsync: dispatchLook } = useDispatchPlayerAction(characterId ?? 0);
  const { mutateAsync: dispatchIdentify, isPending: isIdentifyPending } = useDispatchPlayerAction(
    characterId ?? 0
  );
  const { mutateAsync: dispatchChallenge, isPending: isChallengePending } = useDispatchPlayerAction(
    characterId ?? 0
  );
  const { mutateAsync: dispatchGuard, isPending: isGuardPending } = useDispatchPlayerAction(
    characterId ?? 0
  );
  // #4091 task 12 wired these two items into the menu's `items` list with
  // their own kwargs ({target_persona_id: persona.pk}, plus role_context
  // "contact" for charm_asset) but left no handlerFor case to fire them —
  // a dead click, caught while adding their ITEM_ICONS entries above
  // (fold-in, not filed: CLAUDE.md "Fold In, Don't File").
  const { mutateAsync: dispatchSendAway, isPending: isSendAwayPending } = useDispatchPlayerAction(
    characterId ?? 0
  );
  const { mutateAsync: dispatchCharmAsset, isPending: isCharmAssetPending } =
    useDispatchPlayerAction(characterId ?? 0);

  const performAction = useMutation({
    mutationFn: (params: {
      action_key: string;
      target_persona_id: number;
      technique_id?: number;
      delivery?: string;
      delivery_receiver_ids?: number[];
    }) => createActionRequest(sceneId ?? '', params),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['scene-interactions', sceneId] });
      queryClient.invalidateQueries({ queryKey: ['pending-requests', sceneId] });
    },
  });

  function handleLook() {
    setLookOpen(true);
    setLookLoading(true);
    dispatchLook({
      ref: { backend: 'registry', registry_key: 'look' },
      kwargs: { target_persona_id: personaId },
    })
      .then((result) => {
        if (isDispatchFailure(result)) {
          setLookOpen(false);
          toast.error(result.message ?? "You can't see them from here.");
          return;
        }
        setLookText(result.message ?? '');
      })
      .catch(() => {
        setLookOpen(false);
      })
      .finally(() => setLookLoading(false));
  }

  function handleViewSheet() {
    personaCard?.openCharacterCard({
      id: personaId,
      name: personaName,
      thumbnail_url: thumbnailUrl ?? null,
    });
  }

  // Identify dispatches via the registry path, never the createActionRequest
  // consent pipeline below — it's a no-consent private perception roll
  // (ADR-0024) with no ActionTemplate (#1107 Task 3 review).
  function handleIdentify() {
    dispatchIdentify({
      ref: { backend: 'registry', registry_key: 'identify' },
      kwargs: { target: personaId },
    })
      .then((result) => {
        if (!result.message) return;
        if (result.success) {
          toast.success(result.message);
        } else {
          toast.error(result.message);
        }
      })
      .catch(() => {});
  }

  function handleChallenge() {
    dispatchChallenge({
      ref: { backend: 'registry', registry_key: 'challenge' },
      kwargs: { target: personaId },
    })
      .then((result) => {
        if (isDispatchFailure(result)) {
          toast.error(result.message ?? 'Could not send the challenge.');
          return;
        }
        queryClient.invalidateQueries({ queryKey: combatKeys.duelChallengesAll() }).catch(() => {});
      })
      .catch(() => {});
  }

  // #3448 Succor/Interpose dispatch target_persona_id now (the server resolves
  // the target directly), not the ally_name the pre-#4030 component sent.
  function handleGuard(registryKey: 'scene_succor' | 'scene_interpose') {
    dispatchGuard({
      ref: { backend: 'registry', registry_key: registryKey },
      kwargs: { target_persona_id: personaId },
    })
      .then((result) => {
        if (!result.message) return;
        if (result.success) {
          toast.success(result.message);
        } else {
          toast.error(result.message);
        }
      })
      .catch(() => {});
  }

  // Matches persona_menu.py's own hardcoded kwargs for these two items
  // exactly ({"target_persona_id": persona.pk} / {..., "role_context":
  // "contact"}) — the server never forwards kwargs to the menu payload, so
  // the frontend has to mirror them the same way identify/challenge/
  // scene_succor/scene_interpose already do.
  // On a successful send-away/take-into-service, the persona menu's own
  // availability (its items can change once the hold is gone) and whatever
  // aftermath/rail queries are reading this encounter (#4091 fix round 1,
  // item 4) both need a refetch — not just a toast. `['persona-menu']` is
  // the key prefix `usePersonaMenuQuery` (personaMenuApi.ts) scopes under
  // (no exported key factory exists there to import).
  function invalidateAfterAllegianceAction() {
    queryClient.invalidateQueries({ queryKey: ['persona-menu'] }).catch(() => {});
    queryClient.invalidateQueries({ queryKey: combatKeys.all }).catch(() => {});
  }

  function handleSendAway() {
    dispatchSendAway({
      ref: { backend: 'registry', registry_key: 'send_away' },
      kwargs: { target_persona_id: personaId },
    })
      .then((result) => {
        if (isDispatchFailure(result)) {
          toast.error(result.message ?? 'Could not send them away.');
          return;
        }
        if (result.message) toast.success(result.message);
        invalidateAfterAllegianceAction();
      })
      .catch((err: unknown) => {
        // #4091 fix round 1, item 4: an HTTP-level failure (postDispatchAction
        // throws on non-2xx) used to be swallowed silently here.
        toast.error(err instanceof Error ? err.message : 'Could not send them away.');
      });
  }

  function handleCharmAsset() {
    dispatchCharmAsset({
      ref: { backend: 'registry', registry_key: 'charm_asset' },
      kwargs: { target_persona_id: personaId, role_context: 'contact' },
    })
      .then((result) => {
        if (isDispatchFailure(result)) {
          toast.error(result.message ?? 'Could not take them into service.');
          return;
        }
        if (result.message) toast.success(result.message);
        invalidateAfterAllegianceAction();
      })
      .catch((err: unknown) => {
        toast.error(err instanceof Error ? err.message : 'Could not take them into service.');
      });
  }

  function handleMute() {
    createMute.mutate({
      muted_persona: personaId,
      mute_ic: true,
      mute_ooc: true,
      // #2996: account-first by default.
      account_level: true,
    });
  }

  function submitBlock() {
    if (data?.viewer_persona_id == null || blockReason.trim() === '') {
      return;
    }
    createBlock.mutate(
      {
        blocker_persona: data.viewer_persona_id,
        blocked_persona: personaId,
        reason: blockReason.trim(),
        // #2996 Decision 1: account-first by default -- blocks the target's whole account.
        account_level: true,
      },
      {
        onSettled: () => {
          setBlockDialogOpen(false);
          setBlockReason('');
        },
      }
    );
  }

  function handlerFor(key: string): (() => void) | undefined {
    switch (key) {
      case 'identify':
        return handleIdentify;
      case 'challenge':
        return handleChallenge;
      case 'scene_succor':
        return () => handleGuard('scene_succor');
      case 'scene_interpose':
        return () => handleGuard('scene_interpose');
      case 'send_away':
        return handleSendAway;
      case 'charm_asset':
        return handleCharmAsset;
      case 'treat':
        return () => setTreatDialogOpen(true);
      case 'give_mission':
        return () => setGiveMissionOpen(true);
      case 'mute':
        return handleMute;
      case 'block':
        return () => setBlockDialogOpen(true);
      default:
        return undefined;
    }
  }

  const pendingByKey: Record<string, boolean> = {
    identify: isIdentifyPending,
    challenge: isChallengePending,
    scene_succor: isGuardPending,
    scene_interpose: isGuardPending,
    send_away: isSendAwayPending,
    charm_asset: isCharmAssetPending,
    mute: createMute.isPending,
  };

  function renderMenuItem(kit: MenuKit, item: PersonaMenuItemData) {
    const Icon = ITEM_ICONS[item.key] ?? Zap;
    const disabled = !item.available || (pendingByKey[item.key] ?? false);
    const onClick = disabled ? undefined : handlerFor(item.key);
    return (
      <kit.Item
        key={item.key}
        disabled={disabled}
        title={item.available ? undefined : item.reason || undefined}
        onClick={onClick}
      >
        <Icon className="mr-2 h-4 w-4 shrink-0" />
        <span className="flex-1">{item.label}</span>
        {!item.available && item.reason && (
          <span className="ml-2 text-xs text-muted-foreground">{item.reason}</span>
        )}
      </kit.Item>
    );
  }

  function itemsForGroup(groupKey: string): PersonaMenuItemData[] {
    return items.filter((i) => i.group === groupKey && i.key !== 'look');
  }

  // Direct execute: fires the action immediately via REST, independent of any
  // pose in the composer. This is a "quick action" path, unchanged from the
  // pre-#4030 component — the submenu picks the audience (#903); the plain
  // "Default" entry sends NO delivery so the backend's template default stays
  // the single fallback authority.
  function renderSceneActionSubmenus(kit: MenuKit) {
    return sceneActions.map((action) => {
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
        <kit.Sub key={stableKey}>
          <kit.SubTrigger disabled={performAction.isPending}>
            <Zap className="mr-2 h-4 w-4" />
            {action.display_name}
          </kit.SubTrigger>
          <kit.SubContent>
            <kit.Item disabled={performAction.isPending} onClick={() => fire()}>
              Default ({defaultDelivery.replace('_', ' ')})
            </kit.Item>
            <kit.Item disabled={performAction.isPending} onClick={() => fire('pose')}>
              Openly (whole room)
            </kit.Item>
            <kit.Item disabled={performAction.isPending} onClick={() => fire('whisper')}>
              Subtly (target only)
            </kit.Item>
            {whisperCandidates.length > 0 && (
              <kit.Item
                disabled={performAction.isPending}
                onClick={() => setPendingWhisper({ actionKey, techniqueId })}
              >
                Subtly (choose listeners…)
              </kit.Item>
            )}
            <kit.Item disabled={performAction.isPending} onClick={() => fire('table_talk')}>
              At your table
            </kit.Item>
          </kit.SubContent>
        </kit.Sub>
      );
    });
  }

  // Attach to Pose: stores the action in the composer so it is submitted
  // alongside the next pose. Unchanged from the pre-#4030 component.
  function renderAttachToPose(kit: MenuKit) {
    if (!onAttachAction || sceneActions.length === 0) return null;
    return (
      <>
        <kit.Separator />
        <kit.Label className="text-xs">Attach to Pose</kit.Label>
        {sceneActions.map((action) => {
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
            <kit.Item
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
            </kit.Item>
          );
        })}
      </>
    );
  }

  function renderItems(kit: MenuKit) {
    return (
      <>
        <kit.Label className="flex items-center gap-2 px-2 py-1.5 text-sm font-semibold">
          <PersonaAvatar source={{ name: personaName, thumbnailUrl }} size="sm" />
          <span className="truncate">
            {personaName}
            {/* Demo Screen 1b ("Ysolde (you)") -- the room-sidebar row has its
                own separate "you" tag (CharactersList.tsx); this popup menu's
                header needs its own, since it's a different component. */}
            {data?.is_self && ' (you)'}
          </span>
        </kit.Label>
        {poseActions && (
          <>
            {poseActions.onReply && (
              <kit.Item key="reply" onClick={poseActions.onReply}>
                <Reply className="mr-2 h-4 w-4 shrink-0" />
                Reply
              </kit.Item>
            )}
            {poseActions.onKudos && (
              <kit.Item
                key="kudos"
                disabled={poseActions.kudosDisabled}
                onClick={poseActions.onKudos}
              >
                <Award className="mr-2 h-4 w-4 shrink-0" />
                Kudos
              </kit.Item>
            )}
            <kit.Separator />
          </>
        )}
        <kit.Item
          key="look"
          disabled={!lookAvailable}
          title={lookAvailable ? undefined : lookReason || undefined}
          onClick={lookAvailable ? handleLook : undefined}
        >
          <Eye className="mr-2 h-4 w-4 shrink-0" />
          <span className="flex-1">{lookItem?.label ?? 'Look'}</span>
          {!lookAvailable && lookReason ? (
            <span className="ml-2 text-xs text-muted-foreground">{lookReason}</span>
          ) : (
            // Self menu (demo Screen 1b): a muted reminder that Look, here,
            // previews what everyone else already sees of you.
            data?.is_self && (
              <span className="ml-2 text-xs text-muted-foreground">how others see you</span>
            )
          )}
        </kit.Item>
        <kit.Item key="view-sheet" onClick={handleViewSheet}>
          <IdCard className="mr-2 h-4 w-4 shrink-0" />
          View sheet
        </kit.Item>
        {itemsForGroup('perception').map((item) => renderMenuItem(kit, item))}
        {isLoading && <div className="px-2 py-1.5 text-xs text-muted-foreground">Loading…</div>}
        {!isLoading &&
          groups
            .filter((group) => group.key !== 'perception')
            .map((group) => (
              <Fragment key={`group-${group.key}`}>
                <kit.Separator />
                {itemsForGroup(group.key).map((item) => renderMenuItem(kit, item))}
                {group.key === 'scene' && renderSceneActionSubmenus(kit)}
                {group.key === 'scene' && renderAttachToPose(kit)}
              </Fragment>
            ))}
        {/* Every group's empty_state is a trailing footer line, after ALL
            groups (the demo's closing line) — never inline mid-menu, where
            it would read as belonging only to whichever group happened to
            render it last. */}
        {!isLoading &&
          groups
            .filter((group) => group.empty_state)
            .map((group) => (
              <div key={`empty-${group.key}`} className="px-2 py-1.5 text-xs text-muted-foreground">
                {group.empty_state}
              </div>
            ))}
        {!isLoading && data?.notice && (
          <div className="px-2 py-1.5 text-xs text-muted-foreground">{data.notice}</div>
        )}
      </>
    );
  }

  const trigger = leftClick ? (
    <span className="inline-flex">
      <DropdownMenu onOpenChange={setOpen}>
        <DropdownMenuTrigger asChild>
          <button type="button" className="cursor-pointer font-medium hover:underline">
            {children}
          </button>
        </DropdownMenuTrigger>
        {/* Two independent fixes for opening a Dialog (Look, Block,
                  Treat, Give mission, the whisper picker) from a menu item,
                  both real browser-only (jsdom's synchronous DOM never
                  reproduces either): (1) onCloseAutoFocus -- Radix's
                  default close behavior returns focus to the trigger,
                  landing outside the just-opened Dialog, which the
                  (non-modal, for Look) Dialog's DismissableLayer reads as
                  an outside interaction and dismisses right back. (2) the
                  `!animate-none` override -- Radix's Presence keeps a
                  closing menu's DOM mounted for its whole CSS exit
                  transition (`data-[state=closed]:animate-out`, ~150-200ms:
                  confirmed directly via getComputedStyle in a throwaway
                  Playwright probe -- animationName stays "exit" and the
                  node stays attached from the click until just before
                  250ms) before @radix-ui/react-presence actually unmounts
                  it (it checks getComputedStyle(node).animationName and
                  only unmounts immediately when that reads "none"); the
                  LOOK ITEM ALONE never needed that long a menu (short, one
                  item), so this never mattered until a non-empty group
                  `empty_state` footer (#4030 demo review, round 2 --
                  Screen 1's own "quiet room, no scene" condition, the
                  demo's OWN primary walkthrough) makes the menu tall
                  enough that the still-mounted, still-animating sibling
                  portal interferes with the freshly-opened Dialog's own
                  dismiss detection. A `style` override does NOT work here
                  (tried first, confirmed dead by the same probe):
                  @radix-ui/react-popper's own Content unconditionally
                  resets `style.animation` to `undefined` once positioned
                  (react-popper/dist/index.mjs, PopperContent -- `animation:
                  !isPositioned ? "none" : void 0`), clobbering any inline
                  override every consumer passes. The `!` (Tailwind
                  important) on a CLASS survives that reset, since it never
                  touches the inline `style` object at all. Forcing the
                  exit animation off makes Presence unmount the closing
                  menu SYNCHRONOUSLY instead of ~150-200ms later, removing
                  the coexistence window entirely -- not a guess, and not a
                  timer. */}
        <DropdownMenuContent
          onCloseAutoFocus={(e) => e.preventDefault()}
          className="data-[state=closed]:!animate-none"
        >
          {renderItems(dropdownKit)}
        </DropdownMenuContent>
      </DropdownMenu>
    </span>
  ) : (
    <span className="inline-flex">{children}</span>
  );

  return (
    <>
      {contextMenu ? (
        <ContextMenu onOpenChange={setOpen}>
          <ContextMenuTrigger asChild>{trigger}</ContextMenuTrigger>
          {/* See the matching DropdownMenuContent comment above -- both fixes
              apply identically to the right-click menu. */}
          <ContextMenuContent
            onCloseAutoFocus={(e) => e.preventDefault()}
            className="data-[state=closed]:!animate-none"
          >
            {renderItems(contextKit)}
          </ContextMenuContent>
        </ContextMenu>
      ) : (
        trigger
      )}
      <Dialog open={blockDialogOpen} onOpenChange={setBlockDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Block {personaName}?</DialogTitle>
            <DialogDescription>
              This blocks their whole account — every character they play, not just this one. You
              won't see or be targeted by them. Unblocking takes a full cron cycle to clear, so this
              is deliberate: a reason is required and goes to staff.
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
          <TreatActionPanel sceneId={String(data?.scene_id ?? '')} targetPersonaId={personaId} />
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
      <LookDialog
        open={lookOpen}
        onOpenChange={setLookOpen}
        personaName={personaName}
        thumbnailUrl={thumbnailUrl}
        text={lookText}
        isLoading={lookLoading}
        onViewSheet={handleViewSheet}
      />
    </>
  );
}
