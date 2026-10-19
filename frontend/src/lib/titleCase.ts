/** "agility" -> "Agility", "melee combat" -> "Melee Combat"; for display only. */
export function titleCase(name: string): string {
  return name.replace(/\b\p{L}/gu, (letter) => letter.toUpperCase());
}
