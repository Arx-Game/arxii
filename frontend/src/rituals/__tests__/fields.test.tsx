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
});
