/**
 * AttachFacetDialog component tests.
 */

import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { renderWithProviders } from '@/test/utils/renderWithProviders';
import { AttachFacetDialog } from '../AttachFacetDialog';

// ---------------------------------------------------------------------------
// Module mocks
// ---------------------------------------------------------------------------

vi.mock('../../hooks/useItemFacets', () => ({
  useItemFacets: vi.fn(),
  useCraftAttachFacet: vi.fn(),
  useRemoveItemFacet: vi.fn(),
}));

vi.mock('@/character-creation/queries', () => ({
  useFacets: vi.fn(),
}));

vi.mock('sonner', () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
  },
}));

import * as itemFacetsHooks from '../../hooks/useItemFacets';
import * as characterCreationQueries from '@/character-creation/queries';
import { toast } from 'sonner';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function makeCraftMock() {
  const mutate = vi.fn();
  vi.mocked(itemFacetsHooks.useCraftAttachFacet).mockReturnValue({
    mutate,
    mutateAsync: vi.fn(),
    isPending: false,
    isSuccess: false,
    isError: false,
    isIdle: true,
    error: null,
    data: undefined,
    variables: undefined,
    status: 'idle',
    reset: vi.fn(),
    context: undefined,
    failureCount: 0,
    failureReason: null,
    isPaused: false,
    submittedAt: 0,
  } as unknown as ReturnType<typeof itemFacetsHooks.useCraftAttachFacet>);
  return mutate;
}

function makeRemoveMock() {
  const mutate = vi.fn();
  vi.mocked(itemFacetsHooks.useRemoveItemFacet).mockReturnValue({
    mutate,
    mutateAsync: vi.fn(),
    isPending: false,
    isSuccess: false,
    isError: false,
    isIdle: true,
    error: null,
    data: undefined,
    variables: undefined,
    status: 'idle',
    reset: vi.fn(),
    context: undefined,
    failureCount: 0,
    failureReason: null,
    isPaused: false,
    submittedAt: 0,
  } as unknown as ReturnType<typeof itemFacetsHooks.useRemoveItemFacet>);
  return mutate;
}

function setupDefaultMocks() {
  // No existing facets on the item by default.
  vi.mocked(itemFacetsHooks.useItemFacets).mockReturnValue({
    data: [],
    isLoading: false,
    isError: false,
    error: null,
  } as unknown as ReturnType<typeof itemFacetsHooks.useItemFacets>);

  // One available facet in the library.
  vi.mocked(characterCreationQueries.useFacets).mockReturnValue({
    data: [
      {
        id: 7,
        name: 'Spider',
        full_path: 'Spider',
        description: '',
        parent: null,
        parent_name: null,
        depth: 0,
      },
    ],
    isLoading: false,
    isError: false,
    error: null,
  } as unknown as ReturnType<typeof characterCreationQueries.useFacets>);
}

