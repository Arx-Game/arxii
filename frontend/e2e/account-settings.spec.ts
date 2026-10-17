/**
 * Account settings e2e tests (#3591): password change and TOTP two-factor
 * enrolment on /profile/account.
 *
 * Same conventions as e2e/user-journey.spec.ts (BASE_URL 4001, console-error
 * capture, UI registration with a unique suffix). Playwright specs are
 * standalone files, so the small helpers below are copied rather than
 * imported.
 *
 * Prerequisites:
 *   - Evennia server running on :4001 (`just start` from the repo root)
 *   - DEBUG=True in src/.env (so email goes to console, not Resend SMTP)
 *   - Chromium installed (`cd frontend && npx playwright install chromium`)
 *   - `just seed-test-account` run at least once, which creates the
 *     pre-verified `e2e_test_account` (password `TestPass123!`) used by the
 *     TOTP journey below. TwoFactorCard only shows "Set up" once
 *     account.email_verified is true, and exactly like user-journey.spec.ts
 *     documents, a browser test cannot verify a freshly UI-registered
 *     account for real: the verification key only ever reaches the server
 *     console (DEBUG mode), which this test has no way to read, so the
 *     /auth/email/verify call is mocked at the network layer instead. That
 *     mock satisfies the frontend's "Email Verified" screen but never flips
 *     the row in the database, so a freshly registered account stays
 *     unverified for the rest of the test and cannot reach the TOTP journey.
 *     Email verification is mandatory, so a UI-registered account cannot sign
 *     in either. The password-change journey therefore also uses the seeded
 *     account and restores its password at the end.
 *
 * The TOTP journey is NOT idempotent against a seeded account an earlier run
 * left with 2FA enabled: this test has no way to answer a login-time code
 * challenge for an authenticator it did not just enrol itself, and it fails
 * fast with a clear message rather than hanging in that case. If that
 * happens, delete the account's rows in the admin (MFA > Authenticators) and
 * re-run. A completed run always turns 2FA back off, so this only bites
 * after a run that stopped partway through.
 *
 * Run with: just fe-e2e account-settings
 * CI runs this suite in .github/workflows/real-test.yml (advisory; #4247).
 */

import { createHmac } from 'node:crypto';
import { test, expect, type Browser, type BrowserContext, type Page } from '@playwright/test';

const BASE_URL = 'http://localhost:4001';

const SEEDED_USERNAME = 'e2e_test_account';
const SEEDED_PASSWORD = 'TestPass123!';

/**
 * Suppress expected API-failure console noise, same filter as
 * user-journey.spec.ts.
 */
function filterApiNoise(msg: string): boolean {
  return (
    msg.includes('Failed to load resource') ||
    msg.includes('favicon') ||
    msg.includes('NetworkError') ||
    msg.includes('Load failed') ||
    msg.includes('404')
  );
}

/** Set up console error capture on a page. Returns a getter for the errors array. */
function captureConsoleErrors(page: Page): () => string[] {
  const errors: string[] = [];
  page.on('console', (msg) => {
    if (msg.type() === 'error' && !filterApiNoise(msg.text())) {
      errors.push(msg.text());
    }
  });
  page.on('pageerror', (err) => {
    errors.push(err.message);
  });
  return () => errors;
}

/** Change the signed-in account's password on /profile/account and wait for the success note. */
async function changePasswordOnAccountPage(
  page: Page,
  currentPassword: string,
  newPassword: string
): Promise<void> {
  await page.goto(`${BASE_URL}/profile/account`);
  await page.waitForLoadState('networkidle');
  await expect(page.locator('#current-password')).toBeVisible();

  await page.locator('#current-password').fill(currentPassword);
  await page.locator('#new-password').fill(newPassword);
  await page.locator('#confirm-password').fill(newPassword);
  await page.getByRole('button', { name: 'Change password' }).click();

  await expect(page.getByText('Password changed. You stay signed in.')).toBeVisible({
    timeout: 10000,
  });
}

/**
 * Sign in on a page in a brand-new browser context, and return that context
 * with its own console-error capture.
 *
 * Signing out by clearing cookies in the context that changed the password
 * is a race (#4391): the settings page keeps refetching /api/user/ and the
 * account sub-routes for a moment after "Password changed" appears, and those
 * late responses set the old session cookie back into the jar. A fresh
 * context has no cookies to race with, so the sign-in cannot be overwritten.
 */
async function signInInFreshContext(
  browser: Browser,
  login: string,
  password: string
): Promise<{ context: BrowserContext; page: Page; getErrors: () => string[] }> {
  const context = await browser.newContext();
  const page = await context.newPage();
  const getErrors = captureConsoleErrors(page);
  await loginViaUi(page, login, password);
  return { context, page, getErrors };
}

