/**
 * GiftDesigner Component Tests
 *
 * Tests for the GiftDesigner component which allows players to design custom gifts
 * by selecting a name, 1-2 resonances (affinity is derived), and description.
 */

import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi } from 'vitest';
import { GiftDesigner } from '../../components/magic/GiftDesigner';
import { mockDraftGift, mockResonances } from '../fixtures';
import {
  createTestQueryClient,
  renderWithCharacterCreationProviders,
  seedQueryData,
} from '../testUtils';
import { characterCreationKeys } from '../../queries';

// Mock the API module
vi.mock('../../api', () => ({
  getResonances: vi.fn(),
  createDraftGift: vi.fn(),
}));

// Import the mocked functions for test control
import { createDraftGift } from '../../api';

describe('GiftDesigner', () => {
  const mockOnGiftCreated = vi.fn();
  const mockOnCancel = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
  });

  // Helper function to seed all required query data for GiftDesigner
  function seedGiftDesignerData(queryClient: ReturnType<typeof createTestQueryClient>) {
    seedQueryData(queryClient, characterCreationKeys.resonances(), mockResonances);
  }

  describe('Rendering', () => {
    it('displays the gift designer form', () => {
      const queryClient = createTestQueryClient();
      seedGiftDesignerData(queryClient);

      renderWithCharacterCreationProviders(
        <GiftDesigner onGiftCreated={mockOnGiftCreated} onCancel={mockOnCancel} />,
        { queryClient }
      );

      expect(screen.getByText('Design Your Gift')).toBeInTheDocument();
      expect(screen.getByLabelText(/gift name/i)).toBeInTheDocument();
      expect(screen.getAllByText(/resonances/i).length).toBeGreaterThan(0);
    });

    it('displays resonances for selection', async () => {
      const queryClient = createTestQueryClient();
      seedGiftDesignerData(queryClient);

      renderWithCharacterCreationProviders(<GiftDesigner onGiftCreated={mockOnGiftCreated} />, {
        queryClient,
      });

      await waitFor(() => {
        expect(screen.getByRole('button', { name: 'Shadow' })).toBeInTheDocument();
        expect(screen.getByRole('button', { name: 'Flame' })).toBeInTheDocument();
      });
    });

    it('displays loading state while data is loading', () => {
      const queryClient = createTestQueryClient();
      // Don't seed data - should show loading

      renderWithCharacterCreationProviders(<GiftDesigner onGiftCreated={mockOnGiftCreated} />, {
        queryClient,
      });

      // Loading state shows animated pulse placeholders
      expect(document.querySelector('.animate-pulse')).toBeInTheDocument();
    });

    it('displays description textarea', () => {
      const queryClient = createTestQueryClient();
      seedGiftDesignerData(queryClient);

      renderWithCharacterCreationProviders(<GiftDesigner onGiftCreated={mockOnGiftCreated} />, {
        queryClient,
      });

      expect(screen.getByLabelText(/description/i)).toBeInTheDocument();
    });

    it('highlights resonances with projected values', async () => {
      const queryClient = createTestQueryClient();
      seedGiftDesignerData(queryClient);

      const projectedResonances = [
        {
          resonance_id: 1,
          resonance_name: 'Shadow',
          total: 10,
          sources: [{ distinction_name: 'Patient', value: 10 }],
        },
      ];

      renderWithCharacterCreationProviders(
        <GiftDesigner
          onGiftCreated={mockOnGiftCreated}
          projectedResonances={projectedResonances}
        />,
        { queryClient }
      );

      await waitFor(() => {
        expect(screen.getByRole('button', { name: /Shadow/ })).toBeInTheDocument();
      });

      expect(screen.getByText('+10')).toBeInTheDocument();
    });
  });

  describe('Form Validation', () => {
    it('disables submit button when name is empty', async () => {
      const queryClient = createTestQueryClient();
      seedGiftDesignerData(queryClient);

      renderWithCharacterCreationProviders(<GiftDesigner onGiftCreated={mockOnGiftCreated} />, {
        queryClient,
      });

      await waitFor(() => {
        expect(screen.getByRole('button', { name: 'Shadow' })).toBeInTheDocument();
      });

      // Submit button should be disabled without any selections
      const submitButton = screen.getByRole('button', { name: /create gift/i });
      expect(submitButton).toBeDisabled();
    });

    it('disables submit button when no resonance is selected', async () => {
      const user = userEvent.setup();
      const queryClient = createTestQueryClient();
      seedGiftDesignerData(queryClient);

      renderWithCharacterCreationProviders(<GiftDesigner onGiftCreated={mockOnGiftCreated} />, {
        queryClient,
      });

      await waitFor(() => {
        expect(screen.getByRole('button', { name: 'Shadow' })).toBeInTheDocument();
      });

      // Fill name only
      const nameInput = screen.getByLabelText(/gift name/i);
      await user.type(nameInput, 'Test Gift');

      // Submit button should still be disabled without resonances
      const submitButton = screen.getByRole('button', { name: /create gift/i });
      expect(submitButton).toBeDisabled();
    });

    it('enables submit button when name and resonance are provided', async () => {
      const user = userEvent.setup();
      const queryClient = createTestQueryClient();
      seedGiftDesignerData(queryClient);

      renderWithCharacterCreationProviders(<GiftDesigner onGiftCreated={mockOnGiftCreated} />, {
        queryClient,
      });

      await waitFor(() => {
        expect(screen.getByRole('button', { name: 'Shadow' })).toBeInTheDocument();
      });

      // Fill name
      const nameInput = screen.getByLabelText(/gift name/i);
      await user.type(nameInput, 'Test Gift');

      // Select a resonance
      const shadowButton = screen.getByRole('button', { name: 'Shadow' });
      await user.click(shadowButton);

      // Submit button should now be enabled
      const submitButton = screen.getByRole('button', { name: /create gift/i });
      expect(submitButton).not.toBeDisabled();
    });
  });

  describe('User Interaction', () => {
    it('allows selecting resonances', async () => {
      const user = userEvent.setup();
      const queryClient = createTestQueryClient();
      seedGiftDesignerData(queryClient);

      renderWithCharacterCreationProviders(<GiftDesigner onGiftCreated={mockOnGiftCreated} />, {
        queryClient,
      });

      await waitFor(() => {
        expect(screen.getByRole('button', { name: 'Shadow' })).toBeInTheDocument();
      });

      // Select first resonance
      const shadowButton = screen.getByRole('button', { name: 'Shadow' });
      await user.click(shadowButton);

      // Check the counter shows 1/2
      expect(screen.getByText(/1\/2/)).toBeInTheDocument();
    });

    it('shows derived affinity when resonance is selected', async () => {
      const user = userEvent.setup();
      const queryClient = createTestQueryClient();
      seedGiftDesignerData(queryClient);

      renderWithCharacterCreationProviders(<GiftDesigner onGiftCreated={mockOnGiftCreated} />, {
        queryClient,
      });

      await waitFor(() => {
        expect(screen.getByRole('button', { name: 'Shadow' })).toBeInTheDocument();
      });

      // Select Shadow (abyssal affinity)
      const shadowButton = screen.getByRole('button', { name: 'Shadow' });
      await user.click(shadowButton);

      // Derived affinity section should appear
      expect(screen.getByText('Derived Affinity')).toBeInTheDocument();
      expect(screen.getByText('abyssal')).toBeInTheDocument();
    });

    it('allows selecting up to 2 resonances', async () => {
      const user = userEvent.setup();
      const queryClient = createTestQueryClient();
      seedGiftDesignerData(queryClient);

      renderWithCharacterCreationProviders(<GiftDesigner onGiftCreated={mockOnGiftCreated} />, {
        queryClient,
      });

      await waitFor(() => {
        expect(screen.getByRole('button', { name: 'Shadow' })).toBeInTheDocument();
      });

      // Select first resonance
      const shadowButton = screen.getByRole('button', { name: 'Shadow' });
      await user.click(shadowButton);

      // Select second resonance
      const flameButton = screen.getByRole('button', { name: 'Flame' });
      await user.click(flameButton);

      // Check the counter shows 2/2
      expect(screen.getByText(/2\/2/)).toBeInTheDocument();
    });

    it('allows deselecting a resonance', async () => {
      const user = userEvent.setup();
      const queryClient = createTestQueryClient();
      seedGiftDesignerData(queryClient);

      renderWithCharacterCreationProviders(<GiftDesigner onGiftCreated={mockOnGiftCreated} />, {
        queryClient,
      });

      await waitFor(() => {
        expect(screen.getByRole('button', { name: 'Shadow' })).toBeInTheDocument();
      });

      // Select first resonance
      const shadowButton = screen.getByRole('button', { name: 'Shadow' });
      await user.click(shadowButton);
      expect(screen.getByText(/1\/2/)).toBeInTheDocument();

      // Deselect it
      await user.click(shadowButton);
      expect(screen.getByText(/0\/2/)).toBeInTheDocument();
    });

    it('calls onCancel when cancel button is clicked', async () => {
      const user = userEvent.setup();
      const queryClient = createTestQueryClient();
      seedGiftDesignerData(queryClient);

      renderWithCharacterCreationProviders(
        <GiftDesigner onGiftCreated={mockOnGiftCreated} onCancel={mockOnCancel} />,
        { queryClient }
      );

      const cancelButton = screen.getByRole('button', { name: /cancel/i });
      await user.click(cancelButton);

      expect(mockOnCancel).toHaveBeenCalled();
    });

    it('does not display cancel button when onCancel is not provided', () => {
      const queryClient = createTestQueryClient();
      seedGiftDesignerData(queryClient);

      renderWithCharacterCreationProviders(<GiftDesigner onGiftCreated={mockOnGiftCreated} />, {
        queryClient,
      });

      expect(screen.queryByRole('button', { name: /cancel/i })).not.toBeInTheDocument();
    });

    it('allows typing in name input', async () => {
      const user = userEvent.setup();
      const queryClient = createTestQueryClient();
      seedGiftDesignerData(queryClient);

      renderWithCharacterCreationProviders(<GiftDesigner onGiftCreated={mockOnGiftCreated} />, {
        queryClient,
      });

      const nameInput = screen.getByLabelText(/gift name/i) as HTMLInputElement;
      await user.type(nameInput, 'My Test Gift');

      expect(nameInput.value).toBe('My Test Gift');
    });

    it('allows typing in description textarea', async () => {
      const user = userEvent.setup();
      const queryClient = createTestQueryClient();
      seedGiftDesignerData(queryClient);

      renderWithCharacterCreationProviders(<GiftDesigner onGiftCreated={mockOnGiftCreated} />, {
        queryClient,
      });

      const descriptionInput = screen.getByLabelText(/description/i) as HTMLTextAreaElement;
      await user.type(descriptionInput, 'A powerful gift of shadows');

      expect(descriptionInput.value).toBe('A powerful gift of shadows');
    });
  });

  describe('Form Submission', () => {
    it('successfully creates a gift with valid data', async () => {
      const user = userEvent.setup();
      const queryClient = createTestQueryClient();
      seedGiftDesignerData(queryClient);

      // Mock the createDraftGift API call
      vi.mocked(createDraftGift).mockResolvedValueOnce({
        ...mockDraftGift,
        name: 'My Test Gift',
      });

      renderWithCharacterCreationProviders(<GiftDesigner onGiftCreated={mockOnGiftCreated} />, {
        queryClient,
      });

      await waitFor(() => {
        expect(screen.getByRole('button', { name: 'Shadow' })).toBeInTheDocument();
      });

      // Fill name
      const nameInput = screen.getByLabelText(/gift name/i);
      await user.type(nameInput, 'My Test Gift');

      // Select a resonance (Shadow is id: 1 in mockResonances)
      const shadowButton = screen.getByRole('button', { name: 'Shadow' });
      await user.click(shadowButton);

      // Submit
      const submitButton = screen.getByRole('button', { name: /create gift/i });
      expect(submitButton).not.toBeDisabled();
      await user.click(submitButton);

      // Wait for callback
      await waitFor(() => {
        expect(mockOnGiftCreated).toHaveBeenCalled();
      });

      // Verify the API was called with correct data (no affinity field)
      expect(createDraftGift).toHaveBeenCalledWith({
        name: 'My Test Gift',
        resonances: [1],
        description: '',
      });
    });

    it('submits with description when provided', async () => {
      const user = userEvent.setup();
      const queryClient = createTestQueryClient();
      seedGiftDesignerData(queryClient);

      // Mock the createDraftGift API call
      vi.mocked(createDraftGift).mockResolvedValueOnce(mockDraftGift);

      renderWithCharacterCreationProviders(<GiftDesigner onGiftCreated={mockOnGiftCreated} />, {
        queryClient,
      });

      await waitFor(() => {
        expect(screen.getByRole('button', { name: 'Shadow' })).toBeInTheDocument();
      });

      // Fill all fields
      const nameInput = screen.getByLabelText(/gift name/i);
      await user.type(nameInput, 'Shadow Walker');

      const shadowButton = screen.getByRole('button', { name: 'Shadow' });
      await user.click(shadowButton);

      const descriptionInput = screen.getByLabelText(/description/i);
      await user.type(descriptionInput, 'A gift of walking through shadows');

      // Submit
      const submitButton = screen.getByRole('button', { name: /create gift/i });
      await user.click(submitButton);

      // Wait for callback
      await waitFor(() => {
        expect(createDraftGift).toHaveBeenCalledWith({
          name: 'Shadow Walker',
          resonances: [1],
          description: 'A gift of walking through shadows',
        });
      });
    });

    it('submits with multiple resonances when selected', async () => {
      const user = userEvent.setup();
      const queryClient = createTestQueryClient();
      seedGiftDesignerData(queryClient);

      // Mock the createDraftGift API call
      vi.mocked(createDraftGift).mockResolvedValueOnce(mockDraftGift);

      renderWithCharacterCreationProviders(<GiftDesigner onGiftCreated={mockOnGiftCreated} />, {
        queryClient,
      });

      await waitFor(() => {
        expect(screen.getByRole('button', { name: 'Shadow' })).toBeInTheDocument();
      });

      // Fill all fields
      const nameInput = screen.getByLabelText(/gift name/i);
      await user.type(nameInput, 'Dual Resonance Gift');

      // Select two resonances
      const shadowButton = screen.getByRole('button', { name: 'Shadow' });
      await user.click(shadowButton);
      const flameButton = screen.getByRole('button', { name: 'Flame' });
      await user.click(flameButton);

      // Submit
      const submitButton = screen.getByRole('button', { name: /create gift/i });
      await user.click(submitButton);

      // Wait for callback
      await waitFor(() => {
        expect(createDraftGift).toHaveBeenCalledWith({
          name: 'Dual Resonance Gift',
          resonances: [1, 2],
          description: '',
        });
      });
    });

    it('displays error message on API failure', async () => {
      const user = userEvent.setup();
      const queryClient = createTestQueryClient();
      seedGiftDesignerData(queryClient);

      // Mock the createDraftGift API call to fail
      vi.mocked(createDraftGift).mockRejectedValueOnce(new Error('Server error'));

      renderWithCharacterCreationProviders(<GiftDesigner onGiftCreated={mockOnGiftCreated} />, {
        queryClient,
      });

      await waitFor(() => {
        expect(screen.getByRole('button', { name: 'Shadow' })).toBeInTheDocument();
      });

      // Fill form
      const nameInput = screen.getByLabelText(/gift name/i);
      await user.type(nameInput, 'Test Gift');

      const shadowButton = screen.getByRole('button', { name: 'Shadow' });
      await user.click(shadowButton);

      // Submit
      const submitButton = screen.getByRole('button', { name: /create gift/i });
      await user.click(submitButton);

      // Wait for error to display
      await waitFor(() => {
        expect(screen.getByText('Server error')).toBeInTheDocument();
      });

      // Callback should not have been called
      expect(mockOnGiftCreated).not.toHaveBeenCalled();
    });
  });

  describe('Page Header', () => {
    it('displays stage title and description', () => {
      const queryClient = createTestQueryClient();
      seedGiftDesignerData(queryClient);

      renderWithCharacterCreationProviders(<GiftDesigner onGiftCreated={mockOnGiftCreated} />, {
        queryClient,
      });

      expect(screen.getByText('Design Your Gift')).toBeInTheDocument();
      expect(
        screen.getByText(/create a unique magical gift that defines your character's powers/i)
      ).toBeInTheDocument();
    });
  });
});
