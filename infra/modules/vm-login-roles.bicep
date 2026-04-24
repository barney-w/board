// Assigns Virtual Machine Administrator Login role at VM scope.
// This grants Entra ID users SSH access with sudo privileges.

@description('Name of the virtual machine')
param vmName string

@description('Entra ID object ID of the user to grant VM Administrator Login')
param principalId string

// Virtual Machine Administrator Login role definition ID
var roleDefinitionId = '1c0163c0-47e6-4577-8991-ea5c82e286e4'

resource vm 'Microsoft.Compute/virtualMachines@2024-07-01' existing = {
  name: vmName
}

resource roleAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(vm.id, principalId, roleDefinitionId)
  scope: vm
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roleDefinitionId)
    principalId: principalId
    principalType: 'User'
  }
}
