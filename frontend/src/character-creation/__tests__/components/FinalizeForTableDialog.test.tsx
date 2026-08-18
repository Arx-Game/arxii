/**
 * FinalizeForTableDialog Tests (#3268)
 *
 * Covers: submit payload shape, rendering the backend's 400 `{detail}`
 * verbatim, and the submit-button gating (table + story title required).
 *
 * `@/components/ui/select` is mocked to a plain `<select>` — the real Radix
 * Select doesn't do layout/pointer-capture in jsdom (established pattern,
 * see `boundaries/__tests__/PlayerBoundaryFormDialog.test.tsx`).
 */

import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { vi } from 'vitest';
import { ApiError } from '@/lib/errors';
import type { GMTable } from '@/tables/types';
import { FinalizeForTableDialog } from '../../components/FinalizeForTableDialog';
import { characterCreationKeys } from '../../queries';
import type { FinalizeForTableResponse } from '../../api';

/** Shape of the second argument `mutate(variables, opts)` is called with. */
interface MutateOpts {
  onSuccess?: (data: FinalizeForTableResponse) => void;
  onError?: (err: unknown) => void;
}

vi.mock('@/components/ui/select', () => ({
  Select: ({
    value,
    onValueChange,
    children,
  }: {
    value?: string;
    onValueChange?: (v: string) => void;
    children?: React.ReactNode;
  }) => (
    <select
      value={value}
      onChange={(e) => onValueChange?.(e.target.value)}
      data-testid="mock-select"
    >
      <option value="" disabled>
        Select a table
      </option>
      {children}
    </select>
  ),
  SelectTrigger: ({ children }: { children?: React.ReactNode }) => <>{children}</>,
  SelectValue: () => null,
  SelectContent: ({ children }: { children?: React.ReactNode }) => <>{children}</>,
  SelectItem: ({ value, children }: { value: string; children?: React.ReactNode }) => (
    <option value={value}>{children}</option>
  ),
}));

vi.mock('../../queries', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../queries')>();
  return {
    ...actual,
    useFinalizeDraftForTable: vi.fn(),
  };
});

import * as queries from '../../queries';

function makeTable(overrides: Partial<GMTable> = {}): GMTable {
  return {
    id: 1,
    gm: 10,
    gm_username: 'gmUser',
    name: 'The Salt Road',
    description: '',
    status: 'active',
    created_at: '2026-01-01T00:00:00Z',
    archived_at: null,
    member_count: 2,
    story_count: 1,
    viewer_role: 'gm',
    ...overrides,
  } as GMTable;
}

function makeQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
}

/**
 * Renders the dialog with an explicit (returned) QueryClient — tests that
 * check cache side effects (the unmount-cleanup safety net, #3268 review fix)
 * need a handle on the same client instance the component reads/writes.
 */
function renderDialog(tables: GMTable[] = [makeTable()], client: QueryClient = makeQueryClient()) {
  const utils = render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <FinalizeForTableDialog draftId={7} tables={tables} open={true} onOpenChange={vi.fn()} />
      </MemoryRouter>
    </QueryClientProvider>
  );
  return { ...utils, client };
}

