/**
 * RankingBoardCard — the diegetic herald/Academy board, web-first (#761).
 *
 * Renders inside the focused-item view when the in-world object carries a
 * RankingDisplay. Names + qualitative band labels only — raw numbers never
 * reach the client (the exact figures are hidden mechanics; the world
 * speaks in phrases). The cloaked state shows non-members that a board
 * exists without revealing its names.
 */
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';

import { useRankingBoard } from '../queries';

interface RankingBoardCardProps {
  /** The focused in-world object's id (RankingDisplay is keyed on it). */
  objectId: number;
}

export function RankingBoardCard({ objectId }: RankingBoardCardProps) {
  const { data: board } = useRankingBoard(objectId);
  if (!board) return null; // not a board (or still loading) — stay silent

  const renderBoard = () => {
    if (board.cloaked) {
      return (
        <p className="text-sm italic text-muted-foreground" data-testid="ranking-cloaked">
          The names recorded here are not meant for you.
        </p>
      );
    }
    if (board.rows.length === 0) {
      return <p className="text-sm text-muted-foreground">No names worth recording.</p>;
    }
    return (
      <ol className="space-y-1 text-sm" data-testid="ranking-rows">
        {board.rows.map((row) => (
          <li key={row.persona_name} className="flex items-baseline justify-between gap-2">
            <span className="font-medium">{row.persona_name}</span>
            {row.band_label ? (
              <span className="text-muted-foreground">{row.band_label}</span>
            ) : null}
          </li>
        ))}
      </ol>
    );
  };

  return (
    <Card data-testid="ranking-board">
      <CardHeader>
        <CardTitle className="text-base">{board.title}</CardTitle>
      </CardHeader>
      <CardContent>{renderBoard()}</CardContent>
    </Card>
  );
}
