import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { ColorPicker } from '../ColorPicker';

describe('ColorPicker', () => {
  it('renders a color button trigger', () => {
    render(<ColorPicker onSelectColor={vi.fn()} />);
    expect(screen.getByTitle('Text Color')).toBeInTheDocument();
  });

  it('shows color swatches organized by category when opened', async () => {
    render(<ColorPicker onSelectColor={vi.fn()} />);

    await userEvent.click(screen.getByTitle('Text Color'));

    expect(screen.getByText('Reds')).toBeInTheDocument();
    expect(screen.getByText('Oranges')).toBeInTheDocument();
    expect(screen.getByText('Yellows')).toBeInTheDocument();
    expect(screen.getByText('Greens')).toBeInTheDocument();
    expect(screen.getByText('Blues')).toBeInTheDocument();
    expect(screen.getByText('Purples')).toBeInTheDocument();
    expect(screen.getByText('Cyans')).toBeInTheDocument();
    expect(screen.getByText('Neutrals')).toBeInTheDocument();
  });

  it('renders swatches with correct color titles', async () => {
    render(<ColorPicker onSelectColor={vi.fn()} />);

    await userEvent.click(screen.getByTitle('Text Color'));

    // Check some specific swatches exist
    expect(screen.getByTitle('Color 1')).toBeInTheDocument();
    expect(screen.getByTitle('Color 196')).toBeInTheDocument();
    expect(screen.getByTitle('Color 0')).toBeInTheDocument();
  });

  it('calls onSelectColor with correct index when swatch clicked', async () => {
    const onSelectColor = vi.fn();
    render(<ColorPicker onSelectColor={onSelectColor} />);

    await userEvent.click(screen.getByTitle('Text Color'));
    await userEvent.click(screen.getByTitle('Color 196'));

    expect(onSelectColor).toHaveBeenCalledWith(196);
  });

  it('calls onSelectColor with correct index for neutral colors', async () => {
    const onSelectColor = vi.fn();
    render(<ColorPicker onSelectColor={onSelectColor} />);

    await userEvent.click(screen.getByTitle('Text Color'));
    await userEvent.click(screen.getByTitle('Color 255'));

    expect(onSelectColor).toHaveBeenCalledWith(255);
  });
});
