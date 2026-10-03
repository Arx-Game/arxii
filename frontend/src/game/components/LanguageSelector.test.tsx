/**
 * LanguageSelector (#4090): the composer picker lists trained languages
 * only. A condition can raise comprehension of a tongue the character never
 * speaks (`fluency` stays 0), and that row must not appear as something to
 * speak.
 */
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { LanguageSelector } from './LanguageSelector';
import type { MyLanguage } from '@/species/types';

const rows: MyLanguage[] = [];

vi.mock('@/hooks/useGameSocket', () => ({ useGameSocket: () => ({ send: vi.fn() }) }));
vi.mock('@/species/queries', () => ({
  useMyLanguages: () => ({ data: rows }),
  speciesKeys: { myLanguages: () => ['species', 'my-languages'] },
}));

function row(overrides: Partial<MyLanguage>): MyLanguage {
  return {
    language_id: 1,
    name: 'Common',
    fluency: 80,
    band: 'fluent',
    is_current: false,
    effective_fluency: 80,
    effective_band: 'fluent',
    temporary_sources: [],
    ...overrides,
  };
}

describe('LanguageSelector', () => {
  it('lists the trained row and drops the condition-only row', async () => {
    rows.splice(
      0,
      rows.length,
      row({ language_id: 1, name: 'Arvani', fluency: 50 }),
      row({ language_id: 2, name: 'Tongue A', fluency: 0, temporary_sources: ['X'] })
    );
    // Radix leaves `pointer-events: none` on the body while the menu is open.
    const user = userEvent.setup({ pointerEventsCheck: 0 });
    render(<LanguageSelector character="Wren" />);
    await user.click(screen.getByRole('button', { name: 'Change spoken language' }));
    expect(screen.getByRole('menuitem', { name: /Arvani/ })).toBeInTheDocument();
    expect(screen.queryByRole('menuitem', { name: /Tongue A/ })).not.toBeInTheDocument();
  });
});
