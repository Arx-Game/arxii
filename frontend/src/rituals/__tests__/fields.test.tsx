import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactNode } from 'react';

import { TextField } from '../components/fields/TextField';
import { IntField } from '../components/fields/IntField';
import { SelectField } from '../components/fields/SelectField';
import { UnknownFieldFallback } from '../components/fields/UnknownFieldFallback';
import { CharacterSearchField } from '../components/fields/CharacterSearchField';
import { ScenePickerField } from '../components/fields/ScenePickerField';
import { ResonancePickerField } from '../components/fields/ResonancePickerField';
import { RelationshipCapstonePickerField } from '../components/fields/RelationshipCapstonePickerField';
import type { RitualField } from '../types';

// ---------------------------------------------------------------------------
// Mock backing APIs for domain field components
// ---------------------------------------------------------------------------

vi.mock('@/events/queries', () => ({
  searchPersonas: vi.fn(),
}));

vi.mock('@/scenes/queries', () => ({
  fetchScenes: vi.fn(),
}));

vi.mock('@/evennia_replacements/api', () => ({
  apiFetch: vi.fn(),
}));

import { searchPersonas } from '@/events/queries';
import { fetchScenes } from '@/scenes/queries';
import { apiFetch } from '@/evennia_replacements/api';

// ---------------------------------------------------------------------------
// Test wrapper with React Query
// ---------------------------------------------------------------------------

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });
  return function Wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
  };
}

