import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { NameAutocomplete } from './NameAutocomplete';

const characters = [
  { name: 'Alice', thumbnail_url: '/alice.png' },
  { name: 'Bob', thumbnail_url: null },
  { name: 'Bort', thumbnail_url: '/bort.png' },
];

describe('NameAutocomplete', () => {
  it('shows filtered characters matching query', () => {
    render(
      <NameAutocomplete
        characters={characters}
        query="Bo"
        visible={true}
        onSelect={vi.fn()}
        onDismiss={vi.fn()}
        selectedIndex={0}
      />
    );

    expect(screen.getByText('Bob')).toBeInTheDocument();
    expect(screen.getByText('Bort')).toBeInTheDocument();
    expect(screen.queryByText('Alice')).not.toBeInTheDocument();
  });

  it('clicking selects and calls onSelect', async () => {
    const onSelect = vi.fn();
    render(
      <NameAutocomplete
        characters={characters}
        query="Bo"
        visible={true}
        onSelect={onSelect}
        onDismiss={vi.fn()}
        selectedIndex={0}
      />
    );

    // Use fireEvent.mouseDown because the handler is onMouseDown
    const bobOption = screen.getByText('Bob');
    bobOption.closest('button')!.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }));

    expect(onSelect).toHaveBeenCalledWith('Bob');
  });

  it('empty query shows all characters', () => {
    render(
      <NameAutocomplete
        characters={characters}
        query=""
        visible={true}
        onSelect={vi.fn()}
        onDismiss={vi.fn()}
        selectedIndex={0}
      />
    );

    expect(screen.getByText('Alice')).toBeInTheDocument();
    expect(screen.getByText('Bob')).toBeInTheDocument();
    expect(screen.getByText('Bort')).toBeInTheDocument();
  });

  it('no match shows nothing', () => {
    const { container } = render(
      <NameAutocomplete
        characters={characters}
        query="Zz"
        visible={true}
        onSelect={vi.fn()}
        onDismiss={vi.fn()}
        selectedIndex={0}
      />
    );

    expect(container.querySelector('[role="listbox"]')).not.toBeInTheDocument();
  });

  it('renders nothing when not visible', () => {
    const { container } = render(
      <NameAutocomplete
        characters={characters}
        query=""
        visible={false}
        onSelect={vi.fn()}
        onDismiss={vi.fn()}
        selectedIndex={0}
      />
    );

    expect(container.querySelector('[role="listbox"]')).not.toBeInTheDocument();
  });

  it('highlights the selected index', () => {
    render(
      <NameAutocomplete
        characters={characters}
        query=""
        visible={true}
        onSelect={vi.fn()}
        onDismiss={vi.fn()}
        selectedIndex={1}
      />
    );

    const options = screen.getAllByRole('option');
    expect(options[1]).toHaveAttribute('aria-selected', 'true');
    expect(options[0]).toHaveAttribute('aria-selected', 'false');
  });
});
