/**
 * OutfitCard component tests.
 */

import { fireEvent, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { OutfitCard } from '../OutfitCard';
import type { ItemInstance, Outfit, OutfitSlot } from '../../types';

function makeItem(id: number, name: string, color = '#4ade80'): ItemInstance {
  return {
    id,
    template: {
      id: id + 100,
      name,
      weight: '1.00',
      size: 1,
      value: 0,
      is_container: false,
      is_stackable: false,
      is_consumable: false,
      is_craftable: true,
      image_url: '',
    },
    quality_tier: {
      id: 1,
      name: 'Fine',
      color_hex: color,
      numeric_min: 0,
      numeric_max: 100,
      stat_multiplier: '1.00',
      sort_order: 1,
    },
    display_name: name,
    display_description: 'A simple piece.',
    display_image_url: null,
    contained_in: 1,
    quantity: 1,
    charges: 0,
    is_open: false,
  };
}

function makeSlot(id: number, item: ItemInstance): OutfitSlot {
  return {
    id,
    outfit: 1,
    item_instance: item,
    body_region: 'torso',
    equipment_layer: 'base',
  };
}

function makeOutfit(slots: OutfitSlot[] = []): Outfit {
  return {
    id: 1,
    name: 'Court Attire',
    description: '',
    character_sheet: 1,
    wardrobe: 99,
    slots,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
  };
}

describe('OutfitCard', () => {
  it('renders the outfit name', () => {
    render(<OutfitCard outfit={makeOutfit()} />);
    expect(screen.getByText('Court Attire')).toBeInTheDocument();
  });

  it('renders item thumbnails (max 5 visible) with +N overflow chip', () => {
    const slots = [1, 2, 3, 4, 5, 6, 7, 8].map((i) => makeSlot(i, makeItem(i, `Item ${i}`)));
    const { container } = render(<OutfitCard outfit={makeOutfit(slots)} />);
    const thumbs = container.querySelectorAll('[data-outfit-thumb]');
    expect(thumbs.length).toBe(5);
    expect(screen.getByText('+3')).toBeInTheDocument();
  });

  it('shows an empty hint if the outfit has no slots', () => {
    render(<OutfitCard outfit={makeOutfit([])} />);
    expect(screen.getByText(/no items/i)).toBeInTheDocument();
  });

  it('fires onWear when the Wear button is clicked', () => {
    const onWear = vi.fn();
    render(<OutfitCard outfit={makeOutfit()} onWear={onWear} />);
    fireEvent.click(screen.getByRole('button', { name: /^wear$/i }));
    expect(onWear).toHaveBeenCalledWith(1);
  });

  it('fires onEdit when the Edit button is clicked', () => {
    const onEdit = vi.fn();
    render(<OutfitCard outfit={makeOutfit()} onEdit={onEdit} />);
    fireEvent.click(screen.getByRole('button', { name: /^edit$/i }));
    expect(onEdit).toHaveBeenCalledWith(1);
  });

  it('opens the kebab menu and fires onDelete', async () => {
    const onDelete = vi.fn();
    const user = userEvent.setup();
    render(<OutfitCard outfit={makeOutfit()} onDelete={onDelete} />);
    await user.click(screen.getByRole('button', { name: /more options/i }));
    await user.click(await screen.findByRole('menuitem', { name: /delete/i }));
    expect(onDelete).toHaveBeenCalledWith(1);
  });

  it('renders without crashing when no callbacks are provided', () => {
    const slots = [makeSlot(1, makeItem(1, 'Tunic'))];
    render(<OutfitCard outfit={makeOutfit(slots)} />);
    expect(screen.getByText('Court Attire')).toBeInTheDocument();
  });
});
