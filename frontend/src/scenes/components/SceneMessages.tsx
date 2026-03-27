import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useRef } from 'react';
import { postInteractionReaction } from '../queries';
import type { Interaction } from '../types';
import type { ActionAttachmentInfo } from '../actionTypes';
import { ActionResult } from './ActionResult';
import { FormattedContent } from '@/components/FormattedContent';
import { PersonaContextMenu } from './PersonaContextMenu';

interface Props {
  sceneId: string;
  filteredInteractions: Interaction[];
  onAddTarget?: (personaName: string) => void;
  onAttachAction?: (action: ActionAttachmentInfo) => void;
}

/** Format content based on interaction mode. */
function formatContent(content: string, mode: string) {
  switch (mode) {
    case 'say':
      return (
        <p>
          &ldquo;
          <FormattedContent content={content} />
          &rdquo;
        </p>
      );
    case 'whisper':
      return (
        <p className="italic text-muted-foreground">
          <FormattedContent content={content} />
        </p>
      );
    case 'action':
      return (
        <div className="mt-1">
          <ActionResult content={content} />
        </div>
      );
    default:
      return (
        <p>
          <FormattedContent content={content} />
        </p>
      );
  }
}

export function SceneMessages({
  sceneId,
  filteredInteractions,
  onAddTarget,
  onAttachAction,
}: Props) {
  const queryClient = useQueryClient();
  const interactionIdRef = useRef<number>(0);

  const reactionMutation = useMutation({
    mutationFn: (emoji: string) => postInteractionReaction(interactionIdRef.current, emoji),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['scene-interactions', sceneId] }),
  });

  return (
    <div>
      {filteredInteractions.map((msg) => (
        <div key={msg.id} className="border-b py-2">
          <div className="flex items-center gap-2">
            {msg.persona.thumbnail_url && (
              <img src={msg.persona.thumbnail_url} alt={msg.persona.name} className="h-6 w-6" />
            )}
            <PersonaContextMenu
              personaId={msg.persona.id}
              personaName={msg.persona.name}
              sceneId={sceneId}
              onAttachAction={onAttachAction}
            >
              <span
                onDoubleClick={() => onAddTarget?.(msg.persona.name)}
                className="cursor-pointer"
                title="Double-click to add as target"
              >
                {msg.persona.name}
              </span>
            </PersonaContextMenu>
            <span className="text-xs text-muted-foreground">
              {new Date(msg.timestamp).toLocaleString()}
            </span>
          </div>

          {formatContent(msg.content, msg.mode)}

          <div className="flex gap-2">
            {msg.reactions.map((r) => (
              <button
                key={r.emoji}
                className="text-sm"
                onClick={() => {
                  interactionIdRef.current = msg.id;
                  reactionMutation.mutate(r.emoji);
                }}
              >
                {r.emoji} {r.count}
              </button>
            ))}
            <button
              className="text-sm"
              onClick={() => {
                interactionIdRef.current = msg.id;
                reactionMutation.mutate('\u{1F44D}');
              }}
            >
              {'\u{1F44D}'}
            </button>
          </div>
        </div>
      ))}
    </div>
  );
}
