import * as vscode from 'vscode';
import { VmStatus, VmPowerState } from './azure';
import { getConfig, isConfigured, getHostname } from './config';

/* ------------------------------------------------------------------ */
/*  Tree item helpers                                                   */
/* ------------------------------------------------------------------ */

class StatusItem extends vscode.TreeItem {
  constructor(label: string, description: string, icon: string, command?: vscode.Command) {
    super(label, vscode.TreeItemCollapsibleState.None);
    this.description = description;
    this.iconPath = new vscode.ThemeIcon(icon);
    if (command) {
      this.command = command;
    }
  }
}

class ActionItem extends vscode.TreeItem {
  constructor(label: string, icon: string, command: string) {
    super(label, vscode.TreeItemCollapsibleState.None);
    this.iconPath = new vscode.ThemeIcon(icon);
    this.command = { command, title: label };
  }
}

/* ------------------------------------------------------------------ */
/*  VM Status tree provider                                             */
/* ------------------------------------------------------------------ */

export class VmStatusProvider implements vscode.TreeDataProvider<StatusItem> {
  private readonly onDidChange = new vscode.EventEmitter<StatusItem | undefined>();
  readonly onDidChangeTreeData: vscode.Event<StatusItem | undefined> = this.onDidChange.event;
  private status: VmStatus | undefined;

  constructor() {
    // Start with no status — tree will show appropriate placeholder
  }

  /** Call to refresh the tree with new status data */
  refresh(status: VmStatus | undefined): void {
    this.status = status;
    this.onDidChange.fire(undefined);
  }

  getTreeItem(element: StatusItem): vscode.TreeItem {
    return element;
  }

  getChildren(_element?: StatusItem): StatusItem[] {
    // If not configured, prompt to set up
    if (!isConfigured()) {
      return [
        new StatusItem(
          'Not configured',
          'click to set up',
          'question',
          { command: 'board.configure', title: 'Configure Board' },
        ),
      ];
    }

    const config = getConfig();

    // If we have live status data from polling
    if (this.status) {
      const items: StatusItem[] = [];

      // Power state — always shown
      const stateLabel = formatPowerState(this.status.powerState);
      items.push(new StatusItem('Status', stateLabel, powerStateIcon(this.status.powerState)));

      // IP address — only when available
      if (this.status.ipAddress) {
        items.push(new StatusItem('IP', this.status.ipAddress, 'globe'));
      }

      // FQDN — derive from config (always available when configured)
      items.push(new StatusItem('FQDN', getHostname(config), 'link'));

      // VM size — only when available
      if (this.status.vmSize) {
        items.push(new StatusItem('Size', this.status.vmSize, 'server'));
      }

      return items;
    }

    // Configured but no live status yet (az CLI unavailable or hasn't polled)
    const items: StatusItem[] = [];
    items.push(new StatusItem('FQDN', getHostname(config), 'link'));
    items.push(new StatusItem('Status', 'Azure CLI required for live status', 'info'));
    return items;
  }
}

/* ------------------------------------------------------------------ */
/*  Quick Actions tree provider                                         */
/* ------------------------------------------------------------------ */

export class QuickActionsProvider implements vscode.TreeDataProvider<ActionItem> {
  private readonly onDidChange = new vscode.EventEmitter<ActionItem | undefined>();
  readonly onDidChangeTreeData: vscode.Event<ActionItem | undefined> = this.onDidChange.event;
  private status: VmStatus | undefined;

  constructor() {
    // Start with no status
  }

  /** Call to refresh (e.g., when VM state changes to show Start vs Stop) */
  refresh(status: VmStatus | undefined): void {
    this.status = status;
    this.onDidChange.fire(undefined);
  }

  getTreeItem(element: ActionItem): vscode.TreeItem {
    return element;
  }

  getChildren(_element?: ActionItem): ActionItem[] {
    const items: ActionItem[] = [];

    items.push(new ActionItem('Connect', 'remote', 'board.connect'));
    items.push(new ActionItem('Open Workspace', 'layout', 'board.openWorkspace'));
    items.push(new ActionItem('Open Terminal', 'terminal', 'board.openTerminal'));

    // Contextual Start / Stop
    if (this.status) {
      const state = this.status.powerState;
      if (state === 'running') {
        items.push(new ActionItem('Stop VM', 'debug-stop', 'board.stop'));
      } else if (state === 'stopped' || state === 'deallocated') {
        items.push(new ActionItem('Start VM', 'play', 'board.start'));
      }
      // For starting, deallocating, unknown — omit the start/stop item
    }

    items.push(new ActionItem('Run First-Time Setup', 'gear', 'board.runSetup'));

    if (isConfigured()) {
      const browserItem = new ActionItem('Open in Browser', 'globe', 'board.openInBrowser');
      browserItem.tooltip = 'Open your board in a browser-based IDE';
      items.push(browserItem);
    }

    items.push(new ActionItem('Open in Azure Portal', 'link-external', 'board.openPortal'));

    return items;
  }
}

/* ------------------------------------------------------------------ */
/*  Cheatsheet tree provider                                            */
/* ------------------------------------------------------------------ */

