import { fireEvent, render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import { Provider } from 'react-redux';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { store } from '@/store/store';
import { ExplorationReader } from './ExplorationReader';

// Every ambient row's header is now wrapped in PersonaMenu (#4030), which
// needs a Redux store (useAppSelector) and a query client (useQuery/useMutation)
// above it.
function Wrapper({ children }: { children: React.ReactNode }) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return (
    <Provider store={store}>
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    </Provider>
  );
}

const room = {
  id: 2,
  name: 'Quiet courtyard',
  description: 'Rain rests on the stones.',
  thumbnail_url: null,
  characters: [],
  objects: [],
  exits: [],
  is_owner: false,
  is_public: true,
  hub: null,
};

describe('ExplorationReader', () => {
  it('shows a structured entry state without a transcript', () => {
    render(<ExplorationReader room={null} lifecycleState="entering" />);
    expect(screen.getByRole('heading', { name: 'Finding your place' })).toBeInTheDocument();
    expect(screen.getByTestId('exploration-reader')).not.toHaveTextContent('[');
  });

  it('surfaces entry failure text before a room snapshot exists', () => {
    render(
      <ExplorationReader
        room={null}
        lifecycleState="entry-error"
        entryError="Your location could not be confirmed."
      />
    );
    expect(screen.getByRole('alert')).toHaveTextContent('Your location could not be confirmed.');
  });

  it('renders confirmed room facts and ambient poses as separate entries', () => {
    render(
      <Wrapper>
        <ExplorationReader
          room={room}
          ambientInteractions={[
            {
              id: 9,
              persona: { id: 4, name: 'Mara', thumbnail_url: '' },
              content: 'A bell sounds beyond the wall.',
              line: 'Mara says, "A bell sounds beyond the wall."',
              mode: 'say',
              timestamp: '2026-01-01T00:00:00Z',
              scene_id: null,
              place_id: null,
              place_name: null,
              receiver_persona_ids: [],
              target_persona_ids: [],
            },
          ]}
        />
      </Wrapper>
    );
    expect(screen.getByRole('heading', { name: 'Quiet courtyard' })).toBeInTheDocument();
    expect(screen.getByText('Rain rests on the stones.')).toBeInTheDocument();
    // The body is the whole line (#3858); the header still names the writer.
    expect(screen.getByTestId('actor-line')).toHaveTextContent(
      'Mara says, "A bell sounds beyond the wall."'
    );
    // Once on the card, once at the head of the line.
    expect(screen.getAllByText('Mara')).toHaveLength(2);
  });

  it('renders notes among the ambient poses at their time, not in a section of their own (#3856)', () => {
    render(
      <Wrapper>
        <ExplorationReader
          room={room}
          ambientInteractions={[
            {
              id: 9,
              persona: { id: 4, name: 'Mara', thumbnail_url: '' },
              content: 'A bell sounds beyond the wall.',
              mode: 'say',
              timestamp: '2026-01-01T00:00:20Z',
              scene_id: null,
              place_id: null,
              place_name: null,
              receiver_persona_ids: [],
              target_persona_ids: [],
            },
          ]}
          notes={[
            {
              id: 'n1',
              kind: 'look',
              content: 'Rain rests on the stones.',
              timestamp: '2026-01-01T00:00:10.000Z',
            },
            {
              id: 'n2',
              kind: 'error',
              content: "Command 'lok' is not available.",
              timestamp: '2026-01-01T00:00:30.000Z',
            },
          ]}
        />
      </Wrapper>
    );

    const column = screen.getByRole('list', { name: 'Activity' });
    const rows = [...column.querySelectorAll('[data-feed-row]')].map((row) =>
      row.getAttribute('data-feed-row')
    );
    expect(rows).toEqual(['note:n1', 'interaction:9', 'note:n2']);
    expect(screen.getByRole('alert')).toHaveTextContent("Command 'lok' is not available.");
    expect(screen.queryByText('Nearby activity')).not.toBeInTheDocument();
  });
});

describe('ExplorationReader persona menu (#4030)', () => {
  const ambientInteraction = {
    id: 9,
    persona: { id: 4, name: 'Mara', thumbnail_url: '' },
    content: 'A bell sounds beyond the wall.',
    mode: 'say',
    timestamp: '2026-01-01T00:00:00Z',
    scene_id: null,
    place_id: null,
    place_name: null,
    receiver_persona_ids: [],
    target_persona_ids: [],
  };

  it('right-click on the name opens the menu with Look and View sheet', async () => {
    render(
      <Wrapper>
        <ExplorationReader room={room} ambientInteractions={[ambientInteraction]} />
      </Wrapper>
    );

    fireEvent.contextMenu(screen.getByText('Mara'));
    const menu = await screen.findByRole('menu');
    const labels = within(menu)
      .getAllByRole('menuitem')
      .map((el) => el.textContent);
    expect(labels).toEqual(['Look', 'View sheet']);
  });

  it('right-click on the avatar also opens the menu', async () => {
    render(
      <Wrapper>
        <ExplorationReader room={room} ambientInteractions={[ambientInteraction]} />
      </Wrapper>
    );

    // No thumbnail_url in the fixture — the avatar renders as the persona's initial.
    fireEvent.contextMenu(screen.getByText('M'));
    const menu = await screen.findByRole('menu');
    expect(within(menu).getByRole('menuitem', { name: 'Look' })).toBeInTheDocument();
  });

  it('left-click on the name opens the menu (leftClick)', async () => {
    const user = userEvent.setup();
    render(
      <Wrapper>
        <ExplorationReader room={room} ambientInteractions={[ambientInteraction]} />
      </Wrapper>
    );

    await user.click(screen.getByRole('button', { name: /Mara/ }));
    expect(await screen.findByRole('menu')).toBeInTheDocument();
  });
});
