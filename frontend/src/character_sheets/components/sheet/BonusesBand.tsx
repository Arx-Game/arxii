/**
 * Bonuses (#5206) — every bonus total the character has, and what gave it.
 *
 * One group per bonus kind, headed by the kind's own name; one row per thing the bonuses
 * add to, with its total and each source's share. A row's name shows its definition the
 * way a card's term does in character creation (the shared `DefinedTerm`): on hover or
 * focus, pinned by a click or tap, closed by Escape, a scroll or another click.
 *
 * Server-gated like Abilities: `bonuses` arrives empty when the viewer cannot see the
 * stats section, and the caller drops the band then.
 */

import type { CharacterSheetBonusGroup, CharacterSheetBonusRow } from '@/character_sheets/api';
import { TermButton, TermPopover } from '@/components/term/DefinedTerm';
import { useTermPopover } from '@/components/term/useTermPopover';
import { Band } from './primitives';

/** A signed number with a real minus sign: "+15", "−10". */
function signed(value: number): string {
  return value < 0 ? `−${Math.abs(value)}` : `+${value}`;
}

function totalText(row: CharacterSheetBonusRow): string {
  if (row.immune && row.total === 0) return 'Immune to negative';
  return signed(row.total);
}

export function BonusesBand({ groups }: { groups: CharacterSheetBonusGroup[] }) {
  const popover = useTermPopover();
  const open = popover.openTerm
    ? groups.flatMap((group) => group.rows).find((row) => row.target === popover.openTerm?.name)
    : undefined;
  return (
    <Band title="Bonuses">
      <div className="refsheet-bonus-groups" data-testid="bonus-groups">
        {groups.map((group) => (
          <div key={group.category} className="refsheet-bonus-group">
            <h4 className="refsheet-bonus-heading">{group.heading}</h4>
            {group.rows.map((row) => (
              <div key={row.target} className="refsheet-bonus" data-testid="bonus-row">
                {row.definition.trim() ? (
                  <TermButton
                    name={row.target}
                    className="refsheet-term"
                    ariaLabel={`${row.label}, definition`}
                    popover={popover}
                  >
                    {row.label}
                  </TermButton>
                ) : (
                  <span>{row.label}</span>
                )}
                <span
                  className={
                    row.total < 0 ? 'refsheet-bonus-total refsheet-soft' : 'refsheet-bonus-total'
                  }
                >
                  {totalText(row)}
                </span>
                {row.sources.length > 0 && (
                  <span className="refsheet-bonus-from">
                    {row.sources
                      .map((source) => `${source.label} ${signed(source.value)}`)
                      .join(', ')}
                  </span>
                )}
              </div>
            ))}
          </div>
        ))}
      </div>
      <TermPopover
        openTerm={open ? popover.openTerm : null}
        label={open?.label ?? ''}
        definition={open?.definition ?? ''}
        scope="refsheet"
      />
    </Band>
  );
}
