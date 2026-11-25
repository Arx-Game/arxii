/**
 * The open-box state behind a term's definition box (``DefinedTerm.tsx``, #5206): which
 * term is open, where its word sits, whether a click pinned it, and the document
 * listeners that close it (Escape, a scroll, any other click).
 */

import { useCallback, useEffect, useState } from 'react';

/** The one open box: which term, where its word sits, and whether a click pinned it. */
export interface OpenTerm {
  name: string;
  top: number;
  left: number;
  pinned: boolean;
}

/** Where a definition box goes: viewport coordinates under the word, clamped so the box
 * stays on screen. */
function placeTerm(target: HTMLElement): { top: number; left: number } {
  const rect = target.getBoundingClientRect();
  const width = Math.min(352, window.innerWidth - 24);
  const left = Math.max(12, Math.min(rect.left, window.innerWidth - width - 12));
  const top = rect.bottom + 180 > window.innerHeight ? rect.top - 180 : rect.bottom + 6;
  return { top, left };
}

export interface TermPopoverState {
  openTerm: OpenTerm | null;
  /** The pointer or the focus is on a term: show it, unless it is already open. */
  peek: (target: HTMLElement, name: string) => void;
  /** The pointer or the focus leaves: a pinned box stays. */
  leave: (name: string) => void;
  /** A click or tap: pin it open, or close the one this click had pinned. */
  pin: (target: HTMLElement, name: string) => void;
}

/** The open-box state and the document listeners that close it. */
export function useTermPopover(): TermPopoverState {
  const [openTerm, setOpenTerm] = useState<OpenTerm | null>(null);
  useEffect(() => {
    if (!openTerm) return;
    const close = () => setOpenTerm(null);
    // Any click closes it: a click on a term stops before it reaches the document, and
    // the box itself takes no pointer.
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') close();
    };
    document.addEventListener('click', close);
    document.addEventListener('keydown', onKey);
    window.addEventListener('scroll', close, { passive: true });
    return () => {
      document.removeEventListener('click', close);
      document.removeEventListener('keydown', onKey);
      window.removeEventListener('scroll', close);
    };
  }, [openTerm]);
  const peek = useCallback((target: HTMLElement, name: string) => {
    setOpenTerm((current) =>
      current?.name === name ? current : { name, ...placeTerm(target), pinned: false }
    );
  }, []);
  const leave = useCallback((name: string) => {
    setOpenTerm((current) => (current?.name === name && !current.pinned ? null : current));
  }, []);
  const pin = useCallback((target: HTMLElement, name: string) => {
    setOpenTerm((current) =>
      current?.name === name && current.pinned ? null : { name, ...placeTerm(target), pinned: true }
    );
  }, []);
  return { openTerm, peek, leave, pin };
}
