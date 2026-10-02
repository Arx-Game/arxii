/** GMPromptQueue — the one GM prompt queue in the scene feed (#4101, demo Screen 1). */
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
  const { data } = useGMPrompts(sceneId);
  const [open, setOpen] = useState<GMPrompt | null>(null);
  const prompts = data ?? [];
  if (prompts.length === 0) return null;
  return (
    <section data-testid="gm-prompt-queue" className="rounded-md border border-amber-500/30 p-2">
      <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-amber-600">
        GM prompts
      </h3>
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
