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

  it('shows the fighting style with how it attacks and defends and its skill value (#4921)', () => {
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
      skill_name: 'The Daring Dance',
      skill_value: 30,
    };
    renderSheet(sheet);
    expect(screen.getByText('Fighting style')).toBeInTheDocument();
    expect(screen.getByText('Evasion')).toBeInTheDocument();
    expect(screen.getByText('Never where the blow lands.')).toBeInTheDocument();
    expect(
      screen.getByText('Attacks: one-handed melee, thrown · hits with Agility')
    ).toBeInTheDocument();
    expect(screen.getByText('Defends: evasion · light armor, 3 of 10 counts')).toBeInTheDocument();
    expect(screen.getByText('The Daring Dance 30')).toBeInTheDocument();
    expect(document.body).not.toHaveTextContent(/vow/i);
  });

  it('has no fighting style block without a style (or for a stranger)', () => {
    renderSheet(payload({ family: null }));
    expect(screen.queryByText('Fighting style')).not.toBeInTheDocument();
  });

  it('has no House row for a character without a family', () => {
    renderSheet(payload({ family: null }));
    expect(screen.queryByText('House')).not.toBeInTheDocument();
  });
});
