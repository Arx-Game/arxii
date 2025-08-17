import type { CommandSpec } from '../types';

/**
 * Insert field values into a command prompt template.
 *
 * The prompt may include parameter names that will be replaced by corresponding
 * values from `fields`. Comma-separated segments containing a parameter are
 * omitted if the parameter value is blank.
 *
 * Examples:
 * formatCommand("say message", { message: "hello" });
 * // -> "say hello"
 *
 * formatCommand("give item, target", { item: "coin", target: "bob" });
 * // -> "give coin, bob"
 *
 * // When target is empty the trailing comma segment is removed
 * formatCommand("give item, target", { item: "coin", target: "" });
 * // -> "give coin"
 */
export function formatCommand(prompt: string, fields: Record<string, string>): string {
  let command = prompt;

  // Remove optional comma-separated parts if the parameter is empty
  command = command.replace(/, ([a-z_]+)/g, (match, paramName) => {
    const hasValue = fields[paramName] && fields[paramName].trim() !== '';
    return hasValue ? match : '';
  });

  // Replace each parameter with its value
  Object.entries(fields).forEach(([key, value]) => {
    if (value && value.trim() !== '') {
      const regex = new RegExp(`\\b${key}\\b`, 'g');
      command = command.replace(regex, value);
    }
  });

  return command;
}

/**
 * Group commands by their category, defaulting to "General".
 */
export function groupCommands(commands: CommandSpec[]): Record<string, CommandSpec[]> {
  return commands.reduce((acc: Record<string, CommandSpec[]>, cmd) => {
    const category = cmd.category ?? 'General';
    acc[category] = acc[category] || [];
    acc[category].push(cmd);
    return acc;
  }, {});
}
