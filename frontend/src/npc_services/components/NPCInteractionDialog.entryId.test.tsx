/**
 * #3479 Task 5: NPCInteractionDialog acts as the tab's browsing identity:
 * `useBrowsingIdentity().entryId` is threaded into startInteraction /
 * resolveOffer / endInteraction (null passes through as null, which the
 * client omits from the body).
 */
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi } from 'vitest';

const startInteraction = vi.fn();
const resolveOffer = vi.fn();
const endInteraction = vi.fn();
vi.mock('../interaction', () => ({
  startInteraction: (...args: unknown[]) => startInteraction(...args),
  resolveOffer: (...args: unknown[]) => resolveOffer(...args),
  endInteraction: (...args: unknown[]) => endInteraction(...args),
}));

const useBrowsingIdentity = vi.fn();
vi.mock('@/roster/useBrowsingIdentity', () => ({
  useBrowsingIdentity: () => useBrowsingIdentity(),
}));

import { NPCInteractionDialog } from './NPCInteractionDialog';

const OPEN_STATE = {
  closed: false,
  last_result_message: null,
  available_offers: [{ id: 44, label: 'Ask for work', kind: 'mission' }],
};

beforeEach(() => {
  vi.clearAllMocks();
  useBrowsingIdentity.mockReturnValue({ entryId: 5, name: 'Aria', entry: null });
  startInteraction.mockResolvedValue(OPEN_STATE);
  resolveOffer.mockResolvedValue({ ...OPEN_STATE, closed: true, available_offers: [] });
  endInteraction.mockResolvedValue({ ...OPEN_STATE, closed: true });
});

describe('NPCInteractionDialog browsing identity (#3479)', () => {
  it('starts the interaction as the browsing entry and resolves offers with it', async () => {
    const user = userEvent.setup();
    render(
      <NPCInteractionDialog roleId={12} title="Old Marta" open onOpenChange={() => undefined} />
    );

    await waitFor(() => expect(startInteraction).toHaveBeenCalledWith(12, 5));

    await user.click(await screen.findByRole('button', { name: /ask for work/i }));
    await waitFor(() => expect(resolveOffer).toHaveBeenCalledWith(44, 5));
  });

  it('ends an abandoned interaction as the same entry', async () => {
    const onOpenChange = vi.fn();
    const { rerender } = render(
      <NPCInteractionDialog roleId={12} title="Old Marta" open onOpenChange={onOpenChange} />
    );
    await waitFor(() => expect(startInteraction).toHaveBeenCalled());

    // Radix close path goes through the dialog's own close handler; simulate
    // it directly via the Escape key on the open dialog.
    const user = userEvent.setup();
    await user.keyboard('{Escape}');
    await waitFor(() => expect(endInteraction).toHaveBeenCalledWith(5));
    rerender(
      <NPCInteractionDialog
        roleId={12}
        title="Old Marta"
        open={false}
        onOpenChange={onOpenChange}
      />
    );
  });

  it('passes a null identity through (client omits the field)', async () => {
    useBrowsingIdentity.mockReturnValue({ entryId: null, name: null, entry: null });
    render(
      <NPCInteractionDialog roleId={12} title="Old Marta" open onOpenChange={() => undefined} />
    );
    await waitFor(() => expect(startInteraction).toHaveBeenCalledWith(12, null));
  });
});
