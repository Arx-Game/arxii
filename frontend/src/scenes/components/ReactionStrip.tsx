/**
 * ReactionStrip (#904) — quiet, pull-not-push reaction affordance on a scene
 * event's card. Renders one row per open (or settled, read-only) reaction
 * window: a chip per choice with its count; the viewer's own reaction is
 * highlighted. One tap reacts; settled windows render counts only.
 */
import { useMemo } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useAppSelector } from '@/store/hooks';
import { useMyRosterEntriesQuery } from '@/roster/queries';
import { reactToWindow } from '../queries';
import type { ReactionWindowPayload } from '../types';

interface ReactionStripProps {
  windows: ReactionWindowPayload[];
  sceneId: string;
}

export function ReactionStrip({ windows, sceneId }: ReactionStripProps) {
  const queryClient = useQueryClient();
  // Resolve the viewer's acting persona (mirrors PersonaContextMenu).
  const activeCharacterName = useAppSelector((state) => state.game.active);
  const { data: myRosterEntries = [] } = useMyRosterEntriesQuery();
  const personaId = useMemo(
    () => myRosterEntries.find((e) => e.name === activeCharacterName)?.primary_persona_id ?? null,
    [myRosterEntries, activeCharacterName]
  );
  const mutation = useMutation({
    mutationFn: ({ windowId, choice }: { windowId: number; choice: string }) =>
      reactToWindow(windowId, { persona_id: personaId as number, choice }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['scene-interactions', sceneId] }),
  });

  if (windows.length === 0) return null;

  return (
    <div data-testid="reaction-strip" className="mt-1 flex flex-col gap-1">
      {windows.map((window) => {
        const canReact = window.is_open && personaId != null && window.my_reaction == null;
        return (
          <div key={window.id} className="flex flex-wrap items-center gap-1">
            {window.choices.map((choice) => {
              const count = window.counts[choice.slug] ?? 0;
              const isMine = window.my_reaction === choice.slug;
              const reactorNames = window.reactions
                .filter((r) => r.choice === choice.slug)
                .map((r) => r.persona_name)
                .join(', ');
              return (
                <button
                  key={choice.slug}
                  type="button"
                  title={reactorNames || choice.label}
                  disabled={!canReact || mutation.isPending}
                  onClick={() => mutation.mutate({ windowId: window.id, choice: choice.slug })}
                  className={`rounded-full border px-2 py-0.5 text-xs transition-colors ${
                    isMine
                      ? 'border-amber-500 bg-amber-500/10 font-medium'
                      : canReact
                        ? 'border-muted-foreground/30 hover:border-amber-500/60'
                        : 'border-muted-foreground/20 opacity-60'
                  }`}
                >
                  {choice.label}
                  {count > 0 ? ` ${count}` : ''}
                </button>
              );
            })}
            {!window.is_open && (
              <span className="text-xs text-muted-foreground">(scene closed)</span>
            )}
          </div>
        );
      })}
    </div>
  );
}
