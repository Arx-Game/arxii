/**
 * SceneLinesAndVeilsCard tests (#1771) — read-only aggregate card. Must show
 * shared ADVISORY content + shared treasured subjects, and must NEVER show
 * an owner (the aggregate is anonymized by construction — see
 * world.boundaries.services.scene_lines_and_veils).
 */

import { screen, waitFor, fireEvent } from '@testing-library/react';
import { vi } from 'vitest';
import { renderWithProviders } from '@/test/utils/renderWithProviders';
import { SceneLinesAndVeilsCard } from '../components/SceneLinesAndVeilsCard';

// Mock MyTenureSelect so we can control character selection directly,
// mirroring src/consent/__tests__/PrivacyPage.test.tsx.
vi.mock('@/components/MyTenureSelect', () => ({
  default: ({
    value,
    onChange,
    label,
  }: {
    value: number | null;
    onChange: (v: number | null) => void;
    label?: string;
  }) => (
    <div>
      <label htmlFor="my-tenure-select">{label ?? 'Character'}</label>
      <select
        id="my-tenure-select"
        value={value ?? ''}
        onChange={(e) => onChange(e.target.value ? Number(e.target.value) : null)}
      >
        <option value="">Select tenure</option>
        <option value="1">Aria</option>
      </select>
    </div>
  ),
}));

vi.mock('../queries', () => ({
  useSceneLinesAndVeils: vi.fn(),
}));

import * as queries from '../queries';

function selectTenure() {
  fireEvent.change(screen.getByLabelText('View as'), { target: { value: '1' } });
}

describe('SceneLinesAndVeilsCard', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('shows shared advisory content and treasured subjects, never an owner', async () => {
    vi.mocked(queries.useSceneLinesAndVeils).mockReturnValue({
      data: {
        advisories: [{ theme_name: 'Body horror', detail: 'Prefer it off-page.' }],
        treasured_subjects: [
          { subject_kind: 'npc_fate', subject_label: 'Captain Elara', detail: 'Do not kill.' },
        ],
      },
      isLoading: false,
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
    } as any);

    const { container } = renderWithProviders(<SceneLinesAndVeilsCard sceneId="42" />);
    selectTenure();

    await waitFor(() => {
      expect(screen.getByText('Body horror')).toBeInTheDocument();
    });
    expect(screen.getByText(/Prefer it off-page\./)).toBeInTheDocument();
    expect(screen.getByText('Captain Elara')).toBeInTheDocument();
    expect(screen.getByText(/Do not kill\./)).toBeInTheDocument();

    // No owner-identifying text anywhere in the rendered output.
    expect(container.innerHTML).not.toMatch(/owner/i);
  });

  it('shows an empty state when nothing is shared', async () => {
    vi.mocked(queries.useSceneLinesAndVeils).mockReturnValue({
      data: { advisories: [], treasured_subjects: [] },
      isLoading: false,
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
    } as any);

    renderWithProviders(<SceneLinesAndVeilsCard sceneId="42" />);
    selectTenure();

    await waitFor(() => {
      expect(screen.getByText(/nothing shared|no lines/i)).toBeInTheDocument();
    });
  });
});
