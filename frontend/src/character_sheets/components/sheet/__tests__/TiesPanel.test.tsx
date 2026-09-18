/**
 * The Ties rail (#3906, plus a regression from #3901).
 *
 * Standing and Covenant read the SHEET payload rather than the account-wide society
 * endpoints, because those endpoints only ever answer for the requester's own
 * characters — so a friend allowed to see someone's standing used to get an empty rail
 * no matter what the visibility field said. The server applies `standing_visibility`
 * and hands us rows or nothing; drawing what we are handed IS the gate.
 *
 * Kin is pinned here for a different reason: #3901 nested it inside the Mentors block,
 * so every character without a Mentor's Vow silently lost their family.
 */

import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { describe, expect, it, vi } from 'vitest';

import { TiesPanel } from '../panels';
import type {
  CharacterSheetCovenantRole,
  CharacterSheetMentor,
  CharacterSheetStanding,
} from '@/character_sheets/api';

vi.mock('@/components/character', () => ({
  RelationshipsSection: () => <div data-testid="relationships" />,
}));
vi.mock('@/kinship/components/KinshipPanel', () => ({
  KinshipPanel: () => <div data-testid="kinship" />,
}));
vi.mock('@/achievements/components/TitlesPanel', () => ({
  TitlesPanel: () => <div data-testid="titles" />,
}));
vi.mock('@/renown/components/RenownPanel', () => ({ RenownPanel: () => <div /> }));
vi.mock('@/renown/components/RenownCardPanel', () => ({ RenownCardPanel: () => <div /> }));
vi.mock('@/justice/queries', () => ({ usePersonaHeat: () => ({ data: [] }) }));

const EMPTY_STANDING: CharacterSheetStanding = { memberships: [], reputations: [] };

function renderTies({
  mentors = [],
  standing = EMPTY_STANDING,
  covenants = [],
}: {
  mentors?: CharacterSheetMentor[];
  standing?: CharacterSheetStanding;
  covenants?: CharacterSheetCovenantRole[];
} = {}) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <TiesPanel
          sheetId={42}
          entryId={7}
          isMyCharacter={false}
          viewerPersonaId={5}
          titlesPersonaId={9}
          mentors={mentors}
          standing={standing}
          covenants={covenants}
        />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe('TiesPanel', () => {
  it('draws Kin for a character with no Mentor’s Vow', () => {
    renderTies();
    expect(screen.queryByText('Mentors')).not.toBeInTheDocument();
    expect(screen.getByText('Kin')).toBeInTheDocument();
    expect(screen.getByTestId('kinship')).toBeInTheDocument();
  });

  it('draws Mentors and Kin side by side when a vow exists', () => {
    renderTies({
      mentors: [{ id: 1, name: 'Ilaria', covenant: 'The Long Watch', role: 'Mentor' }],
    });
    expect(screen.getByText('Mentors')).toBeInTheDocument();
    expect(screen.getByText('Ilaria')).toBeInTheDocument();
    expect(screen.getByTestId('kinship')).toBeInTheDocument();
  });

  it('draws the standing rows the payload carries, for a viewer who is not the owner', () => {
    renderTies({
      standing: {
        memberships: [{ organization_id: 10, organization: 'House Valardin', title: 'Voice' }],
        reputations: [{ organization_id: 20, organization: 'The Iron Guard', tier: 'liked' }],
      },
    });
    expect(screen.getByText('House Valardin')).toBeInTheDocument();
    expect(screen.getByText('Voice')).toBeInTheDocument();
    expect(screen.getByText('The Iron Guard')).toBeInTheDocument();
  });

  it('draws the covenant role, which is public', () => {
    renderTies({
      covenants: [
        {
          id: 3,
          covenant_id: 8,
          covenant: 'The Quiet Hand',
          role: 'Blade',
          rank: 'Sworn',
          engaged: false,
        },
      ],
    });
    expect(screen.getByText('Covenant')).toBeInTheDocument();
    expect(screen.getByText('Blade')).toBeInTheDocument();
  });

  it('drops the whole Covenant block when they hold no role', () => {
    renderTies();
    expect(screen.queryByText('Covenant')).not.toBeInTheDocument();
  });

  it('drops the Standing groups when the server withheld standing, keeping Renown', () => {
    // The stranger's view. Standing gone, Titles and Covenant unaffected, and the
    // page keeps its shape — which is what render-or-vanish is for.
    renderTies({ standing: EMPTY_STANDING });
    expect(screen.getByText('Standing')).toBeInTheDocument();
    expect(screen.queryByText('Belongs to')).not.toBeInTheDocument();
    expect(screen.queryByText('Thought of as')).not.toBeInTheDocument();
    expect(screen.getByText('Titles')).toBeInTheDocument();
  });
});
