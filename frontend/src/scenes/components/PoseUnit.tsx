/**
 * PoseUnit — combined pose + linked action renderer.
 *
 * Three rendering states per spec §1:
 *   1. POSE with linked actions — header + action chips + prose body + reactions.
 *   2. POSE without linked actions — narrative-only card (existing SceneMessages format).
 *   3. ACTION standalone (not yet linked to any pose) — chip-only card.
 *
 * Phase 9, Task 9.2.
 */

import { useMemo, useState } from 'react';
import { ChevronDown } from 'lucide-react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { cn } from '@/lib/utils';
import { useAppSelector } from '@/store/hooks';
import { useMyRosterEntriesQuery } from '@/roster/queries';
import { PersonaAvatar } from '@/components/PersonaAvatar';
import { FormattedContent } from '@/components/FormattedContent';
import { Badge } from '@/components/ui/badge';
import { VoteButton } from '@/components/VoteButton';
import { PersonaContextMenu } from './PersonaContextMenu';
import { ActionResult } from './ActionResult';
import { ReactionStrip } from './ReactionStrip';
import { DramaticMomentTagDialog } from './DramaticMomentTagDialog';
import { DramaticMomentSuggestionChip } from './DramaticMomentSuggestionChip';
import { EndorsementControl } from './EndorsementControl';
import { fetchReactionEmojiCatalog, postInteractionReaction } from '../queries';
import type { Interaction, ActionLink } from '../types';
import type { ActionAttachmentInfo } from '../actionTypes';
import { PoseUnitDetailPanel } from './PoseUnitDetailPanel';

// ---------------------------------------------------------------------------
// Action chip
// ---------------------------------------------------------------------------

interface ActionChipProps {
  link: ActionLink;
  onExpandRequest: () => void;
}

function ActionChip({ link, onExpandRequest }: ActionChipProps) {
  const { action_interaction } = link;
  return (
    <button
      type="button"
      className={cn(
        'flex items-center gap-1 rounded-full border border-border bg-muted/50 px-2 py-0.5',
        'text-xs text-foreground transition-colors hover:bg-muted'
      )}
      onClick={onExpandRequest}
      title="Click to expand action details"
    >
      <span className="max-w-[16rem] truncate">{action_interaction.content}</span>
      <ChevronDown className="h-3 w-3 shrink-0 text-muted-foreground" />
    </button>
  );
}

// ---------------------------------------------------------------------------
// Avatar identity affordance (#2156)
// ---------------------------------------------------------------------------

interface PoseUnitAvatarProps {
  interaction: Interaction;
  onAvatarClick?: (persona: PoseUnitAvatarClickPersona) => void;
}

/**
 * Avatar thumbnail in the bubble header. Identity click surface (#2156) — the
 * name stays the PersonaContextMenu action surface; the avatar itself opens
 * the character card. Renders as a plain (non-interactive) avatar when
 * `onAvatarClick` isn't provided.
 */
function PoseUnitAvatar({ interaction, onAvatarClick }: PoseUnitAvatarProps) {
  const avatar = (
    <PersonaAvatar
      source={{
        name: interaction.persona.name,
        thumbnailUrl: interaction.persona.thumbnail_url,
      }}
      size="sm"
    />
  );

  if (!onAvatarClick) {
    return avatar;
  }

  return (
    <button
      type="button"
      aria-label={`View ${interaction.persona.name}`}
      className="rounded-full transition-opacity hover:opacity-80"
      onClick={() =>
        onAvatarClick({
          id: interaction.persona.id,
          name: interaction.persona.name,
          thumbnail_url: interaction.persona.thumbnail_url ?? null,
        })
      }
    >
      {avatar}
    </button>
  );
}

// ---------------------------------------------------------------------------
// Reactions footer (mirrors SceneMessages pattern)
// ---------------------------------------------------------------------------

interface ReactionsFooterProps {
  interaction: Interaction;
  sceneId: string;
}

