/**
 * RelationshipsSection tests
 *
 * Covers:
 * 1. Renders the "Relationships" heading and both sub-sections.
 * 2. Free-text relationships render as list items in the Notes sub-section.
 * 3. When no free-text relationships exist, "TBD" placeholder renders.
 * 4. SoulTetherStatusPanel is rendered (even with empty bond list → shows empty state).
 * 5. characterSheetId is forwarded to SoulTetherStatusPanel (via callerSheetId).
 */

import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactNode } from 'react';

import { RelationshipsSection } from '../RelationshipsSection';

// ---------------------------------------------------------------------------
// Mock SoulTetherStatusPanel so this test is isolated from its query logic.
// We verify props forwarding by asserting against the mock's rendered output.
// ---------------------------------------------------------------------------

vi.mock('@/magic/components/SoulTetherStatusPanel', () => ({
  SoulTetherStatusPanel: ({
    relationshipIds,
    callerSheetId,
  }: {
    relationshipIds: number[];
    callerSheetId?: number;
  }) => (
    <div
      data-testid="soul-tether-status-panel"
      data-relationship-count={relationshipIds.length}
      data-caller-sheet-id={callerSheetId ?? ''}
    >
      {relationshipIds.length === 0 ? 'No active soul tethers.' : 'Soul Tethers loaded'}
    </div>
  ),
}));

// ---------------------------------------------------------------------------
// Wrapper
// ---------------------------------------------------------------------------

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });
  return function Wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
  };
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('RelationshipsSection', () => {
  it('renders the Relationships heading', () => {
    render(<RelationshipsSection />, { wrapper: createWrapper() });

    expect(screen.getByRole('heading', { name: /relationships/i })).toBeInTheDocument();
  });

  it('renders the Notes sub-section heading', () => {
    render(<RelationshipsSection />, { wrapper: createWrapper() });

    expect(screen.getByRole('heading', { name: /notes/i })).toBeInTheDocument();
  });

  it('renders SoulTetherStatusPanel', () => {
    render(<RelationshipsSection />, { wrapper: createWrapper() });

    expect(screen.getByTestId('soul-tether-status-panel')).toBeInTheDocument();
  });

  it('passes characterSheetId as callerSheetId to SoulTetherStatusPanel', () => {
    render(<RelationshipsSection characterSheetId={42} />, { wrapper: createWrapper() });

    const panel = screen.getByTestId('soul-tether-status-panel');
    expect(panel).toHaveAttribute('data-caller-sheet-id', '42');
  });

  it('passes empty relationshipIds to SoulTetherStatusPanel (no enumeration endpoint yet)', () => {
    render(<RelationshipsSection />, { wrapper: createWrapper() });

    const panel = screen.getByTestId('soul-tether-status-panel');
    expect(panel).toHaveAttribute('data-relationship-count', '0');
  });

  it('renders free-text relationships as list items', () => {
    const relationships = ['Childhood friend of Marek', 'Rival of House Ashveil'];
    render(<RelationshipsSection relationships={relationships} />, { wrapper: createWrapper() });

    expect(screen.getByText('Childhood friend of Marek')).toBeInTheDocument();
    expect(screen.getByText('Rival of House Ashveil')).toBeInTheDocument();
  });

  it('renders TBD placeholder when no free-text relationships are provided', () => {
    render(<RelationshipsSection relationships={[]} />, { wrapper: createWrapper() });

    expect(screen.getByText('TBD')).toBeInTheDocument();
  });

  it('renders TBD placeholder when relationships prop is omitted', () => {
    render(<RelationshipsSection />, { wrapper: createWrapper() });

    expect(screen.getByText('TBD')).toBeInTheDocument();
  });

  it('renders both free-text notes and the soul tether panel together', () => {
    const relationships = ['Old ally from the siege'];
    render(<RelationshipsSection relationships={relationships} characterSheetId={10} />, {
      wrapper: createWrapper(),
    });

    // Both sub-sections present
    expect(screen.getByTestId('soul-tether-status-panel')).toBeInTheDocument();
    expect(screen.getByText('Old ally from the siege')).toBeInTheDocument();
  });
});
