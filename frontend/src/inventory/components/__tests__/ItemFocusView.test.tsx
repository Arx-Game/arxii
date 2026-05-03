/**
 * ItemFocusView component tests.
 *
 * The component fetches via ``useVisibleItemDetail``; we mock that hook
 * to drive each branch (loading / error / data) and assert the rendered
 * markup matches the design contract from Task 8 (markdown description,
 * quality tier border accent, stats, no action buttons).
 */

import { screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { renderWithProviders } from '@/test/utils/renderWithProviders';
import type { UseQueryResult } from '@tanstack/react-query';

import { ItemFocusView } from '../ItemFocusView';
import type { ItemInstance } from '../../types';

vi.mock('../../hooks/useVisibleItemDetail', () => ({
  useVisibleItemDetail: vi.fn(),
}));

import * as visibleItemHooks from '../../hooks/useVisibleItemDetail';

type ItemDetailQueryResult = UseQueryResult<ItemInstance, Error>;

function mockUseVisibleItemDetail(partial: Partial<ItemDetailQueryResult>) {
  vi.mocked(visibleItemHooks.useVisibleItemDetail).mockReturnValue({
    data: undefined,
    error: null,
    isLoading: false,
    isError: false,
    isSuccess: false,
    isPending: false,
    isFetching: false,
    isStale: false,
    isPlaceholderData: false,
    refetch: vi.fn(),
    status: 'success',
    fetchStatus: 'idle',
    ...partial,
  } as unknown as ItemDetailQueryResult);
}

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
    ...overrides,
  };
}

const itemRef = { id: 7, name: 'Silver Brooch' };

describe('ItemFocusView', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders without crashing in the loading state', () => {
    mockUseVisibleItemDetail({ isLoading: true, isPending: true, status: 'pending' });
    renderWithProviders(<ItemFocusView item={itemRef} />);
    expect(screen.getByTestId('item-focus-loading')).toBeInTheDocument();
  });

  it('renders the unavailable fallback on error', () => {
    mockUseVisibleItemDetail({ isError: true, error: new Error('not found'), status: 'error' });
    renderWithProviders(<ItemFocusView item={itemRef} />);
    expect(screen.getByText('Silver Brooch')).toBeInTheDocument();
    expect(screen.getByText(/item details unavailable/i)).toBeInTheDocument();
  });

  it('renders the item name and quality tier badge when data resolves', () => {
    mockUseVisibleItemDetail({ data: makeItem(), isSuccess: true });
    renderWithProviders(<ItemFocusView item={itemRef} />);
    expect(screen.getByRole('heading', { name: 'Silver Brooch' })).toBeInTheDocument();
    expect(screen.getByText('Exquisite')).toBeInTheDocument();
  });

  it('renders the markdown description with bold and list items', () => {
    mockUseVisibleItemDetail({ data: makeItem(), isSuccess: true });
    renderWithProviders(<ItemFocusView item={itemRef} />);
    // **silver brooch** -> <strong>silver brooch</strong>
    expect(screen.getByText('silver brooch')).toBeInTheDocument();
    // List items render as plain text
    expect(screen.getByText('looping vines')).toBeInTheDocument();
    expect(screen.getByText('a single garnet')).toBeInTheDocument();
    // Container has the prose+description testid
    expect(screen.getByTestId('item-focus-description')).toBeInTheDocument();
  });

  it('renders the stats grid with weight, size, and value', () => {
    mockUseVisibleItemDetail({ data: makeItem(), isSuccess: true });
    renderWithProviders(<ItemFocusView item={itemRef} />);
    expect(screen.getByText(/weight/i)).toBeInTheDocument();
    expect(screen.getByText(/size/i)).toBeInTheDocument();
    expect(screen.getByText(/value/i)).toBeInTheDocument();
    expect(screen.getByText('0.10')).toBeInTheDocument();
    expect(screen.getByText('50')).toBeInTheDocument();
  });

  it('applies the quality tier color as the image left-border accent', () => {
    mockUseVisibleItemDetail({ data: makeItem(), isSuccess: true });
    renderWithProviders(<ItemFocusView item={itemRef} />);
    const imageWrapper = screen.getByTestId('item-focus-image') as HTMLElement;
    expect(imageWrapper.style.borderLeftColor).toBeTruthy();
    // jsdom normalizes hex to rgb — #a855f7 -> rgb(168, 85, 247)
    expect(imageWrapper.style.borderLeftColor.toLowerCase()).toContain('168, 85, 247');
  });

  it('falls back to the first letter when no display image is provided', () => {
    mockUseVisibleItemDetail({ data: makeItem({ display_image_url: null }), isSuccess: true });
    const { container } = renderWithProviders(<ItemFocusView item={itemRef} />);
    const initialEl = container.querySelector('[data-fallback-initial]');
    expect(initialEl?.textContent).toBe('S');
  });

  it('does NOT render any action buttons (read-only sidebar drill-in)', () => {
    mockUseVisibleItemDetail({ data: makeItem(), isSuccess: true });
    renderWithProviders(<ItemFocusView item={itemRef} />);
    // None of the wardrobe-style actions should appear here.
    expect(screen.queryByRole('button', { name: /^wear$/i })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /^remove$/i })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /^drop$/i })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /^give$/i })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /^put in$/i })).not.toBeInTheDocument();
  });
});
