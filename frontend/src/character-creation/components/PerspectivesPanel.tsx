import type { PerspectiveEntry } from '../types';

/**
 * A holder's perspective opinions, grouped under "On {subject}" notes (#3281).
 *
 * Content renders straight from the shop-window payload: these entries are
 * usually non-public pre-finalize, so linking into CodexModal would 404.
 * Renders bare `.note` spans rather than a heading or frame of its own
 * (#3630), and so requires a `.note-group` ancestor: cg.css scopes `.note`
 * to that class, and a panel mounted outside one renders unstyled. Heritage
 * supplies it with `Marginalia`; TraditionPicker wraps the panel in a
 * `.note-group` div of its own inside the chosen tradition's entry.
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
