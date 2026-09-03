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
 *     The password-change journey does not need a verified email, so it uses
 *     a fresh UI-registered account the same way user-journey.spec.ts does.
 *
 * Run with: just fe-e2e account-settings
 * Not run in CI, since this suite needs a live Evennia backend.
 */

import { createHmac } from 'node:crypto';
import { test, expect, type Page } from '@playwright/test';

const BASE_URL = 'http://localhost:4001';

const SEEDED_USERNAME = 'e2e_test_account';
const SEEDED_PASSWORD = 'TestPass123!';

/** Unique suffix so parallel runs / repeated runs don't collide on usernames. */
function uniqueSuffix(): string {
  return `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

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

/** Register a fresh account through the UI, exactly as user-journey.spec.ts does. */
async function registerFreshAccount(
  page: Page,
  username: string,
  email: string,
  password: string
): Promise<void> {
  await page.goto(`${BASE_URL}/register`);
  await page.waitForLoadState('networkidle');

  await page.locator('#username').fill(username);
  await page.locator('#email').fill(email);
  await page.locator('#password1').fill(password);
  await page.locator('#password2').fill(password);
  await page.locator('#email').blur();

  await page.getByRole('button', { name: /register/i }).click();
  await page.waitForURL('**/register/verify-email', { timeout: 10000 });

  // Mock the email verification API call, same as user-journey.spec.ts. The
  // account is NOT actually verified in the DB, see the header comment.
  await page.route('**/api/auth/browser/v1/auth/email/verify', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ detail: 'Email successfully verified' }),
    });
  });
  await page.goto(`${BASE_URL}/verify-email/dummy-key-for-e2e`);
  await expect(page.locator('h1')).toContainText('Email Verified', { timeout: 10000 });
}

/** Log in through the UI, landing wherever the app sends us (/ or /account/unverified). */
async function loginViaUi(page: Page, login: string, password: string): Promise<void> {
  await page.goto(`${BASE_URL}/login`);
  await page.waitForLoadState('networkidle');

  await page.getByPlaceholder('Username or Email').fill(login);
  await page.getByPlaceholder('Password').fill(password);
  await page.getByRole('button', { name: 'Log In' }).click();

  await page.waitForURL((url) => !url.pathname.startsWith('/login'), { timeout: 10000 });
}

/**
 * If a reauthentication challenge dialog appeared (session too stale, or the
 * server just wants a fresh password), answer it with the account password
 * and continue. A no-op when the dialog never opens.
 */
async function answerReauthIfPresent(page: Page, password: string): Promise<void> {
  const reauthValue = page.locator('#reauth-value');
  if (await reauthValue.isVisible().catch(() => false)) {
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
// Password change: fresh account, no email verification needed
// ---------------------------------------------------------------------------

test.describe('Account settings: password', () => {
  test('change password on /profile/account, then sign in with the new one', async ({ page }) => {
    const getErrors = captureConsoleErrors(page);
    const suffix = uniqueSuffix();
    const username = `acct-pw-${suffix}`;
    const email = `acct-pw-${suffix}@test.com`;
    const oldPassword = 'TestPass123!';
    const newPassword = 'NewTestPass456!';

    await registerFreshAccount(page, username, email, oldPassword);
    await loginViaUi(page, username, oldPassword);

    // ProtectedRoute only requires an authenticated session, not a verified
    // email, so /profile/account is reachable even though this account was
    // never really verified in the DB.
    await page.goto(`${BASE_URL}/profile/account`);
    await page.waitForLoadState('networkidle');
    await expect(page.locator('#current-password')).toBeVisible();

    await page.locator('#current-password').fill(oldPassword);
    await page.locator('#new-password').fill(newPassword);
    await page.locator('#confirm-password').fill(newPassword);
    await page.getByRole('button', { name: 'Change password' }).click();

    await expect(page.getByText('Password changed. You stay signed in.')).toBeVisible({
      timeout: 10000,
    });

    // Sign out by dropping the session cookie (the ProfileDropdown's Logout
    // menu item is not needed to exercise the password-change flow) and log
    // back in with the new password.
    await page.context().clearCookies();
    await loginViaUi(page, username, newPassword);
    expect(page.url()).not.toContain('/login');
    await expect(page.locator('#root')).not.toBeEmpty();

    expect(getErrors()).toEqual([]);
  });
});

// ---------------------------------------------------------------------------
// TOTP enrolment: needs a genuinely verified email, so it uses the seeded
// account rather than a fresh UI registration (see header comment).
// ---------------------------------------------------------------------------

test.describe('Account settings: two-factor authentication', () => {
  test('enrol TOTP, see ten recovery codes, then turn it off', async ({ page }) => {
    const getErrors = captureConsoleErrors(page);

    await loginViaUi(page, SEEDED_USERNAME, SEEDED_PASSWORD);
    await page.goto(`${BASE_URL}/profile/account`);
    await page.waitForLoadState('networkidle');

    const setUpButton = page.getByRole('button', { name: 'Set up' });
    const turnOffButton = page.getByRole('button', { name: 'Turn off' });

    // The seeded account is shared across runs. If a previous run stalled
    // after turning 2FA on, reset it before enrolling again.
    if (await turnOffButton.isVisible().catch(() => false)) {
      await turnOffButton.click();
      await answerReauthIfPresent(page, SEEDED_PASSWORD);
      await expect(setUpButton).toBeVisible({ timeout: 10000 });
    }

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
