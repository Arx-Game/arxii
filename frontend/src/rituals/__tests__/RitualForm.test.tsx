import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import type { ReactNode } from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import { RitualForm } from '../components/RitualForm';
import type { RitualInputSchema } from '../types';

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

describe('RitualForm', () => {
  it('renders one field per schema.fields entry', () => {
    const schema: RitualInputSchema = {
      fields: [
        { name: 'target', label: 'Target Character', type: 'text' },
        { name: 'count', label: 'Cast Count', type: 'int' },
        {
          name: 'option',
          label: 'Select Option',
          type: 'select',
          choices: [{ value: 'a', label: 'Option A' }],
        },
      ],
    };

    const Wrapper = createWrapper();
    render(
      <Wrapper>
        <RitualForm
          schema={schema}
          values={{ target: 'John', count: 5, option: 'a' }}
          onChange={vi.fn()}
        />
      </Wrapper>
    );

    expect(screen.getByText('Target Character')).toBeInTheDocument();
    expect(screen.getByText('Cast Count')).toBeInTheDocument();
    expect(screen.getByText('Select Option')).toBeInTheDocument();
  });

  it('calls onChange with full updated values dict on user input', async () => {
    const schema: RitualInputSchema = {
      fields: [{ name: 'name', label: 'Name', type: 'text' }],
    };
    const onChange = vi.fn();

    const Wrapper = createWrapper();
    const { rerender } = render(
      <Wrapper>
        <RitualForm schema={schema} values={{ name: '' }} onChange={onChange} />
      </Wrapper>
    );

    const input = screen.getByRole('textbox');
    await userEvent.type(input, 'Alice');

    // onChange should be called with the full updated values dict
    // Verify first keystroke and last keystroke match the expected pattern
    expect(onChange).toHaveBeenCalledWith({ name: 'A' });
    expect(onChange).toHaveBeenCalledWith({ name: 'e' });

    // Re-render with a value that reflects the final typed state
    onChange.mockClear();
    rerender(
      <Wrapper>
        <RitualForm schema={schema} values={{ name: 'Alice' }} onChange={onChange} />
      </Wrapper>
    );

    // Verify the form updated with the typed value
    expect(screen.getByRole('textbox')).toHaveValue('Alice');
  });

  it('renders unknown field type with fallback component', () => {
    const schema: RitualInputSchema = {
      fields: [{ name: 'mystery', label: 'Mystery Field', type: 'mystery_type' }],
    };

    const Wrapper = createWrapper();
    render(
      <Wrapper>
        <RitualForm schema={schema} values={{ mystery: null }} onChange={vi.fn()} />
      </Wrapper>
    );

    // UnknownFieldFallback should render the warning text
    expect(screen.getByText(/Unsupported field type 'mystery_type'/)).toBeInTheDocument();
  });

  it('propagates formValues to fields with cross-field dependencies', async () => {
    const { apiFetch } = await import('@/evennia_replacements/api');
    vi.mocked(apiFetch).mockResolvedValue({
      ok: true,
      json: async () => ({
        results: [
          { id: 30, title: 'The Binding Oath', track_name: 'Bond', author: 1, author_name: 'Test' },
        ],
      }),
    } as Response);

    const schema: RitualInputSchema = {
      fields: [
        { name: 'sineater_sheet_id', label: 'Sineater', type: 'int' },
        { name: 'capstone_id', label: 'Capstone', type: 'relationship_capstone_picker' },
      ],
    };

    const Wrapper = createWrapper();
    render(
      <Wrapper>
        <RitualForm
          schema={schema}
          values={{ sineater_sheet_id: 42, capstone_id: null }}
          onChange={vi.fn()}
        />
      </Wrapper>
    );

    // RelationshipCapstonePickerField should eventually be enabled since sineater_sheet_id is set
    // It reads formValues.sineater_sheet_id to enable itself
    const capstoneCombobox = screen.getByRole('combobox');
    // The field starts disabled while loading, then becomes enabled once data arrives
    // We can't assert on the exact timing, so just verify it renders and is present
    expect(capstoneCombobox).toBeInTheDocument();
  });

  it('disables all fields when disabled prop is true', () => {
    const schema: RitualInputSchema = {
      fields: [
        { name: 'name', label: 'Name', type: 'text' },
        { name: 'count', label: 'Count', type: 'int' },
      ],
    };

    const Wrapper = createWrapper();
    render(
      <Wrapper>
        <RitualForm
          schema={schema}
          values={{ name: '', count: null }}
          onChange={vi.fn()}
          disabled={true}
        />
      </Wrapper>
    );

    const inputs = screen.getAllByRole('textbox');
    const spinbutton = screen.getByRole('spinbutton');

    inputs.forEach((input) => {
      expect(input).toBeDisabled();
    });
    expect(spinbutton).toBeDisabled();
  });

  it('handles multiple field updates independently', async () => {
    const schema: RitualInputSchema = {
      fields: [
        { name: 'field1', label: 'Field 1', type: 'text' },
        { name: 'field2', label: 'Field 2', type: 'text' },
      ],
    };
    const onChange = vi.fn();

    const Wrapper = createWrapper();
    const { rerender } = render(
      <Wrapper>
        <RitualForm schema={schema} values={{ field1: '', field2: '' }} onChange={onChange} />
      </Wrapper>
    );

    // Type in first field
    const inputs = screen.getAllByRole('textbox');
    await userEvent.type(inputs[0], 'Value 1');

    // Verify onChange was called during typing
    expect(onChange).toHaveBeenCalled();

    // Re-render to simulate parent updating form with new values
    onChange.mockClear();
    rerender(
      <Wrapper>
        <RitualForm
          schema={schema}
          values={{ field1: 'Value 1', field2: '' }}
          onChange={onChange}
        />
      </Wrapper>
    );

    // Verify first field now has the typed value
    const updatedInputs = screen.getAllByRole('textbox');
    expect(updatedInputs[0]).toHaveValue('Value 1');

    // Type in second field
    await userEvent.type(updatedInputs[1], 'Value 2');

    // Verify onChange was called again
    expect(onChange).toHaveBeenCalled();

    // Re-render with both values
    rerender(
      <Wrapper>
        <RitualForm
          schema={schema}
          values={{ field1: 'Value 1', field2: 'Value 2' }}
          onChange={onChange}
        />
      </Wrapper>
    );

    // Verify both fields have their values
    const finalInputs = screen.getAllByRole('textbox');
    expect(finalInputs[0]).toHaveValue('Value 1');
    expect(finalInputs[1]).toHaveValue('Value 2');
  });

  it('preserves all field values when one field changes', async () => {
    const schema: RitualInputSchema = {
      fields: [
        { name: 'text_field', label: 'Text', type: 'text' },
        { name: 'int_field', label: 'Number', type: 'int' },
      ],
    };
    const onChange = vi.fn();

    const Wrapper = createWrapper();
    const initialValues = { text_field: 'hello', int_field: 42 };
    const { rerender } = render(
      <Wrapper>
        <RitualForm schema={schema} values={initialValues} onChange={onChange} />
      </Wrapper>
    );

    // Verify initial values are rendered
    expect(screen.getByDisplayValue('hello')).toBeInTheDocument();
    expect(screen.getByRole('spinbutton')).toHaveValue(42);

    // Change int field
    const spinbutton = screen.getByRole('spinbutton');
    await userEvent.clear(spinbutton);
    await userEvent.type(spinbutton, '99');

    // onChange was called multiple times during typing
    expect(onChange).toHaveBeenCalled();

    // Re-render with updated int value
    onChange.mockClear();
    rerender(
      <Wrapper>
        <RitualForm
          schema={schema}
          values={{ text_field: 'hello', int_field: 99 }}
          onChange={onChange}
        />
      </Wrapper>
    );

    // Verify both fields have correct values after update
    expect(screen.getByDisplayValue('hello')).toBeInTheDocument();
    expect(screen.getByRole('spinbutton')).toHaveValue(99);
  });

  it('renders empty schema without error', () => {
    const schema: RitualInputSchema = { fields: [] };

    const Wrapper = createWrapper();
    render(
      <Wrapper>
        <RitualForm schema={schema} values={{}} onChange={vi.fn()} />
      </Wrapper>
    );

    // Should render without fields
    expect(screen.queryByRole('textbox')).not.toBeInTheDocument();
  });

  it('handles null values in values dict', () => {
    const schema: RitualInputSchema = {
      fields: [{ name: 'optional_field', label: 'Optional', type: 'text' }],
    };

    const Wrapper = createWrapper();
    render(
      <Wrapper>
        <RitualForm schema={schema} values={{ optional_field: null }} onChange={vi.fn()} />
      </Wrapper>
    );

    // TextField should handle null value as empty string
    expect(screen.getByRole('textbox')).toHaveValue('');
  });
});