type LoginRace = 'navigated' | 'mfa' | 'timeout';

/**
 * Log in through the UI, landing wherever the app sends us (/ or
 * /account/unverified). If the account has TOTP enabled, the login form
 * shows a second "Authenticator code or recovery code" step; pass
 * `getCode` to answer it (e.g. `() => totpCode(secret)`).
 *
 * If that step appears with no `getCode` supplied, this fails fast with a
 * clear message rather than hanging on `waitForURL` forever: there is no way
 * to compute a code for an authenticator this test did not itself enrol
 * (see the header comment).
 */
async function loginViaUi(
  page: Page,
  login: string,
  password: string,
  options: { getCode?: () => string } = {}
): Promise<void> {
  await page.goto(`${BASE_URL}/login`);
  await page.waitForLoadState('networkidle');

  await page.getByPlaceholder('Username or Email').fill(login);
  await page.getByPlaceholder('Password').fill(password);
  await page.getByRole('button', { name: 'Log In' }).click();

  const mfaCodeField = page.locator('#mfa-code');
  const navigated: Promise<LoginRace> = page
    .waitForURL((url) => !url.pathname.startsWith('/login'), { timeout: 15000 })
    .then((): LoginRace => 'navigated')
    .catch((): LoginRace => 'timeout');
  const mfaChallenge: Promise<LoginRace> = mfaCodeField
    .waitFor({ state: 'visible', timeout: 15000 })
    .then((): LoginRace => 'mfa')
    .catch((): LoginRace => 'timeout');

  const outcome = await Promise.race([navigated, mfaChallenge]);

  if (outcome === 'navigated') return;

  if (outcome === 'timeout') {
    // Neither settled inside the window - re-await the navigation promise
    // with a short timeout so the failure surfaces as a real Playwright
    // timeout error instead of the swallowed 'timeout' sentinel above.
    await page.waitForURL((url) => !url.pathname.startsWith('/login'), { timeout: 1 });
    return;
  }

  if (!options.getCode) {
    throw new Error(
      `Login for "${login}" hit a 2FA challenge with no code source supplied. This ` +
        'account already has an authenticator enrolled from a run this spec has no ' +
        'secret for. Delete its rows in the admin (MFA > Authenticators) and re-run.'
    );
  }
  await mfaCodeField.fill(options.getCode());
  await page.getByRole('button', { name: 'Continue' }).click();
  await page.waitForURL((url) => !url.pathname.startsWith('/login'), { timeout: 15000 });
}

/**
 * If a reauthentication challenge dialog appeared (session too stale, or the
 * server just wants a fresh password), answer it with the account password
 * and continue. A no-op when the dialog never opens.
 *
 * The dialog only opens after the guarded mutation's fetch round-trip comes
 * back with a reauthentication-required error, so a plain isVisible() check
 * right after the click is a one-shot snapshot that runs before the dialog
 * exists and always reads false. waitFor() polls instead, so it actually
 * catches the dialog whenever it shows up within the window.
 */
async function answerReauthIfPresent(page: Page, password: string): Promise<void> {
  const reauthValue = page.locator('#reauth-value');
  const present = await reauthValue
    .waitFor({ state: 'visible', timeout: 2000 })
    .then(() => true)
    .catch(() => false);
  if (present) {
    await reauthValue.fill(password);
    await page.getByRole('button', { name: 'Continue' }).click();
    await expect(reauthValue).toBeHidden();
  }
}

const BASE32_ALPHABET = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ234567';

/** Decode an RFC 4648 base32 string (no padding) into a Buffer. */
function base32Decode(input: string): Buffer {
  const clean = input.replace(/=+$/, '').toUpperCase();
  let bits = '';
  for (const char of clean) {
    const value = BASE32_ALPHABET.indexOf(char);
    if (value === -1) throw new Error(`Invalid base32 character in TOTP secret: ${char}`);
    bits += value.toString(2).padStart(5, '0');
  }
  const bytes: number[] = [];
  for (let i = 0; i + 8 <= bits.length; i += 8) {
    bytes.push(parseInt(bits.slice(i, i + 8), 2));
  }
  return Buffer.from(bytes);
}

/**
 * RFC 6238 TOTP over Node's crypto: HMAC-SHA1 of the big-endian 8-byte
 * 30-second counter, dynamic truncation, mod 1e6, zero-padded to 6 digits.
 * Matches allauth's own TOTP implementation (30s period, SHA1, 6 digits).
 */
