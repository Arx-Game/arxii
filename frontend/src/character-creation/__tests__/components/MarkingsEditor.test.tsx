/**
 * MarkingsEditor (#2985, #5241).
 *
 * Removing a marking is not only a change to the markings list. The server drops every
 * quality held on that marking in the same request and refunds its points, so the
 * draft's picks, its totals and its CG points all change with it. The page has to ask
 * for those again; left with the old list it keeps counting the removed marking's
 * points, and the next quality clicked is sent with a pick on a marking that no longer
 * exists, which the server refuses.
 */

import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi } from 'vitest';
import { MarkingsEditor } from '../../components/MarkingsEditor';
import { distinctionKeys } from '@/hooks/useDistinctions';
import { characterCreationKeys } from '../../queries';
import { createMockDraft } from '../fixtures';
import { createTestQueryClient, renderWithCharacterCreationProviders } from '../testUtils';

const deleteDraftMarking = vi.fn();

vi.mock('../../api', () => ({
  listDraftMarkings: vi.fn(async () => [
    { id: 12, body_region: 'face', kind: 'scar', name: 'Seam', description: 'An old cut.' },
  ]),
  createDraftMarking: vi.fn(),
  deleteDraftMarking: (id: number) => deleteDraftMarking(id),
}));
vi.mock('../../queries', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../queries')>()),
  useDraftOffers: () => ({ data: { offers: [], terms: [] }, isLoading: false }),
}));
vi.mock('@/hooks/useDistinctions', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/hooks/useDistinctions')>()),
  useDraftDistinctions: () => ({ data: [] }),
  useSyncDistinctions: () => ({ mutate: vi.fn(), pendingEntries: null }),
}));

describe('MarkingsEditor', () => {
  beforeEach(() => {
    deleteDraftMarking.mockReset();
    deleteDraftMarking.mockResolvedValue(undefined);
  });

  it('asks again for the picks and the points when a marking is removed', async () => {
    const user = userEvent.setup();
    const draft = createMockDraft({ id: 7 });
    const queryClient = createTestQueryClient();
    const invalidate = vi.spyOn(queryClient, 'invalidateQueries');
    renderWithCharacterCreationProviders(<MarkingsEditor draft={draft} />, { queryClient });

    await user.click(await screen.findByRole('button', { name: 'Remove' }));
    await waitFor(() => expect(deleteDraftMarking).toHaveBeenCalledWith(12));

    const asked = () => invalidate.mock.calls.map(([filters]) => filters?.queryKey);
    await waitFor(() => expect(asked()).toContainEqual(distinctionKeys.draftDistinctions(7)));
    expect(asked()).toContainEqual(characterCreationKeys.draft());
    expect(asked()).toContainEqual(characterCreationKeys.draftCGPoints(7));
  });
});
