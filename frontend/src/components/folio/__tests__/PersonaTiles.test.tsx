/**
 * PersonaTiles (#3412 folio primitive) — small squared tabs beneath a
 * portrait, one per persona the character can wear (ruled: renders nothing
 * for a single-persona character). Driven by the existing
 * `useCharacterPersonasQuery`/`useSetActivePersonaMutation` — same mocking
 * technique as `PersonaSwitcher.test.tsx`/`SelectedCharacterChip.test.tsx`.
 */
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import type { SwitchablePersona } from '@/game/personaQueries';
import { PersonaTiles } from '../PersonaTiles';

const { state, mutate } = vi.hoisted(() => ({
  state: { personas: [] as SwitchablePersona[] },
  mutate: vi.fn(),
}));

vi.mock('@/game/personaQueries', () => ({
  useCharacterPersonasQuery: () => ({ data: state.personas }),
  useSetActivePersonaMutation: () => ({ mutate, isPending: false }),
}));

function persona(
  id: number,
  name: string,
  thumbnailMediaUrl: string | null = null
): SwitchablePersona {
  return {
    id,
    name,
    persona_type: 'established',
    is_fake_name: false,
    thumbnail_url: null,
    thumbnail_media_url: thumbnailMediaUrl,
    guise_concept: '',
    guise_quote: '',
    guise_personality: '',
    guise_background: '',
  };
}

describe('PersonaTiles', () => {
  it('renders nothing for a single-persona character', () => {
    state.personas = [persona(1, 'Aria')];

    const { container } = render(<PersonaTiles characterSheetId={42} activePersonaId={1} />);

    expect(container).toBeEmptyDOMElement();
  });

  it('renders a square tab per persona, highlighting the active one', () => {
    state.personas = [persona(1, 'Aria'), persona(2, 'The Veiled Lady')];

    render(<PersonaTiles characterSheetId={42} activePersonaId={1} />);

    const tabs = screen.getAllByRole('tab');
    expect(tabs).toHaveLength(2);
    expect(tabs[0]).toHaveAttribute('aria-selected', 'true');
    expect(tabs[0].className).toContain('border-primary');
    expect(tabs[1]).toHaveAttribute('aria-selected', 'false');
    expect(tabs[1].className).not.toContain('border-primary');
    // No radius on the tiles, per the squared-geometry law.
    expect(tabs[0].className).toContain('rounded-none');
  });

  it('shows the thumbnail when present, else the name (never initials-only)', () => {
    state.personas = [persona(1, 'Aria', 'https://example.com/aria.png'), persona(2, 'Masked')];

    const { container } = render(<PersonaTiles characterSheetId={42} activePersonaId={1} />);

    // Decorative thumbnail (alt="") resolves to role "presentation", not "img".
    expect(container.querySelector('img')).toHaveAttribute('src', 'https://example.com/aria.png');
    expect(screen.getByText('Masked')).toBeInTheDocument();
  });

  it('selecting an inactive tile calls the existing set-active-persona mutation', async () => {
    state.personas = [persona(1, 'Aria'), persona(2, 'The Veiled Lady')];
    const user = userEvent.setup();

    render(<PersonaTiles characterSheetId={42} activePersonaId={1} />);

    await user.click(screen.getByTitle('Switch to The Veiled Lady'));

    expect(mutate).toHaveBeenCalledWith(2);
  });

  it('tiles are real buttons, reachable and focusable by keyboard', async () => {
    state.personas = [persona(1, 'Aria'), persona(2, 'The Veiled Lady')];
    const user = userEvent.setup();

    render(<PersonaTiles characterSheetId={42} activePersonaId={1} />);

    await user.tab();

    expect(document.activeElement).toBe(screen.getByTitle('Aria (currently worn)'));
  });
});
