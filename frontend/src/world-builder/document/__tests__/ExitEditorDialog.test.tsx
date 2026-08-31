import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi } from 'vitest';

import { renderWithProviders } from '@/test/utils/renderWithProviders';
import type { WorldBuilderExitDetail } from '../../types';
import { ExitEditorDialog } from '../ExitEditorDialog';

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
    >
      <option value="" disabled></option>
      {children}
    </select>
  ),
  SelectTrigger: ({
    children,
    id,
    title,
    'data-testid': testId,
  }: {
    children?: React.ReactNode;
    id?: string;
    title?: string;
    'data-testid'?: string;
  }) => (
    <span id={id} title={title} data-testid={testId}>
      {children}
    </span>
  ),
  SelectValue: () => null,
  SelectContent: ({ children }: { children?: React.ReactNode }) => <>{children}</>,
  SelectItem: ({ value, children }: { value: string; children?: React.ReactNode }) => (
    <option value={value}>{children}</option>
  ),
}));

const EXIT: WorldBuilderExitDetail = {
  id: 10,
  name: 'north',
  to_room_id: 200,
  kind: 'door',
  is_open: true,
  aliases: ['n'],
};

function renderDialog(overrides: Partial<Parameters<typeof ExitEditorDialog>[0]> = {}) {
  const runAction = vi.fn();
  const onOpenChange = vi.fn();
  renderWithProviders(
    <ExitEditorDialog
      open
      onOpenChange={onOpenChange}
      exit={EXIT}
      runAction={runAction}
      {...overrides}
    />
  );
  return { runAction, onOpenChange };
}

describe('ExitEditorDialog', () => {
  it('does not dispatch staff_rename_exit when the name is unchanged, but always dispatches staff_set_exit_detail', async () => {
    const { runAction } = renderDialog();
    await userEvent.click(screen.getByTestId('exit-editor-save'));

    expect(runAction).not.toHaveBeenCalledWith('staff_rename_exit', expect.anything());
    expect(runAction).toHaveBeenCalledWith('staff_set_exit_detail', {
      exit_id: 10,
      kind: 'door',
      is_open: true,
      aliases: 'n',
    });
  });

  it('dispatches staff_rename_exit when the name changes', async () => {
    const { runAction } = renderDialog();
    const nameInput = screen.getByTestId('exit-editor-name');
    await userEvent.clear(nameInput);
    await userEvent.type(nameInput, 'the postern');
    await userEvent.click(screen.getByTestId('exit-editor-save'));

    expect(runAction).toHaveBeenCalledWith('staff_rename_exit', {
      exit_id: 10,
      name: 'the postern',
    });
  });

  it('sends the edited kind, openness, and aliases together via staff_set_exit_detail', async () => {
    const { runAction } = renderDialog();
    const kindSelect = screen.getByTestId('exit-editor-kind').closest('select');
    if (!kindSelect) throw new Error('kind select not found');
    await userEvent.selectOptions(kindSelect, 'window');
    await userEvent.click(screen.getByRole('switch'));
    const aliasesInput = screen.getByTestId('exit-editor-aliases');
    await userEvent.clear(aliasesInput);
    await userEvent.type(aliasesInput, 'n, northward');
    await userEvent.click(screen.getByTestId('exit-editor-save'));

    expect(runAction).toHaveBeenCalledWith('staff_set_exit_detail', {
      exit_id: 10,
      kind: 'window',
      is_open: false,
      aliases: 'n, northward',
    });
  });

  it('closes on save', async () => {
    const { onOpenChange } = renderDialog();
    await userEvent.click(screen.getByTestId('exit-editor-save'));
    expect(onOpenChange).toHaveBeenCalledWith(false);
  });

  it('renders lock/secrecy/watcher as disabled stubs with the honest title', () => {
    renderDialog();
    for (const testId of ['exit-editor-lock', 'exit-editor-secrecy', 'exit-editor-watcher']) {
      const el = screen.getByTestId(testId);
      expect(el).toHaveAttribute('title', 'wired when the backing systems land');
      expect(el.closest('select')).toBeDisabled();
    }
  });

  it('renders nothing when no exit is given', () => {
    const { container } = renderWithProviders(
      <ExitEditorDialog open onOpenChange={vi.fn()} exit={null} runAction={vi.fn()} />
    );
    expect(container.querySelector('[data-testid="exit-editor-save"]')).not.toBeInTheDocument();
  });
});
