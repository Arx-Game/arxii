import { test, expect } from '@playwright/test';
import { mockRestRoutes, reachReadySession, type Connection } from './support/gameHarness';

/**
 * #3807 evidence — live outcome delivery (the amber "This happened to you"
 * involvement mark on a resolved social check) and the resolution wheel (the
 * `roulette_result` modal, now a flat proportional-slice SVG disc instead of
 * the old equal-faced prism). Fixture-backed against the mocked `/game`
 * WebSocket, the same harness `narrative-play-delivery.spec.ts` and
 * `pushForeignPose`'s own callers already use — not a live-backend
 * integration test.
 */

/** Pushes a raw `interaction` frame with an explicit mode/target list — the
 * shape `pushForeignPose` already sends, but that helper only varies
 * id/content/sceneId, not `mode`/`target_persona_ids`, which this evidence
 * needs to vary directly. */
function pushActionRow(
  connection: Connection,
  overrides: { id: number; content: string; targetPersonaIds: number[]; sceneId?: number }
): void {
  connection.route.send(
    JSON.stringify([
      'interaction',
      [],
      {
        id: overrides.id,
        persona: { id: 99, name: 'Nyx', thumbnail_url: '' },
        content: overrides.content,
        mode: 'action',
        timestamp: new Date().toISOString(),
        scene_id: overrides.sceneId ?? 1,
        place_id: null,
        place_name: null,
        receiver_persona_ids: [],
        target_persona_ids: overrides.targetPersonaIds,
      },
    ])
  );
}

/**
 * `RouletteResult`'s entrance is its own fade/height-in framer-motion
 * animation (`ANIMATION_DURATION.RESULT_DELAY` + its own transition), so a
 * plain "is it visible" check can pass while the wrapper is still mid-fade at
 * near-zero height — a real screenshot taken right then would show the odds
 * list but an empty gap where the result card belongs. This polls the
 * wrapper's own computed opacity instead of guessing a fixed sleep.
 */
async function waitForResultCardSettled(resultLabel: import('@playwright/test').Locator) {
  await expect
    .poll(
      () =>
        resultLabel.evaluate((el) => {
          const wrapper = el.closest('.overflow-hidden');
          return wrapper ? Number(getComputedStyle(wrapper).opacity) : 0;
        }),
      { timeout: 3_000 }
    )
    .toBeGreaterThan(0.95);
}

/**
 * The dialog itself (overlay + content) runs its own Radix animate-in
 * (`data-[state=open]:fade-in-0 zoom-in-95`, 200ms). A screenshot taken the
 * instant `getByRole('dialog')` resolves visible can land mid-fade, showing
 * the page underneath through a still-transparent overlay/content — that
 * looks like a stacking defect but is really a timing race. Poll both
 * `data-state` and computed opacity before trusting any capture of it.
 */
async function waitForDialogFullyOpen(dialog: import('@playwright/test').Locator) {
  await expect(dialog).toHaveAttribute('data-state', 'open');
  await expect
    .poll(() => dialog.evaluate((el) => Number(getComputedStyle(el).opacity)), {
      timeout: 3_000,
    })
    .toBeGreaterThan(0.99);
}

interface RouletteFace {
  label: string;
  weight: number;
  selected?: boolean;
}

function pushRoulette(connection: Connection, templateName: string, faces: RouletteFace[]): void {
  connection.route.send(
    JSON.stringify([
      'roulette_result',
      [],
      {
        template_name: templateName,
        consequences: faces.map((f) => ({
          label: f.label,
          tier_name: f.label,
          weight: f.weight,
          is_selected: Boolean(f.selected),
        })),
      },
    ])
  );
}

