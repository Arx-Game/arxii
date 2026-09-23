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
