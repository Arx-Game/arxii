import type { PerspectiveEntry } from '../types';

/**
 * A holder's perspective opinions, grouped under "On {subject}" headings (#3281).
 *
 * Content renders straight from the shop-window payload: these entries are
 * usually non-public pre-finalize, so linking into CodexModal would 404.
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
    <div className="mt-6 space-y-4">
      <h4 className="theme-heading text-lg font-semibold">Perspectives</h4>
      {perspectives.map((entry) => (
        <div key={entry.entry_id}>
          <p className="text-sm font-medium">On {entry.subject_name}</p>
          <p className="whitespace-pre-wrap text-sm leading-relaxed text-muted-foreground">
            {entry.lore_content}
          </p>
        </div>
      ))}
    </div>
  );
}
