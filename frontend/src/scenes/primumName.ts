/** "fire" -> "Fire Primum": how a substance's Primum is named to a player (#5125). */
export function primumName(substanceName: string): string {
  return `${substanceName.charAt(0).toUpperCase()}${substanceName.slice(1)} Primum`;
}
