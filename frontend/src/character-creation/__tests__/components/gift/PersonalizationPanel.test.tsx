import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi } from 'vitest';
import {
  PersonalizationPanel,
  sanitizeCustomDescription,
  sanitizeCustomName,
} from '../../../components/gift/PersonalizationPanel';
import { createMockDraft, mockCGExplanations, mockPersonalizationOptions } from '../../fixtures';
import { renderWithCharacterCreationProviders } from '../../testUtils';

const mutate = vi.fn();
let mockIsError = false;
vi.mock('../../../queries', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../../queries')>()),
  useUpdateDraft: () => ({ mutate, mutateAsync: vi.fn(), isError: mockIsError }),
}));

function draftWith(pick = {}) {
  return createMockDraft({
    draft_data: {
      selected_technique_ids: [mockPersonalizationOptions.technique_id],
      technique_personalizations: { [String(mockPersonalizationOptions.technique_id)]: pick },
    },
  });
}

describe('PersonalizationPanel', () => {
  beforeEach(() => {
    mutate.mockReset();
    mockIsError = false;
  });

  it('renders every line from authored copy, never a literal', async () => {
    const user = userEvent.setup();
    renderWithCharacterCreationProviders(
      <PersonalizationPanel
        draft={draftWith()}
        options={mockPersonalizationOptions}
        copy={mockCGExplanations}
      />
    );
    expect(screen.getByText(mockCGExplanations.personalize_heading)).toBeInTheDocument();
    // The gloss line is inside the price section's expanded body.
    await user.click(screen.getByTestId('personalize-summary-price'));
    expect(screen.getByText(mockCGExplanations.personalize_price_gloss)).toBeInTheDocument();
  });

  it('shows each option with its own cost and mechanics', async () => {
    const user = userEvent.setup();
    renderWithCharacterCreationProviders(
      <PersonalizationPanel
        draft={draftWith()}
        options={mockPersonalizationOptions}
        copy={mockCGExplanations}
      />
    );
    await user.click(screen.getByTestId('personalize-summary-price'));
    const price = screen.getByRole('button', { name: /Frost on the skin/ });
    expect(price).toHaveTextContent('+4 power');
    expect(price).toHaveTextContent('1 pt');
    // The demo's Screen 3 rows carry no "level N" segment.
    expect(price).not.toHaveTextContent(/level/i);

    await user.click(screen.getByTestId('personalize-summary-flourish'));
    const flourish = screen.getByRole('button', {
      name: /A chill rides your voice when you cast/,
    });
    expect(flourish).toHaveTextContent('3 pts');
    expect(flourish).not.toHaveTextContent(/level/i);
  });

  it('pressing a price writes it to the draft, pressing again clears it', async () => {
    const user = userEvent.setup();
    const id = String(mockPersonalizationOptions.technique_id);
    const priceId = mockPersonalizationOptions.prices[0].id;
    const { rerender } = renderWithCharacterCreationProviders(
      <PersonalizationPanel
        draft={draftWith()}
        options={mockPersonalizationOptions}
        copy={mockCGExplanations}
      />
    );
    await user.click(screen.getByTestId('personalize-summary-price'));
    await user.click(screen.getByRole('button', { name: /Frost on the skin/ }));
    expect(mutate.mock.calls[0][0].data.draft_data.technique_personalizations[id].price_id).toBe(
      priceId
    );
    rerender(
      <PersonalizationPanel
        draft={draftWith({ price_id: priceId })}
        options={mockPersonalizationOptions}
        copy={mockCGExplanations}
      />
    );
    // The price section's open/closed state is local component state, which
    // `rerender` on the same instance preserves — it is already open from the
    // click above, so no second toggle click here. The summary row's own
    // collapsed label now ALSO reads "Frost on the skin" (it is the current
    // pick), so disambiguate by `aria-pressed` — only the real stance button
    // (inside the expanded picker) carries it; the summary button carries
    // `aria-expanded` instead.
    const pricedStance = screen
      .getAllByRole('button', { name: /Frost on the skin/ })
      .find((button) => button.hasAttribute('aria-pressed'));
    if (!pricedStance) throw new Error('expected a pressed price stance button');
    await user.click(pricedStance);
    expect(
      mutate.mock.calls[1][0].data.draft_data.technique_personalizations[id].price_id
    ).toBeNull();
  });

  it('saves the name on blur', async () => {
    const user = userEvent.setup();
    renderWithCharacterCreationProviders(
      <PersonalizationPanel
        draft={draftWith()}
        options={mockPersonalizationOptions}
        copy={mockCGExplanations}
      />
    );
    await user.click(screen.getByTestId('personalize-summary-name'));
    const input = screen.getByLabelText(mockCGExplanations.personalize_name_label);
    await user.type(input, 'Winterbite');
    await user.tab();
    const id = String(mockPersonalizationOptions.technique_id);
    expect(
      mutate.mock.lastCall?.[0].data.draft_data.technique_personalizations[id].custom_name
    ).toBe('Winterbite');
  });

  it('asks for a resonance before flourishes and forms', () => {
    renderWithCharacterCreationProviders(
      <PersonalizationPanel
        draft={draftWith()}
        options={{
          ...mockPersonalizationOptions,
          needs_resonance: true,
          flourishes: [],
          forms: [],
        }}
        copy={mockCGExplanations}
      />
    );
    expect(screen.getByText(mockCGExplanations.personalize_needs_resonance)).toBeInTheDocument();
  });

  it('shows the sync-error hint when the save mutation errors', () => {
    mockIsError = true;
    renderWithCharacterCreationProviders(
      <PersonalizationPanel
        draft={draftWith()}
        options={mockPersonalizationOptions}
        copy={mockCGExplanations}
      />
    );
    expect(screen.getByText('That pick did not save. Try again.')).toBeInTheDocument();
  });

  it('does not show the sync-error hint when the mutation has not errored', () => {
    renderWithCharacterCreationProviders(
      <PersonalizationPanel
        draft={draftWith()}
        options={mockPersonalizationOptions}
        copy={mockCGExplanations}
      />
    );
    expect(screen.queryByText('That pick did not save. Try again.')).not.toBeInTheDocument();
  });
});

