/**
 * The section row (#3898) — the sheet's eight sections, with the player's own three
 * set apart on the line.
 *
 * Replaces the sixteen-tab strip. The break and the "Yours only" label are the point:
 * a player can see at a glance which half of their sheet nobody else reads, rather
 * than inferring it from which tabs a stranger happens not to have.
 *
 * Buttons rather than Radix tabs because the panels are plain siblings here and each
 * owns its own queries; `aria-current="page"` marks the open one.
 */

export type SheetSection =
  | 'sheet'
  | 'physical'
  | 'ties'
  | 'distinctions'
  | 'magic'
  | 'knowledge'
  | 'holdings'
  | 'growth';

/** The five anyone may open. */
const PUBLIC_SECTIONS: { id: SheetSection; label: string }[] = [
  { id: 'sheet', label: 'Sheet' },
  { id: 'physical', label: 'Physical' },
  { id: 'ties', label: 'Ties' },
  { id: 'distinctions', label: 'Distinctions' },
  { id: 'magic', label: 'Magic' },
];

/** The three only the character's own player opens. */
const OWN_SECTIONS: { id: SheetSection; label: string }[] = [
  { id: 'knowledge', label: 'Knowledge' },
  { id: 'holdings', label: 'Holdings' },
  { id: 'growth', label: 'Growth' },
];

interface SectionRowProps {
  current: SheetSection;
  onSelect: (section: SheetSection) => void;
  /** True only on the viewer's own character: adds the break and the three own sections. */
  isMyCharacter: boolean;
}

export function SectionRow({ current, onSelect, isMyCharacter }: SectionRowProps) {
  return (
    <nav className="refsheet-sections" aria-label="Character sheet sections">
      {PUBLIC_SECTIONS.map((section) => (
        <button
          key={section.id}
          type="button"
          aria-current={current === section.id ? 'page' : undefined}
          onClick={() => onSelect(section.id)}
        >
          {section.label}
        </button>
      ))}
      {isMyCharacter && (
        <>
          <span className="refsheet-sections-break" aria-hidden="true" />
          <span className="refsheet-sections-yours">Yours only</span>
          {OWN_SECTIONS.map((section) => (
            <button
              key={section.id}
              type="button"
              aria-current={current === section.id ? 'page' : undefined}
              onClick={() => onSelect(section.id)}
            >
              {section.label}
            </button>
          ))}
        </>
      )}
    </nav>
  );
}

/** Sections a viewer who is not the owner must never be left sitting on. */
export const OWN_ONLY_SECTIONS: SheetSection[] = OWN_SECTIONS.map((section) => section.id);
