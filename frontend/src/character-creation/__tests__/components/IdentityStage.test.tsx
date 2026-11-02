/**
 * IdentityStage Component Tests
 *
 * Tests for name, concept, quote, and background fields.
 */

import { screen } from '@testing-library/react';
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
    // The first name is asked on the Origin leaf (#4874, ruled 2026-10-19); this stage
    // shows how the name renders and asks for nothing.
    it('shows the name as a line, never as a field', () => {
      const queryClient = createTestQueryClient();

      renderWithCharacterCreationProviders(<IdentityStage draft={mockCompleteDraft} />, {
        queryClient,
      });

      expect(screen.queryByLabelText(/first name/i)).toBeNull();
      expect(screen.getByTestId('identity-name')).toHaveTextContent('Testchar Valardin');
    });

    it('displays full name preview with family name', () => {
      const queryClient = createTestQueryClient();

      renderWithCharacterCreationProviders(<IdentityStage draft={mockCompleteDraft} />, {
        queryClient,
      });

      // The preview moved from an inline "Full name:" paragraph to the record
      // rail's "Name" row (#3630); the rail lists chosen values only.
      expect(screen.getByText('Name', { selector: 'dt' })).toBeInTheDocument();
      expect(screen.getAllByText('Testchar Valardin').length).toBeGreaterThan(0);
    });

    it('shows only first name when no family', () => {
      const queryClient = createTestQueryClient();
      const orphanDraft = createMockDraft({
        ...mockCompleteDraft,
        family: null,
      });

      renderWithCharacterCreationProviders(<IdentityStage draft={orphanDraft} />, { queryClient });

      expect(screen.getByTestId('identity-name')).toHaveTextContent('Testchar');
    });

    it('says where the name is asked when there is none yet', () => {
      const queryClient = createTestQueryClient();

      renderWithCharacterCreationProviders(<IdentityStage draft={mockDraftWithFamily} />, {
        queryClient,
      });

      expect(screen.getByTestId('identity-name')).toHaveTextContent(
        'No first name yet; it is asked on the first page.'
      );
      expect(screen.queryByText('Name', { selector: 'dt' })).toBeNull();
    });
  });

  it("has no personality field: the Actor's Sheet asks its questions instead (#3621)", () => {
    const queryClient = createTestQueryClient();

    renderWithCharacterCreationProviders(<IdentityStage draft={mockCompleteDraft} />, {
      queryClient,
    });

    expect(screen.queryByLabelText(/personality/i)).toBeNull();
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
    it('renders the writing fields on the field idiom and the name as a line and in the rail', () => {
      const queryClient = createTestQueryClient();
      const draft = createMockDraft({ draft_data: { first_name: 'Sharlotte' } });

      renderWithCharacterCreationProviders(<IdentityStage draft={draft} />, { queryClient });

      // Sentence case (#3630): interface chrome is plain, and only the first
      // word is capitalised. The other blocks in this file query the same
      // labels case-insensitively, so they are unaffected.
      for (const label of ['Character concept', 'Character quote']) {
        expect(screen.getByLabelText(label).closest('.field')).not.toBeNull();
      }
      // The first name is asked on the Origin leaf (#4874); here it is a line, not a field.
      expect(screen.queryByLabelText('First name')).toBeNull();
      expect(screen.getByTestId('identity-name')).toHaveTextContent('Sharlotte');
      expect(screen.getByRole('heading', { name: 'Your choices so far' })).toBeInTheDocument();
      expect(screen.getAllByText('Sharlotte').length).toBeGreaterThan(0);
    });
  });
});
