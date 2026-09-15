import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi } from 'vitest';
import { FamilyTemplateForm } from '../../../components/lineage/FamilyTemplateForm';
import { mockFamilyTemplate } from '../../fixtures';

describe('FamilyTemplateForm', () => {
  it('renders features read-only and one card per aspect option', () => {
    render(<FamilyTemplateForm template={mockFamilyTemplate} picks={{}} onToggle={vi.fn()} />);
    expect(screen.getByText(mockFamilyTemplate.features[0].name)).toBeInTheDocument();
    const charge = mockFamilyTemplate.aspect_definitions[0];
    expect(screen.getByText(charge.prompt)).toBeInTheDocument();
    for (const option of charge.options) {
      expect(screen.getByRole('button', { name: new RegExp(option.name) })).toBeInTheDocument();
    }
  });

  it('reports a toggle with the definition, option and max picks', async () => {
    const onToggle = vi.fn();
    render(<FamilyTemplateForm template={mockFamilyTemplate} picks={{}} onToggle={onToggle} />);
    const charge = mockFamilyTemplate.aspect_definitions[0];
    await userEvent.click(screen.getByRole('button', { name: new RegExp(charge.options[0].name) }));
    expect(onToggle).toHaveBeenCalledWith(charge.id, charge.options[0].id, charge.max_picks);
  });

  it('marks a picked option pressed', () => {
    const charge = mockFamilyTemplate.aspect_definitions[0];
    render(
      <FamilyTemplateForm
        template={mockFamilyTemplate}
        picks={{ [charge.id]: [charge.options[1].id] }}
        onToggle={vi.fn()}
      />
    );
    expect(
      screen.getByRole('button', { name: new RegExp(charge.options[1].name) })
    ).toHaveAttribute('aria-pressed', 'true');
  });
});
