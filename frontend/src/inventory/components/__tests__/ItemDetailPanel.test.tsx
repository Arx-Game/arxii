/**
 * ItemDetailPanel component tests.
 */

import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { ItemDetailPanel } from '../ItemDetailPanel';
import type { ItemInstance } from '../../types';

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

describe('ItemDetailPanel', () => {
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
});
