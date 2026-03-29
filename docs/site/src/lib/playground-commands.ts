// Pre-scripted command outputs for the interactive playground

export interface CommandResult {
  output: string;
  delay?: number; // ms before showing output
}

const PROMPT = 'devuser@board-alice:~/projects$ ';

const CHECK_OUTPUT = `
  \x1b[38;2;14;165;233mBoard Check\x1b[0m
  \x1b[38;2;14;165;233m═══════════\x1b[0m

  \x1b[1mSystem\x1b[0m
  ├─ Docker ............... running \x1b[32m✓\x1b[0m
  ├─ Disk ................. 34% (18 GB free) \x1b[32m✓\x1b[0m
  └─ Memory ............... 2.1 / 8.0 GB \x1b[32m✓\x1b[0m

  \x1b[1mdjango-api\x1b[0m
  ├─ Postgres ............. healthy :5432 \x1b[32m✓\x1b[0m
  ├─ Django API ........... healthy :8000 \x1b[32m✓\x1b[0m
  ├─ Migrations ........... up to date \x1b[32m✓\x1b[0m
  └─ DJANGO_SECRET_KEY .... set \x1b[32m✓\x1b[0m

  \x1b[1mnextjs-app\x1b[0m
  ├─ Dependencies ......... installed \x1b[32m✓\x1b[0m
  └─ Build ................ .next/ exists \x1b[32m✓\x1b[0m

  ─────────────────────────────────
  All checks passed (9/9) \x1b[32m✓\x1b[0m

  Welcome aboard. Happy coding

  \x1b[2mboard v1.0.0\x1b[0m
`;

const BOARD_HELP_OUTPUT = `
  Board Quick Reference
  ═════════════════════

  Health & Status
    check              run all health checks
    board-help         show this reference

  Services
    Ctrl+Shift+P in VS Code → "Run Task" for project tasks, or:
    systemctl --user restart <service>    restart a service
    journalctl --user -u <service> -f     stream service logs

  Projects
    ~/projects/        your project workspace

  Need help? Message your shaper or check the docs.
`;

const CURL_OUTPUT = `{
  "status": "healthy",
  "version": "1.4.2",
  "uptime": "3h 42m",
  "checks": {
    "database": "connected",
    "cache": "connected",
    "queue": "0 pending"
  }
}`;

const LS_OUTPUT = `django-api/  nextjs-app/`;

const commands: Record<string, CommandResult> = {
  check: { output: CHECK_OUTPUT, delay: 500 },
  'board-help': { output: BOARD_HELP_OUTPUT },
  help: { output: BOARD_HELP_OUTPUT },
  ls: { output: LS_OUTPUT },
  pwd: { output: '/home/devuser/projects' },
  whoami: { output: 'devuser' },
  'curl localhost:8000/api/health/': { output: CURL_OUTPUT, delay: 200 },
  'curl -s localhost:8000/api/health/': { output: CURL_OUTPUT, delay: 200 },
  clear: { output: '__CLEAR__' },
};

export function executeCommand(input: string): CommandResult {
  const trimmed = input.trim();
  if (trimmed === '') return { output: '' };
  if (commands[trimmed]) return commands[trimmed];
  return { output: `bash: ${trimmed.split(' ')[0]}: command not found` };
}

export { PROMPT };
