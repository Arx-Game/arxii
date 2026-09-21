/**
 * The cast on the sheet's Ties section (#3957).
 *
 * The audience rules are the server's, never re-derived here: a card whose `depth` is
 * null belongs to a third party, and the cast simply has no Depth line to draw for it.
 */
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it } from 'vitest';

import type { CharacterSheetTie } from '@/character_sheets/api';
import { TieCast } from '../TieCast';

const CORVIN: CharacterSheetTie = {
  relationship_id: 77,
  other_name: 'Corvin Ashe',
  other_sheet_id: 12,
  other_entry_id: 34,
  other_companion_id: null,
  labels: [
    {
      label_id: 101,
      type_name: 'Lover',
      awareness: 'clandestine',
      valence: 'warm',
      is_former: false,
      is_mutual: false,
    },
    {
      label_id: 102,
      type_name: 'Rival',
      awareness: 'public',
      valence: 'hostile',
      is_former: false,
      is_mutual: true,
    },
  ],
  depth: 340,
  tier: 2,
  summary_line: 'He was waiting at the north gate.',
  thread: 'Thread, level 2, Silence',
};

const MARROW: CharacterSheetTie = {
  relationship_id: 88,
  other_name: 'The Widow Marrow',
  other_sheet_id: 13,
  other_entry_id: 35,
  other_companion_id: null,
  labels: [
    {
      label_id: 201,
      type_name: 'Kin',
      awareness: 'public',
      valence: 'warm',
      is_former: false,
      is_mutual: false,
    },
  ],
  depth: null,
  tier: null,
  summary_line: 'Has the seal. Says she does not.',
  thread: null,
};

function renderCast(props: Partial<Parameters<typeof TieCast>[0]> = {}) {
  return render(
    <MemoryRouter>
      <TieCast
        ties={[CORVIN, MARROW]}
        entryId={9}
        isMyCharacter={false}
        apThisWeek={null}
        {...props}
      />
    </MemoryRouter>
  );
}

describe('TieCast', () => {
  it('links each name to that tie page', () => {
    renderCast();
    expect(screen.getByRole('link', { name: 'Corvin Ashe' })).toHaveAttribute(
      'href',
      '/characters/9/ties/77'
    );
    expect(screen.getByRole('link', { name: 'The Widow Marrow' })).toHaveAttribute(
      'href',
      '/characters/9/ties/88'
    );
  });

  it('prints depth and tier only where the payload carried them', () => {
    renderCast();
    expect(screen.getByText('Depth 340 · Tier 2')).toBeInTheDocument();
    expect(screen.queryByText(/Depth 0|Depth null/)).not.toBeInTheDocument();
    // The third-party card gets the summary line in place of a number.
    expect(screen.getByText('Has the seal. Says she does not.')).toBeInTheDocument();
    expect(screen.queryAllByText(/^Depth /)).toHaveLength(1);
  });

  it('marks a mutual label and leaves a public one bare', () => {
    renderCast();
    expect(screen.getByText('Rival · mutual')).toBeInTheDocument();
    expect(screen.getByText('Lover · Clandestine')).toBeInTheDocument();
    expect(screen.getByText('Kin')).toBeInTheDocument();
  });

  it('colours each chip by its valence, the way the tie page already does', () => {
    renderCast();
    // The cast was monochrome before the card carried `valence` (#3957 demo-fidelity
    // Finding 3) — a reader could not tell a lover from a rival across the grid.
    expect(screen.getByText('Lover · Clandestine')).toHaveClass('refsheet-tag-warm');
    expect(screen.getByText('Rival · mutual')).toHaveClass('refsheet-tag-hostile');
    // Awareness still rides the border, independently of the ink.
    expect(screen.getByText('Lover · Clandestine')).toHaveClass('refsheet-tag-clandestine');
    expect(screen.getByText('Kin')).not.toHaveClass('refsheet-tag-hostile');
  });

  it('shows the thread line when the tie carries one', () => {
    renderCast();
    expect(screen.getByText('Thread, level 2, Silence')).toBeInTheDocument();
  });

  it('gives the owner the AP ledger and a way in', () => {
    renderCast({ isMyCharacter: true, apThisWeek: 12 });
    expect(screen.getByText('2 ties · 12 AP this week')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Declare a tie' })).toHaveAttribute(
      'href',
      '/characters/9/ties/new'
    );
  });

  it('counts without AP for anyone else, and vanishes when there is nothing', () => {
    renderCast();
    expect(screen.getByText('2 ties')).toBeInTheDocument();
    expect(screen.queryByRole('link', { name: 'Declare a tie' })).not.toBeInTheDocument();

    const { container } = render(
      <MemoryRouter>
        <TieCast ties={[]} entryId={9} isMyCharacter={false} apThisWeek={null} />
      </MemoryRouter>
    );
    expect(container).toBeEmptyDOMElement();
  });

  it('keeps the ledger for an owner with no ties', () => {
    render(
      <MemoryRouter>
        <TieCast ties={[]} entryId={9} isMyCharacter apThisWeek={0} />
      </MemoryRouter>
    );
    expect(screen.getByText('0 ties · 0 AP this week')).toBeInTheDocument();
  });
});
