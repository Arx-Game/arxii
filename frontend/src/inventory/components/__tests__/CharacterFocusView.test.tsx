/**
 * CharacterFocusView component tests.
 *
 * The component is a thin shell over ``useVisibleWornItems``; we mock
 * that hook to drive each branch (loading / empty / populated) without
 * spinning up MSW or a real react-query fetch.
 */

import { fireEvent, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { renderWithProviders } from '@/test/utils/renderWithProviders';
import type { UseQueryResult } from '@tanstack/react-query';

import { CharacterFocusView } from '../CharacterFocusView';
import { humanizeRegionLayer } from '../../humanizeRegionLayer';
import type { VisibleWornItem } from '../../api';

vi.mock('../../hooks/useVisibleWornItems', () => ({
  useVisibleWornItems: vi.fn(),
}));

import * as visibleWornHooks from '../../hooks/useVisibleWornItems';

type VisibleWornQueryResult = UseQueryResult<VisibleWornItem[], Error>;

function mockUseVisibleWornItems(partial: Partial<VisibleWornQueryResult>) {
  vi.mocked(visibleWornHooks.useVisibleWornItems).mockReturnValue({
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
  } as unknown as VisibleWornQueryResult);
}

function makeWornItem(overrides: Partial<VisibleWornItem> = {}): VisibleWornItem {
  return {
    id: 11,
    display_name: 'Linen Tunic',
    body_region: 'torso',
    equipment_layer: 'base',
    ...overrides,
  };
}

const character = { id: 42, name: 'Sera' };

describe('CharacterFocusView', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders the character name in the header', () => {
    mockUseVisibleWornItems({ data: [], isSuccess: true });
    renderWithProviders(
      <CharacterFocusView character={character} observerId={1} onItemClick={vi.fn()} />
    );
    expect(screen.getByRole('heading', { name: 'Sera' })).toBeInTheDocument();
  });

  it('renders skeletons while the worn list is loading', () => {
    mockUseVisibleWornItems({ isLoading: true, isPending: true, status: 'pending' });
    renderWithProviders(
      <CharacterFocusView character={character} observerId={1} onItemClick={vi.fn()} />
    );
    expect(screen.getByTestId('visible-worn-loading')).toBeInTheDocument();
  });

  it('shows the empty-state copy when nothing visible is worn', () => {
    mockUseVisibleWornItems({ data: [], isSuccess: true });
    renderWithProviders(
      <CharacterFocusView character={character} observerId={1} onItemClick={vi.fn()} />
    );
    const emptyMsg = screen.getByText(/nothing visible\./i);
    expect(emptyMsg).toBeInTheDocument();
    expect(emptyMsg).toHaveClass('italic');
    expect(emptyMsg).toHaveClass('text-muted-foreground');
  });

  it('renders one row per visible worn item with the slot label', () => {
    mockUseVisibleWornItems({
      data: [
        makeWornItem({
          id: 1,
          display_name: 'Linen Tunic',
          body_region: 'torso',
          equipment_layer: 'base',
        }),
        makeWornItem({
          id: 2,
          display_name: 'Leather Belt',
          body_region: 'waist',
          equipment_layer: 'over',
        }),
      ],
      isSuccess: true,
    });
    renderWithProviders(
      <CharacterFocusView character={character} observerId={1} onItemClick={vi.fn()} />
    );
    expect(screen.getByText('Linen Tunic')).toBeInTheDocument();
    expect(screen.getByText('Leather Belt')).toBeInTheDocument();
    expect(screen.getByText('Torso (Base)')).toBeInTheDocument();
    expect(screen.getByText('Waist (Over)')).toBeInTheDocument();
  });

  it('fires onItemClick with id and name when a worn-item row is clicked', () => {
    const onItemClick = vi.fn();
    mockUseVisibleWornItems({
      data: [makeWornItem({ id: 7, display_name: 'Silver Brooch' })],
      isSuccess: true,
    });
    renderWithProviders(
      <CharacterFocusView character={character} observerId={1} onItemClick={onItemClick} />
    );
    fireEvent.click(screen.getByRole('button', { name: /silver brooch/i }));
    expect(onItemClick).toHaveBeenCalledWith({ id: 7, name: 'Silver Brooch' });
  });

  it('passes undefined to useVisibleWornItems when observerId is null', () => {
    // Disables the underlying fetch — without an observer the backend
    // would 404 / empty for non-staff. Render still completes.
    mockUseVisibleWornItems({ data: [], isSuccess: true });
    renderWithProviders(
      <CharacterFocusView character={character} observerId={null} onItemClick={vi.fn()} />
    );
    expect(visibleWornHooks.useVisibleWornItems).toHaveBeenCalledWith(character.id, undefined);
  });

  it('renders a hidden status placeholder for the future combat slot', () => {
    mockUseVisibleWornItems({ data: [], isSuccess: true });
    const { container } = renderWithProviders(
      <CharacterFocusView character={character} observerId={1} onItemClick={vi.fn()} />
    );
    const placeholder = container.querySelector('[data-placeholder="status"]');
    expect(placeholder).not.toBeNull();
    expect(placeholder).toHaveClass('hidden');
    expect(placeholder?.getAttribute('aria-hidden')).toBe('true');
  });

  describe('humanizeRegionLayer', () => {
    it('formats known regions and layers with display labels', () => {
      expect(humanizeRegionLayer('torso', 'base')).toBe('Torso (Base)');
      expect(humanizeRegionLayer('left_finger', 'accessory')).toBe('Left Finger (Accessory)');
      expect(humanizeRegionLayer('feet', 'over')).toBe('Feet (Over)');
    });
  });
});
