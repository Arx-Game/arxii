import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi } from 'vitest';

import { renderWithProviders } from '@/test/utils/renderWithProviders';
import { insertableLevels } from '../constants';
import { InsertLevelDialog } from '../InsertLevelDialog';

vi.mock('@/components/ui/select', () => ({
  Select: ({
    value,
    onValueChange,
    children,
  }: {
    value?: string;
    onValueChange?: (v: string) => void;
    children?: React.ReactNode;
  }) => (
    <select
      value={value}
      onChange={(event) => onValueChange?.(event.target.value)}
      aria-label="level picker"
    >
      <option value="" disabled></option>
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

const city = { id: 2, name: 'Arx City', level: 40, level_display: 'City' };
const cityCenter = { id: 100, name: 'The City Center', kind: 'room' as const };
const world = { id: 1, name: 'Nitera', level: 80, level_display: 'World' };
const ward = { id: 3, name: 'Central Ward', level: 30, level_display: 'Ward' };

describe('insertableLevels', () => {
  it('a room under a city: ward, neighborhood, building, highest first', () => {
    expect(insertableLevels(city, cityCenter).map((choice) => choice.value)).toEqual([30, 20, 10]);
  });

  it('a ward under a world: continent, kingdom, region, city', () => {
    expect(insertableLevels(world, ward).map((choice) => choice.value)).toEqual([70, 60, 50, 40]);
  });

  it('a ward under a city: nothing fits', () => {
    expect(insertableLevels(city, ward)).toEqual([]);
  });
});

describe('InsertLevelDialog', () => {
  it('defaults to the highest fitting level, names the pair, and confirms {name, level}', async () => {
    const onConfirm = vi.fn();
    const onClose = vi.fn();
    renderWithProviders(
      <InsertLevelDialog
        between={{ upper: city, lower: cityCenter }}
        onClose={onClose}
        onConfirm={onConfirm}
      />
    );

    expect(screen.getByText('Insert between Arx City and The City Center')).toBeInTheDocument();
    expect(screen.getByRole('combobox', { name: 'level picker' })).toHaveValue('30');
    expect(screen.getByLabelText('Ward name')).toBeInTheDocument();
    expect(screen.getByTestId('insert-level-note')).toHaveTextContent(
      "The City Center moves inside the new ward, which takes its place on Arx City's map"
    );
    expect(screen.getByTestId('insert-level-submit')).toBeDisabled();

    await userEvent.type(screen.getByTestId('insert-level-name'), 'Central Ward');
    await userEvent.click(screen.getByTestId('insert-level-submit'));

    expect(onConfirm).toHaveBeenCalledWith({ name: 'Central Ward', level: 30 });
    expect(onClose).toHaveBeenCalled();
  });

  it('a lower level can be picked instead', async () => {
    const onConfirm = vi.fn();
    renderWithProviders(
      <InsertLevelDialog
        between={{ upper: city, lower: cityCenter }}
        onClose={vi.fn()}
        onConfirm={onConfirm}
      />
    );

    await userEvent.selectOptions(screen.getByRole('combobox', { name: 'level picker' }), '20');
    expect(screen.getByLabelText('Neighborhood name')).toBeInTheDocument();
    await userEvent.type(screen.getByTestId('insert-level-name'), 'Central Neighborhood');
    await userEvent.click(screen.getByTestId('insert-level-submit'));

    expect(onConfirm).toHaveBeenCalledWith({ name: 'Central Neighborhood', level: 20 });
  });

  it('stays closed with no pair', () => {
    renderWithProviders(<InsertLevelDialog between={null} onClose={vi.fn()} onConfirm={vi.fn()} />);
    expect(screen.queryByTestId('insert-level-dialog')).not.toBeInTheDocument();
  });
});
