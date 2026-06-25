import { screen } from '@testing-library/react';
import { vi } from 'vitest';

import { renderWithProviders } from '@/test/utils/renderWithProviders';
import { getPresence } from '@/presence/api';
import { PresencePanel } from './PresencePanel';

vi.mock('@/presence/api', () => ({ getPresence: vi.fn() }));

describe('PresencePanel', () => {
  it('renders the online roster with a coarse idle marker', async () => {
    vi.mocked(getPresence).mockResolvedValue({
      who: [{ name: 'Bram', idle: 'idle' }],
      where: [],
    });
    renderWithProviders(<PresencePanel />);
    expect(await screen.findByText('Bram')).toBeInTheDocument();
    expect(screen.getByText('idle')).toBeInTheDocument();
  });

  it('renders where entries with their location', async () => {
    vi.mocked(getPresence).mockResolvedValue({
      who: [],
      where: [{ persona_name: 'Captain Vale', room_path: 'Umbros - Sable Hold' }],
    });
    renderWithProviders(<PresencePanel />);
    expect(await screen.findByText('Captain Vale')).toBeInTheDocument();
  });
});
