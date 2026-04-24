// Auto-start schedule for standalone VMs using a Logic App.
// Unlike auto-shutdown (Microsoft.DevTestLab/schedules), auto-start
// is only available inside DevTest Labs. For standalone VMs we use a
// Logic App with a recurrence trigger that calls the VM start API.

@description('Name of the VM (used for resource naming)')
param vmName string

@description('Resource ID of the VM to start')
param vmResourceId string

@description('Azure region')
param location string

@description('Start time in HHmm format (e.g. 0800)')
param startTime string

@description('Timezone for the start schedule')
param timezone string

@description('Days of the week to start the VM')
param startDays array = [
  'Monday'
  'Tuesday'
  'Wednesday'
  'Thursday'
  'Friday'
]

@description('Resource tags')
param tags object

var startHour = int(substring(startTime, 0, 2))
var startMinute = int(substring(startTime, 2, 2))

// Virtual Machine Contributor — required to start a VM
var vmContributorRoleId = '9980e02c-c2be-4d73-94e8-173b1dc7cf3c'

resource vm 'Microsoft.Compute/virtualMachines@2024-07-01' existing = {
  name: vmName
}

resource logicApp 'Microsoft.Logic/workflows@2019-05-01' = {
  name: 'logic-autostart-${vmName}'
  location: location
  tags: union(tags, { purpose: 'auto-start' })
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    state: 'Enabled'
    definition: {
      '$schema': 'https://schema.management.azure.com/providers/Microsoft.Logic/schemas/2016-06-01/workflowdefinition.json#'
      contentVersion: '1.0.0.0'
      triggers: {
        Recurrence: {
          type: 'Recurrence'
          recurrence: {
            frequency: 'Week'
            interval: 1
            schedule: {
              weekDays: startDays
              hours: [startHour]
              minutes: [startMinute]
            }
            timeZone: timezone
          }
        }
      }
      actions: {
        Start_VM: {
          type: 'Http'
          inputs: {
            method: 'POST'
            uri: '${environment().resourceManager}${vmResourceId}/start?api-version=2024-07-01'
            authentication: {
              type: 'ManagedServiceIdentity'
            }
          }
        }
      }
    }
  }
}

// Grant the Logic App permission to start the VM
resource roleAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(vm.id, logicApp.id, vmContributorRoleId)
  scope: vm
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', vmContributorRoleId)
    principalId: logicApp.identity.principalId
    principalType: 'ServicePrincipal'
  }
}
