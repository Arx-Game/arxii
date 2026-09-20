/**
 * Your own journal's header (#3941) — your name, and the two standing choices
 * that belong to the whole journal rather than to any one entry.
 *
 * Both are the writer's, and both live here because they are answered once:
 * what becomes of your black journal after your death (the sheet-level
 * default a single entry may still override), and who may Retort or Condemn
 * you (ADR-0306 — rivals, or anyone). Praise and Nominate are never gated by
 * the second one, so it says nothing about them.
 *
 * Write trails the two switch groups in the same wrapping row (demo screen 4):
 * it renders here, inside the switches' own flex-wrap group, rather than as a
 * sibling in the page's header row, which would wrap onto its own line
 * independently of this (wide) block instead of trailing "Anyone".
 */
import { toast } from 'sonner';

import type { PosthumousJournalDisposition, RetortConsent } from '../api';
import { PRIMARY_BUTTON_CLASS } from '../fieldClasses';
import { useJournalSettings, usePatchJournalSettings } from '../queries';
import { PillButton } from './Pill';

export interface YourJournalHeaderProps {
  name: string;
  /** Renders Write trailing the switches when set; omitted when not docked. */
  onWrite?: () => void;
}

export function YourJournalHeader({ name, onWrite }: YourJournalHeaderProps) {
  const { data: settings } = useJournalSettings();
  const patchSettings = usePatchJournalSettings();

  function setDisposition(disposition: PosthumousJournalDisposition) {
    patchSettings.mutate({ disposition }, { onError: (err: Error) => toast.error(err.message) });
  }

  function setConsent(retort_consent: RetortConsent) {
    patchSettings.mutate({ retort_consent }, { onError: (err: Error) => toast.error(err.message) });
  }

  return (
    <div className="flex flex-wrap items-baseline justify-between gap-x-6 gap-y-3">
      <div>
        <div className="jr-sans text-[.6875rem] uppercase tracking-[.14em] text-muted-foreground">
          Your journal
        </div>
        <h1 className="m-0 font-display text-[1.6rem] font-semibold tracking-[.04em]">{name}</h1>
      </div>

      <div className="flex flex-wrap items-center gap-x-2 gap-y-2">
        {settings ? (
          <>
            <span className="jr-sans text-[.8125rem] text-muted-foreground">
              Black journal after your death
            </span>
            <div className="flex flex-wrap gap-1.5">
              <PillButton
                pressed={settings.posthumous_journal_disposition === 'reveal'}
                onClick={() => setDisposition('reveal')}
                className="px-3"
              >
                Reveal
              </PillButton>
              <PillButton
                pressed={settings.posthumous_journal_disposition === 'seal'}
                onClick={() => setDisposition('seal')}
                className="px-3"
              >
                Remain sealed
              </PillButton>
            </div>
            <span className="jr-sans text-[.8125rem] text-muted-foreground">
              Retorts and condemnation
            </span>
            <div className="flex flex-wrap gap-1.5">
              <PillButton
                pressed={settings.retort_consent === 'rivals'}
                onClick={() => setConsent('rivals')}
                className="px-3"
              >
                Rivals only
              </PillButton>
              <PillButton
                pressed={settings.retort_consent === 'anyone'}
                onClick={() => setConsent('anyone')}
                className="px-3"
              >
                Anyone
              </PillButton>
            </div>
          </>
        ) : null}
        {onWrite ? (
          <button type="button" className={PRIMARY_BUTTON_CLASS} onClick={onWrite}>
            Write
          </button>
        ) : null}
      </div>
    </div>
  );
}