function totpCode(secret: string, atMs: number = Date.now()): string {
  const counter = Math.floor(atMs / 30000);
  const counterBuffer = Buffer.alloc(8);
  counterBuffer.writeBigUInt64BE(BigInt(counter));

  const key = base32Decode(secret);
  const hmac = createHmac('sha1', key).update(counterBuffer).digest();

  const offset = hmac[hmac.length - 1] & 0x0f;
  const truncated =
    ((hmac[offset] & 0x7f) << 24) |
    ((hmac[offset + 1] & 0xff) << 16) |
    ((hmac[offset + 2] & 0xff) << 8) |
    (hmac[offset + 3] & 0xff);

  const value = truncated % 1_000_000;
  return value.toString().padStart(6, '0');
}

// ---------------------------------------------------------------------------
// Password change: the seeded account, with its password restored at the end
// ---------------------------------------------------------------------------

test.describe('Account settings: password', () => {
  test('change password on /profile/account, then sign in with the new one', async ({
    page,
    browser,
  }) => {
    const getErrors = captureConsoleErrors(page);
    const newPassword = 'NewTestPass456!';

    // Email verification is mandatory (ACCOUNT_EMAIL_VERIFICATION), and a
    // browser test cannot verify a freshly registered account (see the header
    // comment), so a registered account cannot sign in here. The seeded,
    // verified account is used instead, and its password is put back at the
    // end so a second run starts from the same state. If a run dies between
    // the two changes, restore it in the admin or re-seed the database.
    await loginViaUi(page, SEEDED_USERNAME, SEEDED_PASSWORD);
    await changePasswordOnAccountPage(page, SEEDED_PASSWORD, newPassword);

    // Sign out and sign back in with the new password, in a fresh browser
    // context (see signInInFreshContext). The ProfileDropdown's Logout item is
    // not needed to exercise the password-change flow.
    const newSession = await signInInFreshContext(browser, SEEDED_USERNAME, newPassword);
    expect(newSession.page.url()).not.toContain('/login');
    await expect(newSession.page.locator('#root')).not.toBeEmpty();

    // Put the seeded password back, then prove the restored one signs in.
    await changePasswordOnAccountPage(newSession.page, newPassword, SEEDED_PASSWORD);
    const restored = await signInInFreshContext(browser, SEEDED_USERNAME, SEEDED_PASSWORD);
    expect(restored.page.url()).not.toContain('/login');

    expect(getErrors()).toEqual([]);
    expect(newSession.getErrors()).toEqual([]);
    expect(restored.getErrors()).toEqual([]);
    await newSession.context.close();
    await restored.context.close();
  });
});

// ---------------------------------------------------------------------------
// TOTP enrolment: needs a genuinely verified email, so it uses the seeded
// account rather than a fresh UI registration (see header comment).
// ---------------------------------------------------------------------------

test.describe('Account settings: two-factor authentication', () => {
  test('enrol TOTP, see ten recovery codes, then turn it off', async ({ page }) => {
    const getErrors = captureConsoleErrors(page);

    // This is NOT idempotent against a seeded account left with TOTP already
    // enabled by a prior interrupted run: an enabled authenticator makes the
    // login form demand a code, and this test has no way to produce one for
    // a secret it did not itself just enrol. loginViaUi fails fast with a
    // clear message in that case instead of hanging - see its doc comment.
    // A completed run always ends with 2FA turned back off (below), so this
    // only bites after a run that stopped partway through.
    await loginViaUi(page, SEEDED_USERNAME, SEEDED_PASSWORD);
    await page.goto(`${BASE_URL}/profile/account`);
    await page.waitForLoadState('networkidle');

    const setUpButton = page.getByRole('button', { name: 'Set up' });
    const turnOffButton = page.getByRole('button', { name: 'Turn off' });

    await setUpButton.click();

    const secretCode = page.locator('code').first();
    await expect(secretCode).toBeVisible({ timeout: 10000 });
    const secret = (await secretCode.textContent())?.trim();
    if (!secret) throw new Error('TOTP secret did not render in the enrolment dialog.');

    await page.locator('#totp-code').fill(totpCode(secret));
    await page.getByRole('button', { name: 'Turn on' }).click();
    await answerReauthIfPresent(page, SEEDED_PASSWORD);

    await expect(page.getByText('Save these recovery codes')).toBeVisible({ timeout: 10000 });
    await expect(page.locator('ol li')).toHaveCount(10);

    await page.getByRole('button', { name: 'Done' }).click();

    const telnetSwitch = page.locator('#block-telnet');
    await expect(telnetSwitch).toBeVisible();

    await turnOffButton.click();
    await answerReauthIfPresent(page, SEEDED_PASSWORD);
    await expect(setUpButton).toBeVisible({ timeout: 10000 });

    expect(getErrors()).toEqual([]);
  });
});
