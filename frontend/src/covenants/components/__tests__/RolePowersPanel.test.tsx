/**
 * RolePowersPanel Tests
 *
 * Covers the read-only covenant "Role Powers" panel, which surfaces each active
 * member's passive role power:
 *   1. An engaged role_power with a capability renders the capability name, the
 *      narrative snippet, and an "Engaged" badge.
 *   2. A role_power with capability_name: null renders the "no power" message and
 *      does NOT fabricate a capability.
 *   3. A non-engaged role_power with a capability renders the capability but a
 *      "Latent" indicator rather than "Engaged".
 *   4. No role_powers → empty-state message.
 */

import { render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { vi } from 'vitest';
import type { ReactNode } from 'react';
import { RolePowersPanel } from '../RolePowersPanel';
import type { RolePower, CovenantPowers } from '@/covenants/api';

// ---------------------------------------------------------------------------
// Mock query module
// ---------------------------------------------------------------------------

vi.mock('@/covenants/queries', () => ({
  useCovenantPowers: vi.fn(),
}));

import { useCovenantPowers } from '@/covenants/queries';

// ---------------------------------------------------------------------------
// Wrapper
// ---------------------------------------------------------------------------

function createWrapper() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
  return function Wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
  };
}

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const makeRolePower = (overrides: Partial<RolePower> = {}): RolePower => ({
  membership_id: 1,
  character_sheet: 42,
  covenant_role_id: 7,
  covenant_role_name: 'Warlord',
  resonance_name: 'Fury',
  capability_name: 'Banner of the Vanguard',
  narrative_snippet: 'The host rallies to a single unbroken line.',
  engaged: true,
  ...overrides,
});

function mockPowers(rolePowers: RolePower[], isLoading = false) {
  const data: CovenantPowers = { rites: [], role_powers: rolePowers };
  vi.mocked(useCovenantPowers).mockReturnValue({
    data: isLoading ? undefined : data,
    isLoading,
  } as never);
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('RolePowersPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders the capability, snippet, and an Engaged badge for an engaged power', () => {
    mockPowers([makeRolePower()]);

    render(<RolePowersPanel covenantId={1} />, { wrapper: createWrapper() });

    expect(screen.getByText('Warlord')).toBeInTheDocument();
    expect(screen.getByText('Character #42')).toBeInTheDocument();
    expect(screen.getByText('Banner of the Vanguard')).toBeInTheDocument();
    expect(screen.getByText('The host rallies to a single unbroken line.')).toBeInTheDocument();
    expect(screen.getByText('Engaged')).toBeInTheDocument();
  });

  it('shows a no-power message when capability_name is null without inventing a capability', () => {
    mockPowers([
      makeRolePower({
        capability_name: null,
        narrative_snippet: null,
        resonance_name: 'Fury',
        engaged: false,
      }),
    ]);

    render(<RolePowersPanel covenantId={1} />, { wrapper: createWrapper() });

    expect(screen.getByText('Warlord')).toBeInTheDocument();
    expect(screen.queryByText('Banner of the Vanguard')).not.toBeInTheDocument();
    expect(screen.queryByText('Engaged')).not.toBeInTheDocument();
    expect(screen.getByText(/no power unlocked/i)).toBeInTheDocument();
    expect(screen.getByText(/Fury/)).toBeInTheDocument();
  });

  it('renders a Latent indicator for a non-engaged power with a capability', () => {
    mockPowers([makeRolePower({ engaged: false })]);

    render(<RolePowersPanel covenantId={1} />, { wrapper: createWrapper() });

    expect(screen.getByText('Banner of the Vanguard')).toBeInTheDocument();
    expect(screen.queryByText('Engaged')).not.toBeInTheDocument();
    expect(screen.getByText('Latent')).toBeInTheDocument();
  });

  it('renders an empty-state message when there are no role powers', () => {
    mockPowers([]);

    render(<RolePowersPanel covenantId={1} />, { wrapper: createWrapper() });

    expect(screen.getByText(/No role powers/i)).toBeInTheDocument();
  });
});
