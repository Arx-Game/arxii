import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi, beforeEach } from 'vitest';
import type {
  DiscoveryChallenge,
  DiscoveryKind,
  DiscoveryResult,
  DiscoveryTemplate,
} from '../types';

const mockMutateAsync = vi.fn(() =>
  Promise.resolve({ backend: 'registry', deferred: false, success: true, message: 'Done.' })
);
vi.mock('@/combat/queries', () => ({
  useDispatchPlayerAction: vi.fn(() => ({ mutateAsync: mockMutateAsync, isPending: false })),
}));

vi.mock('sonner', () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
  },
}));

vi.mock('../queries', () => ({
  useDiscovery: vi.fn(),
}));

import { SituationFinder } from '../SituationFinder';
import { useDiscovery } from '../queries';

const checkFitKind: DiscoveryKind = {
  id: 11,
  name: 'Chase',
  description: 'A pursuit through the rooftops.',
  minimum_gm_level: 'junior',
  check_fits: [{ check_type: { id: 7, name: 'Sprint' }, fit_notes: 'footspeed' }],
  difficulty_guide: { risk: 'high', recommended_difficulty: 'hard', guidance_text: 'Real stakes' },
  all_guides: [{ risk: 'high', recommended_difficulty: 'hard', guidance_text: 'Real stakes' }],
  pool_guides: [
    { pool: { id: 3, name: 'Chase pool' }, selection_criteria: 'when they run', is_default: true },
  ],
};

const template: DiscoveryTemplate = {
  id: 5,
  name: 'Rooftop chase',
  category: 1,
  category_name: 'Pursuit',
  description_template: 'Tiles',
};

const challenge: DiscoveryChallenge = {
  id: 9,
  name: 'Chase the courier',
  category: 1,
  category_name: 'Pursuit',
  severity: 4,
  description_template: '',
  goal: 'Catch him',
};

const fullResult: DiscoveryResult = {
  kinds: [checkFitKind],
  templates: [template],
  challenges: [challenge],
};

const emptyResult: DiscoveryResult = { kinds: [], templates: [], challenges: [] };

function mockDiscovery(data: DiscoveryResult) {
  vi.mocked(useDiscovery).mockReturnValue({ data } as unknown as ReturnType<typeof useDiscovery>);
}

beforeEach(() => {
  vi.mocked(useDiscovery).mockReset();
  mockMutateAsync.mockClear();
});

describe('SituationFinder', () => {
  it('opens cold on the kind list and shows fits, guide and pool guidance', () => {
    mockDiscovery(fullResult);

    render(<SituationFinder risk="high" actions={{}} characterId={42} />);

    expect(screen.getByTestId('finder-kind')).toHaveTextContent('Chase');
    expect(screen.getByTestId('finder-check-fit')).toHaveTextContent('Sprint');
    expect(screen.getByTestId('finder-guide')).toHaveTextContent(/hard/i);
    expect(screen.getByTestId('finder-pool-guide')).toHaveTextContent('Chase pool');
  });

  it('passes the typed query and the risk to useDiscovery', async () => {
    const user = userEvent.setup();
    mockDiscovery(emptyResult);

    render(<SituationFinder risk="high" actions={{}} characterId={null} />);
    await user.type(screen.getByTestId('finder-search'), 'chase');

    expect(vi.mocked(useDiscovery)).toHaveBeenLastCalledWith('chase', 'high', true);
  });

  it('fires the template and challenge actions with the row', async () => {
    const user = userEvent.setup();
    mockDiscovery(fullResult);
    const onSelectTemplate = vi.fn();
    const onSelectChallenge = vi.fn();

    render(
      <SituationFinder
        risk={null}
        actions={{
          template: { label: 'Stage', onSelect: onSelectTemplate },
          challenge: { label: 'Place', onSelect: onSelectChallenge },
        }}
        characterId={null}
      />
    );

    await user.click(screen.getByRole('button', { name: 'Stage' }));
    expect(onSelectTemplate).toHaveBeenCalledWith(expect.objectContaining({ id: 5 }));

    await user.click(screen.getByRole('button', { name: 'Place' }));
    expect(onSelectChallenge).toHaveBeenCalledWith(expect.objectContaining({ id: 9 }));
  });

  it('fires the check action with the guide band for the risk', async () => {
    const user = userEvent.setup();
    mockDiscovery(fullResult);
    const onSelectCheck = vi.fn();

    render(
      <SituationFinder
        risk="high"
        actions={{ check: { label: 'Call', onSelect: onSelectCheck } }}
        characterId={null}
      />
    );

    await user.click(screen.getByRole('button', { name: 'Call' }));

    expect(onSelectCheck).toHaveBeenCalledWith({ id: 7, name: 'Sprint' }, 'hard');
  });

  it('passes a null band when there is no guide for the risk', async () => {
    const user = userEvent.setup();
    mockDiscovery({
      kinds: [{ ...checkFitKind, difficulty_guide: null, all_guides: [] }],
      templates: [],
      challenges: [],
    });
    const onSelectCheck = vi.fn();

    render(
      <SituationFinder
        risk="low"
        actions={{ check: { label: 'Call', onSelect: onSelectCheck } }}
        characterId={null}
      />
    );

    await user.click(screen.getByRole('button', { name: 'Call' }));

    expect(onSelectCheck).toHaveBeenCalledWith({ id: 7, name: 'Sprint' }, null);
  });

  it('hides action buttons that the host did not provide', () => {
    mockDiscovery(fullResult);

    render(<SituationFinder risk="high" actions={{}} characterId={null} />);

    expect(screen.queryAllByRole('button')).toHaveLength(0);
  });

  it('hides Suggest when there is no character', () => {
    mockDiscovery(fullResult);

    render(<SituationFinder risk="high" actions={{}} characterId={null} />);

    expect(screen.queryByTestId('finder-suggest')).not.toBeInTheDocument();
  });

  it('shows the empty state when nothing matches a query', async () => {
    const user = userEvent.setup();
    mockDiscovery(emptyResult);

    render(<SituationFinder risk={null} actions={{}} characterId={null} />);
    await user.type(screen.getByTestId('finder-search'), 'zzz');

    expect(screen.getByTestId('finder-empty')).toBeInTheDocument();
  });
});
