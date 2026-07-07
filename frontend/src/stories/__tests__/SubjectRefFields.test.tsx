/**
 * SubjectRefFields tests (#2001 Task 8) — kind-driven typed reference picker
 * shared by ProtectedSubjectFormDialog and RequestClearanceDialog.
 */

import { useState } from 'react';
import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi } from 'vitest';
import { renderWithProviders } from '@/test/utils/renderWithProviders';
import {
  emptySubjectRef,
  SubjectRefFields,
  type SubjectRefValue,
} from '../components/SubjectRefFields';
import type { SubjectKindEnum } from '../types';

vi.mock('@/components/ui/select', () => ({
  Select: ({
    value,
    onValueChange,
    children,
    disabled,
  }: {
    value?: string;
    onValueChange?: (v: string) => void;
    children?: React.ReactNode;
    disabled?: boolean;
  }) => (
    <select
      value={value}
      disabled={disabled}
      onChange={(e) => onValueChange?.(e.target.value)}
      data-testid="mock-select"
    >
      {children}
    </select>
  ),
  SelectTrigger: ({ children }: { children?: React.ReactNode }) => <>{children}</>,
  SelectValue: () => null,
  SelectContent: ({ children }: { children?: React.ReactNode }) => <>{children}</>,
  SelectItem: ({ value, children }: { value: string; children?: React.ReactNode }) => (
    <option value={value}>{children}</option>
  ),
}));

vi.mock('@/events/queries', () => ({
  searchOrganizations: vi.fn().mockResolvedValue([]),
  searchSocieties: vi.fn().mockResolvedValue([]),
}));

function Harness({ initialKind = 'custom' }: { initialKind?: SubjectKindEnum }) {
  const [value, setValue] = useState<SubjectRefValue>(emptySubjectRef(initialKind));
  return <SubjectRefFields value={value} onChange={setValue} />;
}

describe('SubjectRefFields', () => {
  it('shows a character sheet id input for npc_fate', () => {
    renderWithProviders(<Harness initialKind="npc_fate" />);
    expect(screen.getByLabelText(/character sheet id/i)).toBeInTheDocument();
  });

  it('shows an item instance id input for item', () => {
    renderWithProviders(<Harness initialKind="item" />);
    expect(screen.getByLabelText(/item instance id/i)).toBeInTheDocument();
  });

  it('shows a freeform label input for custom', () => {
    renderWithProviders(<Harness initialKind="custom" />);
    expect(screen.getByLabelText(/^label$/i)).toBeInTheDocument();
  });

  it('shows the society/organization toggle for faction', () => {
    renderWithProviders(<Harness initialKind="faction" />);
    expect(screen.getByText('Faction level')).toBeInTheDocument();
    expect(screen.getByLabelText(/society/i)).toBeInTheDocument();
  });

  it('switching kind resets the previously-set ref fields', async () => {
    const user = userEvent.setup();
    renderWithProviders(<Harness initialKind="npc_fate" />);

    await user.type(screen.getByLabelText(/character sheet id/i), '42');
    expect(screen.getByLabelText(/character sheet id/i)).toHaveValue('42');

    const kindSelect = screen.getAllByTestId('mock-select')[0];
    await user.selectOptions(kindSelect, 'custom');

    expect(screen.getByLabelText(/^label$/i)).toHaveValue('');
  });
});
