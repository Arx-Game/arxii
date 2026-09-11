import { test, expect, type Page } from '@playwright/test';

import {
  mockRestRoutes,
  reachReadySession,
  pushForeignPose,
  type Connection,
} from './support/gameHarness';

/**
 * #3761 Task 7 — Playwright journey proving cross-mode encounter
 * reachability end-to-end, in a real running app (Tasks 1-6 built the
 * pieces; this proves them wired together and proves the thing the human
 * explicitly raised during design: ordinary conversation keeps flowing in
 * the center reading pane while the combat rail is open in the sidebar —
 * already true at the code level (composer/reader have zero
 * encounter-awareness), never proven against a real running app before now.
 *
 * A note on how "an encounter starts" is simulated: the plan's draft
 * expected a fake-WS push, but `GamePage`'s `useEncounterForScene`
 * (`src/combat/queries.ts`) learns of an active encounter purely by polling
 * `GET /api/combat/?scene=<id>` — there is no WS-pushed "encounter start"
 * event anywhere in this codebase to reuse or extend. So these journeys
 * boot straight into a scene with an already-active encounter (mocked via
 * `mockRestRoutes`'s `activeEncounterId` option) rather than faking a live
 * mid-session transition — this still exercises the exact same reachability
 * wiring (Tasks 1-6): `hasActiveEncounter` flows from that same query into
 * `GameTopBar`'s banner and `PlaySidebar`'s nav icon either way.
 */

const ENCOUNTER_ID = 77;

/**
 * Boots `/game` into an active scene with an already-active encounter, in
 * the sidebar's default Conversations mode (explicit click below, matching
 * `narrative-play-delivery.spec.ts`'s own established pattern, even though
 * `GamePage`'s initial `sidebarMode` already defaults to 'conversations'
 * whenever a scene is active — being explicit doesn't depend on that default
 * holding).
 */
async function bootWithActiveEncounter(page: Page): Promise<Connection[]> {
  await mockRestRoutes(page, { activeEncounterId: ENCOUNTER_ID });
  const connections = await reachReadySession(page);
  await page
    .getByRole('navigation', { name: 'Sidebar modes' })
    .getByRole('button', { name: 'Conversations', exact: true })
    .click();
  return connections;
}

test.describe('#3761 encounter reachability', () => {
  test('banner and nav icon both appear and both route to the rail while reading Conversations', async ({
    page,
  }) => {
    await bootWithActiveEncounter(page);

    // Both Task 1-3/5 surfaces reach the SAME active encounter while the
    // sidebar is showing an unrelated mode (Conversations, not Here).
    const banner = page.getByText(/in combat/i).first();
    await expect(banner).toBeVisible();
    const sidebarNav = page.getByRole('navigation', { name: 'Sidebar modes' });
    const combatNavButton = sidebarNav.getByRole('button', { name: 'Combat', exact: true });
    await expect(combatNavButton).toBeVisible();

    // Click the TOP-BAR banner (Task 2) — assert it jumps the sidebar to
    // Here mode's Room tab, where CombatRail (Task 5's prop wiring) renders.
    await banner.click();

    await expect(sidebarNav.getByRole('button', { name: 'Here', exact: true })).toHaveAttribute(
      'aria-current',
      'page'
    );
    await expect(page.getByTestId('combat-rail')).toBeVisible();
    await expect(page.getByRole('tab', { name: /your turn/i })).toBeVisible();
  });

  test('clicking the sidebar Combat nav icon also routes to the rail', async ({ page }) => {
    // The SECOND reachability path from Tasks 1-6 (the sidebar nav icon,
    // distinct from the top-bar banner exercised above) — both are real,
    // independently wired routes to the same destination.
    await bootWithActiveEncounter(page);

    const sidebarNav = page.getByRole('navigation', { name: 'Sidebar modes' });
    await sidebarNav.getByRole('button', { name: 'Combat', exact: true }).click();

    await expect(sidebarNav.getByRole('button', { name: 'Here', exact: true })).toHaveAttribute(
      'aria-current',
      'page'
    );
    await expect(page.getByTestId('combat-rail')).toBeVisible();
    await expect(page.getByRole('tab', { name: /your turn/i })).toBeVisible();
  });

  test('ordinary conversation keeps flowing while the rail is open', async ({ page }) => {
    const connections = await bootWithActiveEncounter(page);
    await page
      .getByText(/in combat/i)
      .first()
      .click();
    await expect(page.getByRole('tab', { name: /your turn/i })).toBeVisible();

    // A foreign persona's pose arrives over the WS while the rail is open in
    // the sidebar — the exact concern the human raised during design.
    const poseContent = 'A raven wheels overhead, unbothered by the fighting below.';
    pushForeignPose(connections[0], { id: 9101, content: poseContent });

    // It reaches the center reading pane...
    await expect(page.getByText(poseContent)).toBeVisible();
    // ...and the combat rail stayed mounted and visible throughout — the
    // reader and the rail are genuinely independent surfaces, not one
    // replacing the other.
    await expect(page.getByTestId('combat-rail')).toBeVisible();
    await expect(page.getByRole('tab', { name: /your turn/i })).toBeVisible();
  });

  test('the composer stays enabled and accepts an ordinary pose during an active encounter', async ({
    page,
  }) => {
    const connections = await bootWithActiveEncounter(page);
    await expect(page.getByText(/in combat/i).first()).toBeVisible();

    // The room composer (no conversation tab open) submits a plain pose via
    // REST `POST /api/interactions/submit-pose/` (CommandInput.tsx) — mock
    // it to succeed, exactly like a real server would while combat is live
    // (the composer carries zero encounter-awareness, so this is expected
    // to behave no differently than outside combat).
    let submittedContent: string | null = null;
    await page.route('**/api/interactions/submit-pose/', async (route) => {
      const body = route.request().postDataJSON() as { content?: string };
      submittedContent = body.content ?? null;
      await route.fulfill({ json: { id: 555 } });
    });

    const editor = page.getByRole('textbox');
    const sendButton = page.getByRole('button', { name: 'Send', exact: true });
    // Nothing about an active encounter disables the room composer — the
    // real regression this test guards: if a future change ever gated
    // CommandInput on `hasActiveEncounter`, this would start failing here.
    await expect(editor).toBeEnabled();
    await expect(sendButton).toBeEnabled();

    const poseText = 'Tehom steadies her footing despite the chaos.';
    await editor.fill(poseText);
    await editor.press('Control+Enter');

    await expect.poll(() => submittedContent).toBe(poseText);
    // No disabled state blocked the submission or got stuck afterward.
    await expect(editor).toBeEnabled();
    await expect(sendButton).toBeEnabled();
    await expect(editor).toHaveValue('');

    // The feed itself is WS-driven (GamePage.tsx: "the WS-pushed interaction
    // with no React Query cache to invalidate") — echo the accepted pose
    // back the way a real backend broadcasts a newly created Interaction to
    // the room, including back to its own sender, and confirm it lands.
    connections[0].route.send(
      JSON.stringify([
        'interaction',
        [],
        {
          id: 555,
          persona: { id: 7, name: 'Tehom', thumbnail_url: '' },
          content: poseText,
          mode: 'pose',
          timestamp: new Date().toISOString(),
          scene_id: 1,
          place_id: null,
          place_name: null,
          receiver_persona_ids: [],
          target_persona_ids: [],
        },
      ])
    );
    await expect(page.getByText(poseText)).toBeVisible();
  });
});
