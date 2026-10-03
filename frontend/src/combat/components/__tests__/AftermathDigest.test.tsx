/**
 * Tests for AftermathDigest's "Won over" section (#4091 fix round 1, item 5).
 *
 * WonOverRows itself is covered by combat/__tests__/WonOverRows.test.tsx — this
 * file only pins AftermathDigest's own decision of when to render the
 * "Won over" heading + `data-testid="aftermath-won-over"` wrapper.
 */

import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { AftermathDigest } from '../AftermathDigest';
import type { AftermathDigest as AftermathDigestData } from '../AftermathDigest';

vi.mock('../WonOverRows', () => ({
  WonOverRows: ({ rows }: { rows: unknown[] }) => (
    <div data-testid="won-over-rows-stub">{rows.length} row(s)</div>
  ),
}));

function baseDigest(overrides: Partial<AftermathDigestData> = {}): AftermathDigestData {
  return {
    outcome: 'victory',
    consequence: null,
    conditions: [],
    legend: [],
    beat: null,
    objective: null,
    peril_round_active: false,
    won_over: [],
    ...overrides,
  } as AftermathDigestData;
}

describe('AftermathDigest, Won over section (#4091)', () => {
  it('renders nothing for Won over when won_over is empty', () => {
    render(<AftermathDigest digest={baseDigest({ won_over: [] })} characterId={42} sceneId="1" />);

    expect(screen.queryByTestId('aftermath-won-over')).not.toBeInTheDocument();
  });

  it('renders the Won over heading and WonOverRows when won_over is non-empty', () => {
    const wonOverRow = {
      opponent_id: 7,
      name: 'Road Bandit',
      verb: 'charmed',
      source_label: "Wren's Sweet Talk",
      nameless: true,
      persona_id: null,
      present: true,
      condition: null,
      holds_until_settled: true,
      strength: 3,
      can_bind: true,
      can_take_into_service: false,
      can_send_away: true,
      can_settle: false,
    };

    render(
      <AftermathDigest
        digest={baseDigest({ won_over: [wonOverRow] } as Partial<AftermathDigestData>)}
        characterId={42}
        sceneId="1"
      />
    );

    const section = screen.getByTestId('aftermath-won-over');
    expect(section).toHaveTextContent('Won over');
    expect(screen.getByTestId('won-over-rows-stub')).toHaveTextContent('1 row(s)');
  });
});
