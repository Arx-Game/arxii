import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi } from 'vitest';
import { PersonalizationPanel } from '../../../components/gift/PersonalizationPanel';
import { createMockDraft, mockCGExplanations, mockPersonalizationOptions } from '../../fixtures';
import { renderWithCharacterCreationProviders } from '../../testUtils';

const mutate = vi.fn();
vi.mock('../../../queries', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../../queries')>()),
  useUpdateDraft: () => ({ mutate, mutateAsync: vi.fn() }),
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
  beforeEach(() => mutate.mockReset());

  it('renders every line from authored copy, never a literal', () => {
    renderWithCharacterCreationProviders(
      <PersonalizationPanel
        draft={draftWith()}
        options={mockPersonalizationOptions}
        copy={mockCGExplanations}
      />
    );
    expect(screen.getByText(mockCGExplanations.personalize_heading)).toBeInTheDocument();
    expect(screen.getByText(mockCGExplanations.personalize_price_gloss)).toBeInTheDocument();
  });

  it('shows each option with its own cost and mechanics', () => {
    renderWithCharacterCreationProviders(
      <PersonalizationPanel
        draft={draftWith()}
        options={mockPersonalizationOptions}
        copy={mockCGExplanations}
      />
    );
    const price = screen.getByRole('button', { name: /Frost on the skin/ });
    expect(price).toHaveTextContent('+4 power');
    expect(price).toHaveTextContent('1');
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
    await user.click(screen.getByRole('button', { name: /Frost on the skin/ }));
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
});
