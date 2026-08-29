/**
 * AuthorClueDialog (#3432) — dispatch payload + SECRET-gate visibility tests.
 *
 * Mocks the mutation/actor hooks so the dialog renders synchronously (mirrors
 * StaffSecretsPanel.test.tsx). jsdom can't drive Radix Select's popover/
 * pointer-capture interactions, so `@/components/ui/select` is mocked down to
 * a native `<select>` — the same pattern `BoonAskForm.test.tsx` and
 * `stories/__tests__/SubjectRefFields.test.tsx` use.
 */
import type { ReactNode } from 'react';

import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { AuthorClueDialog } from './AuthorClueDialog';

const mutate = vi.fn();

vi.mock('@/clues/queries', () => ({
  useAuthorClueMutation: vi.fn(() => ({
    mutate,
    isPending: false,
  })),
}));

vi.mock('@/world-builder/useWorldBuilderActor', () => ({
  useWorldBuilderActor: vi.fn(() => 42),
}));

vi.mock('@/store/hooks', () => ({
  useAccount: vi.fn(() => ({ is_staff: false })),
}));

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}));

vi.mock('@/components/ui/select', () => ({
  Select: ({
    value,
    onValueChange,
    children,
  }: {
    value?: string;
    onValueChange?: (v: string) => void;
    children?: ReactNode;
  }) => (
    <select
      aria-label="Target kind"
      value={value ?? ''}
      onChange={(e) => onValueChange?.(e.target.value)}
    >
      {children}
    </select>
  ),
  SelectTrigger: ({ children }: { children?: ReactNode }) => <>{children}</>,
  SelectValue: () => null,
  SelectContent: ({ children }: { children?: ReactNode }) => <>{children}</>,
  SelectItem: ({ value, children }: { value: string; children?: ReactNode }) => (
    <option value={value}>{children}</option>
  ),
}));

import { useAccount } from '@/store/hooks';

const mockUseAccount = vi.mocked(useAccount);

function openDialog(props: Partial<Parameters<typeof AuthorClueDialog>[0]> = {}) {
  render(<AuthorClueDialog trigger={<button>Open</button>} {...props} />);
  fireEvent.click(screen.getByText('Open'));
}

describe('AuthorClueDialog', () => {
  beforeEach(() => {
    mutate.mockClear();
    mockUseAccount.mockReturnValue({ is_staff: false } as ReturnType<typeof useAccount>);
  });

  it('dispatches author_clue with the entered fields for a codex target', () => {
    openDialog();

    fireEvent.change(screen.getByLabelText('Name'), { target: { value: 'Torn Journal Page' } });
    fireEvent.change(screen.getByLabelText('Clue text'), {
      target: { value: 'A page torn from a diary.' },
    });
    fireEvent.change(screen.getByLabelText('Target id'), { target: { value: '7' } });
    fireEvent.click(screen.getByTestId('author-clue-submit'));

    expect(mutate).toHaveBeenCalledWith(
      {
        name: 'Torn Journal Page',
        description: 'A page torn from a diary.',
        target_kind: 'codex',
        target_id: 7,
      },
      expect.anything()
    );
  });

  it('sends target_secondary_id alongside target_id for a persona_link target', () => {
    openDialog();

    fireEvent.change(screen.getByLabelText('Target kind'), {
      target: { value: 'persona_link' },
    });
    fireEvent.change(screen.getByLabelText('Name'), { target: { value: 'The Second Face' } });
    fireEvent.change(screen.getByLabelText('Clue text'), {
      target: { value: 'The mask slips, just once.' },
    });
    fireEvent.change(screen.getByLabelText('Target id'), { target: { value: '3' } });
    fireEvent.change(screen.getByLabelText(/linked persona/i), { target: { value: '4' } });
    fireEvent.click(screen.getByTestId('author-clue-submit'));

    expect(mutate).toHaveBeenCalledWith(
      {
        name: 'The Second Face',
        description: 'The mask slips, just once.',
        target_kind: 'persona_link',
        target_id: 3,
        target_secondary_id: 4,
      },
      expect.anything()
    );
  });

  it('keeps the submit button disabled until name, text, and target id are filled', () => {
    openDialog();
    expect(screen.getByTestId('author-clue-submit')).toBeDisabled();

    fireEvent.change(screen.getByLabelText('Name'), { target: { value: 'x' } });
    fireEvent.change(screen.getByLabelText('Clue text'), { target: { value: 'y' } });
    expect(screen.getByTestId('author-clue-submit')).toBeDisabled();

    fireEvent.change(screen.getByLabelText('Target id'), { target: { value: '1' } });
    expect(screen.getByTestId('author-clue-submit')).not.toBeDisabled();
  });

  it('keeps submit disabled for a persona_link target until the second persona id is set', () => {
    openDialog();
    fireEvent.change(screen.getByLabelText('Target kind'), {
      target: { value: 'persona_link' },
    });
    fireEvent.change(screen.getByLabelText('Name'), { target: { value: 'x' } });
    fireEvent.change(screen.getByLabelText('Clue text'), { target: { value: 'y' } });
    fireEvent.change(screen.getByLabelText('Target id'), { target: { value: '1' } });

    expect(screen.getByTestId('author-clue-submit')).toBeDisabled();

    fireEvent.change(screen.getByLabelText(/linked persona/i), { target: { value: '2' } });
    expect(screen.getByTestId('author-clue-submit')).not.toBeDisabled();
  });

  it('hides the SECRET target kind option for a non-staff account', () => {
    openDialog();
    expect(screen.queryByText('Character Secret')).not.toBeInTheDocument();
  });

  it('shows the SECRET target kind option for a staff account', () => {
    mockUseAccount.mockReturnValue({ is_staff: true } as ReturnType<typeof useAccount>);
    openDialog();
    expect(screen.getByText('Character Secret')).toBeInTheDocument();
  });

  it('locks target_kind to secret and hides the picker when lockedSecretId is given', () => {
    openDialog({ lockedSecretId: 9 });

    expect(screen.queryByLabelText('Target kind')).not.toBeInTheDocument();
    expect(screen.queryByLabelText('Target id')).not.toBeInTheDocument();

    fireEvent.change(screen.getByLabelText('Name'), { target: { value: 'A Whisper Overheard' } });
    fireEvent.change(screen.getByLabelText('Clue text'), {
      target: { value: 'Something said in passing.' },
    });
    fireEvent.click(screen.getByTestId('author-clue-submit'));

    expect(mutate).toHaveBeenCalledWith(
      {
        name: 'A Whisper Overheard',
        description: 'Something said in passing.',
        target_kind: 'secret',
        target_id: 9,
      },
      expect.anything()
    );
  });
});
