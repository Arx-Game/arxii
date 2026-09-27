import { expect, test, type Page, type TestInfo } from '@playwright/test';
import { mockRestRoutes, pushForeignPose, reachReadySession } from './support/gameHarness';

// Live /game UI with the shared REST and WebSocket fixtures; no backend data or
// reload supplies the restored blocks. Screenshots show this fixture state,
// not a production account. Only the three named screenshots are artifacts.
const poseText = 'Nyx places a silver ribbon beside the courtyard fountain.';
const lookText = 'The courtyard wall is lined with pale blue lanterns.';

function text(line: string): string {
  return JSON.stringify(['text', [line], { type: 'look' }]);
}

/** Hovering a block may scroll the document; keep all three viewport frames aligned. */
async function capture(page: Page, testInfo: TestInfo, name: string): Promise<void> {
  await page.evaluate(() => window.scrollTo(0, 0));
  await expect.poll(() => page.evaluate(() => window.scrollY)).toBe(0);
  await page.screenshot({ path: testInfo.outputPath(`live-${name}.png`) });
}

test('dismissed pose and look return in their original order without reloading; All off stays off', async ({
  page,
}, testInfo) => {
  await page.setViewportSize({ width: 1280, height: 800 });
  await mockRestRoutes(page);
  let loads = 0;
  page.on('load', () => {
    loads += 1;
  });
  const [connection] = await reachReadySession(page);
  const initialLoads = loads;
  expect(initialLoads).toBe(1);

  pushForeignPose(connection, { id: 4029, content: poseText });
  await expect(page.getByText(poseText)).toBeVisible();
  connection.route.send(text(lookText));
  await expect(page.getByText(lookText)).toBeVisible();

  const pose = page.locator('[data-feed-block="i:4029"]');
  const look = page.locator('[data-feed-block^="n:"]').filter({ hasText: lookText });
  const lookKey = await look.getAttribute('data-feed-block');
  expect(lookKey).toMatch(/^n:n\d+$/);
  const blocks = page.locator('[data-testid="authoritative-rp-block"] [data-feed-block]');
  await expect(blocks).toHaveCount(2);
  expect(
    await blocks.evaluateAll((elements) => elements.map((el) => el.getAttribute('data-feed-block')))
  ).toEqual(['i:4029', lookKey]);
  await expect(page.getByRole('button', { name: 'Show hidden' })).toHaveCount(0);
  await capture(page, testInfo, 'before');

  await pose.hover();
  await pose.getByRole('button', { name: 'Dismiss' }).click();
  await expect(page.getByText(poseText)).toHaveCount(0);
  await look.hover();
  await look.getByRole('button', { name: 'Dismiss' }).click();
  await expect(page.getByText(lookText)).toHaveCount(0);
  await expect(blocks).toHaveCount(0);
  const showHidden = page.getByRole('button', { name: 'Show hidden' });
  await expect(showHidden).toBeVisible();
  expect(loads).toBe(initialLoads);
  await capture(page, testInfo, 'dismissed');

  await showHidden.click();
  await expect(page.getByText(poseText)).toBeVisible();
  await expect(page.getByText(lookText)).toBeVisible();
  await expect(showHidden).toHaveCount(0);
  expect(
    await blocks.evaluateAll((elements) => elements.map((el) => el.getAttribute('data-feed-block')))
  ).toEqual(['i:4029', lookKey]);
  const all = page
    .getByRole('toolbar', { name: 'Feed filters' })
    .getByRole('button', { name: 'All' });
  await expect(all).toBeFocused();
  expect(loads).toBe(initialLoads);
  await capture(page, testInfo, 'after');

  // Restoring only clears dismissed keys. It must not turn an All-off feed on.
  await look.hover();
  await look.getByRole('button', { name: 'Dismiss' }).click();
  await expect(showHidden).toBeVisible();
  await all.click();
  await expect(all).toHaveAttribute('aria-pressed', 'false');
  await expect(page.getByTestId('feed-all-off')).toBeVisible();
  await showHidden.click();
  await expect(showHidden).toHaveCount(0);
  await expect(page.getByTestId('feed-all-off')).toBeVisible();
  await expect(all).toHaveAttribute('aria-pressed', 'false');
  await expect(all).toBeFocused();
  await expect(page.getByText(poseText)).toHaveCount(0);
  await expect(page.getByText(lookText)).toHaveCount(0);
  expect(loads).toBe(initialLoads);

  await all.click();
  await expect(page.getByText(poseText)).toBeVisible();
  await expect(page.getByText(lookText)).toBeVisible();
  expect(
    await blocks.evaluateAll((elements) => elements.map((el) => el.getAttribute('data-feed-block')))
  ).toEqual(['i:4029', lookKey]);
  expect(loads).toBe(initialLoads);
});
