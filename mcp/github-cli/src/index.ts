#!/usr/bin/env node

import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import {
  CallToolRequestSchema,
  ListToolsRequestSchema,
} from "@modelcontextprotocol/sdk/types.js";
import { spawn } from "child_process";

/**
 * Execute a command and return the output
 */
async function executeCommand(
  command: string,
  args: string[],
  options?: { stdin?: string }
): Promise<{ stdout: string; stderr: string; exitCode: number }> {
  return new Promise((resolve) => {
    const proc = spawn(command, args, {
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

    if (options?.stdin) {
      proc.stdin.write(options.stdin);
      proc.stdin.end();
    }

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

/**
 * Check if gh CLI is available
 */
async function checkGhInstalled(): Promise<boolean> {
  const result = await executeCommand("gh", ["--version"]);
  return result.exitCode === 0;
}

/**
 * Check if gh is authenticated
 */
async function checkGhAuth(): Promise<boolean> {
  const result = await executeCommand("gh", ["auth", "status"]);
  return result.exitCode === 0;
}

const server = new Server(
  {
    name: "github-cli",
    version: "1.0.0",
  },
  {
    capabilities: {
      tools: {},
    },
  }
);

// List available tools
server.setRequestHandler(ListToolsRequestSchema, async () => {
  return {
    tools: [
      {
        name: "create_pr",
        description:
          "Create a pull request from the current branch. Returns the PR URL and number.",
        inputSchema: {
          type: "object",
          properties: {
            title: {
              type: "string",
              description: "The title of the pull request",
            },
            body: {
              type: "string",
              description: "The body/description of the pull request (markdown supported)",
            },
            base: {
              type: "string",
              description: "The base branch to merge into (defaults to repo default branch)",
            },
            draft: {
              type: "boolean",
              description: "Create as a draft pull request",
              default: false,
            },
          },
          required: ["title", "body"],
        },
      },
      {
        name: "get_pr",
        description:
          "Get details of a specific pull request by number. Returns full PR information.",
        inputSchema: {
          type: "object",
          properties: {
            pr_number: {
              type: "number",
              description: "The pull request number",
            },
          },
          required: ["pr_number"],
        },
      },
      {
        name: "list_prs",
        description:
          "List pull requests in the repository. Returns array of PR summaries.",
        inputSchema: {
          type: "object",
          properties: {
            state: {
              type: "string",
              enum: ["open", "closed", "merged", "all"],
              description: "Filter by PR state (default: open)",
              default: "open",
            },
            limit: {
              type: "number",
              description: "Maximum number of PRs to return (1-100, default: 10)",
              default: 10,
            },
          },
        },
      },
      {
        name: "pr_checks",
        description:
          "View CI/check status for a pull request. Returns array of check runs with status.",
        inputSchema: {
          type: "object",
          properties: {
            pr_number: {
              type: "number",
              description: "The pull request number",
            },
          },
          required: ["pr_number"],
        },
      },
    ],
  };
});

// Handle tool calls
server.setRequestHandler(CallToolRequestSchema, async (request) => {
  const { name, arguments: args } = request.params;

  // Check if gh is installed
  if (!(await checkGhInstalled())) {
    return {
      content: [
        {
          type: "text",
          text: `Error: GitHub CLI (gh) is not installed.

To install:
- Windows: winget install GitHub.cli
- macOS: brew install gh
- Linux: See https://github.com/cli/cli#installation

After installing, run: gh auth login`,
        },
      ],
      isError: true,
    };
  }

  // Check if gh is authenticated
  if (!(await checkGhAuth())) {
    return {
      content: [
        {
          type: "text",
          text: `Error: GitHub CLI is not authenticated.

Run: gh auth login

Then follow the prompts to authenticate with your GitHub account.`,
        },
      ],
      isError: true,
    };
  }

  switch (name) {
    case "create_pr": {
      const { title, body, base, draft } = args as {
        title: string;
        body: string;
        base?: string;
        draft?: boolean;
      };

      const cmdArgs = ["pr", "create", "--title", title, "--body", body];
      if (base) {
        cmdArgs.push("--base", base);
      }
      if (draft) {
        cmdArgs.push("--draft");
      }

      const result = await executeCommand("gh", cmdArgs);

      if (result.exitCode !== 0) {
        return {
          content: [
            {
              type: "text",
              text: `Error creating PR:\n${result.stderr}\n${result.stdout}`,
            },
          ],
          isError: true,
        };
      }

      // The output contains the PR URL
      return {
        content: [
          {
            type: "text",
            text: `Pull request created successfully!\n\n${result.stdout.trim()}`,
          },
        ],
      };
    }

    case "get_pr": {
      const { pr_number } = args as { pr_number: number };

      const jsonFields = [
        "number",
        "title",
        "state",
        "body",
        "author",
        "url",
        "headRefName",
        "baseRefName",
        "mergeable",
        "additions",
        "deletions",
        "changedFiles",
        "createdAt",
        "updatedAt",
      ].join(",");

      const result = await executeCommand("gh", [
        "pr",
        "view",
        pr_number.toString(),
        "--json",
        jsonFields,
      ]);

      if (result.exitCode !== 0) {
        return {
          content: [
            {
              type: "text",
              text: `Error getting PR #${pr_number}:\n${result.stderr}\n${result.stdout}`,
            },
          ],
          isError: true,
        };
      }

      return {
        content: [
          {
            type: "text",
            text: result.stdout,
          },
        ],
      };
    }

    case "list_prs": {
      const { state = "open", limit = 10 } = args as {
        state?: string;
        limit?: number;
      };

      const clampedLimit = Math.max(1, Math.min(100, limit));

      const jsonFields = [
        "number",
        "title",
        "state",
        "author",
        "url",
        "headRefName",
        "updatedAt",
      ].join(",");

      const result = await executeCommand("gh", [
        "pr",
        "list",
        "--state",
        state,
        "--limit",
        clampedLimit.toString(),
        "--json",
        jsonFields,
      ]);

      if (result.exitCode !== 0) {
        return {
          content: [
            {
              type: "text",
              text: `Error listing PRs:\n${result.stderr}\n${result.stdout}`,
            },
          ],
          isError: true,
        };
      }

      return {
        content: [
          {
            type: "text",
            text: result.stdout,
          },
        ],
      };
    }

    case "pr_checks": {
      const { pr_number } = args as { pr_number: number };

      const result = await executeCommand("gh", [
        "pr",
        "checks",
        pr_number.toString(),
        "--json",
        "name,state,conclusion,url",
      ]);

      if (result.exitCode !== 0) {
        return {
          content: [
            {
              type: "text",
              text: `Error getting checks for PR #${pr_number}:\n${result.stderr}\n${result.stdout}`,
            },
          ],
          isError: true,
        };
      }

      return {
        content: [
          {
            type: "text",
            text: result.stdout || "No checks found for this PR.",
          },
        ],
      };
    }

    default:
      throw new Error(`Unknown tool: ${name}`);
  }
});

// Start the server
async function main() {
  const transport = new StdioServerTransport();
  await server.connect(transport);
  console.error("github-cli MCP server running on stdio");
}

main().catch((error) => {
  console.error("Fatal error:", error);
  process.exit(1);
});
