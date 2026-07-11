/**
 * RelationshipsSection tests
 *
 * Covers:
 * 1. Renders the "Relationships" heading and both sub-sections.
 * 2. SoulTetherStatusPanel is rendered with bond data from useMyTetherBonds.
 * 3. characterSheetId is forwarded to SoulTetherStatusPanel (via callerSheetId).
 * 4. Bond relationship IDs and bonded names are passed to SoulTetherStatusPanel.
 * 5. Writeups sub-section (#2031): renders with kudos_count, Commend button
 *    hidden when viewer_has_kudosed, exact POST body, 400 message rendered,
 *    empty writeups list renders nothing.
 * 6. Report button (#2159): always shown per writeup, opens WriteupComplaintDialog
 *    with the writeup's id/title.
 * 7. Ties sub-section (#2159): renders RelationshipPanel with characterSheetId/
 *    isMyCharacter forwarded — the free-text Notes subsection it replaced is gone.
 */

import { render, screen, fireEvent, waitFor } from '@testing-library/react';
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
      data-relationship-ids={relationshipIds.join(',')}
      data-caller-sheet-id={callerSheetId ?? ''}
    >
      {relationshipIds.length === 0 ? 'No active soul tethers.' : 'Soul Tethers loaded'}
    </div>
  ),
}));

// ---------------------------------------------------------------------------
// Mock useMyTetherBonds so tests control what bonds are returned.
// Default: no bonds. Individual tests override with vi.mocked().mockReturnValue.
// ---------------------------------------------------------------------------

vi.mock('@/magic/queries', () => ({
  useMyTetherBonds: vi.fn(() => ({ data: [] })),
}));

import { useMyTetherBonds } from '@/magic/queries';

// ---------------------------------------------------------------------------
// Mock the relationships module (writeups + commend mutation). Default: no
// writeups, mutate is a no-op spy. Individual tests override via vi.mocked().
// ---------------------------------------------------------------------------

const mockMutate = vi.fn();

vi.mock('@/relationships/queries', () => ({
  useMyWriteups: vi.fn(() => ({ data: [] })),
  useGiveWriteupKudos: vi.fn(() => ({ mutate: mockMutate, isPending: false })),
}));

import { useMyWriteups } from '@/relationships/queries';

// ---------------------------------------------------------------------------
// Mock RelationshipPanel (#2159) — the real relationship panel has its own
// tests; here we only verify RelationshipsSection composes it correctly.
// ---------------------------------------------------------------------------

vi.mock('@/relationships/components/RelationshipPanel', () => ({
  RelationshipPanel: ({
    characterSheetId,
    isMyCharacter,
  }: {
    characterSheetId?: number;
    isMyCharacter?: boolean;
  }) => (
    <div
      data-testid="relationship-panel"
      data-character-sheet-id={characterSheetId ?? ''}
      data-is-my-character={String(isMyCharacter ?? false)}
    />
  ),
}));

// ---------------------------------------------------------------------------
// Mock WriteupComplaintDialog (#2159) — has its own tests; here we only
// verify RelationshipsSection opens it with the right writeup.
// ---------------------------------------------------------------------------