function ReactionsFooter({ interaction, sceneId }: ReactionsFooterProps) {
  const queryClient = useQueryClient();
  const reactionMutation = useMutation({
    mutationFn: (emoji: string) => postInteractionReaction(interaction.id, emoji),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['scene-interactions', sceneId] });
      if (data?.bump_message) {
        toast.success(data.bump_message);
      }
    },
  });
  // Staff-editable catalog (#1699); valenced entries also nudge the author's regard.
  const { data: catalog } = useQuery({
    queryKey: ['reaction-emoji'],
    queryFn: fetchReactionEmojiCatalog,
    staleTime: 5 * 60 * 1000,
  });
  const existing = new Set(interaction.reactions.map((r) => r.emoji));
  const pickerEntries = (catalog ?? []).filter((entry) => !existing.has(entry.emoji));

  return (
    <div className="mt-1 flex gap-2">
      {interaction.reactions.map((r) => (
        <button key={r.emoji} className="text-sm" onClick={() => reactionMutation.mutate(r.emoji)}>
          {r.emoji} {r.count}
        </button>
      ))}
      {pickerEntries.map((entry) => (
        <button
          key={entry.emoji}
          className="text-sm opacity-60 transition-opacity hover:opacity-100"
          title={
            entry.valence > 0
              ? 'Warms your regard for the author'
              : entry.valence < 0
                ? 'Cools your regard for the author'
                : undefined
          }
          onClick={() => reactionMutation.mutate(entry.emoji)}
        >
          {entry.emoji}
        </button>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// PoseUnit
// ---------------------------------------------------------------------------

/** Minimal persona identity payload forwarded by the avatar-click affordance (#2156). */
export interface PoseUnitAvatarClickPersona {
  id: number;
  name: string;
  thumbnail_url: string | null;
}

export interface PoseUnitProps {
  interaction: Interaction;
  sceneId: string;
  onAddTarget?: (personaName: string) => void;
  onAttachAction?: (action: ActionAttachmentInfo) => void;
  /** When true, shows the "Tag dramatic moment" GM control (#1139). */
  canGm?: boolean;
  /**
   * Avatar-click identity affordance (#2156): fired with the interaction's
   * persona when the avatar thumbnail is clicked. The avatar renders as a
   * plain (non-interactive) image when this prop is absent — the name's
   * PersonaContextMenu remains the action surface either way.
   */
  onAvatarClick?: (persona: PoseUnitAvatarClickPersona) => void;
}

export function PoseUnit({
  interaction,
  sceneId,
  onAddTarget,
  onAttachAction,
  canGm = false,
  onAvatarClick,
}: PoseUnitProps) {
  const isAction = interaction.mode === 'action';
  const actionLinks = interaction.action_links ?? [];
  const hasLinks = actionLinks.length > 0;

  // Auto-expand on first paint when a linked action had a critical outcome
  // (e.g. it defeated its focused opponent) so players don't miss it (#996).
  const [expanded, setExpanded] = useState(() => actionLinks.some((l) => l.has_critical_effect));
  const [tagDialogOpen, setTagDialogOpen] = useState(false);

  const actionInteractionIds = actionLinks.map((l) => l.action_interaction.id);
  const dramaticTags = interaction.dramatic_moment_tags ?? [];
  const dramaticSuggestions = interaction.dramatic_moment_suggestions ?? [];

  // Resolve the viewer's active persona to detect self-pose — mirrors
  // EndorsementControl's self-endorsement guard (same signal, same source).
  // VoteButton has no self-guard of its own (the backend rejects self-votes;
  // this gate is UX only), so PoseUnit computes it and decides whether to mount.
  const activeCharacterName = useAppSelector((state) => state.game.active);
  const { data: myRosterEntries = [] } = useMyRosterEntriesQuery();
  const viewerPersonaId = useMemo(
    () => myRosterEntries.find((e) => e.name === activeCharacterName)?.primary_persona_id ?? null,
    [myRosterEntries, activeCharacterName]
  );
  const isSelfPose = viewerPersonaId != null && interaction.persona.id === viewerPersonaId;
  const canVote = Boolean(sceneId) && !isSelfPose;

  // -------------------------------------------------------------------------
  // State 3: standalone ACTION (not linked to any pose)
  // -------------------------------------------------------------------------
  if (isAction) {
    return (
      <div
        className="my-1.5 max-w-[85%] rounded-lg bg-muted/40 px-3 py-2"
        data-testid="pose-unit-action-standalone"
      >
        <div className="flex items-center gap-2">
          <PoseUnitAvatar interaction={interaction} onAvatarClick={onAvatarClick} />
          <PersonaContextMenu
            personaId={interaction.persona.id}
            personaName={interaction.persona.name}
            sceneId={sceneId}
            onAttachAction={onAttachAction}
          >
            <span
              onDoubleClick={() => onAddTarget?.(interaction.persona.name)}
              className="cursor-pointer text-sm font-medium"
              title="Double-click to add as target"
            >
              {interaction.persona.name}
            </span>
          </PersonaContextMenu>
          <span className="text-xs text-muted-foreground">
            {new Date(interaction.timestamp).toLocaleString()}
          </span>
        </div>
        <div className="mt-1">
          <ActionResult content={interaction.content} />
        </div>
        <button
          type="button"
          className="mt-1 flex items-center gap-1 text-xs text-muted-foreground transition-colors hover:text-foreground"
          onClick={() => setExpanded((v) => !v)}
          data-testid="standalone-action-expand"
          title="Click to expand action details"
        >
          <ChevronDown
            className={cn('h-3 w-3 shrink-0 transition-transform', expanded && 'rotate-180')}
          />
          details
        </button>
        {expanded && <PoseUnitDetailPanel actionInteractionIds={[interaction.id]} />}
        <div className="flex items-center gap-1">
          <ReactionsFooter interaction={interaction} sceneId={sceneId} />
          {canVote && <VoteButton targetType="interaction" targetId={interaction.id} />}
        </div>
        {/* Standalone ACTION rows are authored content (claimed resonances) and
            are endorsable per spec — this is intentional, not a slip. */}
        <EndorsementControl interaction={interaction} sceneId={sceneId} kind="pose" />
        {interaction.pose_kind === 'entry' && (
          <EndorsementControl interaction={interaction} sceneId={sceneId} kind="entry" />
        )}
        <EndorsementControl interaction={interaction} sceneId={sceneId} kind="style" />
      </div>
    );
  }

  // -------------------------------------------------------------------------
  // OUTCOME: combat result narration — authored by the Narrator, not a
  // targetable character, so no avatar / context menu / target affordance.
  // -------------------------------------------------------------------------
  if (interaction.mode === 'outcome') {
    return (
      <div
        className="my-1 pl-2 text-sm italic text-muted-foreground"
        data-testid="pose-unit-outcome"
      >
        <FormattedContent content={interaction.content} />
      </div>
    );
  }

  // -------------------------------------------------------------------------
  // State 1 + 2: POSE (with or without linked actions)
  // -------------------------------------------------------------------------
  return (
    <div className="my-1.5 max-w-[85%] rounded-lg bg-muted/40 px-3 py-2" data-testid="pose-unit">
      {/* Header: avatar + name + timestamp */}
      <div className="flex items-center gap-2">
        <PoseUnitAvatar interaction={interaction} onAvatarClick={onAvatarClick} />
        <PersonaContextMenu
          personaId={interaction.persona.id}
          personaName={interaction.persona.name}
          sceneId={sceneId}
          onAttachAction={onAttachAction}
        >
          <span
            onDoubleClick={() => onAddTarget?.(interaction.persona.name)}
            className="cursor-pointer text-sm font-medium"
            title="Double-click to add as target"
          >
            {interaction.persona.name}
          </span>
        </PersonaContextMenu>
        <span className="text-xs text-muted-foreground">
          {new Date(interaction.timestamp).toLocaleString()}
        </span>
      </div>

      {/* Action chips (state 1 only) */}
      {hasLinks && (
        <div className="mt-1.5 flex flex-wrap gap-1.5" data-testid="action-chips">
          {actionLinks.map((link) => (
            <ActionChip key={link.id} link={link} onExpandRequest={() => setExpanded((v) => !v)} />
          ))}
        </div>
      )}

      {/* Prose body */}
      <div className="mt-1">
        <p>
          <FormattedContent content={interaction.content} />
        </p>
      </div>

      {/* Expandable outcome detail panel */}
      {expanded && actionInteractionIds.length > 0 && (
        <PoseUnitDetailPanel actionInteractionIds={actionInteractionIds} />
      )}

      <ReactionStrip
        windows={interaction.reaction_windows ?? []}
        sceneId={sceneId}
        interactionId={interaction.id}
      />

      {/* Dramatic-moment tag badges (#1139) */}
      {dramaticTags.length > 0 && (
        <div className="mt-1 flex flex-wrap gap-1" data-testid="dramatic-moment-badges">
          {dramaticTags.map((tag) => (
            <Badge
              key={`${tag.moment_type_label}-${tag.character_sheet_id ?? 'none'}`}
              variant="secondary"
              className="text-xs"
            >
              ✶ {tag.moment_type_label}
            </Badge>
          ))}
        </div>
      )}

      {/* GM control: tag a dramatic moment (#1139) */}
      {canGm && (
        <div className="mt-1">
          <button
            type="button"
            className="text-xs text-muted-foreground transition-colors hover:text-foreground"
            onClick={() => setTagDialogOpen(true)}
            data-testid="tag-moment-button"
          >
            ✶ Tag moment
          </button>
          <DramaticMomentTagDialog
            open={tagDialogOpen}
            onClose={() => setTagDialogOpen(false)}
            interactionId={interaction.id}
            sceneId={sceneId}
          />
        </div>
      )}

      {/* GM confirm/dismiss inbox: technique-driven dramatic-moment suggestions (#2183) */}
      {canGm && (
        <DramaticMomentSuggestionChip suggestions={dramaticSuggestions} sceneId={sceneId} />
      )}

      <div className="flex items-center gap-1">
        <ReactionsFooter interaction={interaction} sceneId={sceneId} />
        {canVote && <VoteButton targetType="interaction" targetId={interaction.id} />}
      </div>
      <EndorsementControl interaction={interaction} sceneId={sceneId} kind="pose" />
      {interaction.pose_kind === 'entry' && (
        <EndorsementControl interaction={interaction} sceneId={sceneId} kind="entry" />
      )}
      <EndorsementControl interaction={interaction} sceneId={sceneId} kind="style" />
    </div>
  );
}
