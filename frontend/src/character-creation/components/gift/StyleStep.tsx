/**
 * StyleStep (#4921): the Gift funnel's style step, after the Resonance. Lists the combat
 * styles the draft's Tradition teaches (GET /api/character-creation/combat-styles/), each
 * with how it attacks (weapon kinds, hit stat) and defends (defense style, armor kinds and
 * how much armor counts). Character creation never mentions covenant vows. Choosing one
 * saves `selected_combat_style_id`; the server narrows the training list to its skill.
 */

import { Entry, EntryDoors, EntryList } from '../../folio';
import { useUpdateDraft } from '../../queries';
import type { CGCombatStyleOption, CharacterDraft } from '../../types';
import { attacksLine, defendsLine } from './styleLines';

interface StyleStepProps {
  draft: CharacterDraft;
  styles: CGCombatStyleOption[];
}

function StyleProfile({ style }: { style: CGCombatStyleOption }) {
  const attacks = attacksLine(style);
  return (
    <>
      {attacks && (
        <>
          <span className="profile-key">Attacks</span>
          <span>{attacks}</span>
        </>
      )}
      <span className="profile-key">Defends</span>
      <span>{defendsLine(style)}</span>
    </>
  );
}

export function StyleStep({ draft, styles }: StyleStepProps) {
  const updateDraft = useUpdateDraft();
  const chosenId = draft.selected_combat_style;

  const handleChoose = (styleId: number) => {
    if (styleId === chosenId) return;
    updateDraft.mutate({ draftId: draft.id, data: { selected_combat_style_id: styleId } });
  };

  return (
    <EntryList label="Fighting styles">
      {styles.map((style) => {
        const isChosen = chosenId === style.id;
        return (
          <Entry
            key={style.id}
            name={style.name}
            gloss={style.description || undefined}
            tag={style.defense_style_display}
            chosen={isChosen}
            open={false}
            onChoose={() => handleChoose(style.id)}
            profile={<StyleProfile style={style} />}
          >
            <EntryDoors
              chooseLabel={`Select ${style.name}`}
              onChoose={() => handleChoose(style.id)}
              chosen={isChosen}
            />
          </Entry>
        );
      })}
    </EntryList>
  );
}
