/**
 * #3044 — NpcGiversBlock tests.
 *
 * Verifies: renders nothing with no givers, lists each giver's name with a
 * Talk button, and clicking Talk mounts NPCInteractionDialog with that
 * giver's role_id.
 */
import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi } from 'vitest';

import { renderWithProviders } from '@/test/utils/renderWithProviders';
import type { NpcGiver } from '@/hooks/types';
import { NpcGiversBlock } from './NpcGiversBlock';

vi.mock('@/npc_services/components/NPCInteractionDialog', () => ({
  NPCInteractionDialog: ({ roleId, title }: { roleId: number; title: string }) => (
    <div data-testid="npc-interaction-dialog">
      {title} (role {roleId})
    </div>
  ),
}));

const crier: NpcGiver = { role_id: 12, name: 'Old Marta' };

describe('NpcGiversBlock', () => {
  it('renders nothing when there are no NPC givers', () => {
    const { container } = renderWithProviders(<NpcGiversBlock npcGivers={[]} />);
    expect(container).toBeEmptyDOMElement();
  });

  it('lists each giver with a Talk button', () => {
    renderWithProviders(<NpcGiversBlock npcGivers={[crier]} />);

    expect(screen.getByText('Old Marta')).toBeInTheDocument();
    expect(screen.getByTestId('talk-12')).toBeInTheDocument();
  });

  it('mounts NPCInteractionDialog with the clicked giver role_id on Talk', async () => {
    const user = userEvent.setup();
    renderWithProviders(<NpcGiversBlock npcGivers={[crier]} />);

    expect(screen.queryByTestId('npc-interaction-dialog')).not.toBeInTheDocument();

    await user.click(screen.getByTestId('talk-12'));

    expect(screen.getByTestId('npc-interaction-dialog')).toHaveTextContent('Old Marta (role 12)');
  });
});
