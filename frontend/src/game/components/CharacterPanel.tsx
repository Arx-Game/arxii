import { useAppSelector } from '../../store/hooks'

export function CharacterPanel() {
  const currentCharacter = useAppSelector((state) => state.game.currentCharacter)

  return (
    <div className="rounded-lg border bg-card p-4">
      <h3 className="mb-2 font-semibold">Character</h3>
      {currentCharacter ? (
        <p className="text-sm">{currentCharacter}</p>
      ) : (
        <p className="text-sm text-muted-foreground">No character selected</p>
      )}
    </div>
  )
}
