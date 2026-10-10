/**
 * Staff edit mode on the sheet (#3988): the toggle is staff-only, a field saves and
 * cancels, an empty field keeps a slot, and a past version restores.
 */
import { fireEvent, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type { CharacterSheetPayload, CharacterSheetStaffEdit } from '@/character_sheets/api';
import { renderWithProviders } from '@/test/utils/renderWithProviders';
import { SheetPanel } from '../SheetPanel';
import { StaffEditProvider, StaffEditToggle } from '../StaffEdit';

const patchStaffEdit = vi.fn();
const restoreProfileTextVersion = vi.fn();
const fetchProfileTextVersions = vi.fn();

vi.mock('@/character_sheets/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/character_sheets/api')>();
  return {
    ...actual,
    patchStaffEdit: (...args: unknown[]) => patchStaffEdit(...args),
    restoreProfileTextVersion: (...args: unknown[]) => restoreProfileTextVersion(...args),
  };
});
vi.mock('@/sheet_update_requests/api', () => ({
  fetchProfileTextVersions: (...args: unknown[]) => fetchProfileTextVersions(...args),
}));

const STORED: CharacterSheetStaffEdit = {
  prose: {
    description: '',
    background: 'Raised at the quay.',
    concept: '',
    real_concept: '',
    quote: '',
    never_do: '',
    protect: '',
    fear: '',
    obituary: '',
  },
  name: 'Kathryn',
  ic_birth_year: null,
  true_height_inches: null,
  weight_pounds: null,
  marital_status: 'single',
  vocation: '',
  social_rank: 10,
  build: null,
  gender: null,
  pronouns: null,
  species: null,
  heritage: null,
  origin_realm: null,
  family: null,
  tarot_card: null,
  tarot_reversed: false,
};

function sheet(overrides: Partial<CharacterSheetPayload> = {}): CharacterSheetPayload {
  return {
    id: 20,
    can_edit: true,
    staff_edit: STORED,
    identity: {
      name: 'Kathryn',
      fullname: 'Kathryn',
      concept: '',
      quote: '',
      age: 24,
      birthday: null,
      gender: null,
      pronouns: { subject: 'she', object: 'her', possessive: 'her' },
      species: null,
      heritage: null,
      beginnings: [],
      family: null,
      tarot_card: null,
      origin: null,
      path: null,
      worship: null,
    },
    appearance: { height_inches: null, height_band: '', build: null, description: '' },
    stats: {},
    skills: [],
    distinctions: [],
    magic: null,
    story: { background: 'Raised at the quay.', origin_slots: [] },
    actor_sheet: { never_do: '', protect: '', fear: '', enemy_public_line: '', introductions: [] },
    goals: [],
    beats: [],
    ...overrides,
  } as unknown as CharacterSheetPayload;
}

function renderSheet(payload: CharacterSheetPayload) {
  return renderWithProviders(
    <StaffEditProvider sheet={payload}>
      <StaffEditToggle sheet={payload} />
      <SheetPanel sheet={payload} isMyCharacter={false} rumor={null} languages={null} />
    </StaffEditProvider>
  );
}

describe('staff edit mode', () => {
  beforeEach(() => {
    sessionStorage.clear();
    patchStaffEdit.mockReset();
    restoreProfileTextVersion.mockReset();
    fetchProfileTextVersions.mockReset();
  });
  afterEach(() => sessionStorage.clear());

  it('draws no toggle for a payload without staff fields', () => {
    renderSheet(sheet({ staff_edit: null }));
    expect(screen.queryByRole('switch', { name: 'Edit' })).not.toBeInTheDocument();
    expect(screen.queryByTestId('staff-edit-band')).not.toBeInTheDocument();
  });

  it('is off until toggled; on, empty fields keep a slot', async () => {
    const user = userEvent.setup();
    renderSheet(sheet());
    expect(screen.queryByTestId('staff-edit-band')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Edit As they appear' })).not.toBeInTheDocument();

    await user.click(screen.getByRole('switch', { name: 'Edit' }));

    expect(screen.getByTestId('staff-edit-band')).toBeInTheDocument();
    // The description is empty, so it is hidden off, and a slot on.
    expect(screen.getByRole('button', { name: 'Edit As they appear' })).toHaveTextContent('—');
    expect(sessionStorage.getItem('arx.staffEditMode')).toBe('1');
  });

  it('saves a prose field with Ctrl+Enter and cancels with Esc', async () => {
    const user = userEvent.setup();
    patchStaffEdit.mockResolvedValue(sheet());
    sessionStorage.setItem('arx.staffEditMode', '1');
    renderSheet(sheet());

    await user.click(screen.getByRole('button', { name: 'Edit Where they come from' }));
    const box = screen.getByRole('textbox', { name: 'Where they come from' });
    expect(box).toHaveValue('Raised at the quay.');
    await user.keyboard('{Escape}');
    expect(screen.queryByRole('textbox', { name: 'Where they come from' })).not.toBeInTheDocument();
    expect(patchStaffEdit).not.toHaveBeenCalled();

    await user.click(screen.getByRole('button', { name: 'Edit Where they come from' }));
    const again = screen.getByRole('textbox', { name: 'Where they come from' });
    await user.clear(again);
    await user.type(again, 'Raised on the river.');
    fireEvent.keyDown(again, { key: 'Enter', ctrlKey: true });

    await waitFor(() =>
      expect(patchStaffEdit).toHaveBeenCalledWith(20, { background: 'Raised on the river.' })
    );
    await waitFor(() =>
      expect(
        screen.queryByRole('textbox', { name: 'Where they come from' })
      ).not.toBeInTheDocument()
    );
  });

  it('saves a number field as a number', async () => {
    const user = userEvent.setup();
    patchStaffEdit.mockResolvedValue(sheet());
    sessionStorage.setItem('arx.staffEditMode', '1');
    renderSheet(sheet());

    await user.click(screen.getByRole('button', { name: 'Edit Social rank' }));
    const box = screen.getByRole('spinbutton', { name: 'Social rank' });
    await user.clear(box);
    await user.type(box, '4');
    await user.click(screen.getByRole('button', { name: 'Save' }));

    await waitFor(() => expect(patchStaffEdit).toHaveBeenCalledWith(20, { social_rank: 4 }));
  });

  it("lists a field's versions and restores one", async () => {
    const user = userEvent.setup();
    fetchProfileTextVersions.mockResolvedValue([
      {
        id: 7,
        field: 'background',
        text: 'Raised at the old quay.',
        created_at: '2026-10-01T10:00:00Z',
        ic_date_display: '',
        era_display_name: 'Season 1',
        staff_edited: true,
        reasoning: '',
      },
      {
        id: 8,
        field: 'fear',
        text: 'Fire.',
        created_at: '2026-10-01T10:00:00Z',
        ic_date_display: '',
        era_display_name: null,
        staff_edited: false,
        reasoning: '',
      },
    ]);
    restoreProfileTextVersion.mockResolvedValue(sheet());
    sessionStorage.setItem('arx.staffEditMode', '1');
    renderSheet(sheet());

    await user.click(screen.getByRole('button', { name: 'History of Where they come from' }));
    const history = await screen.findByRole('region', { name: 'Where they come from history' });
    expect(await within(history).findByText('Raised at the old quay.')).toBeInTheDocument();
    expect(within(history).queryByText('Fire.')).not.toBeInTheDocument();

    await user.click(within(history).getByRole('button', { name: 'Restore' }));
    await waitFor(() => expect(restoreProfileTextVersion).toHaveBeenCalledWith(20, 7));
  });
});
