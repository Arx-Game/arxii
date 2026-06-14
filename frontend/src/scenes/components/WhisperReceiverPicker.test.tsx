import { fireEvent, screen } from '@testing-library/react';
import { vi } from 'vitest';
import { WhisperReceiverPicker } from './WhisperReceiverPicker';
import { renderWithProviders } from '@/test/utils/renderWithProviders';
import type { ScenePersona } from '@/scenes/types';

const candidates: ScenePersona[] = [
  { id: 11, name: 'Brand' },
  { id: 12, name: 'Corwin' },
];

describe('WhisperReceiverPicker', () => {
  it('lists candidates and confirms the selected ids', () => {
    const onConfirm = vi.fn();
    renderWithProviders(
      <WhisperReceiverPicker
        open
        onClose={() => {}}
        targetName="Random"
        candidates={candidates}
        onConfirm={onConfirm}
      />
    );

    expect(screen.getByText('Brand')).toBeInTheDocument();
    expect(screen.getByText('Corwin')).toBeInTheDocument();

    fireEvent.click(screen.getByLabelText('Corwin'));
    fireEvent.click(screen.getByRole('button', { name: /Whisper to 2/ }));

    expect(onConfirm).toHaveBeenCalledWith([12]);
  });

  it('confirms an empty list when nothing is selected', () => {
    const onConfirm = vi.fn();
    renderWithProviders(
      <WhisperReceiverPicker
        open
        onClose={() => {}}
        targetName="Random"
        candidates={candidates}
        onConfirm={onConfirm}
      />
    );

    fireEvent.click(screen.getByRole('button', { name: /target only/ }));
    expect(onConfirm).toHaveBeenCalledWith([]);
  });

  it('shows an empty state when no one else is present', () => {
    renderWithProviders(
      <WhisperReceiverPicker
        open
        onClose={() => {}}
        targetName="Random"
        candidates={[]}
        onConfirm={() => {}}
      />
    );

    expect(screen.getByTestId('whisper-picker-empty')).toBeInTheDocument();
  });
});
