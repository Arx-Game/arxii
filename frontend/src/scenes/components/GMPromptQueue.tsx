/**
 * GMPromptQueue — the one GM prompt queue in the scene feed (#4101, demo Screen 1).
 *
 * #4101 final review: the open composer stays mounted when the queue empties
 * underneath it (F3: closing the last prompt, or another GM closing it, must
 * not yank the dialog away mid-send), and a queue that fails to load says so
 * in a role="alert" line instead of rendering nothing (F6).
 */
import { useState } from 'react';
import { useGMPrompts } from '../gmPromptQueries';
import type { GMPrompt, ScenePersona } from '../types';
import { GMPromptRow } from './GMPromptRow';
import { NarrationComposer } from './NarrationComposer';

export function GMPromptQueue({
  sceneId,
  personas,
}: {
  sceneId: string;
  personas: ScenePersona[];
}) {
  const { data, isError, error } = useGMPrompts(sceneId);
  const [open, setOpen] = useState<GMPrompt | null>(null);
  const prompts = data ?? [];
  if (prompts.length === 0 && !open && !isError) return null;
  return (
    <section
      data-testid="gm-prompt-queue"
      className="space-y-1 rounded-md border border-border bg-card p-3"
    >
      <h3 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
        GM prompts
      </h3>
      {isError && (
        <p role="alert" className="text-sm text-destructive">
          {error instanceof Error ? error.message : 'Failed to load GM prompts'}
        </p>
      )}
      {prompts.map((p) => (
        <GMPromptRow key={p.id} prompt={p} sceneId={sceneId} onOpen={setOpen} />
      ))}
      {open && (
        <NarrationComposer
          prompt={open}
          sceneId={sceneId}
          personas={personas}
          open
          onOpenChange={(next) => !next && setOpen(null)}
        />
      )}
    </section>
  );
}
