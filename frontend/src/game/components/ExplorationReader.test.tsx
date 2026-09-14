import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { ExplorationReader } from './ExplorationReader';

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

  it('renders confirmed room facts and ambient poses as separate entries', () => {
    render(
      <ExplorationReader
        room={room}
        ambientInteractions={[
          {
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
          },
        ]}
      />
    );
    expect(screen.getByRole('heading', { name: 'Quiet courtyard' })).toBeInTheDocument();
    expect(screen.getByText('Rain rests on the stones.')).toBeInTheDocument();
    expect(screen.getByText('A bell sounds beyond the wall.')).toBeInTheDocument();
    expect(screen.getByText('Mara')).toBeInTheDocument();
  });

  it('renders notes among the ambient poses at their time, not in a section of their own (#3856)', () => {
    render(
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