test.describe('#3807 outcome delivery + resolution wheel — fixture-backed evidence', () => {
  test('a resolved outcome arrives live and marks the involved viewer', async ({ page }) => {
    await mockRestRoutes(page);
    const connections = await reachReadySession(page);

    pushActionRow(connections[0], {
      id: 910,
      content: 'Nyx attempts to persuade Tehom: Partial Success',
      targetPersonaIds: [7],
    });

    const markedRow = page.getByTestId('involvement-mark-910');
    await expect(markedRow).toBeVisible();
    await expect(markedRow).toContainText('This happened to you');
    await expect(markedRow).toContainText('Nyx attempts to persuade Tehom: Partial Success');
    // The flag is the one element this screen exists to show — assert it
    // reads, not just that the row contains its text.
    await expect(markedRow.getByText('This happened to you')).toBeVisible();

    pushActionRow(connections[0], {
      id: 911,
      content: 'Nyx attempts to persuade the guard: Success',
      targetPersonaIds: [],
    });

    const unmarkedRow = page.getByText('Nyx attempts to persuade the guard: Success');
    await expect(unmarkedRow).toBeVisible();
    await expect(page.getByTestId('involvement-mark-911')).toHaveCount(0);

    // A plain full-page capture can land scrolled so the marked row's own
    // top edge (and the amber flag on it) sits above the fold — scroll it
    // into view first so both rows, and the flag, are actually in frame.
    await markedRow.scrollIntoViewIfNeeded();
    await expect(markedRow.getByText('This happened to you')).toBeInViewport();

    await page.screenshot({
      path: '../docs/reviews/3807-shots/build-screen1-reader.png',
      fullPage: true,
    });
  });

  test('the resolution wheel spins the raw Difficulty -1 chart and lands where resolved', async ({
    page,
  }) => {
    test.setTimeout(60_000);
    await mockRestRoutes(page);
    const connections = await reachReadySession(page);

    pushRoulette(connections[0], 'Persuade', [
      { label: 'Critical Failure', weight: 2 },
      { label: 'Failure', weight: 43 },
      { label: 'Partial Success', weight: 33, selected: true },
      { label: 'Success', weight: 22 },
    ]);

    const dialog = page.getByRole('dialog');
    await expect(dialog).toBeVisible();
    await expect(dialog.getByText('Persuade', { exact: true })).toBeVisible();

    const slices = dialog.getByTestId('roulette-slice');
    await expect(slices).toHaveCount(4);
    const sweeps = await slices.evaluateAll((els) =>
      els.map((el) => Number(el.getAttribute('data-slice-sweep')))
    );
    const expectedSweeps = [7.2, 154.8, 118.8, 79.2];
    sweeps.forEach((sweep, i) => {
      expect(sweep).toBeGreaterThan(expectedSweeps[i] - 0.5);
      expect(sweep).toBeLessThan(expectedSweeps[i] + 0.5);
    });

    // Mid-spin capture, before the disc has landed.
    await expect(dialog.getByTestId('roulette-disc')).toBeVisible();
    await page.screenshot({
      path: '../docs/reviews/3807-shots/build-screen2-spinning.png',
      fullPage: true,
    });

    const disc = dialog.getByTestId('roulette-disc');
    const landingAngle = Number(await disc.getAttribute('data-landing-angle'));
    const selectedSlice = dialog.locator(
      '[data-testid="roulette-slice"][data-slice-selected="true"]'
    );
    const [selStart, selSweep] = await selectedSlice.evaluate((el) => [
      Number(el.getAttribute('data-slice-start')),
      Number(el.getAttribute('data-slice-sweep')),
    ]);
    expect(landingAngle).toBeGreaterThanOrEqual(selStart);
    expect(landingAngle).toBeLessThanOrEqual(selStart + selSweep);

    const oddsRows = dialog.getByTestId('odds-row');
    await expect(oddsRows).toHaveCount(4);
    const oddsText = await oddsRows.allTextContents();
    expect(oddsText[0]).toContain('Success');
    expect(oddsText[0]).toContain('22%');
    expect(oddsText[1]).toContain('Partial Success');
    expect(oddsText[1]).toContain('33%');
    expect(oddsText[2]).toContain('Failure');
    expect(oddsText[2]).toContain('43%');
    expect(oddsText[3]).toContain('Critical Failure');
    expect(oddsText[3]).toContain('2%');

    // Wait for the natural landing (ANIMATION_DURATION.TOTAL = 6s) plus margin.
    // `RouletteResult`'s own label paragraph carries a stable class
    // (`text-lg font-bold`, unique within the dialog) — scoped to it rather
    // than dialog-wide text, since the odds list above also legitimately
    // shows "Partial Success" as a row label.
    const resultLabel = dialog.locator('p.text-lg.font-bold');
    await expect(resultLabel).toBeVisible({ timeout: 9_000 });
    await expect(resultLabel).toHaveText('Partial Success');
    // The caption reads "Outcome" rather than repeating "Partial Success":
    // tier_name === label here, so RouletteResult shows the generic caption
    // instead of showing "Partial Success" twice (once as eyebrow, once as
    // the label) — matching the approved demo's small-caps "OUTCOME" line.
    const resultEyebrow = dialog.locator(
      'p.mb-2.text-xs.font-semibold.uppercase.tracking-wider.opacity-70'
    );
    await expect(resultEyebrow).toHaveText('Outcome');
    await waitForResultCardSettled(resultLabel);

    await page.screenshot({
      path: '../docs/reviews/3807-shots/build-screen2-landed.png',
      fullPage: true,
    });
  });

  test('the resolution wheel draws a flat two-outcome chart', async ({ page }) => {
    test.setTimeout(60_000);
    await mockRestRoutes(page);
    const connections = await reachReadySession(page);

    pushRoulette(connections[0], 'Feat of arms', [
      { label: 'Success', weight: 50 },
      { label: 'Critical Success', weight: 50, selected: true },
    ]);

    const dialog = page.getByRole('dialog');
    await expect(dialog).toBeVisible();

    const slices = dialog.getByTestId('roulette-slice');
    await expect(slices).toHaveCount(2);
    const sweeps = await slices.evaluateAll((els) =>
      els.map((el) => Number(el.getAttribute('data-slice-sweep')))
    );
    sweeps.forEach((sweep) => {
      expect(sweep).toBeGreaterThan(179.5);
      expect(sweep).toBeLessThan(180.5);
    });

    const resultLabel = dialog.locator('p.text-lg.font-bold');
    await expect(resultLabel).toBeVisible({ timeout: 9_000 });
    await expect(resultLabel).toHaveText('Critical Success');
    await waitForResultCardSettled(resultLabel);

    await page.screenshot({
      path: '../docs/reviews/3807-shots/build-screen3-two-outcomes.png',
      fullPage: true,
    });
  });

  test('the wheel modal fits a 400px-wide phone viewport with no horizontal scroll', async ({
    page,
  }) => {
    test.setTimeout(60_000);
    // Reach the ready session at the harness's normal viewport first — the
    // top bar's "Entering world"/"In world" status text `reachReadySession`
    // asserts on is `hidden sm:inline` (GameTopBar), i.e. genuinely hidden by
    // responsive CSS below the `sm` breakpoint, not a defect this evidence is
    // about. Shrink to the phone width only afterward, for the wheel itself.
    await mockRestRoutes(page);
    const connections = await reachReadySession(page);
    await page.setViewportSize({ width: 400, height: 800 });

    pushRoulette(connections[0], 'Persuade', [
      { label: 'Critical Failure', weight: 2 },
      { label: 'Failure', weight: 43 },
      { label: 'Partial Success', weight: 33, selected: true },
      { label: 'Success', weight: 22 },
    ]);

    const dialog = page.getByRole('dialog');
    await expect(dialog).toBeVisible();
    // #3807 review finding: a capture taken the instant the dialog becomes
    // visible can land mid Radix animate-in, with the composer and reader
    // showing through a still-transparent overlay/content — wait for the
    // dialog's own entrance to finish before trusting anything about what's
    // drawn on top of it.
    await waitForDialogFullyOpen(dialog);

    // And wait for the wheel to actually land, same as the desktop captures,
    // so the mobile shot shows the settled result card, not a mid-spin disc.
    const resultLabel = dialog.locator('p.text-lg.font-bold');
    await expect(resultLabel).toBeVisible({ timeout: 9_000 });
    await expect(resultLabel).toHaveText('Partial Success');
    await waitForResultCardSettled(resultLabel);

    const hasNoHorizontalScroll = await page.evaluate(
      () => document.documentElement.scrollWidth <= document.documentElement.clientWidth
    );
    expect(hasNoHorizontalScroll).toBe(true);

    // Permanent stacking assertion (#3807 finding 2): with the dialog open,
    // the point at the composer's Send button must resolve to something
    // inside the dialog, never the composer itself — the dialog's overlay
    // (or content) has to be genuinely on top, not just drawn to look that
    // way. This is the direct check for a real z-index defect, as opposed to
    // the animate-in timing race `waitForDialogFullyOpen` guards against.
    // A plain attribute selector, not `getByRole('button', { name: 'Send' })`
    // — the role query intermittently resolved to zero elements here even
    // though the button was present and unambiguous in the DOM.
    const sendButton = page.locator('button[aria-label="Send"]');
    await expect(sendButton).toHaveCount(1);
    const sendBox = await sendButton.evaluate((el) => el.getBoundingClientRect());
    const topElementIsInDialog = await page.evaluate(
      ({ x, y }) => {
        const el = document.elementFromPoint(x, y);
        const dialogEl = document.querySelector('[role="dialog"]');
        return Boolean(el && dialogEl && dialogEl.contains(el));
      },
      { x: sendBox.x + sendBox.width / 2, y: sendBox.y + sendBox.height / 2 }
    );
    expect(topElementIsInDialog).toBe(true);

    await page.screenshot({
      path: '../docs/reviews/3807-shots/build-mobile-400.png',
      fullPage: true,
    });
  });

  test('the landed wheel renders in dark theme (system color-scheme)', async ({ page }) => {
    test.setTimeout(60_000);
    // Dark mode is next-themes with attribute="class", defaultTheme="system",
    // enableSystem (frontend/src/main.tsx) — it reads matchMedia at mount, so
    // emulating the OS color scheme before navigation is the real mechanism,
    // not a hand-added `dark` class.
    await page.emulateMedia({ colorScheme: 'dark' });
    await mockRestRoutes(page);
    const connections = await reachReadySession(page);
    await expect(page.locator('html')).toHaveClass(/dark/);

    pushRoulette(connections[0], 'Persuade', [
      { label: 'Critical Failure', weight: 2 },
      { label: 'Failure', weight: 43 },
      { label: 'Partial Success', weight: 33, selected: true },
      { label: 'Success', weight: 22 },
    ]);

    const dialog = page.getByRole('dialog');
    await expect(dialog).toBeVisible();
    const resultLabel = dialog.locator('p.text-lg.font-bold');
    await expect(resultLabel).toBeVisible({ timeout: 9_000 });
    await expect(resultLabel).toHaveText('Partial Success');
    await waitForResultCardSettled(resultLabel);

    await page.screenshot({
      path: '../docs/reviews/3807-shots/build-screen2-landed-dark.png',
      fullPage: true,
    });
  });
});
