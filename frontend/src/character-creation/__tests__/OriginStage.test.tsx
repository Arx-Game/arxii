import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi } from 'vitest';
import { OriginStage } from '../components/OriginStage';
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
  return { ...actual, useUpdateDraft: () => ({ mutate, isPending: false }) };
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
      screen.getByRole('button', { name: new RegExp(`begin in ${first.name}`, 'i') })
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

  it('keeps the turn-the-page door closed with a reason until a realm is chosen', async () => {
    renderOrigin();
    const door = await screen.findByRole('button', { name: /turn the page/i });
    expect(door).toHaveAttribute('aria-disabled', 'true');
    expect(screen.getByText(/choose a realm to turn the page/i)).toBeInTheDocument();
  });

  it('asks before changing a chosen realm', async () => {
    renderOrigin(mockDraftWithArea);
    const other = mockStartingAreas.find(
      (a) => a.id !== mockDraftWithArea.selected_area!.id && a.is_accessible
    )!;
    await userEvent.click(
      await screen.findByRole('button', { name: new RegExp(`begin in ${other.name}`, 'i') })
    );
    expect(mutate).not.toHaveBeenCalled();
    expect(screen.getByRole('heading', { name: /begin somewhere else/i })).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: /begin again there/i }));
    expect(mutate).toHaveBeenCalled();
  });

  it('shows a gated realm as readable but closed', async () => {
    renderOrigin();
    const closed = mockStartingAreas.find((a) => !a.is_accessible)!;
    const item = (await screen.findByText(closed.name)).closest('li')!;
    expect(item).toHaveClass('closed');
    expect(within(item).queryByRole('button', { name: /begin in/i })).toBeNull();
  });
});
