/**
 * Stage 5: Path (#3630).
 *
 * Paths as index entries: reading is free, and a path enters the draft only
 * when the player chooses it (never on hover, Decision 6). A path's authored
 * icon (staff-set on Path.icon_name) leads its entry name. The record rail
 * lists the choices made so far; it explains nothing (Decision 8).
 */

import {
  BookOpen,
  Crown,
  Eye,
  Flame,
  Heart,
  type LucideIcon,
  MessageCircle,
  Moon,
  Shield,
  Sparkles,
  Sun,
  Swords,
  TreePine,
  Wand2,
  Zap,
} from 'lucide-react';
import {
  ChapterLeaf,
  CodexLine,
  Entry,
  EntryDoors,
  EntryList,
  Marginalia,
  Note,
  Paragraphs,
  RecordRail,
} from '../folio';
import { useCGExplanations, usePaths, useUpdateDraft } from '../queries';
import type { CharacterDraft, Path } from '../types';
import { Stage } from '../types';

interface PathStageProps {
  draft: CharacterDraft;
}

// Map icon_name strings (from Django admin) to Lucide components.
// Staff can use these names in the Path.icon_name field.
const ICON_MAP: Record<string, LucideIcon> = {
  swords: Swords,
  eye: Eye,
  'message-circle': MessageCircle,
  'book-open': BookOpen,
  sparkles: Sparkles,
  shield: Shield,
  crown: Crown,
  flame: Flame,
  heart: Heart,
  moon: Moon,
  sun: Sun,
  'tree-pine': TreePine,
  wand2: Wand2,
  zap: Zap,
};

export function PathStage({ draft }: PathStageProps) {
  const { data: paths, isLoading, error } = usePaths();
  const { data: copy } = useCGExplanations();
  const updateDraft = useUpdateDraft();

  const choose = (path: Path | null) => {
    updateDraft.mutate({
      draftId: draft.id,
      data: { selected_path_id: path?.id ?? null },
    });
  };

  if (isLoading)
    return (
      <p className="ledger-line" aria-busy="true">
        Loading paths…
      </p>
    );
  if (error) return <p className="ledger-line">The paths could not be read. Try again.</p>;

  const rail = (
    <>
      <RecordRail
        rows={[
          { label: 'Origin', value: draft.selected_area?.name },
          { label: 'Beginnings', value: draft.selected_beginnings?.name },
          { label: 'Species', value: draft.selected_species?.name },
          { label: 'Path', value: draft.selected_path?.name },
        ]}
        ledger="Stage 5 of 11"
      />
      <Marginalia id="note-path">
        {/* PLACEHOLDER: Apostate rewrite */}
        <Note lead="Paths">
          set starting skill suggestions; you freely allocate skills in the stage that follows.
        </Note>
      </Marginalia>
    </>
  );

  return (
    <ChapterLeaf
      stage={Stage.PATH}
      title={copy?.path_heading ?? 'Choose Your Path'}
      intro={copy?.path_intro}
      aside={rail}
    >
      {copy?.path_lore_durance && (
        <div className="leaf-body">
          <p>{copy.path_lore_durance}</p>
        </div>
      )}
      <EntryList label="Paths">
        {paths?.map((p) => {
          const Icon = ICON_MAP[p.icon_name.toLowerCase()] ?? Sparkles;
          const isChosen = draft.selected_path?.id === p.id;
          return (
            <Entry
              key={p.id}
              name={p.name}
              lead={<Icon />}
              tag={p.aspects.join(' · ') || 'Path'}
              chosen={isChosen}
              open={isChosen}
            >
              <Paragraphs text={p.description} />
              {p.skill_suggestions && p.skill_suggestions.length > 0 && (
                <p className="ledger-line">
                  Suggested skills: {p.skill_suggestions.map((s) => s.skill_name).join(', ')}
                </p>
              )}
              <CodexLine entryId={p.codex_entry_ids?.[0]} name={p.name} />
              <EntryDoors
                chooseLabel={`Choose ${p.name}`}
                onChoose={() => choose(p)}
                chosen={isChosen}
                onSetAside={() => choose(null)}
              />
            </Entry>
          );
        })}
      </EntryList>
    </ChapterLeaf>
  );
}
