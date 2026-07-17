import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi } from 'vitest';

import { renderWithProviders } from '@/test/utils/renderWithProviders';
import type { WorldBuilderArea } from '../types';
import { PromoteAreaButton } from './PromoteAreaButton';

const area: WorldBuilderArea = {
  id: 4,
  name: 'Ward of the Lyceum',
  slug: null,
  level: 30,
  level_display: 'Ward',
  origin: 'story',
  parent: 1,
  children_count: 0,
  grid_x: null,
  grid_y: null,
};

function renderButton(overrides: Partial<WorldBuilderArea> = {}) {
  const runAction = vi.fn();
  renderWithProviders(<PromoteAreaButton area={{ ...area, ...overrides }} runAction={runAction} />);
  return { runAction };
}

describe('PromoteAreaButton', () => {
  it('dispatches promote_area with just the area_id after confirming', async () => {
    const { runAction } = renderButton();

    await userEvent.click(screen.getByText('Promote area'));
    await userEvent.click(await screen.findByRole('button', { name: 'Promote' }));

    expect(runAction).toHaveBeenCalledWith('promote_area', { area_id: 4 });
  });

  it('shows the origin badge', () => {
    renderButton();
    expect(screen.getByText('story')).toBeInTheDocument();
  });

  it('hides the promote affordance for an already-authored area', () => {
    renderButton({ origin: 'authored' });
    expect(screen.queryByText('Promote area')).not.toBeInTheDocument();
  });
});
