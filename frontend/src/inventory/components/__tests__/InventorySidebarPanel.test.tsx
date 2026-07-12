/**
 * InventorySidebarPanel tests (#1446).
 *
 * Read-only carried-items list on the game rail's Inventory tab: renders
 * both carried item names, marks the equipped one, and links out to
 * /wardrobe for management.
 */

import { screen } from '@testing-library/react';
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { renderWithProviders } from '@/test/utils/renderWithProviders';
import { InventorySidebarPanel } from '../InventorySidebarPanel';
import type { ItemInstance, EquippedItem } from '../../types';

vi.mock('../../hooks/useInventory', () => ({
  useInventory: vi.fn(),
  useEquippedItems: vi.fn(),
  inventoryKeys: {
    inventory: (characterId: number) => ['inventory', characterId] as const,
    equipped: (characterId: number) => ['equipped', characterId] as const,
  },
}));

import { useInventory, useEquippedItems } from '../../hooks/useInventory';

const mockInventory = vi.mocked(useInventory);
const mockEquipped = vi.mocked(useEquippedItems);

function makeItem(overrides: Partial<ItemInstance> = {}): ItemInstance {
  return {
    id: 1,
    game_object_id: 101,
    access_policy: 'open',
    is_currency_instrument: false,
    suggested_value: 0,
    can_steal: false,
    template: {
      id: 10,
      name: 'Linen Tunic',
      weight: '1.20',
      size: 2,
      value: 25,
      is_container: false,
      is_stackable: false,
      is_consumable: false,
      is_craftable: true,
      image_url: '',
    },
    quality_tier: {
      id: 3,
      name: 'Fine',
      color_hex: '#4ade80',
      numeric_min: 50,
      numeric_max: 75,
      stat_multiplier: '1.10',
      sort_order: 3,
    },
    display_name: 'Linen Tunic',
    display_description: 'A simple linen tunic, well-tailored.',
    display_image_url: null,
    contained_in: 1,
    quantity: 1,
    charges: 0,
    is_open: false,
    is_usable: false,
    ...overrides,
  };
}

function setQueries({
  inventory,
  equipped = [],
}: {
  inventory: ItemInstance[];
  equipped?: EquippedItem[];
}) {
  mockInventory.mockReturnValue({
    data: inventory,
    isLoading: false,
  } as unknown as ReturnType<typeof useInventory>);
  mockEquipped.mockReturnValue({
    data: equipped,
    isLoading: false,
  } as unknown as ReturnType<typeof useEquippedItems>);
}

describe('InventorySidebarPanel', () => {
  beforeEach(() => {
    mockInventory.mockReset();
    mockEquipped.mockReset();
  });

  it('renders both carried item names, marks the equipped one, and links to /wardrobe', () => {
    const tunic = makeItem({ id: 1, display_name: 'Linen Tunic' });
    const dagger = makeItem({ id: 2, display_name: 'Rusty Dagger' });
    setQueries({
      inventory: [tunic, dagger],
      equipped: [
        {
          id: 1,
          item_instance: 1,
          body_region: 'torso',
          equipment_layer: 'outer',
        } as EquippedItem,
      ],
    });

    renderWithProviders(<InventorySidebarPanel characterId={7} />);

    expect(screen.getByText('Linen Tunic')).toBeInTheDocument();
    expect(screen.getByText('Rusty Dagger')).toBeInTheDocument();
    expect(screen.getByTestId('worn-badge-1')).toBeInTheDocument();
    expect(screen.queryByTestId('worn-badge-2')).not.toBeInTheDocument();

    const link = screen.getByRole('link', { name: /wardrobe/i });
    expect(link).toHaveAttribute('href', '/wardrobe');
  });

  it('shows a muted empty state when nothing is carried', () => {
    setQueries({ inventory: [] });
    renderWithProviders(<InventorySidebarPanel characterId={7} />);
    expect(screen.getByText(/aren.t carrying anything/i)).toBeInTheDocument();
  });
});
