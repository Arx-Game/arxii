/**
 * Stage 7: Identity
 *
 * Name, description, personality, and background fields.
 */

import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { motion } from 'framer-motion';
import { useCallback, useEffect, useRef, useState } from 'react';
import { useUpdateDraft } from '../queries';
import type { CharacterDraft } from '../types';

interface IdentityStageProps {
  draft: CharacterDraft;
  onRegisterBeforeLeave?: (check: () => Promise<boolean>) => void;
}

export function IdentityStage({ draft, onRegisterBeforeLeave }: IdentityStageProps) {
  const updateDraft = useUpdateDraft();
  const draftData = draft.draft_data;

  // Local state for text fields — saved on navigation, not on every keystroke
  const [localFirstName, setLocalFirstName] = useState(draftData.first_name ?? '');
  const [localPersonality, setLocalPersonality] = useState(draftData.personality ?? '');
  const [localBackground, setLocalBackground] = useState(draftData.background ?? '');

  const localFieldsRef = useRef({ first_name: '', personality: '', background: '' });
  localFieldsRef.current = {
    first_name: localFirstName,
    personality: localPersonality,
    background: localBackground,
  };

  const saveFields = useCallback(async () => {
    const fields = localFieldsRef.current;
    const server = draft.draft_data;
    const hasChanges =
      fields.first_name !== (server.first_name ?? '') ||
      fields.personality !== (server.personality ?? '') ||
      fields.background !== (server.background ?? '');

    if (!hasChanges) return true;

    try {
      await updateDraft.mutateAsync({
        draftId: draft.id,
        data: {
          draft_data: {
            ...server,
            ...fields,
          },
        },
      });
      return true;
    } catch {
      return window.confirm('Failed to save. Discard changes and continue?');
    }
  }, [draft.id, draft.draft_data, updateDraft]);

  useEffect(() => {
    if (onRegisterBeforeLeave) {
      onRegisterBeforeLeave(saveFields);
    }
  }, [onRegisterBeforeLeave, saveFields]);

  const familyName =
    draft.family?.name ?? (draft.selected_beginnings?.family_known === false ? '' : '');
  const fullNamePreview = localFirstName
    ? familyName
      ? `${localFirstName} ${familyName}`
      : localFirstName
    : '';

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -20 }}
      transition={{ duration: 0.3 }}
      className="space-y-8"
    >
      <div>
        <h2 className="text-2xl font-bold">Identity</h2>
        <p className="mt-2 text-muted-foreground">Define your character's name and story.</p>
      </div>

      {/* Name */}
      <section className="space-y-4">
        <h3 className="text-lg font-semibold">Character Name</h3>
        <div className="max-w-md space-y-2">
          <Label htmlFor="first-name">First Name</Label>
          <Input
            id="first-name"
            value={localFirstName}
            onChange={(e) => setLocalFirstName(e.target.value)}
            placeholder="Enter first name"
            maxLength={20}
          />
          <p className="text-xs text-muted-foreground">
            2-20 characters, letters only, first letter will be capitalized.
          </p>
          {fullNamePreview && (
            <p className="mt-2 text-sm">
              Full name: <span className="font-semibold">{fullNamePreview}</span>
            </p>
          )}
        </div>
      </section>

      {/* Personality */}
      <section className="space-y-4">
        <h3 className="text-lg font-semibold">Personality</h3>
        <div className="space-y-2">
          <Label htmlFor="personality">Personality Traits</Label>
          <Textarea
            id="personality"
            value={localPersonality}
            onChange={(e) => setLocalPersonality(e.target.value)}
            placeholder="Describe your character's personality..."
            rows={3}
            className="resize-y"
          />
          <p className="text-xs text-muted-foreground">
            How does your character think, feel, and behave?
          </p>
        </div>
      </section>

      {/* Background */}
      <section className="space-y-4">
        <h3 className="text-lg font-semibold">Background</h3>
        <div className="space-y-2">
          <Label htmlFor="background">Character History</Label>
          <Textarea
            id="background"
            value={localBackground}
            onChange={(e) => setLocalBackground(e.target.value)}
            placeholder="Tell us about your character's past..."
            rows={6}
            className="resize-y"
          />
          <p className="text-xs text-muted-foreground">
            Your character's history, motivations, and what brought them here.
          </p>
        </div>
      </section>
    </motion.div>
  );
}
