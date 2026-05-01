/**
 * ItemCard component tests.
 */

import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { ItemCard } from '../ItemCard';
import type { ItemInstance } from '../../types';

function makeItem(overrides: Partial<ItemInstance> = {}): ItemInstance {
  return {
    id: 1,
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
    ...overrides,
  };
}

describe('ItemCard', () => {
  it('renders without crashing on minimal valid props', () => {
    render(<ItemCard item={makeItem()} />);
    expect(screen.getByText('Linen Tunic')).toBeInTheDocument();
  });

  it('renders the quality tier badge with the tier name', () => {
    render(<ItemCard item={makeItem()} />);
    expect(screen.getByText('Fine')).toBeInTheDocument();
  });

  it('applies the quality tier color as the left border accent', () => {
    const { container } = render(<ItemCard item={makeItem()} />);
    const card = container.firstChild as HTMLElement;
    expect(card.style.borderLeftColor).toBeTruthy();
    // jsdom normalizes hex to lowercase with full form
    expect(card.style.borderLeftColor.toLowerCase()).toContain('74, 222, 128');
  });

  it('falls back to the first letter when no display image is present', () => {
    render(<ItemCard item={makeItem({ display_image_url: null })} />);
    // Initial fallback is rendered as a div with the letter L
    expect(screen.getByText('L')).toBeInTheDocument();
  });

  it('renders the image when display_image_url is set', () => {
    render(<ItemCard item={makeItem({ display_image_url: 'https://example.com/tunic.png' })} />);
    const img = screen.getByRole('img', { name: /linen tunic/i });
    expect(img).toHaveAttribute('src', 'https://example.com/tunic.png');
  });

  it('fires onClick when the card is clicked', () => {
    const onClick = vi.fn();
    render(<ItemCard item={makeItem()} onClick={onClick} />);
    fireEvent.click(screen.getByText('Linen Tunic'));
    expect(onClick).toHaveBeenCalledWith(1);
  });

  it('renders up to 3 facet chips when facets are passed', () => {
    render(
      <ItemCard item={makeItem()} facetLabels={['Sharpened', 'Lacquered', 'Engraved', 'Scented']} />
    );
    expect(screen.getByText('Sharpened')).toBeInTheDocument();
    expect(screen.getByText('Lacquered')).toBeInTheDocument();
    expect(screen.getByText('Engraved')).toBeInTheDocument();
    // 4th facet collapses into a +N indicator
    expect(screen.queryByText('Scented')).not.toBeInTheDocument();
    expect(screen.getByText('+1')).toBeInTheDocument();
  });

  it('renders gracefully when no quality tier color is available', () => {
    // Defensive: tinted background uses tier.color_hex; should not crash with empty
    const base = makeItem();
    const item: ItemInstance = {
      ...base,
      quality_tier: { ...base.quality_tier, color_hex: '' },
    };
    render(<ItemCard item={item} />);
    expect(screen.getByText('Linen Tunic')).toBeInTheDocument();
  });
});
