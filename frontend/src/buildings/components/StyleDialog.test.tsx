import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi } from 'vitest';

import { renderWithProviders } from '@/test/utils/renderWithProviders';
import type { ArchitecturalStyle } from '../types';
import { StyleDialog } from './StyleDialog';

vi.mock('../queries', () => ({
  useArchitecturalStylesQuery: vi.fn(),
}));

const { useArchitecturalStylesQuery } = await import('../queries');

const styles: ArchitecturalStyle[] = [
  {
    id: 1,
    name: 'Vernacular Timberframe',
    description: 'A common style.',
    is_default: true,
    prestige_bonus: 0,
    cost_multiplier: '1',
  },
  {
    id: 2,
    name: 'Antique Imperial',
    description: 'A throwback style.',
    is_default: false,
    prestige_bonus: 50,
    cost_multiplier: '1.500',
  },
];

function renderDialog(overrides: Partial<Parameters<typeof StyleDialog>[0]> = {}) {
  const runAction = vi.fn();
  const onOpenChange = vi.fn();
  vi.mocked(useArchitecturalStylesQuery).mockReturnValue({
    data: { results: styles, count: styles.length },
    isLoading: false,
  } as never);
  renderWithProviders(
    <StyleDialog
      anchorRoomId={7}
      characterId={42}
      currentStyle={null}
      open
      onOpenChange={onOpenChange}
      runAction={runAction}
      {...overrides}
    />
  );
  return { runAction, onOpenChange };
}

describe('StyleDialog', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('lists learned styles with flavor badges', () => {
    renderDialog();
    expect(screen.getByText('Vernacular Timberframe')).toBeInTheDocument();
    expect(screen.getByText('Antique Imperial')).toBeInTheDocument();
    expect(screen.getByText('Throwback')).toBeInTheDocument();
    expect(screen.getByText('+50 prestige')).toBeInTheDocument();
  });

  it('dispatches set_building_style with the anchor room_id and style name', async () => {
    const { runAction, onOpenChange } = renderDialog();

    // Click "Apply" on the throwback style (the second one).
    const applyButtons = screen.getAllByText('Apply');
    await userEvent.click(applyButtons[1]);

    expect(runAction).toHaveBeenCalledWith('set_building_style', {
      room_id: 7,
      style: 'Antique Imperial',
    });
    expect(onOpenChange).toHaveBeenCalledWith(false);
  });

  it('disables the Apply button for the current style', () => {
    renderDialog({ currentStyle: 'Vernacular Timberframe' });
    const applyButtons = screen.getAllByText('Apply');
    // The first style is the current one — its button should be disabled.
    expect(applyButtons[0]).toBeDisabled();
    // The second style is still applyable.
    expect(applyButtons[1]).toBeEnabled();
  });
});
