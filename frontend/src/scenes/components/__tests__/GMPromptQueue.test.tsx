import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { renderWithProviders } from '@/test/utils/renderWithProviders';
import type { GMPrompt } from '../../types';

vi.mock('../../gmPromptQueries', async (orig) => ({
  ...(await orig<typeof import('../../gmPromptQueries')>()),
  useGMPrompts: vi.fn(),
}));

import { GMPromptQueue } from '../GMPromptQueue';
import { useGMPrompts } from '../../gmPromptQueries';

const mockUseGMPrompts = vi.mocked(useGMPrompts);

const crossing: GMPrompt = {
  id: 7,
  kind: 'crossing',
  kind_label: 'Crossing',
  status: 'pending',
  scene: 1,
  character_sheet: 3,
  subject_name: 'Rowan Ashcombe',
  subject_persona_id: 30,
  moment_type: null,
  moment_type_label: '',
  technique_name: '',
  stake_summary: '',
  room_text: 'room',
  private_text: 'vision',
  prepared_for_character: true,
  created_at: '2026-10-02T00:00:00Z',
};
const moment: GMPrompt = {
  ...crossing,
  id: 8,
  kind: 'dramatic_moment',
  kind_label: 'Dramatic Moment',
  subject_name: 'Tamsin Vale',
  moment_type_label: 'stand against the collapse',
};

describe('GMPromptQueue', () => {
  beforeEach(() => {
    mockUseGMPrompts.mockReturnValue({
      data: [crossing, moment],
      isLoading: false,
    } as unknown as ReturnType<typeof useGMPrompts>);
  });

  it('lists every prompt kind in one queue', () => {
    renderWithProviders(<GMPromptQueue sceneId="1" personas={[]} />);
    expect(screen.getByText('GM prompts')).toBeInTheDocument();
    expect(screen.getByText('Crossing')).toBeInTheDocument();
    expect(screen.getByText('Dramatic Moment')).toBeInTheDocument();
  });

  it('offers Open on narration prompts and Confirm on dramatic moments', () => {
    renderWithProviders(<GMPromptQueue sceneId="1" personas={[]} />);
    expect(screen.getByRole('button', { name: /open crossing/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /confirm dramatic moment/i })).toBeInTheDocument();
  });
});

describe('GMPromptQueue — empty queue', () => {
  it('renders nothing with an empty queue', () => {
    mockUseGMPrompts.mockReturnValue({
      data: [],
      isLoading: false,
    } as unknown as ReturnType<typeof useGMPrompts>);
    const { container } = render(<GMPromptQueue sceneId="1" personas={[]} />);
    expect(container).toBeEmptyDOMElement();
  });
});
