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
const pathsAskedFor = vi.fn();
let mockSuggestions: { skill_id: number; skill_name: string; suggested_value: number }[] = [];
vi.mock('../../queries', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../queries')>()),
  usePaths: (...args: unknown[]) => {
    pathsAskedFor(...args);
    return {
      data: [
        mockPath,
        // No gift is written for this one yet (#5197).
        { ...mockPath, id: 99, name: 'Whisper', aspects: ['Cunning'], not_yet_implemented: true },
      ],
      isLoading: false,
      error: null,
    };
  },
  useCGExplanations: () => ({ data: mockCGExplanations }),
  useUpdateDraft: () => ({ mutate }),
  usePathSkillSuggestions: (pathId: number | undefined) => ({
    data: pathId ? mockSuggestions : undefined,
  }),
}));

describe('PathStage (folio)', () => {
  it('lists paths as entries with their aspects as the tag', () => {
    renderWithCharacterCreationProviders(<PathStage draft={createMockDraft()} />);
    const list = screen.getByRole('list', { name: 'Paths' });
    expect(within(list).getByText(mockPath.name)).toBeInTheDocument();
    expect(within(list).getByText('Cunning')).toBeInTheDocument();
  });

  it('writes the chosen path from the foot door', async () => {
    const user = userEvent.setup();
    renderWithCharacterCreationProviders(
      <PathStage draft={createMockDraft({ selected_path: null })} />
    );
    await user.click(screen.getAllByRole('button', { name: 'Select Whisper' }).at(-1)!);
    expect(mutate).toHaveBeenCalledWith(
      expect.objectContaining({ data: { selected_path_id: 99 } })
    );
  });

  it('marks the chosen path Selected in its name row and offers Clear (#4022)', async () => {
    const user = userEvent.setup();
    renderWithCharacterCreationProviders(
      <PathStage draft={createMockDraft({ selected_path: mockPath })} />
    );
    expect(screen.getByRole('button', { name: `Selected ${mockPath.name}` })).toHaveAttribute(
      'aria-pressed',
      'true'
    );
    await user.click(screen.getByRole('button', { name: 'Clear' }));
    expect(mutate).toHaveBeenCalledWith(
      expect.objectContaining({ data: { selected_path_id: null } })
    );
  });

  // #5197, owner ruling 2026-11-18: a path with no content behind it is not removed. It is
  // marked, and the mark is cosmetic.
  it('marks a path with nothing behind it Not Yet Implemented, and it can still be chosen', async () => {
    const user = userEvent.setup();
    renderWithCharacterCreationProviders(<PathStage draft={createMockDraft()} />);

    const marks = within(screen.getByRole('list', { name: 'Paths' })).getAllByText(
      'Not Yet Implemented'
    );
    expect(marks).toHaveLength(1);
    expect(marks[0].closest('li')).toHaveTextContent('Whisper');

    // The name row's mark and the foot door share the name; either one chooses.
    await user.click(screen.getAllByRole('button', { name: 'Select Whisper' })[0]);
    expect(mutate).toHaveBeenCalledWith(
      expect.objectContaining({ data: expect.objectContaining({ selected_path_id: 99 }) })
    );
  });

  it("asks for the paths under the draft's beginning, whose traditions decide the mark", () => {
    const draft = createMockDraft();
    renderWithCharacterCreationProviders(<PathStage draft={draft} />);

    expect(pathsAskedFor).toHaveBeenCalledWith(draft.selected_beginnings?.id);
  });

  // #5206, call 14: the note promises skill suggestions, so it waits for the path to have some.
  describe('the Paths note', () => {
    afterEach(() => {
      mockSuggestions = [];
    });

    it('is absent before a path is chosen', () => {
      mockSuggestions = [{ skill_id: 1, skill_name: 'Blades', suggested_value: 20 }];
      renderWithCharacterCreationProviders(
        <PathStage draft={createMockDraft({ selected_path: null })} />
      );
      expect(screen.queryByText(/set starting skill suggestions/)).not.toBeInTheDocument();
    });

    it('is absent when the chosen path has no suggestions', () => {
      renderWithCharacterCreationProviders(
        <PathStage draft={createMockDraft({ selected_path: mockPath })} />
      );
      expect(screen.queryByText(/set starting skill suggestions/)).not.toBeInTheDocument();
    });

    it('prints when the chosen path has suggestions', () => {
      mockSuggestions = [{ skill_id: 1, skill_name: 'Blades', suggested_value: 20 }];
      renderWithCharacterCreationProviders(
        <PathStage draft={createMockDraft({ selected_path: mockPath })} />
      );
      expect(screen.getByText(/set starting skill suggestions/)).toBeInTheDocument();
    });
  });
});