class CheatsheetItem extends vscode.TreeItem {
  constructor(
    label: string,
    collapsible: vscode.TreeItemCollapsibleState,
    options?: { description?: string; icon?: string; command?: string },
  ) {
    super(label, collapsible);
    if (options?.description) {
      this.description = options.description;
    }
    if (options?.icon) {
      this.iconPath = new vscode.ThemeIcon(options.icon);
    }
    if (options?.command) {
      this.command = { command: options.command, title: label };
    }
  }

  children?: CheatsheetItem[];
}

export class CheatsheetProvider implements vscode.TreeDataProvider<CheatsheetItem> {
  private readonly items: CheatsheetItem[];

  constructor() {
    const vsCodeCmds = new CheatsheetItem('VS Code Commands', vscode.TreeItemCollapsibleState.Expanded, { icon: 'symbol-event' });
    vsCodeCmds.children = [
      new CheatsheetItem('Import Pass', vscode.TreeItemCollapsibleState.None, { description: 'decrypt .board-pass', icon: 'key', command: 'board.importPass' }),
      new CheatsheetItem('Connect', vscode.TreeItemCollapsibleState.None, { description: 'open remote window', icon: 'remote', command: 'board.connect' }),
      new CheatsheetItem('Start / Stop', vscode.TreeItemCollapsibleState.None, { description: 'power-manage VM', icon: 'play', command: 'board.start' }),
      new CheatsheetItem('First-Time Setup', vscode.TreeItemCollapsibleState.None, { description: 'Git + SSH keys', icon: 'gear', command: 'board.runSetup' }),
      new CheatsheetItem('Open in Browser', vscode.TreeItemCollapsibleState.None, { description: 'Tunnel or code-server', icon: 'globe', command: 'board.openInBrowser' }),
    ];

    const termCmds = new CheatsheetItem('Terminal Commands', vscode.TreeItemCollapsibleState.Expanded, { icon: 'terminal' });
    termCmds.children = [
      new CheatsheetItem('check', vscode.TreeItemCollapsibleState.None, { description: 'run health checks', icon: 'heart' }),
      new CheatsheetItem('board-help', vscode.TreeItemCollapsibleState.None, { description: 'on-VM quick reference', icon: 'question' }),
      new CheatsheetItem('gs / gd / gl', vscode.TreeItemCollapsibleState.None, { description: 'git status / diff / log', icon: 'git-commit' }),
      new CheatsheetItem('dc up / down / ps', vscode.TreeItemCollapsibleState.None, { description: 'docker compose shortcuts', icon: 'package' }),
    ];

    const paths = new CheatsheetItem('Key Paths', vscode.TreeItemCollapsibleState.Collapsed, { icon: 'folder' });
    paths.children = [
      new CheatsheetItem('~/projects/', vscode.TreeItemCollapsibleState.None, { description: 'your workspace', icon: 'folder-opened' }),
      new CheatsheetItem('~/.board/', vscode.TreeItemCollapsibleState.None, { description: 'board config', icon: 'settings-gear' }),
    ];

    const tips = new CheatsheetItem('Tips', vscode.TreeItemCollapsibleState.Collapsed, { icon: 'lightbulb' });
    tips.children = [
      new CheatsheetItem('Auto-shutdown at 7 PM', vscode.TreeItemCollapsibleState.None, { description: 'files persist', icon: 'clock' }),
      new CheatsheetItem('Ctrl+Shift+P > Run Task', vscode.TreeItemCollapsibleState.None, { description: 'project tasks', icon: 'play' }),
      new CheatsheetItem('systemctl --user restart <svc>', vscode.TreeItemCollapsibleState.None, { description: 'restart service', icon: 'refresh' }),
      new CheatsheetItem('journalctl --user -u <svc> -f', vscode.TreeItemCollapsibleState.None, { description: 'stream logs', icon: 'output' }),
    ];

    const fullRef = new CheatsheetItem('Open Full Cheatsheet', vscode.TreeItemCollapsibleState.None, { icon: 'book', command: 'board.cheatsheet' });

    this.items = [vsCodeCmds, termCmds, paths, tips, fullRef];
  }

  getTreeItem(element: CheatsheetItem): vscode.TreeItem {
    return element;
  }

  getChildren(element?: CheatsheetItem): CheatsheetItem[] {
    if (element) {
      return element.children ?? [];
    }
    return this.items;
  }
}

/* ------------------------------------------------------------------ */
/*  Helpers                                                             */
/* ------------------------------------------------------------------ */

function formatPowerState(state: VmPowerState): string {
  switch (state) {
    case 'running':
      return 'Running';
    case 'starting':
      return 'Starting';
    case 'stopped':
      return 'Stopped';
    case 'deallocated':
      return 'Deallocated';
    case 'deallocating':
      return 'Deallocating';
    case 'unknown':
      return 'Unknown';
  }
}

function powerStateIcon(state: VmPowerState): string {
  switch (state) {
    case 'running':
      return 'pulse';
    case 'starting':
      return 'loading~spin';
    case 'stopped':
      return 'debug-stop';
    case 'deallocated':
      return 'circle-slash';
    case 'deallocating':
      return 'loading~spin';
    case 'unknown':
      return 'question';
  }
}
