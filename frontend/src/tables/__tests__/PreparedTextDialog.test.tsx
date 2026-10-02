/**
 * Tests for PreparedTextDialog (#4101 Task 11, demo Screen 6). Mocks the
 * low-level `apiFetch` seam (never the exported query hooks), mirroring
 * `GMPromptRow.test.tsx`'s established idiom, so the real
 * `usePreparedCrossingText`/`usePreparedSurgeText`/`useSavePreparedCrossingText`/
 * `useSavePreparedSurgeText` hooks are exercised.
 */
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactNode } from 'react';

const mockApiFetch = vi.fn();

vi.mock('@/evennia_replacements/api', () => ({
  apiFetch: (...args: unknown[]) => mockApiFetch(...(args as [])),
}));

import { PreparedTextDialog } from '../components/PreparedTextDialog';

function createWrapper() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return function Wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
  };
}

function emptyList() {
  return { ok: true, json: () => Promise.resolve({ count: 0, results: [] }) } as Response;
}

describe('PreparedTextDialog', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('with no existing row, Save POSTs the crossing fields and shows "Staff, or <name>\'s table GM"', async () => {
    const user = userEvent.setup();
    mockApiFetch
      .mockResolvedValueOnce(emptyList()) // GET prepared-crossing-texts
      .mockResolvedValueOnce(emptyList()) // GET prepared-surge-texts
      .mockResolvedValueOnce({
        ok: true,
        json: () =>
          Promise.resolve({
            id: 1,
            character_sheet: 42,
            character_name: 'Rowan Ashcombe',
            vision_text: '',
            manifestation_text: '',
            deed_title: '',
            prepared_by_role: 'table_gm',
            crossing: null,
            updated_at: '2026-10-02T00:00:00Z',
          }),
      } as Response) // POST crossing
      .mockResolvedValueOnce({
        ok: true,
        json: () =>
          Promise.resolve({
            id: 2,
            character_sheet: 42,
            character_name: 'Rowan Ashcombe',
            surge_text: '',
            prepared_by_role: 'table_gm',
            updated_at: '2026-10-02T00:00:00Z',
          }),
      } as Response); // POST surge

    render(
      <PreparedTextDialog
        characterSheetId={42}
        characterName="Rowan Ashcombe"
        open
        onOpenChange={() => {}}
      />,
      { wrapper: createWrapper() }
    );

    expect(await screen.findByText("Staff, or Rowan Ashcombe's table GM")).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Save' }));

    await waitFor(() => expect(mockApiFetch).toHaveBeenCalledTimes(4));
    const [crossingUrl, crossingOptions] = mockApiFetch.mock.calls[2] as [string, RequestInit];
    expect(crossingUrl).toBe('/api/magic/prepared-crossing-texts/');
    expect(crossingOptions.method).toBe('POST');
    expect(JSON.parse(crossingOptions.body as string)).toEqual({
      character_sheet: 42,
      vision_text: '',
      manifestation_text: '',
      deed_title: '',
    });
  });

  it('with an existing row, Save PATCHes it', async () => {
    const user = userEvent.setup();
    mockApiFetch
      .mockResolvedValueOnce({
        ok: true,
        json: () =>
          Promise.resolve({
            count: 1,
            results: [
              {
                id: 7,
                character_sheet: 42,
                character_name: 'Rowan Ashcombe',
                vision_text: 'A dim room.',
                manifestation_text: 'The air stills.',
                deed_title: 'The Still Room',
                prepared_by_role: 'staff',
                crossing: null,
                updated_at: '2026-10-02T00:00:00Z',
              },
            ],
          }),
      } as Response) // GET crossing
      .mockResolvedValueOnce(emptyList()) // GET surge
      .mockResolvedValueOnce({
        ok: true,
        json: () =>
          Promise.resolve({
            id: 7,
            character_sheet: 42,
            character_name: 'Rowan Ashcombe',
            vision_text: 'A dim room, now darker.',
            manifestation_text: 'The air stills.',
            deed_title: 'The Still Room',
            prepared_by_role: 'staff',
            crossing: null,
            updated_at: '2026-10-02T00:01:00Z',
          }),
      } as Response) // PATCH crossing
      .mockResolvedValueOnce({
        ok: true,
        json: () =>
          Promise.resolve({
            id: 2,
            character_sheet: 42,
            character_name: 'Rowan Ashcombe',
            surge_text: '',
            prepared_by_role: 'table_gm',
            updated_at: '2026-10-02T00:00:00Z',
          }),
      } as Response); // POST surge (no existing surge row)

    render(
      <PreparedTextDialog
        characterSheetId={42}
        characterName="Rowan Ashcombe"
        open
        onOpenChange={() => {}}
      />,
      { wrapper: createWrapper() }
    );

    expect(await screen.findByText('Staff')).toBeInTheDocument();
    const vision = await screen.findByLabelText('Vision (private)');
    expect(vision).toHaveValue('A dim room.');

    await user.clear(vision);
    await user.type(vision, 'A dim room, now darker.');
    await user.click(screen.getByRole('button', { name: 'Save' }));

    await waitFor(() => expect(mockApiFetch).toHaveBeenCalledTimes(4));
    const [crossingUrl, crossingOptions] = mockApiFetch.mock.calls[2] as [string, RequestInit];
    expect(crossingUrl).toBe('/api/magic/prepared-crossing-texts/7/');
    expect(crossingOptions.method).toBe('PATCH');
    expect(JSON.parse(crossingOptions.body as string)).toEqual({
      vision_text: 'A dim room, now darker.',
      manifestation_text: 'The air stills.',
      deed_title: 'The Still Room',
    });
  });

  it('shows a 400 detail in role="alert" and keeps the fields', async () => {
    const user = userEvent.setup();
    mockApiFetch
      .mockResolvedValueOnce({
        ok: true,
        json: () =>
          Promise.resolve({
            count: 1,
            results: [
              {
                id: 7,
                character_sheet: 42,
                character_name: 'Rowan Ashcombe',
                vision_text: 'A dim room.',
                manifestation_text: '',
                deed_title: '',
                prepared_by_role: 'staff',
                crossing: null,
                updated_at: '2026-10-02T00:00:00Z',
              },
            ],
          }),
      } as Response) // GET crossing
      .mockResolvedValueOnce(emptyList()) // GET surge
      .mockResolvedValueOnce({
        ok: false,
        status: 400,
        json: () =>
          Promise.resolve({
            non_field_errors: ['That text was used by a crossing and is now a record.'],
          }),
      } as Response) // PATCH crossing fails
      .mockResolvedValueOnce({
        ok: true,
        json: () =>
          Promise.resolve({
            id: 2,
            character_sheet: 42,
            character_name: 'Rowan Ashcombe',
            surge_text: '',
            prepared_by_role: 'table_gm',
            updated_at: '2026-10-02T00:00:00Z',
          }),
      } as Response); // POST surge

    render(
      <PreparedTextDialog
        characterSheetId={42}
        characterName="Rowan Ashcombe"
        open
        onOpenChange={() => {}}
      />,
      { wrapper: createWrapper() }
    );

    const vision = await screen.findByLabelText('Vision (private)');
    await waitFor(() => expect(vision).toHaveValue('A dim room.'));
    await user.click(screen.getByRole('button', { name: 'Save' }));

    expect(
      await screen.findByText('That text was used by a crossing and is now a record.')
    ).toBeInTheDocument();
    expect(screen.getByRole('alert')).toBeInTheDocument();
    // The field the GM was editing is kept, not cleared, on failure.
    expect(screen.getByLabelText('Vision (private)')).toHaveValue('A dim room.');
  });

  it('never renders an account name for "Prepared by" -- only the role label', async () => {
    mockApiFetch
      .mockResolvedValueOnce({
        ok: true,
        json: () =>
          Promise.resolve({
            count: 1,
            results: [
              {
                id: 7,
                character_sheet: 42,
                character_name: 'Rowan Ashcombe',
                vision_text: '',
                manifestation_text: '',
                deed_title: '',
                prepared_by_role: 'table_gm',
                crossing: null,
                updated_at: '2026-10-02T00:00:00Z',
              },
            ],
          }),
      } as Response)
      .mockResolvedValueOnce(emptyList());

    render(
      <PreparedTextDialog
        characterSheetId={42}
        characterName="Rowan Ashcombe"
        open
        onOpenChange={() => {}}
      />,
      { wrapper: createWrapper() }
    );

    expect(await screen.findByText('Table GM')).toBeInTheDocument();
    expect(screen.queryByText(/StaffUser99/)).toBeNull();
    expect(screen.queryByText(/@/)).toBeNull();
  });
});
