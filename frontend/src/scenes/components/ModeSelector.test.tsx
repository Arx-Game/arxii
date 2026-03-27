import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { ModeSelector } from './ModeSelector';

describe('ModeSelector', () => {
  it('renders current mode as button text', () => {
    render(<ModeSelector currentMode="pose" onModeChange={vi.fn()} isAtPlace={false} />);
    expect(screen.getByRole('button', { name: /pose/i })).toBeInTheDocument();
  });

  it('opens dropdown on click', async () => {
    const user = userEvent.setup();
    render(<ModeSelector currentMode="pose" onModeChange={vi.fn()} isAtPlace={false} />);

    await user.click(screen.getByRole('button', { name: /pose/i }));

    expect(screen.getByRole('menuitem', { name: /say/i })).toBeInTheDocument();
  });

  it('shows 4 communication modes when not at a place (tabletalk hidden)', async () => {
    const user = userEvent.setup();
    render(<ModeSelector currentMode="pose" onModeChange={vi.fn()} isAtPlace={false} />);

    await user.click(screen.getByRole('button', { name: /pose/i }));

    const items = screen.getAllByRole('menuitem');
    expect(items).toHaveLength(4);
    expect(screen.queryByRole('menuitem', { name: /tabletalk/i })).not.toBeInTheDocument();
  });

  it('shows all 5 communication modes when at a place', async () => {
    const user = userEvent.setup();
    render(<ModeSelector currentMode="pose" onModeChange={vi.fn()} isAtPlace={true} />);

    await user.click(screen.getByRole('button', { name: /pose/i }));

    const items = screen.getAllByRole('menuitem');
    expect(items).toHaveLength(5);
    expect(screen.getByRole('menuitem', { name: /tabletalk/i })).toBeInTheDocument();
  });

  it('selecting calls onModeChange with the mode key', async () => {
    const onModeChange = vi.fn();
    const user = userEvent.setup();
    render(<ModeSelector currentMode="pose" onModeChange={onModeChange} isAtPlace={false} />);

    await user.click(screen.getByRole('button', { name: /pose/i }));
    await user.click(screen.getByRole('menuitem', { name: /say/i }));

    expect(onModeChange).toHaveBeenCalledWith('say');
  });

  it('displays correct label for non-default mode', () => {
    render(<ModeSelector currentMode="whisper" onModeChange={vi.fn()} isAtPlace={false} />);
    expect(screen.getByRole('button', { name: /whisper/i })).toBeInTheDocument();
  });
});
