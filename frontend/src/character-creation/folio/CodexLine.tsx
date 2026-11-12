/**
 * The "Codex: {name}" ledger line an entry body carries when the thing it
 * describes has a codex entry (#3630).
 *
 * Render-or-vanish: no entry id and no note, no line — a catalog row without codex
 * coverage is not a fault the player should see. Eight stages had this exact
 * three-line shape inlined; the duplication is the reason this exists.
 */
import { CodexTerm } from '@/codex/components/CodexTerm';

interface CodexLineProps {
  /** The codex entry to open. Arrays pass their first id: `ids?.[0]`. */
  entryId: number | null | undefined;
  /** The thing's own name, used verbatim as the link text after "Codex: ". */
  name: string;
  /** Read after the link on the same line, e.g. a beginning's cost. */
  note?: string;
}

export function CodexLine({ entryId, name, note }: CodexLineProps) {
  const hasCodex = typeof entryId === 'number';
  if (!hasCodex && !note) return null;
  return (
    <p className="ledger-line">
      {/* Solid, not CodexTerm's dotted inline-term underline: this is a whole link line. */}
      {hasCodex && (
        <CodexTerm entryId={entryId} className="decoration-solid">
          Codex: {name}
        </CodexTerm>
      )}
      {hasCodex && note && <span aria-hidden="true"> · </span>}
      {note}
    </p>
  );
}