const ITEM_INSTANCE_ID = 42;

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('AttachFacetDialog', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    setupDefaultMocks();
  });

  it('renders the dialog title and description when open', () => {
    makeCraftMock();
    makeRemoveMock();
    renderWithProviders(
      <AttachFacetDialog open={true} onOpenChange={vi.fn()} itemInstanceId={ITEM_INSTANCE_ID} />
    );
    expect(screen.getByText('Attach Facet')).toBeInTheDocument();
    expect(screen.getByText(/quality is determined by your enchanting skill/i)).toBeInTheDocument();
  });

  it('does not render when open=false', () => {
    makeCraftMock();
    makeRemoveMock();
    renderWithProviders(
      <AttachFacetDialog open={false} onOpenChange={vi.fn()} itemInstanceId={ITEM_INSTANCE_ID} />
    );
    expect(screen.queryByText('Attach Facet')).not.toBeInTheDocument();
  });

  it('disables the Attach button when no facet is selected', () => {
    makeCraftMock();
    makeRemoveMock();
    renderWithProviders(
      <AttachFacetDialog open={true} onOpenChange={vi.fn()} itemInstanceId={ITEM_INSTANCE_ID} />
    );
    const attachBtn = screen.getByRole('button', { name: /attach/i });
    expect(attachBtn).toBeDisabled();
  });

  // -------------------------------------------------------------------------
  // Test 1: Submit posts { item_instance, facet } with no tier
  // -------------------------------------------------------------------------
  it('calls mutate with { item_instance, facet } when Spider is selected and Attach clicked', async () => {
    // Radix Popover sets `pointer-events: none` on <body> while closed;
    // user-event guards against this by default. Disable that check so we can
    // interact with the cmdk-backed Combobox popover in jsdom.
    const user = userEvent.setup({ pointerEventsCheck: 0 });
    const mutate = makeCraftMock();
    makeRemoveMock();

    renderWithProviders(
      <AttachFacetDialog open={true} onOpenChange={vi.fn()} itemInstanceId={ITEM_INSTANCE_ID} />
    );

    // Open the combobox popover by clicking the trigger button.
    const triggerButton = screen.getByRole('combobox');
    await user.click(triggerButton);

    // Click the 'Spider' option in the open popover.
    const spiderOption = await screen.findByText('Spider');
    await user.click(spiderOption);

    // Click the Attach button.
    const attachBtn = screen.getByRole('button', { name: /attach/i });
    await user.click(attachBtn);

    expect(mutate).toHaveBeenCalledWith(
      { item_instance: ITEM_INSTANCE_ID, facet: 7 },
      expect.any(Object)
    );

    // Confirm the payload does NOT include attachment_quality_tier.
    const [payload] = mutate.mock.calls[0] as [Record<string, unknown>, unknown];
    expect(Object.keys(payload)).not.toContain('attachment_quality_tier');
  });

  // -------------------------------------------------------------------------
  // Test 2: Success result shows the rolled tier
  // -------------------------------------------------------------------------
  it('shows toast.success with quality tier name on attached=true result', async () => {
    const user = userEvent.setup({ pointerEventsCheck: 0 });
    const mutate = makeCraftMock();
    makeRemoveMock();

    mutate.mockImplementation(
      (
        _vars: unknown,
        callbacks: { onSuccess?: (r: unknown) => void; onError?: (e: unknown) => void }
      ) => {
        callbacks?.onSuccess?.({
          attached: true,
          outcome_name: 'Success',
          quality_tier: { id: 2, name: 'Fine', color_hex: '#888', sort_order: 2 },
          item_facet: { id: 99, item_instance: ITEM_INSTANCE_ID, facet: 7 },
        });
      }
    );

    renderWithProviders(
      <AttachFacetDialog open={true} onOpenChange={vi.fn()} itemInstanceId={ITEM_INSTANCE_ID} />
    );

    // Open combobox and select Spider.
    await user.click(screen.getByRole('combobox'));
    await user.click(await screen.findByText('Spider'));

    // Click Attach.
    await user.click(screen.getByRole('button', { name: /attach/i }));

    await waitFor(() => {
      expect(toast.success).toHaveBeenCalledWith(expect.stringContaining('Fine'));
    });
  });

  // -------------------------------------------------------------------------
  // Test 3: Failed roll shows failure toast
  // -------------------------------------------------------------------------
  it('shows toast.error with failure message on attached=false result', async () => {
    const user = userEvent.setup({ pointerEventsCheck: 0 });
    const mutate = makeCraftMock();
    makeRemoveMock();

    mutate.mockImplementation(
      (
        _vars: unknown,
        callbacks: { onSuccess?: (r: unknown) => void; onError?: (e: unknown) => void }
      ) => {
        callbacks?.onSuccess?.({
          attached: false,
          outcome_name: 'Botch',
          quality_tier: null,
          item_facet: null,
        });
      }
    );

    renderWithProviders(
      <AttachFacetDialog open={true} onOpenChange={vi.fn()} itemInstanceId={ITEM_INSTANCE_ID} />
    );

    // Open combobox and select Spider.
    await user.click(screen.getByRole('combobox'));
    await user.click(await screen.findByText('Spider'));

    // Click Attach.
    await user.click(screen.getByRole('button', { name: /attach/i }));

    await waitFor(() => {
      expect(toast.error).toHaveBeenCalledWith(expect.stringContaining('failed'));
    });
  });

  // -------------------------------------------------------------------------
  // Additional: existing facets show as chips with remove buttons
  // -------------------------------------------------------------------------
  it('renders current facet chips with remove buttons', () => {
    const mutate = makeCraftMock();
    makeRemoveMock();

    vi.mocked(itemFacetsHooks.useItemFacets).mockReturnValue({
      data: [
        {
          id: 11,
          item_instance: ITEM_INSTANCE_ID,
          facet: 3,
          attachment_quality_tier: 2,
          applied_by_account: null,
          applied_at: '2026-01-01T00:00:00Z',
        },
      ],
      isLoading: false,
      isError: false,
      error: null,
    } as unknown as ReturnType<typeof itemFacetsHooks.useItemFacets>);

    renderWithProviders(
      <AttachFacetDialog open={true} onOpenChange={vi.fn()} itemInstanceId={ITEM_INSTANCE_ID} />
    );

    expect(screen.getByText('Facet #3')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /remove facet 3/i })).toBeInTheDocument();

    // Suppress unused variable warning — mutate is set up but not clicked here.
    expect(mutate).not.toHaveBeenCalled();
  });
});
