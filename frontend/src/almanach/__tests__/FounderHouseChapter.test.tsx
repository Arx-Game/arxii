/**
 * FounderHouseChapter (#3983 Plan B Task 5, plate F-II) — name validated
 * live against the template's `name_pattern`, the styled-name gloss
 * updating as the founder types, the Quiddity's single-pick toggle
 * (`max_picks: 1` replaces rather than adds), and a principle axis's range
 * input windowed to the template's own min/max.
 */
import { useState } from 'react';
import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi } from 'vitest';

import type { HouseTemplateOption } from '@/character-creation/api';
import { renderWithProviders } from '@/test/utils/renderWithProviders';
import { FounderHouseChapter } from '../founder/FounderHouseChapter';
import type { FounderDraft, UseFounderDraftResult } from '../founder/founderDraft';

vi.mock('../queries', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../queries')>();
  return {
    ...actual,
    useCharter: () => ({
      data: {
        succession_law: { name: 'Infernal Enatic', codex_entry_id: 7 },
        particle: { born: 'za', taken_in: 'zas' },
        quiddity_prompt: 'Which virtue rules the house?',
        capital_name: 'Perdition',
      },
    }),
  };
});

function baseDraft(): FounderDraft {
  return {
    realm_id: 1,
    title_id: 12,
    template_id: 3,
    house_name: '',
    words: '',
    colors: '',
    sigil_description: '',
    backstory: '',
    aspect_picks: {},
    principles: {},
    founder_relation: 'child',
    founder_is_heir: true,
    kin: [],
    lands: {},
    estate_name: '',
    estate_description: '',
  };
}

function template(overrides: Partial<HouseTemplateOption> = {}): HouseTemplateOption {
  return {
    id: 3,
    name: 'Ducal Charter',
    kind: 1,
    name_pattern: '[A-Z][a-z]+',
    // Only mercy carries an authored window — every other axis falls back
    // to the full -5..5 span (asserted below).
    mercy_min: -2,
    mercy_max: 3,
    aspect_definitions: [
      {
        id: 1,
        name: 'House Quiddity',
        prompt: 'What drives your house?',
        min_picks: 1,
        max_picks: 1,
        options: [
          {
            id: 10,
            name: 'The Veiled',
            description: 'Deception as a way of life.',
            codex_entry_id: 4,
          },
          { id: 11, name: 'Glamour', description: 'Grandeur is the house due.', codex_entry_id: 5 },
        ],
      },
    ],
    features: [],
    holdings: [],
    default_succession_law: { name: 'Infernal Enatic', codex_entry_id: 7 },
    ...overrides,
  } as HouseTemplateOption;
}

/** A small stateful harness — `FounderHouseChapter` is fully controlled by
 * `draft`/`set`, so the styled-name gloss only "updates as typed" when the
 * caller actually re-renders with the patched draft, exactly as the real
 * `useFounderDraft` hook would. */
function Harness({ initial, tpl }: { initial: FounderDraft; tpl: HouseTemplateOption }) {
  const [draft, setDraft] = useState(initial);
  const set: UseFounderDraftResult['set'] = (key, value) =>
    setDraft((prev) => ({ ...prev, [key]: value }));
  return (
    <FounderHouseChapter
      draft={draft}
      set={set}
      template={tpl}
      seatName="Fervor"
      seatTier="duchy"
      realmId={1}
      youName="Given name"
      onNext={() => {}}
    />
  );
}

test('a name failing the pattern shows the chip and the styled name updates as typed', async () => {
  const { container } = renderWithProviders(<Harness initial={baseDraft()} tpl={template()} />);
  // The `.tip` button's OWN text node (its first child) is the live styled
  // name; its nested `.bub` carries the separate gloss text, so a plain
  // `getByText` match against the button's full (concatenated) textContent
  // would never equal just the styled name.
  const styledName = () => container.querySelector('.tip')?.firstChild?.textContent;

  const nameInput = screen.getByLabelText('name');
  await userEvent.type(nameInput, 'candela');

  // Lowercase fails `[A-Z][a-z]+`'s full-match anchor — the chip appears,
  // but the styled-name gloss still reflects exactly what was typed (it
  // previews the reading, it doesn't gate on validity).
  expect(screen.getByText("does not fit the realm's rule")).toBeInTheDocument();
  expect(styledName()).toBe('Given name za candela');

  await userEvent.clear(nameInput);
  await userEvent.type(nameInput, 'Candela');

  expect(screen.queryByText("does not fit the realm's rule")).not.toBeInTheDocument();
  expect(styledName()).toBe('Given name za Candela');
});

test('choosing a second option under a max_picks: 1 definition replaces the first', async () => {
  renderWithProviders(<Harness initial={baseDraft()} tpl={template()} />);

  const veiled = screen.getByRole('button', { name: /The Veiled/ });
  const glamour = screen.getByRole('button', { name: /Glamour/ });

  await userEvent.click(veiled);
  expect(veiled).toHaveAttribute('aria-pressed', 'true');
  expect(glamour).toHaveAttribute('aria-pressed', 'false');

  await userEvent.click(glamour);
  expect(veiled).toHaveAttribute('aria-pressed', 'false');
  expect(glamour).toHaveAttribute('aria-pressed', 'true');
});

test('the range for an axis with window [-2, 3] renders min=-2 max=3', () => {
  renderWithProviders(<Harness initial={baseDraft()} tpl={template()} />);

  const mercyRange = screen.getByRole('slider', { name: 'Ruthlessness to Compassion' });
  expect(mercyRange).toHaveAttribute('min', '-2');
  expect(mercyRange).toHaveAttribute('max', '3');

  // An axis with no authored window falls back to the full -5..5 span.
  const methodRange = screen.getByRole('slider', { name: 'Cunning to Honor' });
  expect(methodRange).toHaveAttribute('min', '-5');
  expect(methodRange).toHaveAttribute('max', '5');
});
