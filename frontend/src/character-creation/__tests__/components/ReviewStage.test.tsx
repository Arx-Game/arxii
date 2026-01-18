/**
 * ReviewStage Component Tests
 *
 * Tests for the final review stage, including validation, submission,
 * and staff-only "Add to Roster" functionality.
 */

import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi } from 'vitest';
import { ReviewStage } from '../../components/ReviewStage';
import { mockCompleteDraft, mockIncompleteDraft, createMockDraft } from '../fixtures';
import { mockPlayerAccount, mockStaffAccount } from '../mocks';
import { renderWithCharacterCreationProviders, createTestQueryClient } from '../testUtils';
import { Stage } from '../../types';

// Mock the API module
vi.mock('../../api', () => ({
  submitDraft: vi.fn(),
  addToRoster: vi.fn(),
}));

describe('ReviewStage', () => {
  const mockOnStageSelect = vi.fn();

  beforeEach(() => {
    mockOnStageSelect.mockClear();
  });

  describe('Character Preview', () => {
    it('displays character full name', () => {
      const queryClient = createTestQueryClient();

      renderWithCharacterCreationProviders(
        <ReviewStage draft={mockCompleteDraft} isStaff={false} onStageSelect={mockOnStageSelect} />,
        { queryClient }
      );

      expect(screen.getByText('Testchar Valardin')).toBeInTheDocument();
    });

    it('displays homeland', () => {
      const queryClient = createTestQueryClient();

      renderWithCharacterCreationProviders(
        <ReviewStage draft={mockCompleteDraft} isStaff={false} onStageSelect={mockOnStageSelect} />,
        { queryClient }
      );

      expect(screen.getByText('Arx City')).toBeInTheDocument();
    });

    it('displays heritage type', () => {
      const queryClient = createTestQueryClient();

      renderWithCharacterCreationProviders(
        <ReviewStage draft={mockCompleteDraft} isStaff={false} onStageSelect={mockOnStageSelect} />,
        { queryClient }
      );

      expect(screen.getByText('Normal Upbringing')).toBeInTheDocument();
    });

    it('displays species', () => {
      const queryClient = createTestQueryClient();

      renderWithCharacterCreationProviders(
        <ReviewStage draft={mockCompleteDraft} isStaff={false} onStageSelect={mockOnStageSelect} />,
        { queryClient }
      );

      // mockCompleteDraft has mockSpeciesElf
      expect(screen.getByText('Elf')).toBeInTheDocument();
    });

    it('displays gender', () => {
      const queryClient = createTestQueryClient();

      renderWithCharacterCreationProviders(
        <ReviewStage draft={mockCompleteDraft} isStaff={false} onStageSelect={mockOnStageSelect} />,
        { queryClient }
      );

      expect(screen.getByText('Female')).toBeInTheDocument();
    });

    it('displays description when provided', () => {
      const queryClient = createTestQueryClient();

      renderWithCharacterCreationProviders(
        <ReviewStage draft={mockCompleteDraft} isStaff={false} onStageSelect={mockOnStageSelect} />,
        { queryClient }
      );

      expect(screen.getByText('A tall figure with piercing eyes.')).toBeInTheDocument();
    });

    it('displays personality when provided', () => {
      const queryClient = createTestQueryClient();

      renderWithCharacterCreationProviders(
        <ReviewStage draft={mockCompleteDraft} isStaff={false} onStageSelect={mockOnStageSelect} />,
        { queryClient }
      );

      expect(screen.getByText('Bold and adventurous.')).toBeInTheDocument();
    });

    it('displays background when provided', () => {
      const queryClient = createTestQueryClient();

      renderWithCharacterCreationProviders(
        <ReviewStage draft={mockCompleteDraft} isStaff={false} onStageSelect={mockOnStageSelect} />,
        { queryClient }
      );

      expect(
        screen.getByText('Born to humble origins but destined for greatness.')
      ).toBeInTheDocument();
    });

    it('shows orphan status when applicable', () => {
      const queryClient = createTestQueryClient();
      const orphanDraft = createMockDraft({
        ...mockCompleteDraft,
        is_orphan: true,
        family: null,
      });

      renderWithCharacterCreationProviders(
        <ReviewStage draft={orphanDraft} isStaff={false} onStageSelect={mockOnStageSelect} />,
        { queryClient }
      );

      expect(screen.getByText('Orphan / No Family')).toBeInTheDocument();
    });
  });

  describe('Validation Summary', () => {
    it('shows incomplete sections warning when stages are incomplete', () => {
      const queryClient = createTestQueryClient();

      renderWithCharacterCreationProviders(
        <ReviewStage
          draft={mockIncompleteDraft}
          isStaff={false}
          onStageSelect={mockOnStageSelect}
        />,
        { queryClient }
      );

      expect(screen.getByText('Incomplete Sections')).toBeInTheDocument();
      expect(
        screen.getByText(/please complete these sections before submitting/i)
      ).toBeInTheDocument();
    });

    it('lists incomplete stages with links', () => {
      const queryClient = createTestQueryClient();

      renderWithCharacterCreationProviders(
        <ReviewStage
          draft={mockIncompleteDraft}
          isStaff={false}
          onStageSelect={mockOnStageSelect}
        />,
        { queryClient }
      );

      // Attributes and Traits are incomplete in mockIncompleteDraft
      expect(screen.getByText('Attributes')).toBeInTheDocument();
      expect(screen.getByText('Traits')).toBeInTheDocument();
    });

    it('navigates to incomplete stage when clicked', async () => {
      const user = userEvent.setup();
      const queryClient = createTestQueryClient();

      renderWithCharacterCreationProviders(
        <ReviewStage
          draft={mockIncompleteDraft}
          isStaff={false}
          onStageSelect={mockOnStageSelect}
        />,
        { queryClient }
      );

      const attributesLink = screen.getByText('Attributes');
      await user.click(attributesLink);

      expect(mockOnStageSelect).toHaveBeenCalledWith(Stage.ATTRIBUTES);
    });

    it('does not show validation warning when all stages complete', () => {
      const queryClient = createTestQueryClient();

      renderWithCharacterCreationProviders(
        <ReviewStage draft={mockCompleteDraft} isStaff={false} onStageSelect={mockOnStageSelect} />,
        { queryClient }
      );

      expect(screen.queryByText('Incomplete Sections')).not.toBeInTheDocument();
    });
  });

  describe('Submit Button - Player', () => {
    it('shows submit button for players', () => {
      const queryClient = createTestQueryClient();

      renderWithCharacterCreationProviders(
        <ReviewStage draft={mockCompleteDraft} isStaff={false} onStageSelect={mockOnStageSelect} />,
        { queryClient, account: mockPlayerAccount }
      );

      expect(screen.getByRole('button', { name: /submit for review/i })).toBeInTheDocument();
    });

    it('submit button is disabled when stages incomplete', () => {
      const queryClient = createTestQueryClient();

      renderWithCharacterCreationProviders(
        <ReviewStage
          draft={mockIncompleteDraft}
          isStaff={false}
          onStageSelect={mockOnStageSelect}
        />,
        { queryClient, account: mockPlayerAccount }
      );

      const submitButton = screen.getByRole('button', { name: /submit for review/i });
      expect(submitButton).toBeDisabled();
    });

    it('submit button is enabled when all stages complete', () => {
      const queryClient = createTestQueryClient();

      renderWithCharacterCreationProviders(
        <ReviewStage draft={mockCompleteDraft} isStaff={false} onStageSelect={mockOnStageSelect} />,
        { queryClient, account: mockPlayerAccount }
      );

      const submitButton = screen.getByRole('button', { name: /submit for review/i });
      expect(submitButton).not.toBeDisabled();
    });

    it('does not show "Add to Roster" button for regular players', () => {
      const queryClient = createTestQueryClient();

      renderWithCharacterCreationProviders(
        <ReviewStage draft={mockCompleteDraft} isStaff={false} onStageSelect={mockOnStageSelect} />,
        { queryClient, account: mockPlayerAccount }
      );

      expect(screen.queryByRole('button', { name: /add to roster/i })).not.toBeInTheDocument();
    });
  });

  describe('Staff-Only Features', () => {
    it('shows "Add to Roster" button for staff', () => {
      const queryClient = createTestQueryClient();

      renderWithCharacterCreationProviders(
        <ReviewStage draft={mockCompleteDraft} isStaff={true} onStageSelect={mockOnStageSelect} />,
        { queryClient, account: mockStaffAccount }
      );

      expect(screen.getByRole('button', { name: /add to roster/i })).toBeInTheDocument();
    });

    it('staff can see both submit and add-to-roster buttons', () => {
      const queryClient = createTestQueryClient();

      renderWithCharacterCreationProviders(
        <ReviewStage draft={mockCompleteDraft} isStaff={true} onStageSelect={mockOnStageSelect} />,
        { queryClient, account: mockStaffAccount }
      );

      expect(screen.getByRole('button', { name: /submit for review/i })).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /add to roster/i })).toBeInTheDocument();
    });

    it('"Add to Roster" button is disabled when stages incomplete', () => {
      const queryClient = createTestQueryClient();

      renderWithCharacterCreationProviders(
        <ReviewStage
          draft={mockIncompleteDraft}
          isStaff={true}
          onStageSelect={mockOnStageSelect}
        />,
        { queryClient, account: mockStaffAccount }
      );

      const rosterButton = screen.getByRole('button', { name: /add to roster/i });
      expect(rosterButton).toBeDisabled();
    });

    it('"Add to Roster" button is enabled when all stages complete', () => {
      const queryClient = createTestQueryClient();

      renderWithCharacterCreationProviders(
        <ReviewStage draft={mockCompleteDraft} isStaff={true} onStageSelect={mockOnStageSelect} />,
        { queryClient, account: mockStaffAccount }
      );

      const rosterButton = screen.getByRole('button', { name: /add to roster/i });
      expect(rosterButton).not.toBeDisabled();
    });
  });

  describe('Page Header', () => {
    it('displays stage title and description', () => {
      const queryClient = createTestQueryClient();

      renderWithCharacterCreationProviders(
        <ReviewStage draft={mockCompleteDraft} isStaff={false} onStageSelect={mockOnStageSelect} />,
        { queryClient }
      );

      expect(screen.getByText('Review & Submit')).toBeInTheDocument();
      expect(
        screen.getByText(/review your character before submitting for approval/i)
      ).toBeInTheDocument();
    });
  });
});
