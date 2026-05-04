// Assigns Virtual Machine Administrator Login role at resource group scope.
// Anyone with this role on the RG can SSH (with sudo) into every VM in the
// group — current and future. New boards inherit the assignment automatically.

@description('Entra ID object ID of the principal (user or group) to grant VM Administrator Login')
param principalId string

@description('Type of the principal: User or Group')
@allowed(['User', 'Group'])
param principalType string = 'User'

// Virtual Machine Administrator Login role definition ID
var roleDefinitionId = '1c0163c0-47e6-4577-8991-ea5c82e286e4'

resource roleAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(resourceGroup().id, principalId, roleDefinitionId)
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roleDefinitionId)
    principalId: principalId
    principalType: principalType
  }
}
