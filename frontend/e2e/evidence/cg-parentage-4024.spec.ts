import * as path from 'node:path';
import { fileURLToPath } from 'node:url';
import { test, expect } from '@playwright/test';
import { COPY, CRADLE, TAKEN_IN, mockCg } from './fixtures/cgLineage';

/**
 * Review evidence for Upbringing parentage (#4024): the real `/characters/create`
 * page on the production bundle, at the Lineage stage, with every `/api/**` call
 * answered by fixtures shaped like the serializers. Walks a Misbegotten through
 * both of its Upbringings: "Raised in the Cradle" (no known parents: the note,
 * the explained tarot ritual, no family or parents) and "Taken In" (adoptive:
 * the note, the adoptive family heading, established-or-own with your own open,
 * and "Your adoptive parents").
 */
const __dirname = path.dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = path.resolve(__dirname, '..', '..', '..');
const EVIDENCE_DIR = path.join(REPO_ROOT, 'docs', 'reviews', '4024');
const shot = (name: string) => path.join(EVIDENCE_DIR, name);

test.describe('Upbringing parentage (#4024) on the production bundle', () => {
  test('Raised in the Cradle: no known parents', async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 1600 });
    await mockCg(page, CRADLE);
    const errors: string[] = [];
    page.on('pageerror', (error) => errors.push(error.message));
    await page.goto('/characters/create');

    await expect(page.getByText(CRADLE.parentage_note)).toBeVisible();
    await expect(page.getByText(COPY.tarot_no_parents_intro)).toBeVisible();
    await expect(page.getByText('Naming Ritual')).toBeVisible();
    await expect(page.getByRole('heading', { name: /your family/i })).toHaveCount(0);
    await expect(page.getByText(/your parents/i)).toHaveCount(0);
    await page.waitForTimeout(400);
    await page.screenshot({ path: shot('cradle-no-known-parents-1280.png'), fullPage: true });
    expect(errors).toEqual([]);
  });

  test('Taken In: adoptive family, your own open by default', async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 1600 });
    await mockCg(page, TAKEN_IN);
    const errors: string[] = [];
    page.on('pageerror', (error) => errors.push(error.message));
    await page.goto('/characters/create');

    await expect(page.getByText(TAKEN_IN.parentage_note)).toBeVisible();
    await expect(page.getByRole('heading', { name: COPY.adoptive_family_heading })).toBeVisible();
    await expect(page.getByRole('radio', { name: 'Your own family' })).toBeChecked();
    await expect(page.getByRole('radio', { name: 'An established family' })).not.toBeChecked();
    await expect(page.getByText('Your adoptive parents')).toBeVisible();
    await expect(page.getByText(/Tree of Souls; the first parent/)).toHaveCount(0);
    // Adoptive parents pass nothing by blood: no species line or picker.
    await expect(page.getByText('First parent')).toBeVisible();
    await expect(page.getByRole('combobox', { name: 'Other parent species' })).toHaveCount(0);
    await page.waitForTimeout(400);
    await page.screenshot({ path: shot('taken-in-adoptive-1280.png'), fullPage: true });
    expect(errors).toEqual([]);
  });

  test('Cradle at phone width', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 1800 });
    await mockCg(page, CRADLE);
    await page.goto('/characters/create');
    await expect(page.getByText(CRADLE.parentage_note)).toBeVisible();
    await page.screenshot({ path: shot('cradle-390.png'), fullPage: true });
  });
});
