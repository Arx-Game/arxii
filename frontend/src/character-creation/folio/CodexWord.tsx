/**
 * A single in-world term inside otherwise-plain arrival copy (#3540 OOC
 * sweep). Looks up an exact-name codex entry and links it via CodexTerm when
 * one exists; falls back to plain text otherwise (render-or-vanish, no error
 * state; a renamed or missing entry is not a fault the player should see).
 */
import type { ReactNode } from 'react';
import { CodexTerm } from '@/codex/components/CodexTerm';
import { useCodexEntryByName } from '@/codex/queries';

interface CodexWordProps {
  name: string;
  children: ReactNode;
}

export function CodexWord({ name, children }: CodexWordProps) {
  const { data: entry } = useCodexEntryByName(name);
  if (entry) {
    return <CodexTerm entryId={entry.id}>{children}</CodexTerm>;
  }
  return <>{children}</>;
}
