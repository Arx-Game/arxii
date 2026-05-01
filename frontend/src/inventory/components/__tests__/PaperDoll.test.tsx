/**
 * PaperDoll component tests.
 */

import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { PaperDoll } from '../PaperDoll';
import type { EquippedItemDisplay } from '../PaperDoll';

const baseItem: EquippedItemDisplay = {
  id: 1,
  body_region: 'torso',
  equipment_layer: 'base',
  display_name: 'Linen Tunic',
  display_image_url: null,
  quality_color_hex: '#4ade80',
};

describe('PaperDoll', () => {
  it('renders without crashing on empty equipment', () => {
    render(<PaperDoll equipped={[]} />);
    // Silhouette SVG is present
    expect(screen.getByRole('img', { name: /paper doll/i })).toBeInTheDocument();
  });

  it('renders empty slot indicators (no item) for every body region', () => {
    const { container } = render(<PaperDoll equipped={[]} />);
    // Slots are rect elements with data-slot attribute
    const slots = container.querySelectorAll('[data-slot]');
    expect(slots.length).toBeGreaterThan(0);
    // All slots should be marked empty
    slots.forEach((slot) => {
      expect(slot.getAttribute('data-occupied')).toBe('false');
    });
  });

  it('marks a slot as occupied when an equipped item is present', () => {
    const { container } = render(<PaperDoll equipped={[baseItem]} />);
    const torsoSlot = container.querySelector('[data-slot="torso"]');
    expect(torsoSlot).not.toBeNull();
    expect(torsoSlot?.getAttribute('data-occupied')).toBe('true');
  });

  it('fires onSlotClick when an empty slot is clicked', () => {
    const onSlotClick = vi.fn();
    const onItemClick = vi.fn();
    const { container } = render(
      <PaperDoll equipped={[]} onSlotClick={onSlotClick} onItemClick={onItemClick} />
    );
    const torsoSlot = container.querySelector('[data-slot="torso"]');
    expect(torsoSlot).not.toBeNull();
    fireEvent.click(torsoSlot as Element);
    expect(onSlotClick).toHaveBeenCalledWith('torso');
    expect(onItemClick).not.toHaveBeenCalled();
  });

  it('fires onItemClick when an occupied slot is clicked', () => {
    const onSlotClick = vi.fn();
    const onItemClick = vi.fn();
    const { container } = render(
      <PaperDoll equipped={[baseItem]} onSlotClick={onSlotClick} onItemClick={onItemClick} />
    );
    const torsoSlot = container.querySelector('[data-slot="torso"]');
    fireEvent.click(torsoSlot as Element);
    expect(onItemClick).toHaveBeenCalledWith(baseItem.id);
    expect(onSlotClick).not.toHaveBeenCalled();
  });

  it('falls back to first letter when no display image is provided', () => {
    const { container } = render(<PaperDoll equipped={[baseItem]} />);
    const initialEl = container.querySelector('[data-fallback-initial]');
    expect(initialEl?.textContent).toBe('L');
  });

  it('uses quality color as the slot border accent on occupied slots', () => {
    const { container } = render(<PaperDoll equipped={[baseItem]} />);
    const torsoSlot = container.querySelector('[data-slot="torso"]') as HTMLElement | null;
    expect(torsoSlot?.getAttribute('stroke')).toBe('#4ade80');
  });
});
