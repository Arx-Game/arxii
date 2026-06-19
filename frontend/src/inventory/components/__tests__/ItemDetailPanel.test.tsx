/**
 * ItemDetailPanel component tests.
 */

import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { ItemDetailPanel } from '../ItemDetailPanel';
import type { ItemInstance } from '../../types';

// ---------------------------------------------------------------------------
// Module mocks
// ---------------------------------------------------------------------------

vi.mock('../../hooks/useItemFacets', () => ({
  useItemFacets: vi.fn(),
  useQualityTiers: vi.fn(),
  useRemoveItemFacet: vi.fn(),
}));

vi.mock('../../hooks/useUseItem', () => ({ useUseItem: vi.fn() }));

vi.mock('@/character-creation/queries', () => ({
  useFacets: vi.fn(),
}));

// AttachFacetDialog has its own tests; stub it here to avoid deep render.
vi.mock('../AttachFacetDialog', () => ({
  AttachFacetDialog: ({
    open,
    itemInstanceId,
  }: {
    open: boolean;
    onOpenChange: (v: boolean) => void;
    itemInstanceId: number;
  }) =>
    open ? (
      <div data-testid="attach-facet-dialog" data-item-id={itemInstanceId}>
        AttachFacetDialog
      </div>
    ) : null,
}));

vi.mock('sonner', () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
  },
}));

import * as itemFacetsHooks from '../../hooks/useItemFacets';
import * as characterCreationQueries from '@/character-creation/queries';
import { useUseItem } from '../../hooks/useUseItem';

// ---------------------------------------------------------------------------
// Default mock setup helpers
// ---------------------------------------------------------------------------

