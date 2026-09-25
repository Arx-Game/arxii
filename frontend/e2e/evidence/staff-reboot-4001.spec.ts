import * as path from 'node:path';
import { fileURLToPath } from 'node:url';
import { test, expect } from '@playwright/test';
import { frames, mockRestRoutes, reachReadySession, type Connection } from '../support/gameHarness';

/**
 * Review evidence for the staff console's Restart game control (#4001): the
 * real game page (production build, real composer, selector and console sheet)
 * with REST and the socket answered by the shared harness fixtures. Captures
 * the console sheet with its Restart game control, the inline confirm step,
 * proves Cancel sends nothing, and proves the confirm sends `@reboot` through
 * the console path exactly like a typed Commands-mode line.
 */
const __dirname = path.dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = path.resolve(__dirname, '..', '..', '..');
const EVIDENCE_DIR = path.join(REPO_ROOT, 'docs', 'reviews', '4001');
const shot = (name: string) => path.join(EVIDENCE_DIR, name);

/** Every text frame this connection sent, as `[line, kwargs]`. */
function sentLines(connection: Connection): Array<[string, Record<string, unknown>]> {
  return frames(connection)
    .filter(([type]) => type === 'text')
    .map(([, args, kwargs]) => [String(args[0]), kwargs]);
}

test.describe('staff console: Restart game asks first, then sends @reboot (#4001)', () => {
  test('desktop 1280: control, confirm, cancel, confirm again', async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 800 });
    await mockRestRoutes(page, { staff: true });
    const errors: string[] = [];
    page.on('pageerror', (error) => errors.push(error.message));
    const [connection] = await reachReadySession(page);

    // Staff pick Commands; the Console control appears in the toolbar.
    await page.getByRole('button', { name: /^Pose$/ }).click();
    await page.getByRole('menuitem', { name: 'Commands' }).click();
    await page.getByRole('button', { name: /^Console/ }).click();
    const sheet = page.getByRole('dialog', { name: 'Console' });
    await expect(sheet).toBeVisible();
    await expect(sheet.getByRole('button', { name: 'Restart game' })).toBeVisible();
    // Let the sheet's slide-in finish so the capture shows it in place.
    await page.waitForTimeout(500);
    await page.screenshot({ path: shot('console-restart-control-1280.png'), fullPage: true });

    // The control asks first; nothing goes to the server yet.
    await sheet.getByRole('button', { name: 'Restart game' }).click();
    await expect(
      sheet.getByText('Both daemons stop and come back in about a minute.')
    ).toBeVisible();
    await expect(sheet.getByRole('button', { name: 'Restart for everyone' })).toBeVisible();
    await page.screenshot({ path: shot('console-restart-confirm-1280.png'), fullPage: true });
    expect(sentLines(connection).map(([line]) => line)).not.toContain('@reboot');

    // Cancel closes the step and still sends nothing.
    await sheet.getByRole('button', { name: 'Cancel' }).click();
    await expect(sheet.getByText('Both daemons stop and come back in about a minute.')).toHaveCount(
      0
    );
    expect(sentLines(connection).map(([line]) => line)).not.toContain('@reboot');

    // Confirm sends `@reboot` through the console path, flagged like a typed line,
    // and the console echoes it above the server's answer.
    await sheet.getByRole('button', { name: 'Restart game' }).click();
    await sheet.getByRole('button', { name: 'Restart for everyone' }).click();
    await expect.poll(() => sentLines(connection)).toContainEqual(['@reboot', { console: true }]);
    await expect(sheet.getByTestId('staff-console-lines')).toContainText('@reboot');
    connection.route.send(
      JSON.stringify([
        'text',
        ['Restarting the game: both daemons stop now and come back shortly.'],
        { console: true },
      ])
    );
    await expect(sheet.getByTestId('staff-console-lines')).toContainText('come back shortly');
    await page.screenshot({ path: shot('console-restart-sent-1280.png'), fullPage: true });
    expect(errors).toEqual([]);
  });

  test('phone 390: the control and the confirm step fit the narrow sheet', async ({ page }) => {
    // The shared harness reads a desktop-only status label to know the session
    // is ready, so reach the session wide, then narrow the viewport.
    await page.setViewportSize({ width: 1280, height: 800 });
    await mockRestRoutes(page, { staff: true });
    await reachReadySession(page);
    await page.setViewportSize({ width: 390, height: 844 });
    await page.getByRole('button', { name: /^Pose$/ }).click();
    await page.getByRole('menuitem', { name: 'Commands' }).click();
    await page.getByRole('button', { name: /^Console/ }).click();
    const sheet = page.getByRole('dialog', { name: 'Console' });
    await sheet.getByRole('button', { name: 'Restart game' }).click();
    await expect(sheet.getByRole('button', { name: 'Restart for everyone' })).toBeVisible();
    await page.screenshot({ path: shot('console-restart-confirm-390.png'), fullPage: true });
  });
});
