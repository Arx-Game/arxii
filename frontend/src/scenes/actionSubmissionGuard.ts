/** Prevents one correlated attached action from being dispatched twice. */
export class AttachedActionSubmissionGuard {
  private readonly inFlight = new Set<string>();
  private readonly completed = new Set<string>();

  /** Claims an id, returning false when it is already running or complete. */
  start(id: string): boolean {
    if (this.inFlight.has(id) || this.completed.has(id)) return false;
    this.inFlight.add(id);
    return true;
  }

  /** Marks a request complete and prevents replayed prose acknowledgements. */
  succeed(id: string): void {
    this.inFlight.delete(id);
    this.completed.add(id);
  }

  /** Releases a failed request so the player can retry it. */
  fail(id: string): void {
    this.inFlight.delete(id);
  }
}
