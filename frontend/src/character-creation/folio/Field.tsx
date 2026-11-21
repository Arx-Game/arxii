/** Forms as writing (#3540): an inscription label over a serif control on a hairline. */
import type { ReactNode } from 'react';

interface FieldProps {
  id: string;
  label: string;
  hint?: string;
  /** A width class for a field that sits in a `.field-row` (#5241), e.g. `narrow`. */
  className?: string;
  children: ReactNode;
}

export function Field({ id, label, hint, className, children }: FieldProps) {
  return (
    <div className={className ? `field ${className}` : 'field'}>
      <label htmlFor={id}>{label}</label>
      {children}
      {hint && <span className="hint">{hint}</span>}
    </div>
  );
}
