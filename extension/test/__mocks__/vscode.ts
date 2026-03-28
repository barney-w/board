// Minimal VS Code API mock for unit tests.
// Only stub what the tested modules actually import.

export const workspace = {
  getConfiguration: () => ({
    get: () => undefined,
    update: async () => {},
  }),
};

export const window = {
  showErrorMessage: async () => undefined,
  showInformationMessage: async () => undefined,
  showInputBox: async () => undefined,
  showOpenDialog: async () => undefined,
};

export const commands = {
  executeCommand: async () => {},
};

export const ConfigurationTarget = {
  Global: 1,
  Workspace: 2,
  WorkspaceFolder: 3,
};
