import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { ModeToggle } from '../ModeToggle';

const mockSetTheme = vi.fn();
let mockTheme: string | undefined = 'light';
vi.mock('next-themes', () => ({
  useTheme: () => ({ theme: mockTheme, setTheme: mockSetTheme }),
}));

describe('ModeToggle', () => {
  it('renders the sun for light and cycles to dark', async () => {
    mockTheme = 'light';
    render(<ModeToggle />);
    expect(screen.getByRole('button', { name: /Theme: light\. Switch to dark\./ })).toBeVisible();
    await userEvent.click(screen.getByRole('button'));
    expect(mockSetTheme).toHaveBeenCalledWith('dark');
  });

  it('an unrecognized stored theme renders as system, never an empty button', () => {
    // next-themes hands back whatever localStorage holds, unvalidated — a
    // stale value from an older deploy used to leave the button ICONLESS but
    // clickable, with the first click "switching to" light (indexOf -1).
    mockTheme = 'parchment';
    render(<ModeToggle />);
    const button = screen.getByRole('button', { name: /Theme: system\. Switch to light\./ });
    expect(button.querySelector('svg')).not.toBeNull();
  });

  it('an undefined theme (first paint) also renders as system', () => {
    mockTheme = undefined;
    render(<ModeToggle />);
    expect(
      screen.getByRole('button', { name: /Theme: system\./ }).querySelector('svg')
    ).not.toBeNull();
  });
});
