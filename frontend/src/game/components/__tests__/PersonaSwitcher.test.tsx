import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import type { SwitchablePersona } from '../../personaQueries';
import { PersonaSwitcher } from '../PersonaSwitcher';

const { state, mutate } = vi.hoisted(() => ({
  state: { personas: [] as SwitchablePersona[] },
  mutate: vi.fn(),
}));

vi.mock('../../personaQueries', () => ({
  useCharacterPersonasQuery: () => ({ data: state.personas }),
  useSetActivePersonaMutation: () => ({ mutate, isPending: false }),
  useSetPersonaProfileMutation: () => ({
    mutate: vi.fn(),
    reset: vi.fn(),
    isPending: false,
    isError: false,
    error: null,
  }),
}));

function persona(
  id: number,
  name: string,
  type: SwitchablePersona['persona_type']
): SwitchablePersona {
  return {
    id,
    name,
    persona_type: type,
    is_fake_name: type === 'temporary',
    thumbnail_url: null,
    thumbnail_media_url: null,
    guise_concept: '',
    guise_quote: '',
    guise_personality: '',
    guise_background: '',
  };
}

describe('PersonaSwitcher', () => {
  it('shows the worn face when more than one identity exists', () => {
    state.personas = [
      persona(1, 'Bob the Great', 'primary'),
      persona(2, 'Robert DVile', 'established'),
    ];
    render(<PersonaSwitcher characterSheetId={1} activePersonaId={2} />);
    expect(screen.getByText('Robert DVile')).toBeInTheDocument();
  });

  it('renders just the name (no switcher) for a single identity', () => {
    state.personas = [persona(1, 'Bob the Great', 'primary')];
    render(<PersonaSwitcher characterSheetId={1} activePersonaId={1} />);
    expect(screen.getByText('Bob the Great')).toBeInTheDocument();
    expect(screen.queryByTitle(/Switch which identity/)).not.toBeInTheDocument();
  });
});