vi.mock('@/relationships/components/WriteupComplaintDialog', () => ({
  WriteupComplaintDialog: ({
    open,
    writeupType,
    writeupId,
    writeupTitle,
  }: {
    open: boolean;
    writeupType: string;
    writeupId: number;
    writeupTitle: string;
  }) =>
    open ? (
      <div
        data-testid="writeup-complaint-dialog"
        data-writeup-type={writeupType}
        data-writeup-id={writeupId}
        data-writeup-title={writeupTitle}
      />
    ) : null,
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

  it('renders the Ties sub-section heading', () => {
    render(<RelationshipsSection />, { wrapper: createWrapper() });

    expect(screen.getByRole('heading', { name: /ties/i })).toBeInTheDocument();
  });

  it('renders RelationshipPanel with characterSheetId and isMyCharacter forwarded', () => {
    render(<RelationshipsSection characterSheetId={42} isMyCharacter />, {
      wrapper: createWrapper(),
    });

    const panel = screen.getByTestId('relationship-panel');
    expect(panel).toHaveAttribute('data-character-sheet-id', '42');
    expect(panel).toHaveAttribute('data-is-my-character', 'true');
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

  it('passes bond relationship IDs to SoulTetherStatusPanel when bonds exist', () => {
    vi.mocked(useMyTetherBonds).mockReturnValue({
      data: [
        {
          relationship_id: 7,
          bonded_character_sheet_id: 99,
          bonded_character_name: 'Aelindra',
          soul_tether_role: 'SINEATER',
        },
      ],
    } as ReturnType<typeof useMyTetherBonds>);

    render(<RelationshipsSection characterSheetId={42} />, { wrapper: createWrapper() });

    const panel = screen.getByTestId('soul-tether-status-panel');
    expect(panel).toHaveAttribute('data-relationship-count', '1');
    expect(panel).toHaveAttribute('data-relationship-ids', '7');
  });

  it('shows empty state when no bonds are returned', () => {
    vi.mocked(useMyTetherBonds).mockReturnValue({
      data: [],
    } as unknown as ReturnType<typeof useMyTetherBonds>);

    render(<RelationshipsSection />, { wrapper: createWrapper() });

    const panel = screen.getByTestId('soul-tether-status-panel');
    expect(panel).toHaveAttribute('data-relationship-count', '0');
    expect(screen.getByText('No active soul tethers.')).toBeInTheDocument();
  });

  // -------------------------------------------------------------------------
  // Writeups sub-section (#2031)
  // -------------------------------------------------------------------------

  describe('Writeups sub-section', () => {
    it('renders nothing when there are no writeups', () => {
      vi.mocked(useMyWriteups).mockReturnValue({
        data: [],
      } as unknown as ReturnType<typeof useMyWriteups>);

      render(<RelationshipsSection isMyCharacter characterSheetId={42} />, {
        wrapper: createWrapper(),
      });

      expect(screen.queryByRole('heading', { name: /writeups/i })).not.toBeInTheDocument();
    });

    it('renders a writeup with title, author, writeup text, and kudos_count', () => {
      vi.mocked(useMyWriteups).mockReturnValue({
        data: [
          {
            id: 1,
            author: 5,
            author_name: 'Marek',
            title: 'A Debt Repaid',
            writeup: 'They stood by me when it mattered most.',
            track: 1,
            track_name: 'Trust',
            points_earned: 3,
            coloring: '',
            visibility: 'shared',
            is_first_impression: false,
            linked_scene: null,
            created_at: '2026-01-01T00:00:00Z',
            kudos_count: 4,
            viewer_has_kudosed: false,
          },
        ],
      } as unknown as ReturnType<typeof useMyWriteups>);

      render(<RelationshipsSection isMyCharacter characterSheetId={42} />, {
        wrapper: createWrapper(),
      });

      expect(screen.getByRole('heading', { name: /writeups/i })).toBeInTheDocument();
      expect(screen.getByText('A Debt Repaid')).toBeInTheDocument();
      expect(screen.getByText(/Marek/)).toBeInTheDocument();
      expect(screen.getByText('They stood by me when it mattered most.')).toBeInTheDocument();
      expect(screen.getByText(/4 kudos/)).toBeInTheDocument();
    });

    it('shows the Commend button when viewer_has_kudosed is false', () => {
      vi.mocked(useMyWriteups).mockReturnValue({
        data: [
          {
            id: 1,
            author_name: 'Marek',
            title: 'A Debt Repaid',
            writeup: 'writeup text',
            kudos_count: 0,
            viewer_has_kudosed: false,
          },
        ],
      } as unknown as ReturnType<typeof useMyWriteups>);

      render(<RelationshipsSection isMyCharacter characterSheetId={42} />, {
        wrapper: createWrapper(),
      });

      expect(screen.getByRole('button', { name: /commend/i })).toBeInTheDocument();
    });

    it('hides the Commend button when viewer_has_kudosed is true', () => {
      vi.mocked(useMyWriteups).mockReturnValue({
        data: [
          {
            id: 1,
            author_name: 'Marek',
            title: 'A Debt Repaid',
            writeup: 'writeup text',
            kudos_count: 1,
            viewer_has_kudosed: true,
          },
        ],
      } as unknown as ReturnType<typeof useMyWriteups>);

      render(<RelationshipsSection isMyCharacter characterSheetId={42} />, {
        wrapper: createWrapper(),
      });

      expect(screen.queryByRole('button', { name: /commend/i })).not.toBeInTheDocument();
    });

    it('POSTs the exact kudos body when Commend is clicked', () => {
      vi.mocked(useMyWriteups).mockReturnValue({
        data: [
          {
            id: 77,
            author_name: 'Marek',
            title: 'A Debt Repaid',
            writeup: 'writeup text',
            kudos_count: 0,
            viewer_has_kudosed: false,
          },
        ],
      } as unknown as ReturnType<typeof useMyWriteups>);
      mockMutate.mockClear();

      render(<RelationshipsSection isMyCharacter characterSheetId={42} />, {
        wrapper: createWrapper(),
      });

      fireEvent.click(screen.getByRole('button', { name: /commend/i }));

      expect(mockMutate).toHaveBeenCalledTimes(1);
      expect(mockMutate).toHaveBeenCalledWith(
        { writeup_type: 'update', writeup_id: 77 },
        expect.objectContaining({ onError: expect.any(Function) })
      );
    });

    it('renders the exact server message verbatim when the commend POST fails', async () => {
      vi.mocked(useMyWriteups).mockReturnValue({
        data: [
          {
            id: 77,
            author_name: 'Marek',
            title: 'A Debt Repaid',
            writeup: 'writeup text',
            kudos_count: 0,
            viewer_has_kudosed: false,
          },
        ],
      } as unknown as ReturnType<typeof useMyWriteups>);
      mockMutate.mockImplementation(
        (_body: unknown, { onError }: { onError: (err: unknown) => void }) => {
          onError(new Error('You have already commended this writeup.'));
        }
      );

      render(<RelationshipsSection isMyCharacter characterSheetId={42} />, {
        wrapper: createWrapper(),
      });

      fireEvent.click(screen.getByRole('button', { name: /commend/i }));

      await waitFor(() => {
        expect(screen.getByText('You have already commended this writeup.')).toBeInTheDocument();
      });
    });

    it('does not fetch writeups when isMyCharacter is false', () => {
      vi.mocked(useMyWriteups).mockClear();

      render(<RelationshipsSection characterSheetId={42} />, {
        wrapper: createWrapper(),
      });

      expect(useMyWriteups).toHaveBeenCalledWith(42, false);
    });

    it('passes characterSheetId as subject_character narrowing to useMyWriteups', () => {
      vi.mocked(useMyWriteups).mockClear();

      render(<RelationshipsSection isMyCharacter characterSheetId={99} />, {
        wrapper: createWrapper(),
      });

      expect(useMyWriteups).toHaveBeenCalledWith(99, true);
    });

    // -----------------------------------------------------------------------
    // Report button + WriteupComplaintDialog (#2159)
    // -----------------------------------------------------------------------

    it('shows a Report button beside Commend', () => {
      vi.mocked(useMyWriteups).mockReturnValue({
        data: [
          {
            id: 77,
            author_name: 'Marek',
            title: 'A Debt Repaid',
            writeup: 'writeup text',
            kudos_count: 0,
            viewer_has_kudosed: false,
          },
        ],
      } as unknown as ReturnType<typeof useMyWriteups>);

      render(<RelationshipsSection isMyCharacter characterSheetId={42} />, {
        wrapper: createWrapper(),
      });

      expect(screen.getByRole('button', { name: /report/i })).toBeInTheDocument();
    });

    it('opens WriteupComplaintDialog with the writeup id/title when Report is clicked', () => {
      vi.mocked(useMyWriteups).mockReturnValue({
        data: [
          {
            id: 77,
            author_name: 'Marek',
            title: 'A Debt Repaid',
            writeup: 'writeup text',
            kudos_count: 0,
            viewer_has_kudosed: true,
          },
        ],
      } as unknown as ReturnType<typeof useMyWriteups>);

      render(<RelationshipsSection isMyCharacter characterSheetId={42} />, {
        wrapper: createWrapper(),
      });

      expect(screen.queryByTestId('writeup-complaint-dialog')).not.toBeInTheDocument();

      fireEvent.click(screen.getByRole('button', { name: /report/i }));

      const dialog = screen.getByTestId('writeup-complaint-dialog');
      expect(dialog).toHaveAttribute('data-writeup-type', 'update');
      expect(dialog).toHaveAttribute('data-writeup-id', '77');
      expect(dialog).toHaveAttribute('data-writeup-title', 'A Debt Repaid');
    });
  });
});
