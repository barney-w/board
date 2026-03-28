"use strict";
// Minimal VS Code API mock for unit tests.
// Only stub what the tested modules actually import.
Object.defineProperty(exports, "__esModule", { value: true });
exports.ConfigurationTarget = exports.commands = exports.window = exports.workspace = void 0;
exports.workspace = {
    getConfiguration: () => ({
        get: () => undefined,
        update: async () => { },
    }),
};
exports.window = {
    showErrorMessage: async () => undefined,
    showInformationMessage: async () => undefined,
    showInputBox: async () => undefined,
    showOpenDialog: async () => undefined,
};
exports.commands = {
    executeCommand: async () => { },
};
exports.ConfigurationTarget = {
    Global: 1,
    Workspace: 2,
    WorkspaceFolder: 3,
};
//# sourceMappingURL=vscode.js.map