/**
 * WorshipSection (#3779): the public faith line, the visions list for the owner and staff,
 * the owner's Pray control, and staff's prayers and Send-vision control.
 */

import { render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactNode } from 'react';
import { vi } from 'vitest';
import { WorshipSection } from '../components/WorshipSection';

vi.mock('../queries', () => ({
  useVisions: vi.fn(),
  usePrayers: vi.fn(),
  usePrayMutation: vi.fn(() => ({ mutate: vi.fn(), isPending: false })),
  useSendVision: vi.fn(() => ({ mutate: vi.fn(), isPending: false })),
}));
vi.mock('@/character-creation/queries', () => ({
  useWorshippedBeings: vi.fn(() => ({ data: [{ id: 1, name: 'The Shepherd' }] })),
}));

import * as queries from '../queries';

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

const vision = {
  id: 7,
  recipient: 3,
  being_name: null,
  body: 'A door opens in the dark.',
  reveal_source: false,
  prayer: null,
  clue: null,
  clue_slug: null,
  episode: null,
  episode_title: null,
  sent_at: new Date().toISOString(),
};

const prayer = {
  id: 11,
  character_sheet: 3,
  being: 1,
  being_name: 'The Shepherd',
  text: 'Keep this house.',
  devotion_granted: 1,
  dire_straits: '' as const,
  answered: false,
  prayed_at: new Date().toISOString(),
};

function arm(visions: unknown[], prayers: unknown[]) {
  vi.mocked(queries.useVisions).mockReturnValue({ data: visions } as never);
  vi.mocked(queries.usePrayers).mockReturnValue({ data: prayers } as never);
}

describe('WorshipSection', () => {
  it('shows the owner their faith, their visions and the Pray control', () => {
    arm([vision], []);
    render(
      <WorshipSection
        sheetId={3}
        characterName="Alaric"
        isMyCharacter
        isStaff={false}
        publicWorship={{ id: 1, name: 'The Shepherd' }}
      />,
      { wrapper }
    );
    expect(screen.getByTestId('public-worship')).toHaveTextContent('Worships The Shepherd.');
    expect(screen.getByTestId('vision-card')).toHaveTextContent('A door opens in the dark.');
    expect(screen.getByTestId('vision-card')).not.toHaveTextContent('from');
    expect(screen.getByTestId('pray-button')).toBeInTheDocument();
    expect(screen.queryByTestId('send-vision-button')).not.toBeInTheDocument();
    expect(screen.queryByTestId('prayers-list')).not.toBeInTheDocument();
  });

  it('names the being on a revealed vision', () => {
    arm([{ ...vision, being_name: 'The Shepherd', reveal_source: true }], []);
    render(
      <WorshipSection
        sheetId={3}
        characterName="Alaric"
        isMyCharacter
        isStaff={false}
        publicWorship={null}
      />,
      { wrapper }
    );
    expect(screen.getByTestId('vision-card')).toHaveTextContent('from The Shepherd');
    expect(screen.getByTestId('public-worship')).toHaveTextContent('No declared faith.');
  });

  it('gives staff the prayers and the Send-vision control, and no Pray control', () => {
    arm([], [prayer]);
    render(
      <WorshipSection
        sheetId={3}
        characterName="Alaric"
        isMyCharacter={false}
        isStaff
        publicWorship={null}
      />,
      { wrapper }
    );
    expect(screen.getByTestId('send-vision-button')).toBeInTheDocument();
    expect(screen.getByTestId('prayer-row')).toHaveTextContent('Keep this house.');
    expect(screen.getByTestId('prayer-row')).toHaveTextContent('(act of devotion)');
    expect(screen.getByTestId('visions-empty')).toBeInTheDocument();
    expect(screen.queryByTestId('pray-button')).not.toBeInTheDocument();
  });

  it('shows a stranger only the public faith', () => {
    arm([], []);
    render(
      <WorshipSection
        sheetId={3}
        characterName="Alaric"
        isMyCharacter={false}
        isStaff={false}
        publicWorship={{ id: 1, name: 'The Shepherd' }}
      />,
      { wrapper }
    );
    expect(screen.getByTestId('public-worship')).toBeInTheDocument();
    expect(screen.queryByTestId('visions-list')).not.toBeInTheDocument();
    expect(screen.queryByTestId('pray-button')).not.toBeInTheDocument();
    expect(queries.useVisions).toHaveBeenLastCalledWith(3, false);
  });
});
