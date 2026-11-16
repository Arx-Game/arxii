/**
 * The page-turn (#3540): the way back, the door forward, and the reason a door is closed.
 * Back and forward are the same button (owner ruling 2026-11-16, #5146), and a stage may
 * put one door of its own between them.
 */

interface Door {
  label: string;
  onClick: () => void;
}
interface BetweenDoor extends Door {
  disabled?: boolean;
}
interface NextDoor extends Door {
  disabled?: boolean;
  /** Shown beside the door while it is disabled; also its aria-describedby. */
  reason?: string;
}
interface PageTurnProps {
  back?: Door;
  /** A door of the stage's own, drawn between the way back and the way forward. */
  between?: BetweenDoor;
  next?: NextDoor;
}

export function PageTurn({ back, between, next }: PageTurnProps) {
  const reasonId = next?.reason ? 'page-turn-reason' : undefined;
  return (
    <div className="page-turn">
      {back ? (
        <button type="button" className="btn" onClick={back.onClick}>
          {back.label}
        </button>
      ) : (
        <span />
      )}
      {between && (
        <button type="button" className="btn" disabled={between.disabled} onClick={between.onClick}>
          {between.label}
        </button>
      )}
      {next && (
        <span className="plate-door" style={{ margin: 0 }}>
          {next.disabled && next.reason && (
            <span className="door-reason" id={reasonId} tabIndex={-1}>
              {next.reason}
            </span>
          )}
          <button
            type="button"
            className="btn"
            aria-disabled={next.disabled ? 'true' : undefined}
            aria-describedby={next.disabled ? reasonId : undefined}
            onClick={() => {
              if (next.disabled) {
                document.getElementById(reasonId ?? '')?.focus();
                return;
              }
              next.onClick();
            }}
          >
            {next.label}
          </button>
        </span>
      )}
    </div>
  );
}
