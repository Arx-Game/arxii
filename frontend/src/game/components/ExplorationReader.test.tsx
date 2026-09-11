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
});
