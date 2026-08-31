import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi } from 'vitest';

import { renderWithProviders } from '@/test/utils/renderWithProviders';
import type { WorldBuilderRoomDescVariant } from '../../types';
import { VariantsPanel } from '../VariantsPanel';

vi.mock('@/components/ui/select', () => ({
  Select: ({
    value,
    onValueChange,
    disabled,
    children,
  }: {
    value?: string;
    onValueChange?: (v: string) => void;
    disabled?: boolean;
    children?: React.ReactNode;
  }) => (
    <select
      value={value}
      disabled={disabled}
      onChange={(event) => onValueChange?.(event.target.value)}
      aria-label="variant-select"
    >
      <option value=""></option>
      {children}
    </select>
  ),
  SelectTrigger: ({ children }: { children?: React.ReactNode }) => <>{children}</>,
  SelectValue: () => null,
  SelectContent: ({ children }: { children?: React.ReactNode }) => <>{children}</>,
  SelectItem: ({ value, children }: { value: string; children?: React.ReactNode }) => (
    <option value={value}>{children}</option>
  ),
}));

const WINTER: WorldBuilderRoomDescVariant = {
  id: 1,
  season: 'winter',
  phase: null,
  description: 'Frost creeps up the windows.',
};
const NIGHT: WorldBuilderRoomDescVariant = {
  id: 2,
  season: null,
  phase: 'night',
  description: 'Lanterns are lit against the dark.',
};

function renderPanel(overrides: Partial<Parameters<typeof VariantsPanel>[0]> = {}) {
  const runAction = vi.fn();
  renderWithProviders(
    <VariantsPanel roomId={100} variants={[WINTER, NIGHT]} runAction={runAction} {...overrides} />
  );
  return { runAction };
}

describe('VariantsPanel', () => {
  it('is collapsed by default, showing only the season/phase summary', () => {
    renderPanel();
    expect(screen.getByTestId('variants-summary')).toHaveTextContent('winter, night');
    expect(screen.queryByTestId('variant-row')).not.toBeInTheDocument();
  });

  it('shows "none yet" when there are no variants', () => {
    renderPanel({ variants: [] });
    expect(screen.getByTestId('variants-summary')).toHaveTextContent('none yet');
  });

  it('expanding lists each variant with edit/remove', async () => {
    renderPanel();
    await userEvent.click(screen.getByRole('button', { name: /variants:/ }));

    const rows = screen.getAllByTestId('variant-row');
    expect(rows).toHaveLength(2);
    expect(rows[0]).toHaveTextContent('Frost creeps up the windows.');
  });

  it('adding a new variant dispatches staff_set_room_desc_variant with season/phase/description', async () => {
    const { runAction } = renderPanel();
    await userEvent.click(screen.getByRole('button', { name: /variants:/ }));
    await userEvent.click(screen.getByTestId('variant-add-open'));

    const [seasonSelect, phaseSelect] = screen.getAllByLabelText('variant-select');
    await userEvent.selectOptions(seasonSelect, 'summer');
    await userEvent.selectOptions(phaseSelect, 'dawn');
    await userEvent.type(screen.getByTestId('variant-description'), 'Warm light through the door.');
    await userEvent.click(screen.getByTestId('variant-save'));

    expect(runAction).toHaveBeenCalledWith('staff_set_room_desc_variant', {
      room_id: 100,
      season: 'summer',
      phase: 'dawn',
      description: 'Warm light through the door.',
    });
  });

  it('editing an existing variant locks season/phase and re-saves under the same triple', async () => {
    const { runAction } = renderPanel();
    await userEvent.click(screen.getByRole('button', { name: /variants:/ }));
    await userEvent.click(screen.getAllByTestId('variant-edit')[0]);

    const [seasonSelect] = screen.getAllByLabelText('variant-select');
    expect(seasonSelect).toBeDisabled();
    expect(screen.getByTestId('variant-description')).toHaveValue('Frost creeps up the windows.');

    await userEvent.click(screen.getByTestId('variant-save'));
    expect(runAction).toHaveBeenCalledWith('staff_set_room_desc_variant', {
      room_id: 100,
      season: 'winter',
      phase: undefined,
      description: 'Frost creeps up the windows.',
    });
  });

  it('remove dispatches staff_remove_room_desc_variant with the variant id', async () => {
    const { runAction } = renderPanel();
    await userEvent.click(screen.getByRole('button', { name: /variants:/ }));
    await userEvent.click(screen.getAllByTestId('variant-remove')[0]);

    expect(runAction).toHaveBeenCalledWith('staff_remove_room_desc_variant', { variant_id: 1 });
  });

  it('disables Save until a description is entered', async () => {
    renderPanel({ variants: [] });
    await userEvent.click(screen.getByRole('button', { name: /variants:/ }));
    await userEvent.click(screen.getByTestId('variant-add-open'));

    expect(screen.getByTestId('variant-save')).toBeDisabled();
  });
});
