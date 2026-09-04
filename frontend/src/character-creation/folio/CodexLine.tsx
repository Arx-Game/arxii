/**
 * The "Codex: {name}" ledger line an entry body carries when the thing it
 * describes has a codex entry (#3630).
 *
 * Render-or-vanish: no entry id, no line — a catalog row without codex
 * coverage is not a fault the player should see. Eight stages had this exact
 * three-line shape inlined; the duplication is the reason this exists.
 */
import { CodexTerm } from '@/codex/components/CodexTerm';

interface CodexLineProps {
  /** The codex entry to open. Arrays pass their first id: `ids?.[0]`. */
  entryId: number | null | undefined;
  /** The thing's own name, used verbatim as the link text after "Codex: ". */
  name: string;
}

export function CodexLine({ entryId, name }: CodexLineProps) {
  if (typeof entryId !== 'number') return null;
  return (
    <p className="ledger-line">
      <CodexTerm entryId={entryId}>Codex: {name}</CodexTerm>
    </p>
  );
}
