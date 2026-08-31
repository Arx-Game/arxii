import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi } from 'vitest';

import { renderWithProviders } from '@/test/utils/renderWithProviders';
import { AddDialog, type AddDialogProps } from '../AddDialog';

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
      aria-label="room picker"
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

function renderDialog(overrides: Partial<AddDialogProps> = {}) {
  const onConfirm = vi.fn();
  const onOpenChange = vi.fn();
  renderWithProviders(
    <AddDialog mode="rooms" open onOpenChange={onOpenChange} onConfirm={onConfirm} {...overrides} />
  );
  return { onConfirm, onOpenChange };
}

const NEIGHBOR = { roomId: 5, intoName: 'east', outName: 'west' };
const ROOM_OPTIONS = [
  { id: 5, name: 'The Gallery Stair' },
  { id: 6, name: 'The Kitchen' },
];

describe('AddDialog — areas mode', () => {
  it('hides the connection rows entirely and confirms {kind: "area"}', async () => {
    const { onConfirm } = renderDialog({ mode: 'areas' });

    expect(screen.queryByTestId('add-dialog-entrance-row')).not.toBeInTheDocument();
    expect(screen.queryByText(/Entrance from/)).not.toBeInTheDocument();

    await userEvent.type(screen.getByTestId('add-dialog-name'), 'Central Ward');
    await userEvent.click(screen.getByTestId('add-dialog-submit'));

    expect(onConfirm).toHaveBeenCalledWith({ kind: 'area', name: 'Central Ward' });
  });

  it('disables Add until a name is entered', () => {
    renderDialog({ mode: 'areas' });
    expect(screen.getByTestId('add-dialog-submit')).toBeDisabled();
  });
});

describe('AddDialog — rooms mode payload assembly', () => {
  it('auto-fills both rows from the adjacent neighbor and collapses to one link on confirm', async () => {
    const { onConfirm } = renderDialog({ defaultNeighbor: NEIGHBOR, roomOptions: ROOM_OPTIONS });

    expect(screen.getByTestId('add-dialog-entrance-name')).toHaveValue('east');
    expect(screen.getByTestId('add-dialog-exit-name')).toHaveValue('west');

    await userEvent.type(screen.getByTestId('add-dialog-name'), 'The Wine Cellar');
    await userEvent.click(screen.getByTestId('add-dialog-submit'));

    expect(onConfirm).toHaveBeenCalledWith({
      kind: 'room',
      name: 'The Wine Cellar',
      entrance: { roomId: 5, exitName: 'east' },
      exit: { roomId: 5, exitName: 'west' },
    });
  });

  it('removing the entrance row is a one-way exit — only the exit connection is sent', async () => {
    const { onConfirm } = renderDialog({ defaultNeighbor: NEIGHBOR, roomOptions: ROOM_OPTIONS });

    await userEvent.click(screen.getByTestId('add-dialog-entrance-remove'));
    expect(screen.getByTestId('add-dialog-entrance-removed')).toBeInTheDocument();

    await userEvent.type(screen.getByTestId('add-dialog-name'), 'The Wine Cellar');
    await userEvent.click(screen.getByTestId('add-dialog-submit'));

    expect(onConfirm).toHaveBeenCalledWith({
      kind: 'room',
      name: 'The Wine Cellar',
      entrance: null,
      exit: { roomId: 5, exitName: 'west' },
    });
  });

  it('removing both rows shows the free-standing note and sends no connections', async () => {
    const { onConfirm } = renderDialog({ defaultNeighbor: NEIGHBOR, roomOptions: ROOM_OPTIONS });

    await userEvent.click(screen.getByTestId('add-dialog-entrance-remove'));
    await userEvent.click(screen.getByTestId('add-dialog-exit-remove'));
    expect(screen.getByTestId('add-dialog-freestanding-note')).toBeInTheDocument();

    await userEvent.type(screen.getByTestId('add-dialog-name'), 'The Attic');
    await userEvent.click(screen.getByTestId('add-dialog-submit'));

    expect(onConfirm).toHaveBeenCalledWith({
      kind: 'room',
      name: 'The Attic',
      entrance: null,
      exit: null,
    });
  });

  it('with no adjacent neighbor, both rows start removed and the free-standing note shows immediately', () => {
    renderDialog({ defaultNeighbor: null, roomOptions: ROOM_OPTIONS });

    expect(screen.getByTestId('add-dialog-entrance-removed')).toBeInTheDocument();
    expect(screen.getByTestId('add-dialog-exit-removed')).toBeInTheDocument();
    expect(screen.getByTestId('add-dialog-freestanding-note')).toBeInTheDocument();
  });

  it('editing the exit name to custom text carries it through to the payload', async () => {
    const { onConfirm } = renderDialog({ defaultNeighbor: NEIGHBOR, roomOptions: ROOM_OPTIONS });

    await userEvent.clear(screen.getByTestId('add-dialog-exit-name'));
    await userEvent.type(screen.getByTestId('add-dialog-exit-name'), 'the mirror-door');
    await userEvent.type(screen.getByTestId('add-dialog-name'), 'The Wine Cellar');
    await userEvent.click(screen.getByTestId('add-dialog-submit'));

    expect(onConfirm).toHaveBeenCalledWith(
      expect.objectContaining({
        exit: { roomId: 5, exitName: 'the mirror-door' },
      })
    );
  });

  it('picking a different room for exit-to than entrance-from sends two independent connections', async () => {
    const { onConfirm } = renderDialog({ defaultNeighbor: NEIGHBOR, roomOptions: ROOM_OPTIONS });

    const exitRow = screen.getByTestId('add-dialog-exit-row');
    await userEvent.selectOptions(within(exitRow).getByRole('combobox'), '6');
    await userEvent.type(screen.getByTestId('add-dialog-name'), 'The Wine Cellar');
    await userEvent.click(screen.getByTestId('add-dialog-submit'));

    expect(onConfirm).toHaveBeenCalledWith({
      kind: 'room',
      name: 'The Wine Cellar',
      entrance: { roomId: 5, exitName: 'east' },
      exit: { roomId: 6, exitName: 'west' },
    });
  });

  it('resets its fields whenever it reopens', async () => {
    const onConfirm = vi.fn();
    const { rerender } = renderWithProviders(
      <AddDialog
        mode="rooms"
        open
        onOpenChange={vi.fn()}
        onConfirm={onConfirm}
        defaultNeighbor={NEIGHBOR}
        roomOptions={ROOM_OPTIONS}
      />
    );
    await userEvent.type(screen.getByTestId('add-dialog-name'), 'Leftover text');

    rerender(
      <AddDialog
        mode="rooms"
        open={false}
        onOpenChange={vi.fn()}
        onConfirm={onConfirm}
        defaultNeighbor={NEIGHBOR}
        roomOptions={ROOM_OPTIONS}
      />
    );
    rerender(
      <AddDialog
        mode="rooms"
        open
        onOpenChange={vi.fn()}
        onConfirm={onConfirm}
        defaultNeighbor={NEIGHBOR}
        roomOptions={ROOM_OPTIONS}
      />
    );

    expect(screen.getByTestId('add-dialog-name')).toHaveValue('');
  });
});
