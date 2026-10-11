/**
 * Picker (#4239): nothing under two characters, hits of the one kind, and
 * Create offered in place.
 */
import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi } from 'vitest';

import { renderWithProviders } from '@/test/utils/renderWithProviders';
import { Picker } from '../shared/Picker';

vi.mock('../queries', () => ({
  useSearch: (q: string) => ({
    data:
      q.length >= 2
        ? [
            { kind: 'family', id: 4, name: 'Katta', sub: 'noble' },
            { kind: 'person', id: 11, name: 'Kathryn mar Katta', sub: 'Katta' },
          ]
        : undefined,
  }),
}));

test('shows hits of its kind and offers Create in place', async () => {
  const onPick = vi.fn();
  const onCreate = vi.fn();
  renderWithProviders(
    <Picker
      kind="family"
      placeholder="Search families"
      onPick={onPick}
      createLabel="Create Family"
      onCreate={onCreate}
    />
  );
  expect(screen.getByRole('button', { name: 'Create Family' })).toBeInTheDocument();
  await userEvent.type(screen.getByRole('searchbox'), 'Ka');
  expect(screen.getByRole('button', { name: /Katta noble/ })).toBeInTheDocument();
  expect(screen.queryByRole('button', { name: /Kathryn/ })).toBeNull();
  await userEvent.click(screen.getByRole('button', { name: /Katta noble/ }));
  expect(onPick).toHaveBeenCalledWith(expect.objectContaining({ kind: 'family', id: 4 }));
});
