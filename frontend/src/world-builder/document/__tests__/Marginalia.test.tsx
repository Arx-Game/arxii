import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi } from 'vitest';

import { renderWithProviders } from '@/test/utils/renderWithProviders';
import type { WorldBuilderComfort, WorldBuilderExitDetail, WorldBuilderRoom } from '../../types';
import { Marginalia } from '../Marginalia';

function makeRoom(overrides: Partial<WorldBuilderRoom> = {}): WorldBuilderRoom {
  return {
    id: 100,
    name: 'The Grand Foyer',
    description: '',
    is_public: true,
    is_social_hub: false,
    is_outdoor: false,
    enclosure: 'walled',
    size_name: null,
    grid_x: 0,
    grid_y: 0,
    floor: 0,
    fixture_key: null,
    origin: 'authored',
    exported_at: null,
    published_at: null,
    needs_prose: false,
    art_url: null,
    stats: [],
    area_id: 1,
    size_units: null,
    default_blueprint: null,
    places: [],
    feature: null,
    functionaries: [],
    ambient_counts: { lines: 0, emits: 0 },
    travel_hub: null,
    starting_bindings: [],
    occupant_count: 0,
    clues: [],
    clue_triggers: [],
    portal_anchors: [],
    desc_variants: [],
    ...overrides,
  };
}

const COMFORT: WorldBuilderComfort = { level: 2, points: 2, amenity: 0, axes: [] };

const EXIT: WorldBuilderExitDetail = {
  id: 10,
  name: 'north',
  to_room_id: 200,
  kind: 'door',
  is_open: true,
  aliases: ['n'],
};

function renderMarginalia(overrides: Partial<Parameters<typeof Marginalia>[0]> = {}) {
  const onOpenExit = vi.fn();
  const onAddExit = vi.fn();
  const onOpenArt = vi.fn();
  renderWithProviders(
    <Marginalia
      room={makeRoom()}
      exits={[EXIT]}
      comfort={COMFORT}
      cluesCount={0}
      clueTriggersCount={0}
      onOpenExit={onOpenExit}
      onAddExit={onAddExit}
      onOpenArt={onOpenArt}
      {...overrides}
    />
  );
  return { onOpenExit, onAddExit, onOpenArt };
}

describe('Marginalia', () => {
  it('renders every exit as a chip and opens the editor on click', async () => {
    const { onOpenExit } = renderMarginalia();
    const chip = screen.getByTestId('exit-chip-10');
    expect(chip).toHaveTextContent('north');
    await userEvent.click(chip);
    expect(onOpenExit).toHaveBeenCalledWith(EXIT);
  });

  it('marks a closed exit and a window exit distinctly', () => {
    renderMarginalia({
      exits: [
        { id: 11, name: 'window', to_room_id: null, kind: 'window', is_open: false, aliases: [] },
      ],
    });
    expect(screen.getByTestId('exit-chip-11')).toHaveTextContent('window ⊞ ⊘');
  });

  it('the ⊕ affordance fires onAddExit', async () => {
    const { onAddExit } = renderMarginalia();
    await userEvent.click(screen.getByTestId('add-exit-button'));
    expect(onAddExit).toHaveBeenCalled();
  });

  it('shows Ownership with honest "not tracked yet" for deed/tenants and the real listing', () => {
    renderMarginalia({ room: makeRoom({ is_public: false }) });
    const panel = screen.getByTestId('marginalia-panel-ownership');
    expect(panel).toHaveTextContent('not tracked yet');
    expect(panel).toHaveTextContent('private');
  });

  it('shows People as a read-only functionary list', () => {
    renderMarginalia({ room: makeRoom({ functionaries: ['Doorward Essa (greeter)'] }) });
    expect(screen.getByTestId('marginalia-panel-people')).toHaveTextContent('Doorward Essa');
  });

  it('shows Ambience counts and comfort — no editor affordance (T7 builds it)', () => {
    renderMarginalia({ room: makeRoom({ ambient_counts: { lines: 2, emits: 1 } }) });
    const panel = screen.getByTestId('marginalia-panel-ambience');
    expect(panel).toHaveTextContent('2');
    expect(panel).toHaveTextContent('1');
    expect(panel).toHaveTextContent('level 2');
  });

  it('shows Places & Things with the feature slot', () => {
    renderMarginalia({
      room: makeRoom({
        places: [{ id: 1, name: 'the hearth', description: '' }],
        feature: { kind: 'LAB', level: 2 },
      }),
    });
    const panel = screen.getByTestId('marginalia-panel-places-things');
    expect(panel).toHaveTextContent('the hearth');
    expect(panel).toHaveTextContent('LAB · level 2');
  });

  it('shows Law & Danger stats when present, else "not tracked yet"', () => {
    renderMarginalia({
      room: makeRoom({
        stats: [
          { key: 'crime', label: 'Crime', default: 0, effective: 3, authored: null, pinned: null },
        ],
      }),
    });
    expect(screen.getByTestId('marginalia-panel-law-danger')).toHaveTextContent('3');
  });

  it('shows Secrets & Story counts', () => {
    renderMarginalia({ cluesCount: 2, clueTriggersCount: 1 });
    const panel = screen.getByTestId('marginalia-panel-secrets-story');
    expect(panel).toHaveTextContent('2');
    expect(panel).toHaveTextContent('1');
  });

  it('shows "unresonant ground" when no resonance stat is in the payload', () => {
    renderMarginalia();
    expect(screen.getByTestId('marginalia-panel-resonance')).toHaveTextContent('unresonant ground');
  });

  it('shows a resonance stat when the payload carries one', () => {
    renderMarginalia({
      room: makeRoom({
        stats: [
          {
            key: 'resonance_hope',
            label: 'Hope',
            default: 0,
            effective: 4,
            authored: null,
            pinned: null,
          },
        ],
      }),
    });
    const panel = screen.getByTestId('marginalia-panel-resonance');
    expect(panel).toHaveTextContent('Hope');
    expect(panel).toHaveTextContent('4');
    expect(panel).not.toHaveTextContent('unresonant ground');
  });

  it('the Art panel shows resolved art and its door fires onOpenArt (#3535)', async () => {
    const { onOpenArt } = renderMarginalia({
      room: makeRoom({ art_url: 'https://img.example/ward.png' }),
    });
    expect(screen.getByTestId('marginalia-art')).toHaveAttribute(
      'src',
      'https://img.example/ward.png'
    );
    await userEvent.click(screen.getByTestId('open-art-button'));
    expect(onOpenArt).toHaveBeenCalled();
  });

  it('bare walls read honestly when nothing resolves (#3535)', () => {
    renderMarginalia({ room: makeRoom({ art_url: null }) });
    expect(screen.getByText('bare walls')).toBeInTheDocument();
  });
});
