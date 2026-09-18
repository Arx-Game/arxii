/**
 * The Estate section's Domains block (#3901).
 *
 * Two things are worth pinning, and both are rulings rather than mechanics.
 *
 * The block VANISHES when there is nothing, and that is the common case rather than the
 * edge: most organizations hold no land, and plenty hold their buildings under
 * individual rather than org control. A line reading "no domains" would be an
 * empty-state card by another name, which the sheet's rulings forbid.
 *
 * And a domain is never the character's own. The row names whose it is and where, so a
 * player new to a roster character can learn their house holds a keep and go find it —
 * which is the whole reason the line was kept rather than deleted.
 */

import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { describe, expect, it, vi } from 'vitest';

import { EstatePanel } from '../panels';
import type { CharacterSheetDomain } from '@/character_sheets/api';

vi.mock('@/justice/components/CrimeTab', () => ({ CrimeTab: () => <div /> }));
vi.mock('@/locations/components/LocationsTab', () => ({ LocationsTab: () => <div /> }));
vi.mock('@/estates/components/AgreementsPanel', () => ({ AgreementsPanel: () => <div /> }));
vi.mock('@/status/queries', () => ({ useCharacterPurse: () => ({ data: { balance: 0 } }) }));
vi.mock('@/inventory/hooks/useInventory', () => ({ useInventory: () => ({ data: [] }) }));
vi.mock('@/inventory/hooks/useOutfits', () => ({ useOutfits: () => ({ data: [] }) }));

const THORNMERE: CharacterSheetDomain = {
  id: 1,
  name: 'Thornmere',
  organization: 'House du Verane',
  where: 'The Lantern Ward',
};

function renderEstate(domains: CharacterSheetDomain[]) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <EstatePanel
          sheetId={42}
          viewedPersonaId={9}
          isActiveCharacter
          viewerEntryId={1}
          domains={domains}
        />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe('Estate domains', () => {
  it('draws nothing at all when the character’s houses hold no land', () => {
    renderEstate([]);
    expect(screen.queryByText('Their houses hold')).not.toBeInTheDocument();
    expect(screen.queryByText(/no domains/i)).not.toBeInTheDocument();
  });

  it('names the land, whose it is, and where to find it', () => {
    renderEstate([THORNMERE]);
    expect(screen.getByText('Their houses hold')).toBeInTheDocument();
    expect(screen.getByText('Thornmere')).toBeInTheDocument();
    expect(screen.getByText('House du Verane')).toBeInTheDocument();
    expect(screen.getByText('The Lantern Ward')).toBeInTheDocument();
  });

  it('does not claim the land is the character’s own', () => {
    renderEstate([THORNMERE]);
    expect(screen.getByText(/land their organizations hold/i)).toBeInTheDocument();
  });
});
