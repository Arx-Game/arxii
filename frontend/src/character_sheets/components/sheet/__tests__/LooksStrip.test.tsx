/** The plate's looks strip (#3898, #4151): moods label the looks, repeats are numbered. */
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import type { CharacterSheetLook } from '@/character_sheets/api';
import { LooksStrip } from '../LooksStrip';

function look(id: number, mood: string, current = false): CharacterSheetLook {
  return {
    tenure_media_id: id,
    url: `https://x/${id}.jpg`,
    title: '',
    look: mood,
    is_current: current,
  };
}

describe('LooksStrip', () => {
  it('numbers a mood that more than one look shows', () => {
    render(
      <LooksStrip
        looks={[look(1, 'Furious', true), look(2, 'Amused'), look(3, 'Furious')]}
        shownId={1}
        onShow={() => {}}
        canWear={false}
        isSaving={false}
      />
    );
    expect(screen.getByText('Furious')).toBeInTheDocument();
    expect(screen.getByText('Furious 2')).toBeInTheDocument();
    expect(screen.getByText('Amused')).toBeInTheDocument();
  });

  it('gives the owner an Add tile, even before there are any looks', () => {
    const onAdd = vi.fn();
    render(
      <LooksStrip
        looks={[]}
        shownId={null}
        onShow={() => {}}
        canWear
        onAdd={onAdd}
        isSaving={false}
      />
    );
    fireEvent.click(screen.getByRole('button', { name: 'Add a look' }));
    expect(onAdd).toHaveBeenCalled();
  });

  it('shows a visitor nothing when there are no looks', () => {
    const { container } = render(
      <LooksStrip looks={[]} shownId={null} onShow={() => {}} canWear={false} isSaving={false} />
    );
    expect(container).toBeEmptyDOMElement();
  });
});
