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

import { useState } from 'react';
import { ChevronDown } from 'lucide-react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { cn } from '@/lib/utils';
import { useViewerPersonaId } from '@/roster/persona';
import { excerptOf } from '@/lib/formatParser';
import { PersonaAvatar } from '@/components/PersonaAvatar';
import { FormattedContent } from '@/components/FormattedContent';
import { Badge } from '@/components/ui/badge';
import { NominateButton } from '@/components/NominateButton';
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
  // #3294 — no companion art exists; the owner's own thumbnail stands in even
  // when the companion is the displayed actor (see PoseUnitActorLabel).
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
// Companion attribution (#3294)
// ---------------------------------------------------------------------------

interface PoseUnitActorLabelProps {
  interaction: Interaction;
  onAddTarget?: (personaName: string) => void;
}

/**
 * The pose's displayed actor name (#3294): the bonded companion when the pose
 * carries `attributed_companion`, else the writer's own (already per-viewer
 * resolved) persona name. A companion pose always shows an owner tell next to
 * the name — honest puppetry, never a hidden actor. Double-click-to-target
 * still names the owner's own persona (`interaction.persona.name`), since a
 * companion has no targetable Persona of its own.
 */
function PoseUnitActorLabel({ interaction, onAddTarget }: PoseUnitActorLabelProps) {
  const companion = interaction.attributed_companion;
  const displayName = companion ? companion.name : interaction.persona.name;
  return (
    <span
      onDoubleClick={() => onAddTarget?.(interaction.persona.name)}
      className="cursor-pointer text-sm font-medium"
      title="Double-click to add as target"
    >
      {displayName}
      {companion && (
        <span
          className="ml-1 text-xs font-normal text-muted-foreground"
          title={`Puppeted by ${interaction.persona.name}`}
          data-testid="companion-owner-tell"
        >
          (via {interaction.persona.name})
        </span>
      )}
    </span>
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
          title={valenceTitle(entry.valence)}
          onClick={() => reactionMutation.mutate(entry.emoji)}
        >
          {entry.emoji}
        </button>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Parent-reply chip (#3787 demo Screen 2)
// ---------------------------------------------------------------------------

/**
 * "Answering "<excerpt>"" — the parent chip. Replaces the placeholder
 * `Replying to pose {id}` now that `interaction.reply_to` carries real data
 * (#3787 Tasks 1-2). Clicking it reveals the parent's content in place,
 * matching the demo's "reveal-in-place" affordance.
 *
 * The chip NEVER re-derives an actor: both the quoted excerpt and the
 * revealed block below show only `parent.content` (already the exact,
 * per-viewer-rendered text the reader elsewhere shows for that row), never
 * `parent.persona.name`. That is what keeps it safe on a concealed working —
 * the line stays exactly as unattributed as it already was.
 */
function ParentChip({
  replyTo,
  parent,
}: {
  replyTo: { id: string; timestamp: string };
  parent: Interaction | undefined;
}) {
  const [revealed, setRevealed] = useState(false);
  return (
    <div className="mt-1" data-testid="parent-reference">
      <button
        type="button"
        className="block w-full rounded-r border-l-2 border-primary/50 px-2 py-1 text-left text-xs text-muted-foreground transition-colors hover:text-primary"
        onClick={() => setRevealed((v) => !v)}
        aria-expanded={revealed}
        data-testid={`parent-chip-${replyTo.id}`}
      >
        Answering{' '}
        {parent ? (
          <span className="italic text-foreground">&ldquo;{excerptOf(parent.content)}&rdquo;</span>
        ) : (
          <span className="italic">a pose not currently loaded</span>
        )}
      </button>
      {revealed && parent && (
        <div
          className="ml-2 mt-1 rounded border border-dashed px-2 py-1 text-xs"
          data-testid={`parent-reveal-${replyTo.id}`}
        >
          <FormattedContent content={parent.content} />
        </div>
      )}
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
  /** Historical readers must not mount mutation controls. */
  readOnly?: boolean;
  /**
   * Lookup for resolving `interaction.reply_to` to its parent Interaction
   * (#3787) — `reply_to` itself carries only `{id, timestamp}` (a thread
   * selector, not the parent's content), so the parent chip's quoted
   * excerpt needs the full row. Built once by the caller that already holds
   * every loaded interaction (`ThreadedNarrativeReader.tsx`) rather than
   * fetched per-pose. Absent/a miss (the parent isn't in the currently
   * loaded window) degrades to a chip with no quote, never a fetch.
   */
  interactionsById?: ReadonlyMap<number, Interaction>;
}

/** Why a reaction chip nudges your regard, shown on hover. */
function valenceTitle(valence: number): string | undefined {
  if (valence > 0) return 'Warms your regard for the author';
  if (valence < 0) return 'Cools your regard for the author';
  return undefined;
}

export function PoseUnit({
  interaction,
  sceneId,
  onAddTarget,
  onAttachAction,
  canGm = false,
  onAvatarClick,
  readOnly = false,
  interactionsById,
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
  // NominateButton has no self-guard of its own (the backend refuses your own
  // characters; this gate is UX only), so PoseUnit computes it and decides
  // whether to mount (#3738). #3787: this is now `useViewerPersonaId()`, the
  // single extracted source of truth also used by `ThreadedNarrativeReader`'s
  // involvement mark — do not add a second inline computation here.
  const viewerPersonaId = useViewerPersonaId();
  const isSelfPose = viewerPersonaId != null && interaction.persona.id === viewerPersonaId;
  const canNominate = Boolean(sceneId) && !isSelfPose;

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
          {!readOnly && <ReactionsFooter interaction={interaction} sceneId={sceneId} />}
          {!readOnly && canNominate && (
            <NominateButton
              targetType="interaction"
              targetId={interaction.id}
              nomineeName={interaction.persona.name}
            />
          )}
        </div>
        {/* Standalone ACTION rows are authored content (claimed resonances) and
            are endorsable per spec — this is intentional, not a slip. */}
        {!readOnly && (
          <EndorsementControl interaction={interaction} sceneId={sceneId} kind="pose" />
        )}
        {interaction.pose_kind === 'entry' && !readOnly && (
          <EndorsementControl interaction={interaction} sceneId={sceneId} kind="entry" />
        )}
        {!readOnly && (
          <EndorsementControl interaction={interaction} sceneId={sceneId} kind="style" />
        )}
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
        {readOnly ? (
          <PoseUnitActorLabel interaction={interaction} />
        ) : (
          <PersonaContextMenu
            personaId={interaction.persona.id}
            personaName={interaction.persona.name}
            sceneId={sceneId}
            onAttachAction={onAttachAction}
          >
            <PoseUnitActorLabel interaction={interaction} onAddTarget={onAddTarget} />
          </PersonaContextMenu>
        )}
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

      {interaction.reply_to && (
        <ParentChip
          replyTo={interaction.reply_to}
          parent={interactionsById?.get(Number(interaction.reply_to.id))}
        />
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

      {!readOnly && (
        <ReactionStrip
          windows={interaction.reaction_windows ?? []}
          sceneId={sceneId}
          interactionId={interaction.id}
        />
      )}

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
      {canGm && !readOnly && (
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
      {canGm && !readOnly && (
        <DramaticMomentSuggestionChip suggestions={dramaticSuggestions} sceneId={sceneId} />
      )}

      <div className="flex items-center gap-1">
        {!readOnly && <ReactionsFooter interaction={interaction} sceneId={sceneId} />}
        {!readOnly && canNominate && (
          <NominateButton
            targetType="interaction"
            targetId={interaction.id}
            nomineeName={interaction.persona.name}
          />
        )}
      </div>
      {!readOnly && <EndorsementControl interaction={interaction} sceneId={sceneId} kind="pose" />}
      {interaction.pose_kind === 'entry' && !readOnly && (
        <EndorsementControl interaction={interaction} sceneId={sceneId} kind="entry" />
      )}
      {!readOnly && <EndorsementControl interaction={interaction} sceneId={sceneId} kind="style" />}
    </div>
  );
}
