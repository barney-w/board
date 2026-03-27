import * as vscode from 'vscode';
import { VmPowerState } from './azure';
import { getConfig } from './config';

export type StatusBarState = VmPowerState | 'not-configured';

export class StatusBar implements vscode.Disposable {
  private item: vscode.StatusBarItem;
  private healthLines: string[] = [];

  constructor() {
    this.item = vscode.window.createStatusBarItem(
      vscode.StatusBarAlignment.Left,
      100,
    );
    this.item.show();
  }

  /** Update display based on current state, optionally with health data */
  update(state: StatusBarState, healthLines?: string[]): void {
    if (healthLines !== undefined) {
      this.healthLines = healthLines;
    }

    // Reset background colour — only set for specific states
    this.item.backgroundColor = undefined;

    switch (state) {
      case 'not-configured':
        this.item.text = '$(remote) Board \u2014 Import Pass';
        this.item.command = 'board.importPass';
        this.item.tooltip = 'Import a board pass to get started';
        break;
      case 'running': {
        const issues = this.healthLines.filter(l => l.includes('\u2717')).length;
        if (issues > 0) {
          this.item.text = `$(remote) Board \u26A0 ${issues} issue(s)`;
        } else {
          this.item.text = '$(remote) Board \u2713';
        }
        this.item.command = 'board.connect';
        this.item.tooltip = this.buildRunningTooltip();
        break;
      }
      case 'starting':
        this.item.text = '$(remote) Board \u2191 starting...';
        this.item.command = undefined;
        this.item.tooltip = 'Board is starting up';
        this.item.backgroundColor = new vscode.ThemeColor(
          'statusBarItem.warningBackground',
        );
        break;
      case 'stopped':
      case 'deallocated':
        this.item.text = '$(remote) Board \u2193';
        this.item.command = 'board.start';
        this.item.tooltip = 'Click to start board';
        this.healthLines = [];
        break;
      case 'deallocating':
        this.item.text = '$(remote) Board \u2193 stopping...';
        this.item.command = undefined;
        this.item.tooltip = 'Board is stopping';
        this.item.backgroundColor = new vscode.ThemeColor(
          'statusBarItem.warningBackground',
        );
        this.healthLines = [];
        break;
      case 'unknown':
        this.item.text = '$(remote) Board ?';
        this.item.command = 'board.connect';
        this.item.tooltip = 'Cannot determine board status';
        this.item.backgroundColor = new vscode.ThemeColor(
          'statusBarItem.errorBackground',
        );
        this.healthLines = [];
        break;
    }
  }

  /** Update only the health portion of the tooltip */
  updateHealth(healthLines: string[]): void {
    this.healthLines = healthLines;
    // Re-render tooltip if the VM is currently showing as running
    if (this.item.text.includes('\u2713') || this.item.text.includes('\u26A0')) {
      this.item.tooltip = this.buildRunningTooltip();
    }
  }

  dispose(): void {
    this.item.dispose();
  }

  /* ------------------------------------------------------------------ */
  /*  Internals                                                          */
  /* ------------------------------------------------------------------ */

  private buildRunningTooltip(): string {
    const config = getConfig();
    let tooltip = `board-${config.developerName} \u00B7 ${config.region}\nRunning`;
    if (this.healthLines.length > 0) {
      tooltip += '\n\nServices:\n' + this.healthLines.map(l => `  ${l}`).join('\n');
    }
    tooltip += '\n\nClick to connect';
    return tooltip;
  }
}
