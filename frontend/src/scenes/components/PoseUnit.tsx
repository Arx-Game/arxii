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
import { PersonaContextMenu } from './PersonaContextMenu';
import { ActionResult } from './ActionResult';
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
      className={cn(
        'flex items-center gap-1 rounded-full border border-border bg-muted/50 px-2 py-0.5',
        'text-xs text-foreground hover:bg-muted transition-colors',
      )}
      onClick={onExpandRequest}
      title="Click to expand action details"
    >
      <span className="truncate max-w-[16rem]">{action_interaction.content}</span>
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
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: ['scene-interactions', sceneId] }),
  });

  return (
    <div className="mt-1 flex gap-2">
      {interaction.reactions.map((r) => (
        <button
          key={r.emoji}
          className="text-sm"
          onClick={() => reactionMutation.mutate(r.emoji)}
        >
          {r.emoji} {r.count}
        </button>
      ))}
      <button
        className="text-sm"
        onClick={() => reactionMutation.mutate('\u{1F44D}')}
      >
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
}

export function PoseUnit({ interaction, sceneId, onAddTarget, onAttachAction }: PoseUnitProps) {
  const [expanded, setExpanded] = useState(false);

  const isAction = interaction.mode === 'action';
  const actionLinks = interaction.action_links ?? [];
  const hasLinks = actionLinks.length > 0;

  const actionInteractionIds = actionLinks.map((l) => l.action_interaction.id);

  // -------------------------------------------------------------------------
  // State 3: standalone ACTION (not linked to any pose)
  // -------------------------------------------------------------------------
  if (isAction) {
    return (
      <div className="border-b py-2" data-testid="pose-unit-action-standalone">
        <div className="flex items-center gap-2">
          <PersonaAvatar
            source={{ name: interaction.persona.name, thumbnailUrl: interaction.persona.thumbnail_url }}
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
        <ReactionsFooter interaction={interaction} sceneId={sceneId} />
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
          source={{ name: interaction.persona.name, thumbnailUrl: interaction.persona.thumbnail_url }}
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
            <ActionChip
              key={link.id}
              link={link}
              onExpandRequest={() => setExpanded((v) => !v)}
            />
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

      <ReactionsFooter interaction={interaction} sceneId={sceneId} />
    </div>
  );
}
