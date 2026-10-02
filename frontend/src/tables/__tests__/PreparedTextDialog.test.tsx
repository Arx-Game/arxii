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

function okJson(body: unknown) {
  return { ok: true, json: () => Promise.resolve(body) } as Response;
}

function renderDialog() {
  return render(
    <PreparedTextDialog
      characterSheetId={42}
      characterName="Rowan Ashcombe"
      open
      onOpenChange={() => {}}
    />,
    { wrapper: createWrapper() }
  );
}

describe('PreparedTextDialog', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('with no existing rows, Save POSTs both the crossing and surge fields and shows Saved.', async () => {
    const user = userEvent.setup();
    mockApiFetch
      .mockResolvedValueOnce(emptyList()) // GET prepared-crossing-texts
      .mockResolvedValueOnce(emptyList()) // GET prepared-surge-texts
      .mockResolvedValueOnce(
        okJson({
          id: 1,
          character_sheet: 42,
          character_name: 'Rowan Ashcombe',
          vision_text: 'A new vision.',
          manifestation_text: '',
          deed_title: '',
          prepared_by_role: 'table_gm',
          crossing: null,
          updated_at: '2026-10-02T00:00:00Z',
        })
      ) // POST crossing
      .mockResolvedValueOnce(
        okJson({
          id: 2,
          character_sheet: 42,
          character_name: 'Rowan Ashcombe',
          surge_text: 'A surge line.',
          prepared_by_role: 'table_gm',
          updated_at: '2026-10-02T00:00:00Z',
        })
      ); // POST surge

    renderDialog();

    expect(await screen.findByText("Staff, or Rowan Ashcombe's table GM")).toBeInTheDocument();

    await user.type(screen.getByLabelText('Vision (private)'), 'A new vision.');
    await user.type(screen.getByLabelText('Audere surge'), 'A surge line.');
    await user.click(screen.getByRole('button', { name: 'Save' }));

    await waitFor(() => expect(mockApiFetch).toHaveBeenCalledTimes(4));

    const [crossingUrl, crossingOptions] = mockApiFetch.mock.calls[2] as [string, RequestInit];
    expect(crossingUrl).toBe('/api/magic/prepared-crossing-texts/');
    expect(crossingOptions.method).toBe('POST');
    expect(JSON.parse(crossingOptions.body as string)).toEqual({
      character_sheet: 42,
      vision_text: 'A new vision.',
      manifestation_text: '',
      deed_title: '',
    });

    const [surgeUrl, surgeOptions] = mockApiFetch.mock.calls[3] as [string, RequestInit];
    expect(surgeUrl).toBe('/api/magic/prepared-surge-texts/');
    expect(surgeOptions.method).toBe('POST');
    expect(JSON.parse(surgeOptions.body as string)).toEqual({
      character_sheet: 42,
      surge_text: 'A surge line.',
    });

    expect(await screen.findByRole('status')).toHaveTextContent('Saved.');
  });

  it('skips the Crossing POST entirely when only the surge is filled in (no existing Crossing row)', async () => {
    const user = userEvent.setup();
    mockApiFetch
      .mockResolvedValueOnce(emptyList()) // GET crossing
      .mockResolvedValueOnce(emptyList()) // GET surge
      .mockResolvedValueOnce(
        okJson({
          id: 2,
          character_sheet: 42,
          character_name: 'Rowan Ashcombe',
          surge_text: 'Only a surge line.',
          prepared_by_role: 'table_gm',
          updated_at: '2026-10-02T00:00:00Z',
        })
      ); // POST surge

    renderDialog();
    await screen.findByText("Staff, or Rowan Ashcombe's table GM");

    await user.type(screen.getByLabelText('Audere surge'), 'Only a surge line.');
    await user.click(screen.getByRole('button', { name: 'Save' }));

    // Exactly 3 calls total -- the blank Crossing fields never POST.
    await waitFor(() => expect(mockApiFetch).toHaveBeenCalledTimes(3));
    const [surgeUrl, surgeOptions] = mockApiFetch.mock.calls[2] as [string, RequestInit];
    expect(surgeUrl).toBe('/api/magic/prepared-surge-texts/');
    expect(surgeOptions.method).toBe('POST');
    expect(JSON.parse(surgeOptions.body as string)).toEqual({
      character_sheet: 42,
      surge_text: 'Only a surge line.',
    });
  });

  it('with an existing Crossing row, Save PATCHes it and skips the still-blank surge save', async () => {
    const user = userEvent.setup();
    mockApiFetch
      .mockResolvedValueOnce(
        okJson({
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
        })
      ) // GET crossing
      .mockResolvedValueOnce(emptyList()) // GET surge (no existing row)
      .mockResolvedValueOnce(
        okJson({
          id: 7,
          character_sheet: 42,
          character_name: 'Rowan Ashcombe',
          vision_text: 'A dim room, now darker.',
          manifestation_text: 'The air stills.',
          deed_title: 'The Still Room',
          prepared_by_role: 'staff',
          crossing: null,
          updated_at: '2026-10-02T00:01:00Z',
        })
      ); // PATCH crossing

    renderDialog();

    expect(await screen.findByText('Staff')).toBeInTheDocument();
    const vision = await screen.findByLabelText('Vision (private)');
    await waitFor(() => expect(vision).toHaveValue('A dim room.'));

    await user.clear(vision);
    await user.type(vision, 'A dim room, now darker.');
    await user.click(screen.getByRole('button', { name: 'Save' }));

    // Exactly 3 calls total -- the blank surge (no existing row) never saves.
    await waitFor(() => expect(mockApiFetch).toHaveBeenCalledTimes(3));
    const [crossingUrl, crossingOptions] = mockApiFetch.mock.calls[2] as [string, RequestInit];
    expect(crossingUrl).toBe('/api/magic/prepared-crossing-texts/7/');
    expect(crossingOptions.method).toBe('PATCH');
    expect(JSON.parse(crossingOptions.body as string)).toEqual({
      vision_text: 'A dim room, now darker.',
      manifestation_text: 'The air stills.',
      deed_title: 'The Still Room',
    });
  });

  it('with an existing Surge row, Save PATCHes it even while the Crossing fields are blank', async () => {
    const user = userEvent.setup();
    mockApiFetch
      .mockResolvedValueOnce(emptyList()) // GET crossing (no existing row)
      .mockResolvedValueOnce(
        okJson({
          count: 1,
          results: [
            {
              id: 3,
              character_sheet: 42,
              character_name: 'Rowan Ashcombe',
              surge_text: 'Old surge line.',
              prepared_by_role: 'table_gm',
              updated_at: '2026-10-02T00:00:00Z',
            },
          ],
        })
      ) // GET surge
      .mockResolvedValueOnce(
        okJson({
          id: 3,
          character_sheet: 42,
          character_name: 'Rowan Ashcombe',
          surge_text: 'New surge line.',
          prepared_by_role: 'table_gm',
          updated_at: '2026-10-02T00:01:00Z',
        })
      ); // PATCH surge

    renderDialog();

    const surge = await screen.findByLabelText('Audere surge');
    await waitFor(() => expect(surge).toHaveValue('Old surge line.'));

    await user.clear(surge);
    await user.type(surge, 'New surge line.');
    await user.click(screen.getByRole('button', { name: 'Save' }));

    // Exactly 3 calls total -- the blank Crossing (no existing row) never POSTs.
    await waitFor(() => expect(mockApiFetch).toHaveBeenCalledTimes(3));
    const [surgeUrl, surgeOptions] = mockApiFetch.mock.calls[2] as [string, RequestInit];
    expect(surgeUrl).toBe('/api/magic/prepared-surge-texts/3/');
    expect(surgeOptions.method).toBe('PATCH');
    expect(JSON.parse(surgeOptions.body as string)).toEqual({ surge_text: 'New surge line.' });
  });

  it('clearing every field of an existing Crossing row still PATCHes it with blank values', async () => {
    const user = userEvent.setup();
    mockApiFetch
      .mockResolvedValueOnce(
        okJson({
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
        })
      ) // GET crossing
      .mockResolvedValueOnce(emptyList()) // GET surge
      .mockResolvedValueOnce(
        okJson({
          id: 7,
          character_sheet: 42,
          character_name: 'Rowan Ashcombe',
          vision_text: '',
          manifestation_text: '',
          deed_title: '',
          prepared_by_role: 'staff',
          crossing: null,
          updated_at: '2026-10-02T00:01:00Z',
        })
      ); // PATCH crossing, erased

    renderDialog();

    const vision = await screen.findByLabelText('Vision (private)');
    await waitFor(() => expect(vision).toHaveValue('A dim room.'));
    const manifestation = screen.getByLabelText('Manifestation (room)');
    const deedTitle = screen.getByLabelText('Deed title');

    await user.clear(vision);
    await user.clear(manifestation);
    await user.clear(deedTitle);
    await user.click(screen.getByRole('button', { name: 'Save' }));

    // An EXISTING row still PATCHes even cleared back to blank -- "clear it"
    // is a deliberate edit, not a no-op skipped the way a brand-new all-blank
    // row is (fix round 1, item 6).
    await waitFor(() => expect(mockApiFetch).toHaveBeenCalledTimes(3));
    const [crossingUrl, crossingOptions] = mockApiFetch.mock.calls[2] as [string, RequestInit];
    expect(crossingUrl).toBe('/api/magic/prepared-crossing-texts/7/');
    expect(crossingOptions.method).toBe('PATCH');
    expect(JSON.parse(crossingOptions.body as string)).toEqual({
      vision_text: '',
      manifestation_text: '',
      deed_title: '',
    });
  });

  it('reseeds from the server value on reopen, discarding an abandoned draft (fix round 2)', async () => {
    const user = userEvent.setup();
    mockApiFetch
      .mockResolvedValueOnce(
        okJson({
          count: 1,
          results: [
            {
              id: 7,
              character_sheet: 42,
              character_name: 'Rowan Ashcombe',
              vision_text: 'Original vision.',
              manifestation_text: '',
              deed_title: '',
              prepared_by_role: 'staff',
              crossing: null,
              updated_at: '2026-10-02T00:00:00Z',
            },
          ],
        })
      ) // GET crossing
      .mockResolvedValueOnce(emptyList()); // GET surge

    const { rerender } = render(
      <PreparedTextDialog
        characterSheetId={42}
        characterName="Rowan Ashcombe"
        open
        onOpenChange={() => {}}
      />,
      { wrapper: createWrapper() }
    );

    const vision = await screen.findByLabelText('Vision (private)');
    await waitFor(() => expect(vision).toHaveValue('Original vision.'));

    await user.clear(vision);
    await user.type(vision, 'Abandoned draft.');
    expect(screen.getByLabelText('Vision (private)')).toHaveValue('Abandoned draft.');

    // The dialog CLOSES, but -- unlike `TableMemberRoster`'s own usage, which
    // unmounts it -- this component instance stays mounted, as a parent that
    // keeps it around and merely toggles `open` would do.
    rerender(
      <PreparedTextDialog
        characterSheetId={42}
        characterName="Rowan Ashcombe"
        open={false}
        onOpenChange={() => {}}
      />
    );

    // Reopen.
    rerender(
      <PreparedTextDialog
        characterSheetId={42}
        characterName="Rowan Ashcombe"
        open
        onOpenChange={() => {}}
      />
    );

    // No new fetch was needed -- the query's cached value never changed --
    // but the reopened dialog must show the server value, not the abandoned
    // in-memory draft.
    await waitFor(() =>
      expect(screen.getByLabelText('Vision (private)')).toHaveValue('Original vision.')
    );
  });

  it('shows a 400 detail in role="alert" and keeps a value the GM typed after load', async () => {
    const user = userEvent.setup();
    const originalRow = {
      id: 7,
      character_sheet: 42,
      character_name: 'Rowan Ashcombe',
      vision_text: 'Original vision.',
      manifestation_text: '',
      deed_title: '',
      prepared_by_role: 'staff',
      crossing: null,
      updated_at: '2026-10-02T00:00:00Z',
    };
    mockApiFetch
      .mockResolvedValueOnce(okJson({ count: 1, results: [originalRow] })) // GET crossing
      .mockResolvedValueOnce(emptyList()) // GET surge
      .mockResolvedValueOnce({
        ok: false,
        status: 400,
        json: () =>
          Promise.resolve({
            non_field_errors: ['That text was used by a crossing and is now a record.'],
          }),
      } as Response) // PATCH crossing fails
      // The failed save invalidates the crossing query; it is still actively
      // observed (the dialog stays open), so it refetches automatically --
      // the server's row is unchanged by the failed PATCH.
      .mockResolvedValueOnce(okJson({ count: 1, results: [originalRow] })); // GET crossing (refetch)

    renderDialog();

    const vision = await screen.findByLabelText('Vision (private)');
    await waitFor(() => expect(vision).toHaveValue('Original vision.'));

    await user.clear(vision);
    await user.type(vision, 'Edited after load.');
    await user.click(screen.getByRole('button', { name: 'Save' }));

    expect(
      await screen.findByText('That text was used by a crossing and is now a record.')
    ).toBeInTheDocument();
    expect(screen.getByRole('alert')).toBeInTheDocument();

    // The post-failure refetch resolves and must NOT re-seed the form --
    // the GM's own typed edit is what must still be showing.
    await waitFor(() => expect(mockApiFetch).toHaveBeenCalledTimes(4));
    expect(screen.getByLabelText('Vision (private)')).toHaveValue('Edited after load.');
  });

  it('never renders an account name for "Prepared by" -- only the role label', async () => {
    mockApiFetch
      .mockResolvedValueOnce(
        okJson({
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
              // Not a real field the serializer sends (PreparedCrossingTextSerializer
              // exposes only `prepared_by_role`, never a raw account name) -- injected
              // here so this assertion can actually fail if the component ever reads
              // a raw account field instead of the role label.
              prepared_by: 'StaffUser99',
              crossing: null,
              updated_at: '2026-10-02T00:00:00Z',
            },
          ],
        })
      )
      .mockResolvedValueOnce(emptyList());

    renderDialog();

    expect(await screen.findByText('Table GM')).toBeInTheDocument();
    expect(screen.queryByText(/StaffUser99/)).toBeNull();
    expect(screen.queryByText(/@/)).toBeNull();
  });
  // #4101 final review, F9: a character with only a surge row still names
  // who prepared it, rather than the "nobody yet" fallback.
  it("names the surge row's author when there is no Crossing row", async () => {
    mockApiFetch.mockResolvedValueOnce(emptyList()).mockResolvedValueOnce(
      okJson({
        count: 1,
        results: [
          {
            id: 3,
            character_sheet: 42,
            character_name: 'Rowan Ashcombe',
            surge_text: 'Old surge line.',
            prepared_by_role: 'staff',
            updated_at: '2026-10-02T00:00:00Z',
          },
        ],
      })
    );

    renderDialog();

    expect(await screen.findByText('Staff')).toBeInTheDocument();
    expect(screen.queryByText("Staff, or Rowan Ashcombe's table GM")).toBeNull();
  });
});
