/** The page-turn (#3540): a quiet way back, one primary door forward, and the reason a door is closed. */

interface Door {
  label: string;
  onClick: () => void;
}
interface NextDoor extends Door {
  disabled?: boolean;
  /** Shown beside the door while it is disabled; also its aria-describedby. */
  reason?: string;
}
interface PageTurnProps {
  back?: Door;
  next?: NextDoor;
}

export function PageTurn({ back, next }: PageTurnProps) {
  const reasonId = next?.reason ? 'page-turn-reason' : undefined;
  return (
    <div className="page-turn">
      {back ? (
        <button type="button" className="btn-quiet" onClick={back.onClick}>
          ‹ {back.label}
        </button>
      ) : (
        <span />
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
