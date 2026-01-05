#!/usr/bin/env node

import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import {
  CallToolRequestSchema,
  ListToolsRequestSchema,
  ListPromptsRequestSchema,
  GetPromptRequestSchema,
} from "@modelcontextprotocol/sdk/types.js";
import { spawn } from "child_process";
import * as path from "path";

// Project root is 3 levels up from dist/index.js
const PROJECT_ROOT = path.resolve(
  path.dirname(new URL(import.meta.url).pathname.replace(/^\/([A-Z]:)/, "$1")),
  "..",
  "..",
  ".."
);
const SRC_DIR = path.join(PROJECT_ROOT, "src");

const EVENNIA_RULES = `# Evennia Development Rules

## Command Usage
- **Always use \`arx shell -c "..."\` or \`arx manage\`** instead of raw Python commands
- **Use Evennia commands** (\`arx start\`, \`arx shell\`, \`arx test\`) not Django commands (\`python manage.py\`, \`runserver\`)
- The \`arx\` CLI properly initializes Evennia's environment; direct Python/Django commands may fail

## Migrations
- **Never run \`makemigrations\` or \`migrate\` automatically** — generate migration files for manual review only
- When creating migrations, output the migration file content and let the user save and apply it manually
- Use the \`generate_migration_file\` tool to create migration content
- Use the \`check_migrations\` tool to see current migration status

## Models
- Use \`SharedMemoryModel\` (from \`evennia.utils.idmapper.models\`) for frequently-accessed, rarely-changed data
- This provides caching benefits for models like Family, Species, Origins, etc.

## Testing
- Run tests with \`arx test\` not \`python manage.py test\`
- Run \`arx manage migrate\` first if fresh environment

## Server
- Start server with \`arx start\` not \`arx manage runserver\`
- \`arx start\` properly starts Evennia with portal and server processes
`;

/**
 * Execute a command and return the output
 */
async function executeCommand(
  command: string,
  args: string[],
  cwd: string
): Promise<{ stdout: string; stderr: string; exitCode: number }> {
  return new Promise((resolve) => {
    const proc = spawn(command, args, {
      cwd,
      shell: true,
      env: { ...process.env },
    });

    let stdout = "";
    let stderr = "";

    proc.stdout.on("data", (data) => {
      stdout += data.toString();
    });

    proc.stderr.on("data", (data) => {
      stderr += data.toString();
    });

    proc.on("close", (code) => {
      resolve({
        stdout,
        stderr,
        exitCode: code ?? 1,
      });
    });

    proc.on("error", (err) => {
      resolve({
        stdout,
        stderr: err.message,
        exitCode: 1,
      });
    });
  });
}

const server = new Server(
  {
    name: "arxdev-evennia",
    version: "1.0.0",
  },
  {
    capabilities: {
      tools: {},
      prompts: {},
    },
  }
);

// List available tools
server.setRequestHandler(ListToolsRequestSchema, async () => {
  return {
    tools: [
      {
        name: "run_evennia_shell",
        description:
          "Execute Python code in the Evennia shell context. Use this instead of running Python directly.",
        inputSchema: {
          type: "object",
          properties: {
            code: {
              type: "string",
              description: "Python code to execute in the Evennia shell",
            },
          },
          required: ["code"],
        },
      },
      {
        name: "check_migrations",
        description:
          "Show the current migration status for all apps. Use this to see which migrations are applied or pending.",
        inputSchema: {
          type: "object",
          properties: {
            app: {
              type: "string",
              description: "Optional: specific app to check migrations for",
            },
          },
        },
      },
      {
        name: "generate_migration_file",
        description:
          "Generate migration file content for model changes. Returns the migration content for manual review and saving. NEVER applies migrations automatically.",
        inputSchema: {
          type: "object",
          properties: {
            app: {
              type: "string",
              description: "The app label to generate migrations for",
            },
            name: {
              type: "string",
              description: "Optional: name for the migration file",
            },
            dry_run: {
              type: "boolean",
              description: "If true, only show what would be generated without creating files",
              default: true,
            },
          },
          required: ["app"],
        },
      },
    ],
  };
});

// Handle tool calls
server.setRequestHandler(CallToolRequestSchema, async (request) => {
  const { name, arguments: args } = request.params;

  switch (name) {
    case "run_evennia_shell": {
      const code = (args as { code: string }).code;
      const result = await executeCommand("uv", ["run", "arx", "shell", "-c", code], SRC_DIR);

      return {
        content: [
          {
            type: "text",
            text:
              result.exitCode === 0
                ? result.stdout || "(no output)"
                : `Error (exit code ${result.exitCode}):\n${result.stderr}\n${result.stdout}`,
          },
        ],
      };
    }

    case "check_migrations": {
      const app = (args as { app?: string }).app;
      const cmdArgs = ["run", "arx", "manage", "showmigrations"];
      if (app) {
        cmdArgs.push(app);
      }

      const result = await executeCommand("uv", cmdArgs, SRC_DIR);

      return {
        content: [
          {
            type: "text",
            text:
              result.exitCode === 0
                ? result.stdout
                : `Error (exit code ${result.exitCode}):\n${result.stderr}\n${result.stdout}`,
          },
        ],
      };
    }

    case "generate_migration_file": {
      const { app, name: migrationName, dry_run = true } = args as {
        app: string;
        name?: string;
        dry_run?: boolean;
      };

      const cmdArgs = ["run", "arx", "manage", "makemigrations", app, "--dry-run"];
      if (migrationName) {
        cmdArgs.push("--name", migrationName);
      }

      // Always use --dry-run to prevent automatic file creation
      // The user must manually save and apply migrations
      const result = await executeCommand("uv", cmdArgs, SRC_DIR);

      let output = result.stdout;
      if (result.exitCode === 0) {
        output += "\n\n⚠️  This is a DRY RUN. No migration files were created.\n";
        output += "To create the migration, manually save the content above to:\n";
        output += `  src/${app}/migrations/<number>_<name>.py\n`;
        output += "Then run: arx manage migrate";
      }

      return {
        content: [
          {
            type: "text",
            text:
              result.exitCode === 0
                ? output
                : `Error (exit code ${result.exitCode}):\n${result.stderr}\n${result.stdout}`,
          },
        ],
      };
    }

    default:
      throw new Error(`Unknown tool: ${name}`);
  }
});

// List available prompts
server.setRequestHandler(ListPromptsRequestSchema, async () => {
  return {
    prompts: [
      {
        name: "evennia_rules",
        description:
          "Rules and guidelines for working with Evennia in the Arx II project. Load this prompt to understand proper command usage, migration handling, and model patterns.",
      },
    ],
  };
});

// Get prompt content
server.setRequestHandler(GetPromptRequestSchema, async (request) => {
  const { name } = request.params;

  if (name === "evennia_rules") {
    return {
      messages: [
        {
          role: "user",
          content: {
            type: "text",
            text: EVENNIA_RULES,
          },
        },
      ],
    };
  }

  throw new Error(`Unknown prompt: ${name}`);
});

// Start the server
async function main() {
  const transport = new StdioServerTransport();
  await server.connect(transport);
  console.error("arxdev-evennia MCP server running on stdio");
}

main().catch((error) => {
  console.error("Fatal error:", error);
  process.exit(1);
});
