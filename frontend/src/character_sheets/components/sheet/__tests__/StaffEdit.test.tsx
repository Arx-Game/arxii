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
const fetchStaffOptions = vi.fn();
const runStaffRowAction = vi.fn();
const fetchStaffMagicOptions = vi.fn();

vi.mock('@/character_sheets/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/character_sheets/api')>();
  return {
    ...actual,
    patchStaffEdit: (...args: unknown[]) => patchStaffEdit(...args),
    restoreProfileTextVersion: (...args: unknown[]) => restoreProfileTextVersion(...args),
    fetchStaffOptions: (...args: unknown[]) => fetchStaffOptions(...args),
    runStaffRowAction: (...args: unknown[]) => runStaffRowAction(...args),
    fetchStaffMagicOptions: (...args: unknown[]) => fetchStaffMagicOptions(...args),
  };
});
vi.mock('@/sheet_update_requests/api', () => ({
  fetchProfileTextVersions: (...args: unknown[]) => fetchProfileTextVersions(...args),
}));

const STORED: CharacterSheetStaffEdit = {
  rows: {
    stats: {},
    skills: {},
    specializations: {},
    distinctions: [],
    form: {},
    markings: [],
    beginnings: null,
    path: null,
    class_level: null,
    public_being: null,
    secret_being: null,
    has_vitals: true,
    has_gift: true,
    has_aura: false,
  },
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
    glimpse: '',
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

const OPTIONS = {
  stats: [
    { id: 1, name: 'strength' },
    { id: 2, name: 'wits' },
  ],
  skills: [],
  specializations: [],
  distinctions: [{ id: 30, name: 'Keen Eyes' }],
  form_traits: [],
  beginnings: [],
  paths: [],
  beings: [],
  marking_regions: [],
  marking_kinds: [],
  enemy_kinds: [],
  enemy_degrees: [],
  enemy_power_tiers: [],
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
    runStaffRowAction.mockReset();
    fetchStaffOptions.mockReset();
    fetchStaffOptions.mockResolvedValue(OPTIONS);
    fetchStaffMagicOptions.mockReset();
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

  it('saves the stats a staff editor fills on a sheet that had none (#4221)', async () => {
    const user = userEvent.setup();
    runStaffRowAction.mockResolvedValue(sheet());
    sessionStorage.setItem('arx.staffEditMode', '1');
    renderSheet(sheet());

    const rowsBand = await screen.findByTestId('staff-rows-band');
    await user.type(within(rowsBand).getByRole('spinbutton', { name: 'strength' }), '3');
    await user.click(within(rowsBand).getByRole('button', { name: 'Save stats' }));
    await waitFor(() =>
      expect(runStaffRowAction).toHaveBeenCalledWith(20, {
        path: 'staff-stats',
        method: 'PATCH',
        body: { stats: { '1': 3 } },
      })
    );
  });

  it('removes a held distinction without a request (#4221)', async () => {
    const user = userEvent.setup();
    runStaffRowAction.mockResolvedValue(sheet());
    sessionStorage.setItem('arx.staffEditMode', '1');
    const held = sheet({
      staff_edit: {
        ...STORED,
        rows: {
          ...STORED.rows,
          distinctions: [
            { id: 77, distinction: 30, name: 'Keen Eyes', rank: 1, max_rank: 1, feature: '' },
          ],
        },
      },
    });
    renderSheet(held);

    const rowsBand = await screen.findByTestId('staff-rows-band');
    await user.click(within(rowsBand).getByRole('button', { name: 'Remove Keen Eyes' }));
    await waitFor(() =>
      expect(runStaffRowAction).toHaveBeenCalledWith(20, {
        path: 'staff-distinction',
        method: 'PATCH',
        body: { character_distinction: 77 },
      })
    );
  });
  it('grants magic to a giftless sheet, each pick narrowing the next (#4224)', async () => {
    const user = userEvent.setup();
    runStaffRowAction.mockResolvedValue(sheet());
    fetchStaffMagicOptions.mockImplementation(
      async (_sheet: number, tradition: string, gift: string) => ({
        traditions: [{ id: 5, name: 'Lamplighters' }],
        gifts: tradition ? [{ id: 6, name: 'Embers' }] : [],
        techniques: gift
          ? [
              { id: 7, name: 'Kindle' },
              { id: 8, name: 'Smother' },
            ]
          : [],
        resonances: gift ? [{ id: 9, name: 'Warmth' }] : [],
        stats: [{ id: 1, name: 'strength' }],
        skills: [{ id: 2, name: 'Occult' }],
        technique_limit: 1,
      })
    );
    sessionStorage.setItem('arx.staffEditMode', '1');
    renderSheet(sheet({ staff_edit: { ...STORED, rows: { ...STORED.rows, has_gift: false } } }));

    const editor = await screen.findByTestId('staff-magic-editor');
    await user.selectOptions(within(editor).getByRole('combobox', { name: 'Tradition' }), '5');
    await user.selectOptions(await within(editor).findByRole('combobox', { name: 'Gift' }), '6');
    await user.click(await within(editor).findByRole('checkbox', { name: 'Kindle' }));
    expect(within(editor).getByRole('checkbox', { name: 'Smother' })).toBeDisabled();
    await user.selectOptions(within(editor).getByRole('combobox', { name: 'Resonance' }), '9');
    await user.selectOptions(within(editor).getByRole('combobox', { name: 'Anima stat' }), '1');
    await user.selectOptions(within(editor).getByRole('combobox', { name: 'Anima skill' }), '2');
    await user.type(within(editor).getByRole('textbox', { name: 'Glimpse' }), 'A spark.');
    await user.click(within(editor).getByRole('button', { name: 'Grant magic' }));
    await waitFor(() =>
      expect(runStaffRowAction).toHaveBeenCalledWith(20, {
        path: 'staff-magic',
        method: 'POST',
        body: {
          tradition: 5,
          gift: 6,
          techniques: [7],
          resonance: 9,
          anima_stat: 1,
          anima_skill: 2,
          ritual_name: '',
          glimpse: 'A spark.',
        },
      })
    );
  });

  it('offers no Grant magic once the sheet holds a gift (#4224)', async () => {
    sessionStorage.setItem('arx.staffEditMode', '1');
    renderSheet(sheet());
    await screen.findByTestId('staff-rows-band');
    expect(screen.queryByTestId('staff-magic-editor')).not.toBeInTheDocument();
    expect(fetchStaffMagicOptions).not.toHaveBeenCalled();
  });
});
