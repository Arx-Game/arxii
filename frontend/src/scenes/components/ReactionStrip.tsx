/**
 * ReactionStrip (#904) — quiet, pull-not-push reaction affordance on a scene
 * event's card. Renders one row per open (or settled, read-only) reaction
 * window: a chip per choice with its count; the viewer's own reaction is
 * highlighted. One tap reacts; settled windows render counts only.
 *
 * Also renders the first-kudos chip (#2031): when no kudos-kind window has
 * been lazily opened on this pose yet, a standalone "Kudos" chip lazily
 * opens one via reactToInteraction. Once a kudos window exists it takes
 * over via the normal per-window row above — no duplicate chip.
 */
import { useMemo } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useAppSelector } from '@/store/hooks';
import { useMyRosterEntriesQuery } from '@/roster/queries';
import { reactToWindow, reactToInteraction } from '../queries';
import type { ReactionWindowPayload } from '../types';

// Matches ReactionWindowKind.KUDOS's wire value (src/world/scenes/constants.py).
const KUDOS_KIND = 'kudos';

interface ReactionStripProps {
  windows: ReactionWindowPayload[];
  sceneId: string;
  interactionId: number;
}

export function ReactionStrip({ windows, sceneId, interactionId }: ReactionStripProps) {
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
  const kudosMutation = useMutation({
    mutationFn: () =>
      reactToInteraction({
        persona_id: personaId as number,
        interaction_id: interactionId,
        kind: KUDOS_KIND,
        choice: KUDOS_KIND,
      }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['scene-interactions', sceneId] }),
  });

  const hasKudosWindow = windows.some((window) => window.kind === KUDOS_KIND);

  if (windows.length === 0 && hasKudosWindow) return null;

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
      {!hasKudosWindow && (
        <div className="flex flex-wrap items-center gap-1">
          <button
            type="button"
            title="Kudos"
            disabled={personaId == null || kudosMutation.isPending}
            onClick={() => kudosMutation.mutate()}
            className={`rounded-full border px-2 py-0.5 text-xs transition-colors ${
              personaId == null
                ? 'border-muted-foreground/20 opacity-60'
                : 'border-muted-foreground/30 hover:border-amber-500/60'
            }`}
          >
            Kudos
          </button>
          {kudosMutation.isError && (
            <span className="text-xs text-destructive">{kudosMutation.error.message}</span>
          )}
        </div>
      )}
    </div>
  );
}
