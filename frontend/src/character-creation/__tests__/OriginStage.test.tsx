import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi } from 'vitest';
import { OriginStage } from '../components/OriginStage';
import { useStartingAreas } from '../queries';
import {
  mockCGExplanations,
  mockDraftWithArea,
  mockEmptyDraft,
  mockStartingAreas,
} from './fixtures';
import {
  createTestQueryClient,
  renderWithCharacterCreationProviders,
  seedCharacterCreationQueries,
} from './testUtils';

const mutate = vi.fn();
vi.mock('../queries', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../queries')>();
  return {
    ...actual,
    useUpdateDraft: () => ({ mutate, isPending: false }),
    useStartingAreas: vi.fn(actual.useStartingAreas),
  };
});

beforeAll(() => {
  // jsdom has no <dialog>.showModal
  HTMLDialogElement.prototype.showModal = function () {
    this.setAttribute('open', '');
  };
  HTMLDialogElement.prototype.close = function () {
    this.removeAttribute('open');
  };
});
afterEach(() => mutate.mockClear());

function renderOrigin(draft = mockEmptyDraft) {
  const queryClient = createTestQueryClient();
  seedCharacterCreationQueries(queryClient, {
    startingAreas: mockStartingAreas,
    explanations: mockCGExplanations,
  });
  return renderWithCharacterCreationProviders(
    <OriginStage draft={draft} onStageSelect={vi.fn()} />,
    { queryClient }
  );
}

describe('OriginStage', () => {
  it('opens with the one question and no other copy before the entries', async () => {
    renderOrigin();
    expect(await screen.findByRole('heading', { level: 1 })).toHaveTextContent(
      mockCGExplanations.origin_heading
    );
    expect(screen.queryByText(mockCGExplanations.origin_intro)).toBeNull();
    const list = screen.getByRole('list', { name: /starting realms/i });
    expect(within(list).getAllByRole('listitem')).toHaveLength(mockStartingAreas.length);
  });

  it('chooses a realm on the door, never on hover, and clears dependents', async () => {
    renderOrigin();
    const first = mockStartingAreas[0];
    await userEvent.hover(await screen.findByText(first.name));
    expect(mutate).not.toHaveBeenCalled();
    await userEvent.click(
      screen.getByRole('button', { name: new RegExp(`choose ${first.name}`, 'i') })
    );
    expect(mutate).toHaveBeenCalledWith(
      expect.objectContaining({
        data: expect.objectContaining({
          selected_area_id: first.id,
          selected_beginnings_id: null,
          selected_species_id: null,
          family_id: null,
        }),
      })
    );
  });

  it('keeps the next door closed with a reason until a realm is chosen', async () => {
    renderOrigin();
    const door = await screen.findByRole('button', { name: /^next:/i });
    expect(door).toHaveAttribute('aria-disabled', 'true');
    expect(screen.getByText(/choose a starting realm to continue/i)).toBeInTheDocument();
  });

  it('asks before changing a chosen realm', async () => {
    renderOrigin(mockDraftWithArea);
    const other = mockStartingAreas.find(
      (a) => a.id !== mockDraftWithArea.selected_area!.id && a.is_accessible
    )!;
    await userEvent.click(
      await screen.findByRole('button', { name: new RegExp(`choose ${other.name}`, 'i') })
    );
    expect(mutate).not.toHaveBeenCalled();
    expect(screen.getByRole('heading', { name: /change starting realm/i })).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: /change realm/i }));
    expect(mutate).toHaveBeenCalled();
  });

  it('shows a gated realm as readable but closed', async () => {
    renderOrigin();
    const closed = mockStartingAreas.find((a) => !a.is_accessible)!;
    const item = (await screen.findByText(closed.name)).closest('li')!;
    expect(item).toHaveClass('closed');
    expect(within(item).queryByRole('button', { name: /choose/i })).toBeNull();
  });

  it('shows the busy line while the record opens', () => {
    vi.mocked(useStartingAreas).mockReturnValueOnce({
      data: undefined,
      isLoading: true,
      error: null,
    } as unknown as ReturnType<typeof useStartingAreas>);
    renderOrigin();
    expect(screen.getByText('Opening the record.')).toHaveAttribute('aria-busy', 'true');
  });

  it('shows the read-failure line when the starting realms cannot be read', () => {
    vi.mocked(useStartingAreas).mockReturnValueOnce({
      data: undefined,
      isLoading: false,
      error: new Error('boom'),
    } as unknown as ReturnType<typeof useStartingAreas>);
    renderOrigin();
    expect(
      screen.getByText('The starting realms could not be read. Try again.')
    ).toBeInTheDocument();
  });
});
