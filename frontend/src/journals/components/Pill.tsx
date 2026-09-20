/**
 * The Reading Room's pill (#3941) — a choice you can see the state of.
 *
 * Every either/or on this page wears one: which journal you are writing in,
 * what happens to a black entry after your death, who may retort to you, which
 * slice of a writer's journal you are reading. Pressed is `aria-pressed`, so
 * the state is a fact for a screen reader too, not just a fill colour.
 */
import { cn } from '@/lib/utils';

export interface PillButtonProps {
  pressed: boolean;
  onClick: () => void;
  children: React.ReactNode;
  className?: string;
}

export function PillButton({ pressed, onClick, children, className }: PillButtonProps) {
  return (
    <button
      type="button"
      aria-pressed={pressed}
      onClick={(event) => {
        event.stopPropagation();
        onClick();
      }}
      className={cn(
        'jr-sans jr-pill cursor-pointer rounded-full border px-[.9rem] py-[.3rem] text-[.8125rem]',
        pressed ? 'border-foreground bg-foreground text-background' : 'bg-transparent',
        className
      )}
    >
      {children}
    </button>
  );
}
