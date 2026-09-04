/**
 * PathStage Component Tests (#3630 folio)
 */

import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi } from 'vitest';
import { PathStage } from '../../components/PathStage';
import { createMockDraft, mockCGExplanations, mockPath } from '../fixtures';
import { renderWithCharacterCreationProviders } from '../testUtils';

const mutate = vi.fn();
vi.mock('../../queries', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../queries')>()),
  usePaths: () => ({
    data: [mockPath, { ...mockPath, id: 99, name: 'Whisper', aspects: ['Cunning'] }],
    isLoading: false,
    error: null,
  }),
  useCGExplanations: () => ({ data: mockCGExplanations }),
  useUpdateDraft: () => ({ mutate }),
}));

describe('PathStage (folio)', () => {
  it('lists paths as entries with their aspects as the tag', () => {
    renderWithCharacterCreationProviders(<PathStage draft={createMockDraft()} />);
    const list = screen.getByRole('list', { name: 'Paths' });
    expect(within(list).getByText(mockPath.name)).toBeInTheDocument();
    expect(within(list).getByText('Cunning')).toBeInTheDocument();
  });

  it('writes the chosen path and marks it selected', async () => {
    const user = userEvent.setup();
    renderWithCharacterCreationProviders(
      <PathStage draft={createMockDraft({ selected_path: mockPath })} />
    );
    await user.click(screen.getByRole('button', { name: 'Choose Whisper' }));
    expect(mutate).toHaveBeenCalledWith(
      expect.objectContaining({ data: { selected_path_id: 99 } })
    );
    expect(screen.getByRole('button', { name: `Choose ${mockPath.name}` })).toHaveAttribute(
      'aria-pressed',
      'true'
    );
  });
});
