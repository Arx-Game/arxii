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
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { cn } from '@/lib/utils';
import { PersonaAvatar } from '@/components/PersonaAvatar';
import { FormattedContent } from '@/components/FormattedContent';
import { Badge } from '@/components/ui/badge';
import { PersonaContextMenu } from './PersonaContextMenu';
import { ActionResult } from './ActionResult';
import { ReactionStrip } from './ReactionStrip';
import { DramaticMomentTagDialog } from './DramaticMomentTagDialog';
import { EndorsementControl } from './EndorsementControl';
import { postInteractionReaction } from '../queries';
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
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['scene-interactions', sceneId] }),
  });

  return (
    <div className="mt-1 flex gap-2">
      {interaction.reactions.map((r) => (
        <button key={r.emoji} className="text-sm" onClick={() => reactionMutation.mutate(r.emoji)}>
          {r.emoji} {r.count}
        </button>
      ))}
      <button className="text-sm" onClick={() => reactionMutation.mutate('\u{1F44D}')}>
        {'\u{1F44D}'}
      </button>
    </div>
  );
}

// ---------------------------------------------------------------------------
// PoseUnit
// ---------------------------------------------------------------------------

export interface PoseUnitProps {
  interaction: Interaction;
  sceneId: string;
  onAddTarget?: (personaName: string) => void;
  onAttachAction?: (action: ActionAttachmentInfo) => void;
  /** When true, shows the "Tag dramatic moment" GM control (#1139). */
  canGm?: boolean;
}

export function PoseUnit({
  interaction,
  sceneId,
  onAddTarget,
  onAttachAction,
  canGm = false,
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

  // -------------------------------------------------------------------------
  // State 3: standalone ACTION (not linked to any pose)
  // -------------------------------------------------------------------------
  if (isAction) {
    return (
      <div className="border-b py-2" data-testid="pose-unit-action-standalone">
        <div className="flex items-center gap-2">
          <PersonaAvatar
            source={{
              name: interaction.persona.name,
              thumbnailUrl: interaction.persona.thumbnail_url,
            }}
            size="sm"
          />
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
        <ReactionsFooter interaction={interaction} sceneId={sceneId} />
        {/* Standalone ACTION rows are authored content (claimed resonances) and
            are endorsable per spec — this is intentional, not a slip. */}
        <EndorsementControl interaction={interaction} sceneId={sceneId} kind="pose" />
        {interaction.pose_kind === 'entry' && (
          <EndorsementControl interaction={interaction} sceneId={sceneId} kind="entry" />
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
        className="border-b py-1.5 pl-2 text-sm italic text-muted-foreground"
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
    <div className="border-b py-2" data-testid="pose-unit">
      {/* Header: avatar + name + timestamp */}
      <div className="flex items-center gap-2">
        <PersonaAvatar
          source={{
            name: interaction.persona.name,
            thumbnailUrl: interaction.persona.thumbnail_url,
          }}
          size="sm"
        />
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

      <ReactionStrip windows={interaction.reaction_windows ?? []} sceneId={sceneId} />

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

      <ReactionsFooter interaction={interaction} sceneId={sceneId} />
      <EndorsementControl interaction={interaction} sceneId={sceneId} kind="pose" />
      {interaction.pose_kind === 'entry' && (
        <EndorsementControl interaction={interaction} sceneId={sceneId} kind="entry" />
      )}
    </div>
  );
}
