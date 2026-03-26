@description('Name of the VM (used to construct the schedule resource name)')
param vmName string

@description('Resource ID of the VM')
param vmResourceId string

@description('Azure region')
param location string

@description('Shutdown time in HHmm format')
param shutdownTime string

@description('Timezone for the shutdown schedule')
param timezone string

@description('Whether to send email notification before shutdown')
param enableNotification bool

@description('Email address for shutdown notification')
param notificationEmail string

@description('Resource tags')
param tags object

resource schedule 'Microsoft.DevTestLab/schedules@2018-09-15' = {
  // Azure requires this exact naming pattern
  name: 'shutdown-computevm-${vmName}'
  location: location
  tags: tags
  properties: {
    status: 'Enabled'
    taskType: 'ComputeVmShutdownTask'
    dailyRecurrence: {
      time: shutdownTime
    }
    timeZoneId: timezone
    targetResourceId: vmResourceId
    notificationSettings: enableNotification ? {
      status: 'Enabled'
      timeInMinutes: 30
      emailRecipient: notificationEmail
      notificationLocale: 'en'
    } : {
      status: 'Disabled'
    }
  }
}
