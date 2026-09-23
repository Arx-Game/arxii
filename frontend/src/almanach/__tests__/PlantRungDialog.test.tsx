import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi } from 'vitest';

import { renderWithProviders } from '@/test/utils/renderWithProviders';
import { PlantRungDialog } from '../ladder/PlantRungDialog';

test('plants a named county under a duchy', async () => {
  const onConfirm = vi.fn();
  renderWithProviders(
    <PlantRungDialog
      parent={{ title_id: 1, name: 'Fervor', tier: 'duchy' }}
      open
      onClose={() => {}}
      onConfirm={onConfirm}
    />
  );
  await userEvent.type(screen.getByLabelText('name'), 'Rescoldo');
  await userEvent.click(screen.getByRole('button', { name: 'Plant' }));
  expect(onConfirm).toHaveBeenCalledWith({
    tier: 'county',
    name: 'Rescoldo',
    held_by_org_id: null,
  });
});

test('with no parent, opens straight into root mode: no toggle, root tier choices, atRoot on submit (I9)', async () => {
  const onConfirm = vi.fn();
  renderWithProviders(
    <PlantRungDialog parent={null} open onClose={() => {}} onConfirm={onConfirm} />
  );
  expect(screen.queryByRole('button', { name: /at the realm root/i })).toBeNull();
  expect(screen.getByText('the realm')).toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'empire' })).toBeInTheDocument();
  expect(screen.queryByRole('button', { name: 'county' })).toBeNull();

  await userEvent.type(screen.getByLabelText('name'), 'Veyrane');
  await userEvent.click(screen.getByRole('button', { name: 'Plant' }));
  expect(onConfirm).toHaveBeenCalledWith({
    tier: 'empire',
    name: 'Veyrane',
    held_by_org_id: null,
    atRoot: true,
  });
});

test('with allowRoot, the plant seg toggles between under-parent and root tier choices (I9)', async () => {
  const onConfirm = vi.fn();
  renderWithProviders(
    <PlantRungDialog
      parent={{ title_id: 1, name: 'Fervor', tier: 'duchy' }}
      allowRoot
      open
      onClose={() => {}}
      onConfirm={onConfirm}
    />
  );
  // Defaults OFF — the seg exists but "under Fervor" is pressed, matching
  // every caller that never passes `allowRoot` at all.
  expect(screen.getByRole('button', { name: 'under Fervor' })).toHaveAttribute(
    'aria-pressed',
    'true'
  );
  expect(screen.getByRole('button', { name: 'county' })).toBeInTheDocument();

  await userEvent.click(screen.getByRole('button', { name: 'at the realm root' }));
  expect(screen.getByText('the realm')).toBeInTheDocument();
  expect(screen.queryByRole('button', { name: 'county' })).toBeNull();
  expect(screen.getByRole('button', { name: 'duchy' })).toBeInTheDocument();

  await userEvent.type(screen.getByLabelText('name'), 'Veyrane');
  await userEvent.click(screen.getByRole('button', { name: 'Plant' }));
  expect(onConfirm).toHaveBeenCalledWith(
    expect.objectContaining({ name: 'Veyrane', atRoot: true })
  );
});

test('a barony parent offers no tier choices and Plant stays disabled even once named (M7)', async () => {
  renderWithProviders(
    <PlantRungDialog
      parent={{ title_id: 3, name: 'Ascua', tier: 'barony' }}
      open
      onClose={() => {}}
      onConfirm={vi.fn()}
    />
  );
  expect(screen.queryByRole('group', { name: 'Tier' })?.children.length ?? 0).toBe(0);

  // A name alone doesn't unblock Plant — there is no tier left to plant.
  await userEvent.type(screen.getByLabelText('name'), 'Anything');
  expect(screen.getByRole('button', { name: 'Plant' })).toBeDisabled();
});