function setupDefaultMocks() {
  vi.mocked(useUseItem).mockReturnValue({
    mutate: vi.fn(),
    isPending: false,
  } as unknown as ReturnType<typeof useUseItem>);

  vi.mocked(itemFacetsHooks.useItemFacets).mockReturnValue({
    data: [],
    isLoading: false,
    isError: false,
    error: null,
  } as unknown as ReturnType<typeof itemFacetsHooks.useItemFacets>);

  vi.mocked(itemFacetsHooks.useQualityTiers).mockReturnValue({
    data: [],
    isLoading: false,
    isError: false,
    error: null,
  } as unknown as ReturnType<typeof itemFacetsHooks.useQualityTiers>);

  vi.mocked(itemFacetsHooks.useRemoveItemFacet).mockReturnValue({
    mutate: vi.fn(),
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

  vi.mocked(characterCreationQueries.useFacets).mockReturnValue({
    data: [],
    isLoading: false,
    isError: false,
    error: null,
  } as unknown as ReturnType<typeof characterCreationQueries.useFacets>);
}

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

function makeItem(overrides: Partial<ItemInstance> = {}): ItemInstance {
  return {
    id: 7,
    template: {
      id: 70,
      name: 'Silver Brooch',
      weight: '0.10',
      size: 1,
      value: 50,
      is_container: false,
      is_stackable: false,
      is_consumable: false,
      is_craftable: true,
      image_url: '',
    },
    quality_tier: {
      id: 4,
      name: 'Exquisite',
      color_hex: '#a855f7',
      numeric_min: 75,
      numeric_max: 90,
      stat_multiplier: '1.25',
      sort_order: 4,
    },
    display_name: 'Silver Brooch',
    display_description:
      'A delicate **silver brooch** etched with:\n\n- looping vines\n- a single garnet\n\nIts clasp turns smoothly.',
    display_image_url: null,
    contained_in: 1,
    quantity: 1,
    charges: 0,
    is_open: false,
    is_usable: false,
    ...overrides,
  };
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('ItemDetailPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    setupDefaultMocks();
  });

  it('renders nothing visible when closed', () => {
    render(<ItemDetailPanel item={makeItem()} open={false} onOpenChange={vi.fn()} />);
    expect(screen.queryByText('Silver Brooch')).not.toBeInTheDocument();
  });

  it('renders the item name and quality tier when open', () => {
    render(<ItemDetailPanel item={makeItem()} open={true} onOpenChange={vi.fn()} />);
    expect(screen.getByText('Silver Brooch')).toBeInTheDocument();
    expect(screen.getByText('Exquisite')).toBeInTheDocument();
  });

  it('renders markdown description with bold and list', () => {
    render(<ItemDetailPanel item={makeItem()} open={true} onOpenChange={vi.fn()} />);
    // Bold appears as <strong>
    expect(screen.getByText('silver brooch')).toBeInTheDocument();
    // List items render
    expect(screen.getByText('looping vines')).toBeInTheDocument();
    expect(screen.getByText('a single garnet')).toBeInTheDocument();
  });

  it('renders the stats grid (weight, size, value)', () => {
    render(<ItemDetailPanel item={makeItem()} open={true} onOpenChange={vi.fn()} />);
    expect(screen.getByText(/weight/i)).toBeInTheDocument();
    expect(screen.getByText(/size/i)).toBeInTheDocument();
    expect(screen.getByText(/value/i)).toBeInTheDocument();
    expect(screen.getByText('0.10')).toBeInTheDocument();
    expect(screen.getByText('50')).toBeInTheDocument();
  });

  it('shows Wear action when item is not equipped', () => {
    const onWear = vi.fn();
    render(
      <ItemDetailPanel
        item={makeItem()}
        open={true}
        onOpenChange={vi.fn()}
        onWear={onWear}
        isEquipped={false}
      />
    );
    const wear = screen.getByRole('button', { name: /^wear$/i });
    fireEvent.click(wear);
    expect(onWear).toHaveBeenCalledWith(7);
  });

  it('shows Remove action instead of Wear when equipped', () => {
    const onRemove = vi.fn();
    render(
      <ItemDetailPanel
        item={makeItem()}
        open={true}
        onOpenChange={vi.fn()}
        onRemove={onRemove}
        isEquipped={true}
      />
    );
    expect(screen.queryByRole('button', { name: /^wear$/i })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /^remove$/i }));
    expect(onRemove).toHaveBeenCalledWith(7);
  });

  it('falls back to first letter when no display image is provided', () => {
    render(<ItemDetailPanel item={makeItem()} open={true} onOpenChange={vi.fn()} />);
    expect(screen.getByText('S', { selector: '[data-fallback-initial]' })).toBeInTheDocument();
  });

  it('renders gracefully when item is null', () => {
    render(<ItemDetailPanel item={null} open={true} onOpenChange={vi.fn()} />);
    // No item — panel may be open but nothing about Silver Brooch
    expect(screen.queryByText('Silver Brooch')).not.toBeInTheDocument();
  });

  // -------------------------------------------------------------------------
  // Attach Facet button
  // -------------------------------------------------------------------------

  it('renders an Attach Facet button in the action row', () => {
    render(<ItemDetailPanel item={makeItem()} open={true} onOpenChange={vi.fn()} />);
    expect(screen.getByRole('button', { name: /attach facet/i })).toBeInTheDocument();
  });

  it('opens AttachFacetDialog when Attach Facet is clicked', () => {
    render(<ItemDetailPanel item={makeItem()} open={true} onOpenChange={vi.fn()} />);
    expect(screen.queryByTestId('attach-facet-dialog')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /attach facet/i }));
    expect(screen.getByTestId('attach-facet-dialog')).toBeInTheDocument();
  });

  // -------------------------------------------------------------------------
  // Live facet chips
  // -------------------------------------------------------------------------

  it('does not show facet section when item has no facets', () => {
    render(<ItemDetailPanel item={makeItem()} open={true} onOpenChange={vi.fn()} />);
    expect(screen.queryByText(/^facets$/i)).not.toBeInTheDocument();
  });

  it('renders live facet chips with resolved name and remove button', () => {
    vi.mocked(itemFacetsHooks.useItemFacets).mockReturnValue({
      data: [
        {
          id: 11,
          item_instance: 7,
          facet: 3,
          attachment_quality_tier: 4,
          applied_by_account: null,
          applied_at: '2026-01-01T00:00:00Z',
        },
      ],
      isLoading: false,
      isError: false,
      error: null,
    } as unknown as ReturnType<typeof itemFacetsHooks.useItemFacets>);

    vi.mocked(characterCreationQueries.useFacets).mockReturnValue({
      data: [{ id: 3, name: 'Wolf', full_path: 'Creatures / Wolf', description: '' }],
      isLoading: false,
      isError: false,
      error: null,
    } as unknown as ReturnType<typeof characterCreationQueries.useFacets>);

    vi.mocked(itemFacetsHooks.useQualityTiers).mockReturnValue({
      data: [{ id: 4, name: 'Exquisite', color_hex: '#a855f7', sort_order: 4 }],
      isLoading: false,
      isError: false,
      error: null,
    } as unknown as ReturnType<typeof itemFacetsHooks.useQualityTiers>);

    render(<ItemDetailPanel item={makeItem()} open={true} onOpenChange={vi.fn()} />);

    expect(screen.getByText('Creatures / Wolf')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /remove facet 3/i })).toBeInTheDocument();
  });

  it('falls back to "Facet #<id>" when facet id is not in useFacets data', () => {
    vi.mocked(itemFacetsHooks.useItemFacets).mockReturnValue({
      data: [
        {
          id: 22,
          item_instance: 7,
          facet: 99,
          attachment_quality_tier: 1,
          applied_by_account: null,
          applied_at: '2026-01-01T00:00:00Z',
        },
      ],
      isLoading: false,
      isError: false,
      error: null,
    } as unknown as ReturnType<typeof itemFacetsHooks.useItemFacets>);

    render(<ItemDetailPanel item={makeItem()} open={true} onOpenChange={vi.fn()} />);

    expect(screen.getByText('Facet #99')).toBeInTheDocument();
  });

  // -------------------------------------------------------------------------
  // Use button
  // -------------------------------------------------------------------------

  it('hides the Use button when the item is not usable', () => {
    render(
      <ItemDetailPanel
        item={makeItem({ is_usable: false })}
        characterId={1}
        open
        onOpenChange={vi.fn()}
      />
    );
    expect(screen.queryByRole('button', { name: /^use$/i })).toBeNull();
  });

  it('disables Use for a depleted consumable', () => {
    const item = makeItem({
      is_usable: true,
      charges: 0,
      template: { ...makeItem().template, is_consumable: true },
    });
    render(<ItemDetailPanel item={item} characterId={1} open onOpenChange={vi.fn()} />);
    expect(screen.getByRole('button', { name: /^use$/i })).toBeDisabled();
  });

  it('calls the use mutation with the item id when Use is clicked', () => {
    const mutate = vi.fn();
    vi.mocked(useUseItem).mockReturnValue({ mutate, isPending: false } as unknown as ReturnType<
      typeof useUseItem
    >);
    const item = makeItem({
      is_usable: true,
      charges: 3,
      template: { ...makeItem().template, is_consumable: true },
    });
    render(<ItemDetailPanel item={item} characterId={1} open onOpenChange={vi.fn()} />);
    fireEvent.click(screen.getByRole('button', { name: /^use$/i }));
    expect(mutate).toHaveBeenCalledWith(item.id, expect.any(Object));
  });

  it('use-result block resets when the panel switches to a different item', () => {
    const mutate = vi.fn((_id, opts) =>
      opts.onSuccess({
        charges_remaining: 2,
        destroyed: false,
        soft_deleted: false,
        applied_effect_count: 1,
      })
    );
    vi.mocked(useUseItem).mockReturnValue({ mutate, isPending: false } as unknown as ReturnType<
      typeof useUseItem
    >);

    const itemA = makeItem({
      id: 7,
      is_usable: true,
      charges: 3,
      template: { ...makeItem().template, is_consumable: true },
    });
    const itemB = makeItem({
      id: 99,
      display_name: 'Iron Dagger',
      is_usable: true,
      charges: 3,
      template: { ...makeItem().template, is_consumable: true },
    });

    const { rerender } = render(
      <ItemDetailPanel item={itemA} characterId={1} open onOpenChange={vi.fn()} />
    );
    fireEvent.click(screen.getByRole('button', { name: /^use$/i }));
    expect(screen.getByTestId('use-result')).toBeInTheDocument();

    rerender(<ItemDetailPanel item={itemB} characterId={1} open onOpenChange={vi.fn()} />);
    expect(screen.queryByTestId('use-result')).toBeNull();
  });

  it('calls removeMutation.mutate when remove button is clicked', () => {
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

    vi.mocked(itemFacetsHooks.useItemFacets).mockReturnValue({
      data: [
        {
          id: 11,
          item_instance: 7,
          facet: 3,
          attachment_quality_tier: 1,
          applied_by_account: null,
          applied_at: '2026-01-01T00:00:00Z',
        },
      ],
      isLoading: false,
      isError: false,
      error: null,
    } as unknown as ReturnType<typeof itemFacetsHooks.useItemFacets>);

    render(<ItemDetailPanel item={makeItem()} open={true} onOpenChange={vi.fn()} />);

    fireEvent.click(screen.getByRole('button', { name: /remove facet 3/i }));
    expect(mutate).toHaveBeenCalledWith(11, expect.any(Object));
  });
});
