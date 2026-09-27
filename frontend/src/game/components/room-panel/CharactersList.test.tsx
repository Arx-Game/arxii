import { fireEvent, render, screen, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { Provider } from 'react-redux';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { store } from '@/store/store';
import { CharactersList } from './CharactersList';

const others = [
  { dbref: '#100', name: 'Alice', thumbnail_url: null },
  { dbref: '#101', name: 'Bob', thumbnail_url: null },
];

// PersonaMenu (#4030) needs a Redux store (useAppSelector) and a query client
// (useQuery/useMutation) above it; only the tests below render a row with a
// persona id set (the only condition that mounts it).
function Wrapper({ children }: { children: React.ReactNode }) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return (
    <Provider store={store}>
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    </Provider>
  );
}

describe('the threshold mark (#3867)', () => {
  it('marks a present character who has not entered the scene, and the viewer likewise', () => {
    render(
      <CharactersList
        characters={[
          { ...others[0], in_scene: true },
          { ...others[1], in_scene: false },
        ]}
        viewer={{ name: 'Hero', thumbnailUrl: null }}
        viewerInScene={false}
      />
    );
    const rows = screen.getAllByRole('listitem');
    expect(within(rows[0]).getByTestId('threshold-mark')).toHaveAttribute(
      'title',
      'Not yet in the scene'
    );
    expect(within(rows[1]).queryByTestId('threshold-mark')).toBeNull();
    expect(within(rows[2]).getByTestId('threshold-mark')).toBeInTheDocument();
  });

  it('marks nobody when there is no live scene', () => {
    render(<CharactersList characters={others} viewer={{ name: 'Hero', thumbnailUrl: null }} />);
    expect(screen.queryByTestId('threshold-mark')).toBeNull();
  });
});

describe('CharactersList "you" row (#3856)', () => {
  it('lists the viewer first, tagged you, and counts them among the characters', () => {
    render(
      <CharactersList
        characters={others}
        viewer={{ name: 'Hero', thumbnailUrl: null }}
        onViewerClick={vi.fn()}
      />
    );

    expect(screen.getByText('Characters (3)')).toBeInTheDocument();
    const rows = screen.getAllByRole('listitem');
    expect(rows.map((row) => row.textContent)).toEqual([
      expect.stringContaining('Hero'),
      expect.stringContaining('Alice'),
      expect.stringContaining('Bob'),
    ]);
    expect(within(rows[0]).getByText('you')).toBeInTheDocument();
  });

  it('clicking the viewer row calls onViewerClick, never onCharacterClick', () => {
    const onViewerClick = vi.fn();
    const onCharacterClick = vi.fn();
    render(
      <CharactersList
        characters={others}
        viewer={{ name: 'Hero', thumbnailUrl: null }}
        onViewerClick={onViewerClick}
        onCharacterClick={onCharacterClick}
      />
    );

    fireEvent.click(screen.getByRole('button', { name: /hero/i }));

    expect(onViewerClick).toHaveBeenCalledTimes(1);
    expect(onCharacterClick).not.toHaveBeenCalled();
  });

  it('still says nobody else is here below the viewer when the room is otherwise empty', () => {
    render(<CharactersList characters={[]} viewer={{ name: 'Hero', thumbnailUrl: null }} />);

    expect(screen.getByText('Characters (1)')).toBeInTheDocument();
    expect(screen.getByText('Hero')).toBeInTheDocument();
    expect(screen.getByText('Nobody else here.')).toBeInTheDocument();
  });

  it('renders as before when no viewer is supplied', () => {
    render(<CharactersList characters={others} />);

    expect(screen.getByText('Characters (2)')).toBeInTheDocument();
    expect(screen.queryByText('you')).not.toBeInTheDocument();
  });
});

describe('CharactersList persona menu (#4030)', () => {
  it('right-click on a character row with a persona_id opens the menu with Look and View sheet', async () => {
    render(
      <Wrapper>
        <CharactersList
          characters={[{ ...others[0], persona_id: 10 }, others[1]]}
          onCharacterClick={vi.fn()}
        />
      </Wrapper>
    );

    fireEvent.contextMenu(screen.getByText('Alice'));
    const menu = await screen.findByRole('menu');
    const labels = within(menu)
      .getAllByRole('menuitem')
      .map((el) => el.textContent);
    expect(labels).toEqual(['Look', 'View sheet']);
  });

  it('left-click on a character row with a persona_id still calls onCharacterClick', () => {
    const onCharacterClick = vi.fn();
    render(
      <Wrapper>
        <CharactersList
          characters={[{ ...others[0], persona_id: 10 }]}
          onCharacterClick={onCharacterClick}
        />
      </Wrapper>
    );

    fireEvent.click(screen.getByRole('button', { name: /alice/i }));

    expect(onCharacterClick).toHaveBeenCalledWith(
      expect.objectContaining({ dbref: '#100', persona_id: 10 })
    );
  });

  it('a row with no persona_id renders with no menu, as today', () => {
    render(<CharactersList characters={others} onCharacterClick={vi.fn()} />);

    fireEvent.contextMenu(screen.getByText('Alice'));

    expect(screen.queryByRole('menu')).not.toBeInTheDocument();
  });

  it("right-click on the viewer's you row opens the menu when viewerPersonaId is set", async () => {
    render(
      <Wrapper>
        <CharactersList
          characters={others}
          viewer={{ name: 'Hero', thumbnailUrl: null }}
          viewerPersonaId={7}
          onViewerClick={vi.fn()}
        />
      </Wrapper>
    );

    fireEvent.contextMenu(screen.getByText('Hero'));
    const menu = await screen.findByRole('menu');
    expect(within(menu).getByRole('menuitem', { name: 'Look' })).toBeInTheDocument();
  });

  it('the you row renders with no menu when viewerPersonaId is absent, as today', () => {
    render(
      <CharactersList
        characters={others}
        viewer={{ name: 'Hero', thumbnailUrl: null }}
        onViewerClick={vi.fn()}
      />
    );

    fireEvent.contextMenu(screen.getByText('Hero'));

    expect(screen.queryByRole('menu')).not.toBeInTheDocument();
  });
});
