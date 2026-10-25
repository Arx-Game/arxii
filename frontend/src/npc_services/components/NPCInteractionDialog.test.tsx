/**
 * #4457: each offer in the summoned-NPC menu carries the server's price line
 * (`price.display`), printed after the label verbatim; an offer without a
 * price shows its label alone. #4659: a course taught under a Tradition adds its
 * teaching line under the price.
 */
import { render, screen } from '@testing-library/react';
import { vi } from 'vitest';

const startInteraction = vi.fn();
vi.mock('../interaction', () => ({
  startInteraction: (...args: unknown[]) => startInteraction(...args),
  resolveOffer: vi.fn(),
  endInteraction: vi.fn(),
}));

vi.mock('@/roster/useBrowsingIdentity', () => ({
  useBrowsingIdentity: () => ({ entryId: 5, name: 'Aria', entry: null }),
}));

import { NPCInteractionDialog } from './NPCInteractionDialog';

const ENROLL_LINE = 'Enroll: 2s · 1 Golden Hare · 6 AP a session, the first one now';

const price = (display: string, teaching_line: string | null = null) => ({
  ap: 6,
  coppers: 200,
  golden_hares: 1,
  per_session_ap: 6,
  development_remaining: null,
  development_total: null,
  training_points: null,
  teaching_line,
  display,
});

beforeEach(() => {
  vi.clearAllMocks();
  startInteraction.mockResolvedValue({
    closed: false,
    last_result_message: null,
    available_offers: [
      { id: 1, label: 'Course: Occult', kind: 'skill_course', price: price(ENROLL_LINE) },
      { id: 2, label: 'Ask for work', kind: 'mission', price: null },
    ],
  });
});

describe('NPCInteractionDialog price line (#4457)', () => {
  it("prints an offer's price display after its label", async () => {
    render(
      <NPCInteractionDialog
        roleId={12}
        title="Academy Trainer"
        open
        onOpenChange={() => undefined}
      />
    );

    const course = await screen.findByRole('button', { name: /Course: Occult/ });
    expect(course).toHaveTextContent(`Course: Occult${ENROLL_LINE}`);
  });

  it('shows the label alone when the offer has no price', async () => {
    render(
      <NPCInteractionDialog
        roleId={12}
        title="Academy Trainer"
        open
        onOpenChange={() => undefined}
      />
    );

    const mission = await screen.findByRole('button', { name: 'Ask for work' });
    expect(mission).toHaveTextContent(/^Ask for work$/);
  });

  it("prints a course's teaching line under its price (#4659)", async () => {
    const TEACHING =
      'Taught in the manner of Smiling Shadows. Teaches well: your Shadowcraft. Sessions are easier for you.';
    startInteraction.mockResolvedValue({
      closed: false,
      last_result_message: null,
      available_offers: [
        {
          id: 1,
          label: 'Course: Occult',
          kind: 'skill_course',
          price: price(ENROLL_LINE, TEACHING),
        },
      ],
    });
    render(
      <NPCInteractionDialog
        roleId={12}
        title="Academy Trainer"
        open
        onOpenChange={() => undefined}
      />
    );

    const course = await screen.findByRole('button', { name: /Course: Occult/ });
    expect(course).toHaveTextContent(`Course: Occult${ENROLL_LINE}${TEACHING}`);
  });
});
