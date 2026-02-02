/**
 * GiftDesigner Component Tests
 *
 * Tests for the GiftDesigner component which allows players to design custom gifts
 * by selecting a name, affinity, resonances, and description.
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
import type { Affinity } from '../../types';

// Mock the API module
vi.mock('../../api', () => ({
  getAffinities: vi.fn(),
  getResonances: vi.fn(),
  createDraftGift: vi.fn(),
}));

// Import the mocked functions for test control
import { createDraftGift } from '../../api';

// Mock affinities data
const mockAffinities: Affinity[] = [
  { id: 1, name: 'Celestial', description: 'Light and order', affinity_type: 'celestial' },
  { id: 2, name: 'Primal', description: 'Nature and instinct', affinity_type: 'primal' },
  { id: 3, name: 'Abyssal', description: 'Shadow and entropy', affinity_type: 'abyssal' },
];

describe('GiftDesigner', () => {
  const mockOnGiftCreated = vi.fn();
  const mockOnCancel = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
  });

  // Helper function to seed all required query data for GiftDesigner
  function seedGiftDesignerData(queryClient: ReturnType<typeof createTestQueryClient>) {
    seedQueryData(queryClient, characterCreationKeys.affinities(), mockAffinities);
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
      expect(screen.getByText('Affinity')).toBeInTheDocument();
    });

    it('displays all three affinities after loading', async () => {
      const queryClient = createTestQueryClient();
      seedGiftDesignerData(queryClient);

      renderWithCharacterCreationProviders(<GiftDesigner onGiftCreated={mockOnGiftCreated} />, {
        queryClient,
      });

      await waitFor(() => {
        expect(screen.getByText('Celestial')).toBeInTheDocument();
        expect(screen.getByText('Primal')).toBeInTheDocument();
        expect(screen.getByText('Abyssal')).toBeInTheDocument();
      });
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
  });

  describe('Form Validation', () => {
    it('disables submit button when name is empty', async () => {
      const queryClient = createTestQueryClient();
      seedGiftDesignerData(queryClient);

      renderWithCharacterCreationProviders(<GiftDesigner onGiftCreated={mockOnGiftCreated} />, {
        queryClient,
      });

      // Wait for data to load
      await waitFor(() => {
        expect(screen.getByText('Celestial')).toBeInTheDocument();
      });

      // Submit button should be disabled without any selections
      const submitButton = screen.getByRole('button', { name: /create gift/i });
      expect(submitButton).toBeDisabled();
    });

    it('disables submit button when no affinity is selected', async () => {
      const user = userEvent.setup();
      const queryClient = createTestQueryClient();
      seedGiftDesignerData(queryClient);

      renderWithCharacterCreationProviders(<GiftDesigner onGiftCreated={mockOnGiftCreated} />, {
        queryClient,
      });

      // Wait for data to load
      await waitFor(() => {
        expect(screen.getByText('Celestial')).toBeInTheDocument();
      });

      // Fill name only
      const nameInput = screen.getByLabelText(/gift name/i);
      await user.type(nameInput, 'Test Gift');

      // Select a resonance
      const shadowButton = screen.getByRole('button', { name: 'Shadow' });
      await user.click(shadowButton);

      // Submit button should still be disabled without affinity
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

      // Wait for data to load
      await waitFor(() => {
        expect(screen.getByText('Celestial')).toBeInTheDocument();
      });

      // Fill name
      const nameInput = screen.getByLabelText(/gift name/i);
      await user.type(nameInput, 'Test Gift');

      // Select affinity
      const celestialButton = screen.getByText('Celestial').closest('button');
      await user.click(celestialButton!);

      // Submit button should still be disabled without resonances
      const submitButton = screen.getByRole('button', { name: /create gift/i });
      expect(submitButton).toBeDisabled();
    });

    it('enables submit button when all required fields are filled', async () => {
      const user = userEvent.setup();
      const queryClient = createTestQueryClient();
      seedGiftDesignerData(queryClient);

      renderWithCharacterCreationProviders(<GiftDesigner onGiftCreated={mockOnGiftCreated} />, {
        queryClient,
      });

      // Wait for data to load
      await waitFor(() => {
        expect(screen.getByText('Celestial')).toBeInTheDocument();
      });

      // Fill name
      const nameInput = screen.getByLabelText(/gift name/i);
      await user.type(nameInput, 'Test Gift');

      // Select affinity
      const celestialButton = screen.getByText('Celestial').closest('button');
      await user.click(celestialButton!);

      // Select a resonance
      const shadowButton = screen.getByRole('button', { name: 'Shadow' });
      await user.click(shadowButton);

      // Submit button should now be enabled
      const submitButton = screen.getByRole('button', { name: /create gift/i });
      expect(submitButton).not.toBeDisabled();
    });
  });

  describe('User Interaction', () => {
    it('allows selecting an affinity', async () => {
      const user = userEvent.setup();
      const queryClient = createTestQueryClient();
      seedGiftDesignerData(queryClient);

      renderWithCharacterCreationProviders(<GiftDesigner onGiftCreated={mockOnGiftCreated} />, {
        queryClient,
      });

      await waitFor(() => {
        expect(screen.getByText('Celestial')).toBeInTheDocument();
      });

      // Click on Celestial affinity
      const celestialButton = screen.getByText('Celestial').closest('button');
      await user.click(celestialButton!);

      // Should show selected state (ring-2 class)
      expect(celestialButton).toHaveClass('ring-2');
    });

    it('allows switching affinity selection', async () => {
      const user = userEvent.setup();
      const queryClient = createTestQueryClient();
      seedGiftDesignerData(queryClient);

      renderWithCharacterCreationProviders(<GiftDesigner onGiftCreated={mockOnGiftCreated} />, {
        queryClient,
      });

      await waitFor(() => {
        expect(screen.getByText('Celestial')).toBeInTheDocument();
      });

      // Click on Celestial affinity
      const celestialButton = screen.getByText('Celestial').closest('button');
      await user.click(celestialButton!);
      expect(celestialButton).toHaveClass('ring-2');

      // Click on Primal affinity
      const primalButton = screen.getByText('Primal').closest('button');
      await user.click(primalButton!);
      expect(primalButton).toHaveClass('ring-2');
      expect(celestialButton).not.toHaveClass('ring-2');
    });

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

      // Wait for data to load
      await waitFor(() => {
        expect(screen.getByText('Celestial')).toBeInTheDocument();
      });

      // Fill name
      const nameInput = screen.getByLabelText(/gift name/i);
      await user.type(nameInput, 'My Test Gift');

      // Select affinity (Celestial is id: 1)
      const celestialButton = screen.getByText('Celestial').closest('button');
      await user.click(celestialButton!);

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

      // Verify the API was called with correct data
      expect(createDraftGift).toHaveBeenCalledWith({
        name: 'My Test Gift',
        affinity: 1,
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

      // Wait for data to load
      await waitFor(() => {
        expect(screen.getByText('Celestial')).toBeInTheDocument();
      });

      // Fill all fields
      const nameInput = screen.getByLabelText(/gift name/i);
      await user.type(nameInput, 'Shadow Walker');

      const celestialButton = screen.getByText('Celestial').closest('button');
      await user.click(celestialButton!);

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
          affinity: 1,
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

      // Wait for data to load
      await waitFor(() => {
        expect(screen.getByText('Celestial')).toBeInTheDocument();
      });

      // Fill all fields
      const nameInput = screen.getByLabelText(/gift name/i);
      await user.type(nameInput, 'Dual Resonance Gift');

      const celestialButton = screen.getByText('Celestial').closest('button');
      await user.click(celestialButton!);

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
          affinity: 1,
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

      // Wait for data to load
      await waitFor(() => {
        expect(screen.getByText('Celestial')).toBeInTheDocument();
      });

      // Fill form
      const nameInput = screen.getByLabelText(/gift name/i);
      await user.type(nameInput, 'Test Gift');

      const celestialButton = screen.getByText('Celestial').closest('button');
      await user.click(celestialButton!);

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
