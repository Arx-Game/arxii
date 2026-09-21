/**
 * The Relationships block on the sheet (#3957).
 *
 * Two things and no branch: the soul tether panel, then the cast. The old writeups
 * block and the own-vs-foreign panel are gone — what a viewer may see is decided by the
 * server and arrives in `ties`, so this component has nothing left to gate.
 */

import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';

import type { CharacterSheetTie } from '@/character_sheets/api';
import { RelationshipsSection } from '../RelationshipsSection';

vi.mock('@/magic/components/SoulTetherStatusPanel', () => ({
  SoulTetherStatusPanel: ({
    relationshipIds,
    callerSheetId,
    bondedCharacterNames,
  }: {
    relationshipIds: number[];
    callerSheetId?: number;
    bondedCharacterNames: Record<number, string>;
  }) => (
    <div
      data-testid="soul-tether-status-panel"
      data-relationship-ids={relationshipIds.join(',')}
      data-caller-sheet-id={callerSheetId ?? ''}
      data-bonded={Object.values(bondedCharacterNames).join(',')}
    />
  ),
}));

vi.mock('@/magic/queries', () => ({
  useMyTetherBonds: vi.fn(() => ({ data: [] })),
}));

import { useMyTetherBonds } from '@/magic/queries';

const TIE: CharacterSheetTie = {
  relationship_id: 77,
  other_name: 'Corvin Ashe',
  other_sheet_id: 12,
  other_entry_id: 34,
  other_companion_id: null,
  labels: [
    {
      type_name: 'Lover',
      awareness: 'public',
      valence: 'warm',
      is_former: false,
      is_mutual: false,
    },
  ],
  depth: 340,
  tier: 2,
  summary_line: 'He was waiting at the north gate.',
  thread: null,
};

function renderSection(props: Partial<Parameters<typeof RelationshipsSection>[0]> = {}) {
  return render(
    <MemoryRouter>
      <RelationshipsSection
        characterSheetId={42}
        entryId={7}
        isMyCharacter={false}
        ties={[TIE]}
        tiesApThisWeek={null}
        {...props}
      />
    </MemoryRouter>
  );
}

describe('RelationshipsSection', () => {
  it('draws the soul tether panel with the viewed sheet and its bonds', () => {
    vi.mocked(useMyTetherBonds).mockReturnValue({
      data: [{ relationship_id: 5, bonded_character_name: 'Aria' }],
    } as unknown as ReturnType<typeof useMyTetherBonds>);
    renderSection();
    const panel = screen.getByTestId('soul-tether-status-panel');
    expect(panel).toHaveAttribute('data-caller-sheet-id', '42');
    expect(panel).toHaveAttribute('data-relationship-ids', '5');
    expect(panel).toHaveAttribute('data-bonded', 'Aria');
  });

  it('draws the cast from the payload, linking each tie off the roster entry', () => {
    vi.mocked(useMyTetherBonds).mockReturnValue({ data: [] } as unknown as ReturnType<
      typeof useMyTetherBonds
    >);
    renderSection();
    expect(screen.getByRole('link', { name: 'Corvin Ashe' })).toHaveAttribute(
      'href',
      '/characters/7/ties/77'
    );
    expect(screen.getByText('Depth 340 · Tier 2')).toBeInTheDocument();
    expect(screen.getByText('1 tie')).toBeInTheDocument();
  });

  it('gives the owner the AP ledger and the way in', () => {
    vi.mocked(useMyTetherBonds).mockReturnValue({ data: [] } as unknown as ReturnType<
      typeof useMyTetherBonds
    >);
    renderSection({ isMyCharacter: true, tiesApThisWeek: 12 });
    expect(screen.getByText('1 tie · 12 AP this week')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Declare a tie' })).toBeInTheDocument();
  });

  it('has no writeups block left to draw', () => {
    vi.mocked(useMyTetherBonds).mockReturnValue({ data: [] } as unknown as ReturnType<
      typeof useMyTetherBonds
    >);
    renderSection({ isMyCharacter: true });
    expect(screen.queryByText('Writeups')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Commend' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Report' })).not.toBeInTheDocument();
  });
});
