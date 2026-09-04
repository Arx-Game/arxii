/** An in-world confirm on a native <dialog> (#3540): one door, one quiet way back. */
import { useEffect, useRef, type ReactNode } from 'react';

interface ConfirmDialogProps {
  open: boolean;
  title: string;
  children: ReactNode;
  confirmLabel: string;
  cancelLabel: string;
  onConfirm: () => void;
  onCancel: () => void;
}

export function ConfirmDialog({
  open,
  title,
  children,
  confirmLabel,
  cancelLabel,
  onConfirm,
  onCancel,
}: ConfirmDialogProps) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    if (open && !el.open) {
      // jsdom (and some older browsers) lack HTMLDialogElement.showModal; fall back
      // to the plain `open` attribute so the dialog still appears (#3540 review).
      if (typeof el.showModal === 'function') el.showModal();
      else el.setAttribute('open', '');
    }
    if (!open && el.open) el.close();
  }, [open]);
  return (
    <dialog ref={ref} className="confirm" onCancel={onCancel}>
      <h2>{title}</h2>
      <p>{children}</p>
      <div className="doors">
        <button type="button" className="btn" onClick={onConfirm}>
          {confirmLabel}
        </button>
        <button type="button" className="btn-quiet" onClick={onCancel}>
          {cancelLabel}
        </button>
      </div>
    </dialog>
  );
}
