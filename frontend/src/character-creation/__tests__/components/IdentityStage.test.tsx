/**
 * IdentityStage Component Tests
 *
 * Tests for name, personality, and background fields.
 * (Description moved to AppearanceStage)
 */

import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi } from 'vitest';
import { IdentityStage } from '../../components/IdentityStage';
import { mockDraftWithFamily, mockCompleteDraft, createMockDraft } from '../fixtures';
import { renderWithCharacterCreationProviders, createTestQueryClient } from '../testUtils';

// Mock the API module
vi.mock('../../api', () => ({
  updateDraft: vi.fn(),
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

      expect(screen.getByText(/full name:/i)).toBeInTheDocument();
      expect(screen.getByText('Testchar Valardin')).toBeInTheDocument();
    });

    it('shows only first name when no family', () => {
      const queryClient = createTestQueryClient();
      const orphanDraft = createMockDraft({
        ...mockCompleteDraft,
        is_orphan: true,
        family: null,
        selected_heritage: null,
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

  describe('Background Section', () => {
    it('displays background textarea', () => {
      const queryClient = createTestQueryClient();

      renderWithCharacterCreationProviders(<IdentityStage draft={mockDraftWithFamily} />, {
        queryClient,
      });

      expect(screen.getByLabelText(/character history/i)).toBeInTheDocument();
    });

    it('shows current background value', () => {
      const queryClient = createTestQueryClient();

      renderWithCharacterCreationProviders(<IdentityStage draft={mockCompleteDraft} />, {
        queryClient,
      });

      const textarea = screen.getByLabelText(/character history/i) as HTMLTextAreaElement;
      expect(textarea.value).toBe('Born to humble origins but destined for greatness.');
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

      renderWithCharacterCreationProviders(<IdentityStage draft={mockDraftWithFamily} />, {
        queryClient,
      });

      expect(screen.getByText('Identity')).toBeInTheDocument();
      expect(screen.getByText(/define your character's name and story/i)).toBeInTheDocument();
    });
  });
});
