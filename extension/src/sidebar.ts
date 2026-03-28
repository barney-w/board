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