describe('FinalizeForTableDialog', () => {
  it('submits {target_table, story_title, story_description} to finalizeDraftForTable', async () => {
    const mutateFn = vi.fn();
    vi.mocked(queries.useFinalizeDraftForTable).mockReturnValue({
      mutate: mutateFn,
      isPending: false,
    } as unknown as ReturnType<typeof queries.useFinalizeDraftForTable>);

    const user = userEvent.setup();
    renderDialog();

    await userEvent.selectOptions(screen.getByTestId('mock-select'), '1');
    await user.type(screen.getByLabelText(/story title/i), 'The Long Road Home');
    await user.type(screen.getByLabelText(/story description/i), 'A caravan crosses the wastes.');
    await user.click(screen.getByRole('button', { name: /^finalize for my table$/i }));

    expect(mutateFn).toHaveBeenCalledWith(
      {
        draftId: 7,
        payload: {
          target_table: 1,
          story_title: 'The Long Road Home',
          story_description: 'A caravan crosses the wastes.',
        },
      },
      expect.any(Object)
    );
  });

  it('omits story_description when left blank', async () => {
    const mutateFn = vi.fn();
    vi.mocked(queries.useFinalizeDraftForTable).mockReturnValue({
      mutate: mutateFn,
      isPending: false,
    } as unknown as ReturnType<typeof queries.useFinalizeDraftForTable>);

    const user = userEvent.setup();
    renderDialog();

    await userEvent.selectOptions(screen.getByTestId('mock-select'), '1');
    await user.type(screen.getByLabelText(/story title/i), 'The Long Road Home');
    await user.click(screen.getByRole('button', { name: /^finalize for my table$/i }));

    expect(mutateFn).toHaveBeenCalledWith(
      expect.objectContaining({
        payload: expect.objectContaining({ story_description: undefined }),
      }),
      expect.any(Object)
    );
  });

  it('renders the backend 400 detail verbatim on failure', async () => {
    const mutateFn = vi.fn((_vars: unknown, opts: MutateOpts) => {
      opts.onError?.(
        new ApiError('That draft is not complete yet.', {
          status: 400,
          detail: 'That draft is not complete yet.',
        })
      );
    });
    vi.mocked(queries.useFinalizeDraftForTable).mockReturnValue({
      mutate: mutateFn,
      isPending: false,
    } as unknown as ReturnType<typeof queries.useFinalizeDraftForTable>);

    const user = userEvent.setup();
    renderDialog();

    await userEvent.selectOptions(screen.getByTestId('mock-select'), '1');
    await user.type(screen.getByLabelText(/story title/i), 'The Long Road Home');
    await user.click(screen.getByRole('button', { name: /^finalize for my table$/i }));

    expect(await screen.findByText('That draft is not complete yet.')).toBeInTheDocument();
  });

  it('shows a success panel naming the message and linking to the specific table', async () => {
    const mutateFn = vi.fn((_vars: unknown, opts: MutateOpts) => {
      opts.onSuccess?.({
        character_id: 55,
        roster_entry_id: 66,
        story_id: 77,
        message: 'GM character created on the Available roster.',
      });
    });
    vi.mocked(queries.useFinalizeDraftForTable).mockReturnValue({
      mutate: mutateFn,
      isPending: false,
    } as unknown as ReturnType<typeof queries.useFinalizeDraftForTable>);

    const user = userEvent.setup();
    renderDialog([makeTable({ id: 42 })]);

    await userEvent.selectOptions(screen.getByTestId('mock-select'), '42');
    await user.type(screen.getByLabelText(/story title/i), 'The Long Road Home');
    await user.click(screen.getByRole('button', { name: /^finalize for my table$/i }));

    expect(
      await screen.findByText('GM character created on the Available roster.')
    ).toBeInTheDocument();
    const link = screen.getByRole('link', { name: /go to my table/i });
    expect(link).toHaveAttribute('href', '/tables/42');
  });

  it('clears the finalized draft from cache when the link to the table is clicked', async () => {
    const mutateFn = vi.fn((_vars: unknown, opts: MutateOpts) => {
      opts.onSuccess?.({
        character_id: 55,
        roster_entry_id: 66,
        story_id: 77,
        message: 'GM character created on the Available roster.',
      });
    });
    vi.mocked(queries.useFinalizeDraftForTable).mockReturnValue({
      mutate: mutateFn,
      isPending: false,
    } as unknown as ReturnType<typeof queries.useFinalizeDraftForTable>);

    const user = userEvent.setup();
    const client = makeQueryClient();
    client.setQueryData(characterCreationKeys.draft(), { id: 7 });
    renderDialog([makeTable()], client);

    await userEvent.selectOptions(screen.getByTestId('mock-select'), '1');
    await user.type(screen.getByLabelText(/story title/i), 'The Long Road Home');
    await user.click(screen.getByRole('button', { name: /^finalize for my table$/i }));
    await user.click(await screen.findByRole('link', { name: /go to my table/i }));

    expect(client.getQueryData(characterCreationKeys.draft())).toBeNull();
  });

  it('clears the finalized draft from cache on unmount even if the player never dismisses the panel (#3268 review fix)', async () => {
    const mutateFn = vi.fn((_vars: unknown, opts: MutateOpts) => {
      opts.onSuccess?.({
        character_id: 55,
        roster_entry_id: 66,
        story_id: 77,
        message: 'GM character created on the Available roster.',
      });
    });
    vi.mocked(queries.useFinalizeDraftForTable).mockReturnValue({
      mutate: mutateFn,
      isPending: false,
    } as unknown as ReturnType<typeof queries.useFinalizeDraftForTable>);

    const user = userEvent.setup();
    const client = makeQueryClient();
    client.setQueryData(characterCreationKeys.draft(), { id: 7 });
    const { unmount } = renderDialog([makeTable()], client);

    await userEvent.selectOptions(screen.getByTestId('mock-select'), '1');
    await user.type(screen.getByLabelText(/story title/i), 'The Long Road Home');
    await user.click(screen.getByRole('button', { name: /^finalize for my table$/i }));
    await screen.findByText('GM character created on the Available roster.');

    // Simulates a router navigation away (e.g. browser Back) that unmounts
    // ReviewStage/this dialog directly, bypassing the X/Cancel/Link handlers.
    unmount();

    expect(client.getQueryData(characterCreationKeys.draft())).toBeNull();
  });

  it('does not touch the draft cache on unmount when the player never finalized', () => {
    vi.mocked(queries.useFinalizeDraftForTable).mockReturnValue({
      mutate: vi.fn(),
      isPending: false,
    } as unknown as ReturnType<typeof queries.useFinalizeDraftForTable>);

    const client = makeQueryClient();
    const sentinelDraft = { id: 7 };
    client.setQueryData(characterCreationKeys.draft(), sentinelDraft);
    const { unmount } = renderDialog([makeTable()], client);

    unmount();

    expect(client.getQueryData(characterCreationKeys.draft())).toBe(sentinelDraft);
  });

  describe('submit gating', () => {
    it('is disabled until a table and a story title are both set', async () => {
      vi.mocked(queries.useFinalizeDraftForTable).mockReturnValue({
        mutate: vi.fn(),
        isPending: false,
      } as unknown as ReturnType<typeof queries.useFinalizeDraftForTable>);

      const user = userEvent.setup();
      renderDialog();

      const submitButton = screen.getByRole('button', { name: /^finalize for my table$/i });
      expect(submitButton).toBeDisabled();

      await userEvent.selectOptions(screen.getByTestId('mock-select'), '1');
      expect(submitButton).toBeDisabled();

      await user.type(screen.getByLabelText(/story title/i), 'The Long Road Home');
      expect(submitButton).not.toBeDisabled();
    });

    it('is disabled while the mutation is pending', () => {
      vi.mocked(queries.useFinalizeDraftForTable).mockReturnValue({
        mutate: vi.fn(),
        isPending: true,
      } as unknown as ReturnType<typeof queries.useFinalizeDraftForTable>);

      renderDialog();

      expect(screen.getByRole('button', { name: /finalizing/i })).toBeDisabled();
    });
  });
});
