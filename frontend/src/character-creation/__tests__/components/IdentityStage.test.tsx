/**
 * IdentityStage Component Tests
 *
 * Tests for name, concept, quote, personality, and background fields.
 */

import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi } from 'vitest';
import { IdentityStage } from '../../components/IdentityStage';
import {
  mockCGExplanations,
  mockDraftWithFamily,
  mockCompleteDraft,
  createMockDraft,
} from '../fixtures';
import {
  renderWithCharacterCreationProviders,
  createTestQueryClient,
  seedQueryData,
} from '../testUtils';
import { characterCreationKeys } from '../../queries';

// Mock the API module
vi.mock('../../api', () => ({
  updateDraft: vi.fn(),
  getCGExplanations: vi.fn(),
  getWorshippedBeings: vi.fn().mockResolvedValue([]),
}));

describe('IdentityStage', () => {
  describe('Character Name Section', () => {
    it('displays first name input field', () => {
      const queryClient = createTestQueryClient();

      renderWithCharacterCreationProviders(<IdentityStage draft={mockDraftWithFamily} />, {
        queryClient,
      });

      expect(screen.getByLabelText(/first name/i)).toBeInTheDocument();
    });

    it('shows current first name value', () => {
      const queryClient = createTestQueryClient();

      renderWithCharacterCreationProviders(<IdentityStage draft={mockCompleteDraft} />, {
        queryClient,
      });

      const input = screen.getByLabelText(/first name/i) as HTMLInputElement;
      expect(input.value).toBe('Testchar');
    });

    it('displays full name preview with family name', () => {
      const queryClient = createTestQueryClient();

      renderWithCharacterCreationProviders(<IdentityStage draft={mockCompleteDraft} />, {
        queryClient,
      });

      // The preview moved from an inline "Full name:" paragraph to the record
      // rail's "Name" row (#3630); the rail lists chosen values only.
      expect(screen.getByText('Name', { selector: 'dt' })).toBeInTheDocument();
      expect(screen.getByText('Testchar Valardin')).toBeInTheDocument();
    });

    it('shows only first name when no family', () => {
      const queryClient = createTestQueryClient();
      const orphanDraft = createMockDraft({
        ...mockCompleteDraft,
        family: null,
      });

      renderWithCharacterCreationProviders(<IdentityStage draft={orphanDraft} />, { queryClient });

      expect(screen.getByText('Testchar')).toBeInTheDocument();
    });

    it('displays character limit hint', () => {
      const queryClient = createTestQueryClient();

      renderWithCharacterCreationProviders(<IdentityStage draft={mockDraftWithFamily} />, {
        queryClient,
      });

      expect(screen.getByText(/2-20 characters/i)).toBeInTheDocument();
    });
  });

  describe('Personality Section', () => {
    it('displays personality textarea', () => {
      const queryClient = createTestQueryClient();

      renderWithCharacterCreationProviders(<IdentityStage draft={mockDraftWithFamily} />, {
        queryClient,
      });

      expect(screen.getByLabelText(/personality traits/i)).toBeInTheDocument();
    });

    it('shows current personality value', () => {
      const queryClient = createTestQueryClient();

      renderWithCharacterCreationProviders(<IdentityStage draft={mockCompleteDraft} />, {
        queryClient,
      });

      const textarea = screen.getByLabelText(/personality traits/i) as HTMLTextAreaElement;
      expect(textarea.value).toBe('Bold and adventurous.');
    });
  });

  describe('Concept Section', () => {
    it('displays concept input field', () => {
      const queryClient = createTestQueryClient();

      renderWithCharacterCreationProviders(<IdentityStage draft={mockDraftWithFamily} />, {
        queryClient,
      });

      expect(screen.getByLabelText(/character concept/i)).toBeInTheDocument();
    });

    it('shows current concept value', () => {
      const queryClient = createTestQueryClient();

      renderWithCharacterCreationProviders(<IdentityStage draft={mockCompleteDraft} />, {
        queryClient,
      });

      const input = screen.getByLabelText(/character concept/i) as HTMLInputElement;
      expect(input.value).toBe('A warrior seeking redemption.');
    });
  });

  describe('Quote Section', () => {
    it('displays quote input field', () => {
      const queryClient = createTestQueryClient();

      renderWithCharacterCreationProviders(<IdentityStage draft={mockDraftWithFamily} />, {
        queryClient,
      });

      expect(screen.getByLabelText(/character quote/i)).toBeInTheDocument();
    });

    it('shows current quote value', () => {
      const queryClient = createTestQueryClient();

      renderWithCharacterCreationProviders(<IdentityStage draft={mockCompleteDraft} />, {
        queryClient,
      });

      const input = screen.getByLabelText(/character quote/i) as HTMLInputElement;
      expect(input.value).toBe('The dawn comes for all.');
    });
  });

  describe('User Interaction', () => {
    it('allows typing in first name field', async () => {
      const user = userEvent.setup();
      const queryClient = createTestQueryClient();

      renderWithCharacterCreationProviders(<IdentityStage draft={mockDraftWithFamily} />, {
        queryClient,
      });

      const input = screen.getByLabelText(/first name/i);
      await user.clear(input);
      await user.type(input, 'NewName');

      // The input accepts typing (mutation will handle persistence)
      // We verify it's not disabled and accepts input
      expect(input).not.toBeDisabled();
    });
  });

  describe('Page Header', () => {
    it('displays stage title and description', () => {
      const queryClient = createTestQueryClient();
      seedQueryData(queryClient, characterCreationKeys.explanations(), mockCGExplanations);

      renderWithCharacterCreationProviders(<IdentityStage draft={mockDraftWithFamily} />, {
        queryClient,
      });

      expect(screen.getByText('Identity')).toBeInTheDocument();
      expect(screen.getByText(/define your character.*s name and story/i)).toBeInTheDocument();
    });
  });

  describe('Folio markup', () => {
    it('renders the four writing fields on the field idiom and the name in the rail', () => {
      const queryClient = createTestQueryClient();
      const draft = createMockDraft({ draft_data: { first_name: 'Sharlotte' } });

      renderWithCharacterCreationProviders(<IdentityStage draft={draft} />, { queryClient });

      // Sentence case (#3630): interface chrome is plain, and only the first
      // word is capitalised. The other blocks in this file query the same
      // labels case-insensitively, so they are unaffected.
      for (const label of [
        'First name',
        'Character concept',
        'Character quote',
        'Personality traits',
      ]) {
        expect(screen.getByLabelText(label).closest('.field')).not.toBeNull();
      }
      expect(screen.getByRole('heading', { name: 'Your choices so far' })).toBeInTheDocument();
      expect(screen.getByText('Sharlotte')).toBeInTheDocument();
    });
  });
});