describe('PersonalizationPanel collapsed summary rows (#4099 demo-fidelity fix)', () => {
  beforeEach(() => {
    mutate.mockReset();
    mockIsError = false;
  });

  it('starts every section collapsed, with no picker content visible', () => {
    renderWithCharacterCreationProviders(
      <PersonalizationPanel
        draft={draftWith()}
        options={mockPersonalizationOptions}
        copy={mockCGExplanations}
      />
    );
    for (const sectionKey of ['name', 'flourish', 'form', 'price']) {
      expect(screen.getByTestId(`personalize-summary-${sectionKey}`)).toHaveAttribute(
        'aria-expanded',
        'false'
      );
    }
    expect(screen.queryByLabelText(mockCGExplanations.personalize_name_label)).toBeNull();
    expect(screen.queryByRole('button', { name: /Frost on the skin/ })).not.toBeInTheDocument();
  });

  it('a collapsed row with no pick shows the "none chosen" copy key, no cost chip', () => {
    renderWithCharacterCreationProviders(
      <PersonalizationPanel
        draft={draftWith()}
        options={mockPersonalizationOptions}
        copy={mockCGExplanations}
      />
    );
    const priceSummary = screen.getByTestId('personalize-summary-price');
    expect(priceSummary).toHaveTextContent(mockCGExplanations.personalize_summary_none);
    expect(priceSummary.querySelector('.cost')).toBeNull();
  });

  it('clicking a collapsed row expands it, exposing the existing picker', async () => {
    const user = userEvent.setup();
    renderWithCharacterCreationProviders(
      <PersonalizationPanel
        draft={draftWith()}
        options={mockPersonalizationOptions}
        copy={mockCGExplanations}
      />
    );
    const priceSummary = screen.getByTestId('personalize-summary-price');
    await user.click(priceSummary);
    expect(priceSummary).toHaveAttribute('aria-expanded', 'true');
    expect(screen.getByRole('button', { name: /Frost on the skin/ })).toBeInTheDocument();
  });

  it('a collapsed row with an existing pick shows that pick and its own cost', () => {
    const priceId = mockPersonalizationOptions.prices[0].id;
    renderWithCharacterCreationProviders(
      <PersonalizationPanel
        draft={draftWith({ price_id: priceId })}
        options={mockPersonalizationOptions}
        copy={mockCGExplanations}
      />
    );
    const priceSummary = screen.getByTestId('personalize-summary-price');
    // Collapsed by default, but already showing the current pick.
    expect(priceSummary).toHaveAttribute('aria-expanded', 'false');
    expect(priceSummary).toHaveTextContent('Frost on the skin');
    expect(priceSummary).toHaveTextContent('1 pt');
  });
});

describe('sanitizeCustomName', () => {
  it('replaces an em dash and an en dash with a plain hyphen', () => {
    expect(sanitizeCustomName('Winter—bite')).toBe('Winter-bite');
    expect(sanitizeCustomName('Winter–bite')).toBe('Winter-bite');
  });

  it('strips the telnet markup character', () => {
    expect(sanitizeCustomName('Scorch|Lash')).toBe('ScorchLash');
  });

  it('strips control characters, including a newline (a name is single-line)', () => {
    expect(sanitizeCustomName('Scorch\nLash\x07')).toBe('ScorchLash');
  });

  it('leaves an already-clean name untouched', () => {
    expect(sanitizeCustomName('Winterbite')).toBe('Winterbite');
  });
});

describe('sanitizeCustomDescription', () => {
  it('keeps newlines (paragraph breaks are allowed)', () => {
    expect(sanitizeCustomDescription('Line one\nLine two')).toBe('Line one\nLine two');
  });

  it('strips other control characters', () => {
    expect(sanitizeCustomDescription('Cold\x07 to the touch')).toBe('Cold to the touch');
  });

  it('does not touch dashes (the dash rule is name-only)', () => {
    expect(sanitizeCustomDescription('Flame gutters—then nothing.')).toBe(
      'Flame gutters—then nothing.'
    );
  });
});
