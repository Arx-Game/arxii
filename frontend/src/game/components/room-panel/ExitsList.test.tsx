import { fireEvent, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { renderWithProviders } from '@/test/utils/renderWithProviders';
import { ExitsList } from './ExitsList';

const exit = { dbref: '#314', name: 'North gate', thumbnail_url: null };

describe('ExitsList', () => {
  it('keeps the original left-click travel callback on the target-menu trigger', () => {
    const onExit = vi.fn();
    renderWithProviders(
      <ExitsList exits={[exit]} onExit={onExit} partition="account-6" actorId={42} />
    );

    fireEvent.click(screen.getByRole('button', { name: 'North gate' }));
    expect(onExit).toHaveBeenCalledWith(exit);
  });

  it('keeps the existing empty-exits message', () => {
    renderWithProviders(
      <ExitsList exits={[]} onExit={vi.fn()} partition="account-6" actorId={42} />
    );
    expect(screen.getByText('No obvious exits.')).toBeInTheDocument();
  });
});