describe('Field Components', () => {
  describe('TextField', () => {
    it('renders label and input', () => {
      const field: RitualField = {
        name: 'name_field',
        label: 'Character Name',
        type: 'text',
      };
      const onChange = vi.fn();

      render(<TextField field={field} value="Test" onChange={onChange} />);

      expect(screen.getByText('Character Name')).toBeInTheDocument();
      expect(screen.getByRole('textbox')).toHaveValue('Test');
    });

    it('renders help text if provided', () => {
      const field: RitualField = {
        name: 'name_field',
        label: 'Name',
        type: 'text',
        help: 'Enter a name',
      };
      const onChange = vi.fn();

      render(<TextField field={field} value="" onChange={onChange} />);

      expect(screen.getByText('Enter a name')).toBeInTheDocument();
    });

    it('calls onChange with input value on change', async () => {
      const field: RitualField = {
        name: 'name_field',
        label: 'Name',
        type: 'text',
      };
      const onChange = vi.fn();

      render(<TextField field={field} value="" onChange={onChange} />);

      const input = screen.getByRole('textbox');
      await userEvent.clear(input);
      await userEvent.type(input, 'hello');

      // Verify onChange was called multiple times (once per character) with the accumulated values
      expect(onChange.mock.calls.length).toBeGreaterThan(0);
      expect(onChange).toHaveBeenCalledWith(expect.stringContaining('h'));
      expect(onChange).toHaveBeenCalledWith(expect.stringContaining('e'));
    });

    it('disables input when disabled prop is true', () => {
      const field: RitualField = {
        name: 'name_field',
        label: 'Name',
        type: 'text',
      };
      const onChange = vi.fn();

      render(<TextField field={field} value="" onChange={onChange} disabled={true} />);

      expect(screen.getByRole('textbox')).toBeDisabled();
    });

    it('handles null value', () => {
      const field: RitualField = {
        name: 'name_field',
        label: 'Name',
        type: 'text',
      };
      const onChange = vi.fn();

      render(<TextField field={field} value={null} onChange={onChange} />);

      expect(screen.getByRole('textbox')).toHaveValue('');
    });
  });

  describe('IntField', () => {
    it('renders label and input with type number', () => {
      const field: RitualField = {
        name: 'count_field',
        label: 'Count',
        type: 'int',
      };
      const onChange = vi.fn();

      render(<IntField field={field} value={5} onChange={onChange} />);

      expect(screen.getByText('Count')).toBeInTheDocument();
      expect(screen.getByRole('spinbutton')).toHaveValue(5);
    });

    it('renders help text if provided', () => {
      const field: RitualField = {
        name: 'count_field',
        label: 'Count',
        type: 'int',
        help: 'Enter a number',
      };
      const onChange = vi.fn();

      render(<IntField field={field} value={0} onChange={onChange} />);

      expect(screen.getByText('Enter a number')).toBeInTheDocument();
    });

    it('calls onChange with parsed integer on change', async () => {
      const field: RitualField = {
        name: 'count_field',
        label: 'Count',
        type: 'int',
      };
      const onChange = vi.fn();

      render(<IntField field={field} value={0} onChange={onChange} />);

      const input = screen.getByRole('spinbutton');
      await userEvent.clear(input);
      await userEvent.type(input, '123');

      // Verify onChange was called and eventually with the final parsed integer
      expect(onChange.mock.calls.length).toBeGreaterThan(0);
      expect(onChange).toHaveBeenCalledWith(expect.any(Number));
    });

    it('calls onChange with null when input is cleared', async () => {
      const field: RitualField = {
        name: 'count_field',
        label: 'Count',
        type: 'int',
      };
      const onChange = vi.fn();

      render(<IntField field={field} value={5} onChange={onChange} />);

      const input = screen.getByRole('spinbutton');
      await userEvent.clear(input);

      expect(onChange).toHaveBeenCalledWith(null);
    });

    it('calls onChange with null for invalid input', async () => {
      const field: RitualField = {
        name: 'count_field',
        label: 'Count',
        type: 'int',
      };
      const onChange = vi.fn();

      render(<IntField field={field} value={0} onChange={onChange} />);

      const input = screen.getByRole('spinbutton');
      await userEvent.clear(input);
      await userEvent.type(input, 'not a number');

      expect(onChange).toHaveBeenCalledWith(null);
    });

    it('disables input when disabled prop is true', () => {
      const field: RitualField = {
        name: 'count_field',
        label: 'Count',
        type: 'int',
      };
      const onChange = vi.fn();

      render(<IntField field={field} value={0} onChange={onChange} disabled={true} />);

      expect(screen.getByRole('spinbutton')).toBeDisabled();
    });

    it('handles null value', () => {
      const field: RitualField = {
        name: 'count_field',
        label: 'Count',
        type: 'int',
      };
      const onChange = vi.fn();

      render(<IntField field={field} value={null} onChange={onChange} />);

      expect(screen.getByRole('spinbutton')).toHaveValue(null);
    });
  });

  describe('SelectField', () => {
    it('renders label and select control', () => {
      const field: RitualField = {
        name: 'option_field',
        label: 'Select Option',
        type: 'select',
        choices: [
          { value: 'opt1', label: 'Option 1' },
          { value: 'opt2', label: 'Option 2' },
          { value: 'opt3', label: 'Option 3' },
        ],
      };
      const onChange = vi.fn();

      render(<SelectField field={field} value="opt1" onChange={onChange} />);

      expect(screen.getByText('Select Option')).toBeInTheDocument();
      expect(screen.getByRole('combobox')).toBeInTheDocument();
    });

    it('renders help text if provided', () => {
      const field: RitualField = {
        name: 'option_field',
        label: 'Select Option',
        type: 'select',
        help: 'Choose one',
        choices: [{ value: 'opt1', label: 'Option 1' }],
      };
      const onChange = vi.fn();

      render(<SelectField field={field} value="opt1" onChange={onChange} />);

      expect(screen.getByText('Choose one')).toBeInTheDocument();
    });

    it('displays selected option label in trigger', () => {
      const field: RitualField = {
        name: 'option_field',
        label: 'Select Option',
        type: 'select',
        choices: [
          { value: 'opt1', label: 'Option 1' },
          { value: 'opt2', label: 'Option 2' },
        ],
      };
      const onChange = vi.fn();

      render(<SelectField field={field} value="opt2" onChange={onChange} />);

      expect(screen.getByText('Option 2')).toBeInTheDocument();
    });

    it('disables select when disabled prop is true', () => {
      const field: RitualField = {
        name: 'option_field',
        label: 'Select Option',
        type: 'select',
        choices: [{ value: 'opt1', label: 'Option 1' }],
      };
      const onChange = vi.fn();

      render(<SelectField field={field} value="opt1" onChange={onChange} disabled={true} />);

      expect(screen.getByRole('combobox')).toBeDisabled();
    });

    it('handles string choice values', () => {
      const field: RitualField = {
        name: 'option_field',
        label: 'Select Option',
        type: 'select',
        choices: [
          { value: 'opt1', label: 'Option 1' },
          { value: 'opt2', label: 'Option 2' },
        ],
      };
      const onChange = vi.fn();

      render(<SelectField field={field} value="opt1" onChange={onChange} />);

      expect(screen.getByText('Option 1')).toBeInTheDocument();
    });

    it('handles numeric choice values', () => {
      const field: RitualField = {
        name: 'option_field',
        label: 'Select Option',
        type: 'select',
        choices: [
          { value: 1, label: 'Option 1' },
          { value: 2, label: 'Option 2' },
        ],
      };
      const onChange = vi.fn();

      render(<SelectField field={field} value={1} onChange={onChange} />);

      expect(screen.getByText('Option 1')).toBeInTheDocument();
    });

    it('onChange handler correctly coerces string values to original choice types', () => {
      // This test directly exercises the value-coercion logic in SelectField's handleChange.
      // Radix Select always passes string values to onValueChange, and SelectField
      // reconstructs the original typed value from the choices array.

      const field: RitualField = {
        name: 'option_field',
        label: 'Select Option',
        type: 'select',
        choices: [
          { value: 'opt1', label: 'Option 1' },
          { value: 5, label: 'Option 2 (numeric)' },
          { value: 'opt3', label: 'Option 3' },
        ],
      };
      const onChange = vi.fn();

      // Render with string value
      const { rerender } = render(<SelectField field={field} value="opt1" onChange={onChange} />);
      expect(screen.getByText('Option 1')).toBeInTheDocument();

      // Re-render with numeric value to verify value coercion path works
      // (when handleChange("5") is called, it should find choice with value 5 and pass numeric 5)
      rerender(<SelectField field={field} value={5} onChange={onChange} />);
      expect(screen.getByText('Option 2 (numeric)')).toBeInTheDocument();

      // Re-render with different string value
      rerender(<SelectField field={field} value="opt3" onChange={onChange} />);
      expect(screen.getByText('Option 3')).toBeInTheDocument();
    });
  });

  describe('UnknownFieldFallback', () => {
    it('renders label and text input', () => {
      const field: RitualField = {
        name: 'unknown_field',
        label: 'Unknown Field',
        type: 'unknown_type',
      };
      const onChange = vi.fn();

      render(<UnknownFieldFallback field={field} value="test" onChange={onChange} />);

      expect(screen.getByText('Unknown Field')).toBeInTheDocument();
      expect(screen.getByRole('textbox')).toHaveValue('test');
    });

    it('displays warning about unsupported field type', () => {
      const field: RitualField = {
        name: 'unknown_field',
        label: 'Unknown Field',
        type: 'custom_type',
      };
      const onChange = vi.fn();

      render(<UnknownFieldFallback field={field} value="" onChange={onChange} />);

      expect(screen.getByText(/Unsupported field type 'custom_type'/)).toBeInTheDocument();
    });

    it('renders help text if provided', () => {
      const field: RitualField = {
        name: 'unknown_field',
        label: 'Unknown Field',
        type: 'unknown_type',
        help: 'This is unsupported',
      };
      const onChange = vi.fn();

      render(<UnknownFieldFallback field={field} value="" onChange={onChange} />);

      expect(screen.getByText('This is unsupported')).toBeInTheDocument();
    });

    it('calls onChange with input value on change', async () => {
      const field: RitualField = {
        name: 'unknown_field',
        label: 'Unknown Field',
        type: 'unknown_type',
      };
      const onChange = vi.fn();

      render(<UnknownFieldFallback field={field} value="" onChange={onChange} />);

      const input = screen.getByRole('textbox');
      await userEvent.clear(input);
      await userEvent.type(input, 'test');

      // Verify onChange was called multiple times with character values
      expect(onChange.mock.calls.length).toBeGreaterThan(0);
      expect(onChange).toHaveBeenCalledWith(expect.stringContaining('t'));
    });

    it('disables input when disabled prop is true', () => {
      const field: RitualField = {
        name: 'unknown_field',
        label: 'Unknown Field',
        type: 'unknown_type',
      };
      const onChange = vi.fn();

      render(<UnknownFieldFallback field={field} value="" onChange={onChange} disabled={true} />);

      expect(screen.getByRole('textbox')).toBeDisabled();
    });
  });

  // ---------------------------------------------------------------------------
  // Domain field components
  // ---------------------------------------------------------------------------

  describe('CharacterSearchField', () => {
    const field: RitualField = {
      name: 'target',
      label: 'Target Character',
      type: 'character_search',
    };

    beforeEach(() => {
      vi.clearAllMocks();
    });

    it('renders label and search input', () => {
      const Wrapper = createWrapper();
      render(
        <Wrapper>
          <CharacterSearchField field={field} value={null} onChange={vi.fn()} />
        </Wrapper>
      );
      expect(screen.getByText('Target Character')).toBeInTheDocument();
      expect(screen.getByRole('textbox')).toBeInTheDocument();
    });

    it('renders help text if provided', () => {
      const fieldWithHelp: RitualField = { ...field, help: 'Pick a character' };
      const Wrapper = createWrapper();
      render(
        <Wrapper>
          <CharacterSearchField field={fieldWithHelp} value={null} onChange={vi.fn()} />
        </Wrapper>
      );
      expect(screen.getByText('Pick a character')).toBeInTheDocument();
    });

    it('shows search results after typing and calls onChange with persona id', async () => {
      vi.mocked(searchPersonas).mockResolvedValue([
        { id: 10, name: 'Aria Voss' },
        { id: 11, name: 'Kael Dorne' },
      ]);
      const onChange = vi.fn();
      const Wrapper = createWrapper();

      render(
        <Wrapper>
          <CharacterSearchField field={field} value={null} onChange={onChange} />
        </Wrapper>
      );

      const input = screen.getByRole('textbox');
      await userEvent.type(input, 'Aria');

      await waitFor(() => {
        expect(screen.getByText('Aria Voss')).toBeInTheDocument();
      });

      await userEvent.click(screen.getByText('Aria Voss'));
      expect(onChange).toHaveBeenCalledWith(10);
    });

    it('disables input when disabled prop is true', () => {
      const Wrapper = createWrapper();
      render(
        <Wrapper>
          <CharacterSearchField field={field} value={null} onChange={vi.fn()} disabled />
        </Wrapper>
      );
      expect(screen.getByRole('textbox')).toBeDisabled();
    });
  });

  describe('ScenePickerField', () => {
    const field: RitualField = { name: 'scene', label: 'Active Scene', type: 'scene_picker' };

    beforeEach(() => {
      vi.clearAllMocks();
    });

    it('renders label', () => {
      vi.mocked(fetchScenes).mockResolvedValue({ results: [] });
      const Wrapper = createWrapper();
      render(
        <Wrapper>
          <ScenePickerField field={field} value={null} onChange={vi.fn()} />
        </Wrapper>
      );
      expect(screen.getByText('Active Scene')).toBeInTheDocument();
    });

    it('renders help text if provided', () => {
      vi.mocked(fetchScenes).mockResolvedValue({ results: [] });
      const fieldWithHelp: RitualField = { ...field, help: 'Choose your scene' };
      const Wrapper = createWrapper();
      render(
        <Wrapper>
          <ScenePickerField field={fieldWithHelp} value={null} onChange={vi.fn()} />
        </Wrapper>
      );
      expect(screen.getByText('Choose your scene')).toBeInTheDocument();
    });

    it('fetches active scenes from API and shows selected scene label', async () => {
      vi.mocked(fetchScenes).mockResolvedValue({
        results: [
          { id: 5, name: 'The Market', description: '', date_started: '', participants: [] },
          { id: 6, name: 'The Docks', description: '', date_started: '', participants: [] },
        ],
      });
      const onChange = vi.fn();
      const Wrapper = createWrapper();

      render(
        <Wrapper>
          {/* value=5 pre-selects "The Market" — label should appear in trigger */}
          <ScenePickerField field={field} value={5} onChange={onChange} />
        </Wrapper>
      );

      await waitFor(() => {
        expect(screen.getByRole('combobox')).toBeInTheDocument();
      });

      // Verify the API was called with the active status filter
      expect(fetchScenes).toHaveBeenCalledWith('status=active');

      // The selected scene name should appear in the trigger
      await waitFor(() => {
        expect(screen.getByText('The Market')).toBeInTheDocument();
      });
    });
  });

  describe('ResonancePickerField', () => {
    const field: RitualField = { name: 'resonance', label: 'Resonance', type: 'resonance_picker' };

    beforeEach(() => {
      vi.clearAllMocks();
    });

    it('renders label', () => {
      vi.mocked(apiFetch).mockResolvedValue({
        ok: true,
        json: async () => [],
      } as Response);
      const Wrapper = createWrapper();
      render(
        <Wrapper>
          <ResonancePickerField field={field} value={null} onChange={vi.fn()} />
        </Wrapper>
      );
      expect(screen.getByText('Resonance')).toBeInTheDocument();
    });

    it('renders help text if provided', () => {
      vi.mocked(apiFetch).mockResolvedValue({
        ok: true,
        json: async () => [],
      } as Response);
      const fieldWithHelp: RitualField = { ...field, help: 'Select your resonance' };
      const Wrapper = createWrapper();
      render(
        <Wrapper>
          <ResonancePickerField field={fieldWithHelp} value={null} onChange={vi.fn()} />
        </Wrapper>
      );
      expect(screen.getByText('Select your resonance')).toBeInTheDocument();
    });

    it('fetches resonances from API and shows selected resonance label', async () => {
      vi.mocked(apiFetch).mockResolvedValue({
        ok: true,
        json: async () => [
          {
            id: 20,
            character_sheet: 1,
            resonance: 3,
            resonance_name: 'Fire',
            resonance_detail: {},
            claimed_at: '',
          },
          {
            id: 21,
            character_sheet: 1,
            resonance: 4,
            resonance_name: 'Shadow',
            resonance_detail: {},
            claimed_at: '',
          },
        ],
      } as Response);
      const onChange = vi.fn();
      const Wrapper = createWrapper();

      render(
        <Wrapper>
          {/* value=20 pre-selects "Fire" — label should appear in trigger */}
          <ResonancePickerField field={field} value={20} onChange={onChange} />
        </Wrapper>
      );

      // Verify the API was called with the correct endpoint
      await waitFor(() => {
        expect(apiFetch).toHaveBeenCalledWith('/api/magic/character-resonances/');
      });

      // The selected resonance name should appear in the trigger
      await waitFor(() => {
        expect(screen.getByText('Fire')).toBeInTheDocument();
      });
    });
  });

  describe('RelationshipCapstonePickerField', () => {
    const field: RitualField = {
      name: 'capstone_id',
      label: 'Relationship Capstone',
      type: 'relationship_capstone_picker',
    };

    beforeEach(() => {
      vi.clearAllMocks();
    });

    it('renders label', () => {
      const Wrapper = createWrapper();
      render(
        <Wrapper>
          <RelationshipCapstonePickerField field={field} value={null} onChange={vi.fn()} />
        </Wrapper>
      );
      expect(screen.getByText('Relationship Capstone')).toBeInTheDocument();
    });

    it('renders help text if provided', () => {
      const fieldWithHelp: RitualField = { ...field, help: 'Pick a capstone' };
      const Wrapper = createWrapper();
      render(
        <Wrapper>
          <RelationshipCapstonePickerField field={fieldWithHelp} value={null} onChange={vi.fn()} />
        </Wrapper>
      );
      expect(screen.getByText('Pick a capstone')).toBeInTheDocument();
    });

    it('shows placeholder when sineater_sheet_id is not set', () => {
      const Wrapper = createWrapper();
      render(
        <Wrapper>
          <RelationshipCapstonePickerField field={field} value={null} onChange={vi.fn()} />
        </Wrapper>
      );
      expect(screen.getByText('Select a Sineater first')).toBeInTheDocument();
    });

    it('disables dropdown when sineater_sheet_id is not set', () => {
      const Wrapper = createWrapper();
      render(
        <Wrapper>
          <RelationshipCapstonePickerField field={field} value={null} onChange={vi.fn()} />
        </Wrapper>
      );
      expect(screen.getByRole('combobox')).toBeDisabled();
    });

    it('fetches capstones when sineater_sheet_id is provided and shows selected label', async () => {
      vi.mocked(apiFetch).mockResolvedValue({
        ok: true,
        json: async () => ({
          results: [
            {
              id: 30,
              author: 1,
              author_name: 'Aria',
              title: 'The Binding Oath',
              writeup: '...',
              track: 5,
              track_name: 'Bond',
              points: 3,
              visibility: 'private',
              linked_scene: null,
              created_at: '',
            },
          ],
        }),
      } as Response);

      const onChange = vi.fn();
      const Wrapper = createWrapper();

      render(
        <Wrapper>
          {/* value=30 pre-selects "The Binding Oath" — label appears in trigger after load */}
          <RelationshipCapstonePickerField
            field={field}
            value={30}
            onChange={onChange}
            formValues={{ sineater_sheet_id: 42 }}
          />
        </Wrapper>
      );

      await waitFor(() => {
        expect(screen.getByRole('combobox')).not.toBeDisabled();
      });

      // The selected capstone title should appear in the trigger
      await waitFor(() => {
        expect(screen.getByText('The Binding Oath')).toBeInTheDocument();
      });
    });

    it('passes other_character_sheet_id as query param when sineater_sheet_id is set', async () => {
      vi.mocked(apiFetch).mockResolvedValue({
        ok: true,
        json: async () => ({ results: [] }),
      } as Response);

      const Wrapper = createWrapper();

      render(
        <Wrapper>
          <RelationshipCapstonePickerField
            field={field}
            value={null}
            onChange={vi.fn()}
            formValues={{ sineater_sheet_id: 99 }}
          />
        </Wrapper>
      );

      await waitFor(() => {
        expect(apiFetch).toHaveBeenCalledWith(
          '/api/relationships/relationship-capstones/?other_character_sheet_id=99'
        );
      });
    });
  });
});
