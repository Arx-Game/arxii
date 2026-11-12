/**
 * SheetPanel (#3898) — the front of the character sheet. Only the rows a reading
 * needs are filled in; the rest of the payload is the serializer's empty shape.
 */
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it } from 'vitest';

import type { CharacterSheetPayload } from '@/character_sheets/api';
import { SheetPanel } from '../SheetPanel';

function payload(overrides: { family: { id: number; name: string } | null }) {
  return {
    id: 20,
    can_edit: false,
    identity: {
      name: 'Kathryn mar Katta',
      fullname: 'Kathryn mar Katta',
      concept: '',
      quote: '',
      age: 24,
      birthday: null,
      chronological_age: null,
      biological_age: null,
      withered_years: null,
      gender: null,
      pronouns: { subject: 'she', object: 'her', possessive: 'hers' },
      species: null,
      heritage: null,
      beginnings: [],
      family: overrides.family,
      tarot_card: null,
      origin: null,
      path: null,
      worship: null,
      worship_sincere: null,
      current_mood: null,
      vacancy: null,
    },
    appearance: {
      height_inches: null,
      height_band: '',
      build: null,
      description: '',
      form_traits: [],
    },
    stats: {},
    buffed_stats: {},
    skills: [],
    path: null,
    distinctions: [],
    magic: null,
    story: { background: '', origin_story_state: 'NOT_STARTED', origin_slots: [] },
    actor_sheet: {
      never_do: '',
      protect: '',
      fear: '',
      enemy_public_line: '',
      enemy: null,
      introductions: [],
    },
    goals: [],
    beats: [],
    personas: [],
    theming: {},
    profile_picture: null,
    current_residence: null,
    looks: [],
    plate_ink: 'ember',
    worn: [],
    natural_weapons: [],
    combat_style: null,
    mentors: [],
    domains: [],
    keyring: [],
    standing: { memberships: [], reputations: [] },
    covenants: [],
    ties: [],
    ties_ap_this_week: null,
  } as unknown as CharacterSheetPayload;
}

function renderSheet(sheet: CharacterSheetPayload) {
  return render(
    <MemoryRouter>
      <SheetPanel sheet={sheet} isMyCharacter={false} rumor={null} languages={null} />
    </MemoryRouter>
  );
}

describe('SheetPanel', () => {
  it('links the House row to the family page by the Family pk, never the org route', () => {
    // A Family pk is not an Organization pk, and the org page is member-only
    // besides (#4210); the family page is keyed by the Family pk (#4209).
    renderSheet(payload({ family: { id: 7, name: 'Katta' } }));
    expect(screen.getByRole('link', { name: 'Katta' })).toHaveAttribute('href', '/families/7');
    expect(document.querySelector('a[href^="/orgs/"]')).toBeNull();
  });

  it('shows the fighting style card: tradition, attacks, defends, vows and its skill (#4921)', () => {
    const sheet = payload({ family: null });
    sheet.combat_style = {
      id: 3,
      name: 'The Daring Dance',
      description: 'Never where the blow lands.',
      defense_style: 'evasion',
      defense_style_display: 'Evasion',
      armor_share_tenths: 3,
      hit_stat_name: 'agility',
      weapon_kinds: [
        { value: 'melee_one_hand', label: 'One-Handed Melee' },
        { value: 'thrown', label: 'Thrown' },
      ],
      armor_kinds: [{ value: 'light_armor', label: 'Light Armor' }],
      skill_name: 'The Daring Dance Skill',
      skill_value: 30,
      tradition_name: 'Masque',
      vows: ['Quicksilver', 'Warden'],
    };
    renderSheet(sheet);
    expect(screen.getByText('Fighting style')).toBeInTheDocument();
    expect(screen.getByText('Evasion')).toBeInTheDocument();
    expect(screen.getByText('Never where the blow lands.')).toBeInTheDocument();
    const row = (label: string) => screen.getByText(label, { selector: 'dt' }).nextElementSibling;
    expect(row('Tradition')).toHaveTextContent('Masque');
    expect(row('Attacks')).toHaveTextContent('one-handed melee, thrown · hits with Agility');
    expect(row('Defends')).toHaveTextContent('evasion · light armor, 3 of 10 counts');
    // The sheet shows the style's vows (demo screen 6); creation never does.
    expect(row('Vows')).toHaveTextContent('Quicksilver, Warden');
    expect(row('The Daring Dance Skill')).toHaveTextContent('30');
  });

  it('drops the Tradition and Vows rows when the style has neither', () => {
    const sheet = payload({ family: null });
    sheet.combat_style = {
      id: 4,
      name: 'Stillwater Hand',
      description: '',
      defense_style: 'evasion',
      defense_style_display: 'Evasion',
      armor_share_tenths: 0,
      hit_stat_name: null,
      weapon_kinds: [{ value: 'unarmed', label: 'Unarmed' }],
      armor_kinds: [],
      skill_name: '',
      skill_value: 0,
      tradition_name: null,
      vows: [],
    };
    renderSheet(sheet);
    expect(screen.getByText('Stillwater Hand')).toBeInTheDocument();
    expect(screen.queryByText('Tradition', { selector: 'dt' })).not.toBeInTheDocument();
    expect(screen.queryByText('Vows', { selector: 'dt' })).not.toBeInTheDocument();
    expect(screen.getByText('Attacks', { selector: 'dt' }).nextElementSibling).toHaveTextContent(
      'unarmed'
    );
  });

  it('has no fighting style block without a style (or for a stranger)', () => {
    renderSheet(payload({ family: null }));
    expect(screen.queryByText('Fighting style')).not.toBeInTheDocument();
  });

  it('has no House row for a character without a family', () => {
    renderSheet(payload({ family: null }));
    expect(screen.queryByText('House')).not.toBeInTheDocument();
  });

  it('shows a buffed stat beside its stored value and an unbuffed one alone (#4730)', () => {
    const sheet = payload({ family: null });
    sheet.stats = { strength: 2, agility: 3, wits: 5 };
    sheet.buffed_stats = { strength: 9, wits: 4 };
    renderSheet(sheet);
    const rows = screen.getByTestId('stats-grid').querySelectorAll('.refsheet-stat');
    expect(rows[0]).toHaveTextContent('Strength2 (9 with buffs)');
    expect(rows[1]).toHaveTextContent(/^Agility3$/);
    expect(rows[2]).toHaveTextContent('Wits5 (4 with debuffs)');
    expect(screen.getAllByTestId('stat-buffed')).toHaveLength(2);
  });
});
