import type { PerspectiveEntry } from '../types';

/**
 * A holder's perspective opinions, grouped under "On {subject}" notes (#3281).
 *
 * Content renders straight from the shop-window payload: these entries are
 * usually non-public pre-finalize, so linking into CodexModal would 404.
 * Mounted inside a `Marginalia` note-group (#3630), so it renders bare
 * `.note` spans rather than its own heading/frame.
 */
export function PerspectivesPanel({
  perspectives,
}: {
  perspectives: PerspectiveEntry[] | undefined;
}) {
  if (!perspectives || perspectives.length === 0) {
    return null;
  }
  return (
    <>
      {perspectives.map((entry) => (
        <span className="note" key={entry.entry_id}>
          <b>On {entry.subject_name}</b> <span>{entry.lore_content}</span>
        </span>
      ))}
    </>
  );
}
