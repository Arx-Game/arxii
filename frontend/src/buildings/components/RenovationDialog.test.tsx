import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi } from 'vitest';

import { renderWithProviders } from '@/test/utils/renderWithProviders';
import type { BuildingKind } from '../types';
import { RenovationDialog } from './RenovationDialog';

vi.mock('../queries', () => ({
  useBuildingKindsQuery: vi.fn(),
}));

const { useBuildingKindsQuery } = await import('../queries');

const kinds: BuildingKind[] = [
  {
    id: 1,
    name: 'House',
    description: 'A residential dwelling.',
    is_residential: true,
    is_commercial: false,
    is_fortified: false,
    is_occult: false,
    is_maritime: false,
    is_agrarian: false,
    is_aerial: false,
    is_subterranean: false,
    is_secret: false,
  },
  {
    id: 2,
    name: 'Fortress',
    description: 'A fortified hold.',
    is_residential: false,
    is_commercial: false,
    is_fortified: true,
    is_occult: false,
    is_maritime: false,
    is_agrarian: false,
    is_aerial: false,
    is_subterranean: true,
    is_secret: false,
  },
];

function renderDialog(overrides: Partial<Parameters<typeof RenovationDialog>[0]> = {}) {
  const runAction = vi.fn();
  const onOpenChange = vi.fn();
  vi.mocked(useBuildingKindsQuery).mockReturnValue({
    data: { results: kinds, count: kinds.length },
    isLoading: false,
  } as never);
  renderWithProviders(
    <RenovationDialog
      anchorRoomId={7}
      currentKind="House"
      renovationCost={15000}
      open
      onOpenChange={onOpenChange}
      runAction={runAction}
      {...overrides}
    />
  );
  return { runAction, onOpenChange };
}

describe('RenovationDialog', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders the cost from the manager payload', () => {
    renderDialog();
    expect(screen.getByText(/Cost:.*15000.*coppers/)).toBeInTheDocument();
  });

  it('excludes the current kind from the list', () => {
    renderDialog();
    // The dialog's Renovate button for "House" should NOT be present (current kind).
    // Only "Fortress" remains.
    expect(screen.getByText('Fortress')).toBeInTheDocument();
    expect(screen.queryByText('House')).not.toBeInTheDocument();
  });

  it('dispatches start_building_renovation with the anchor room_id and target_kind', async () => {
    const { runAction, onOpenChange } = renderDialog();

    await userEvent.click(screen.getByText('Renovate'));

    expect(runAction).toHaveBeenCalledWith('start_building_renovation', {
      room_id: 7,
      target_kind: 'Fortress',
    });
    expect(onOpenChange).toHaveBeenCalledWith(false);
  });
});
