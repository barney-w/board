// ── Dev VM Infrastructure ──
// Composes AVM modules + custom auto-shutdown module

// ── Parameters ──

@description('Azure region for all resources')
param location string = 'australiaeast'

@description('Environment identifier for naming and tagging')
param environment string = 'personal'

@description('Short region code for naming convention')
param regionShort string = 'aue'

@maxLength(12)
@description('Developer username (lowercase, alphanumeric)')
param developerName string

@description('VM size SKU')
param vmSku string = 'Standard_D2s_v6'

@description('OS disk size in GB')
param osDiskSizeGb int = 128

@description('OS disk storage tier')
param osDiskSku string = 'StandardSSD_LRS'

@secure()
@description('SSH public key for the admin user')
param adminSshPublicKey string

@description('Source IP address or CIDR allowed to SSH. Must be specified explicitly.')
param allowedSshSourceIP string

@description('Whether to attach a public IP to the VM')
param enablePublicIp bool = true

@description('Whether to allow direct HTTPS access (port 443) for browser IDE reverse proxy')
param enableDirectHttps bool = false

@description('Idle-aware shutdown start time in HHmm format (VM powers off when idle after this)')
param autoShutdownTime string = '1900'

@description('Hard backstop shutdown time in HHmm format (VM is force-deallocated regardless of activity)')
param backstopShutdownTime string = '2200'

@description('Timezone for auto-shutdown')
param autoShutdownTimezone string = 'AUS Eastern Standard Time'

@description('Whether to send email notification before shutdown')
param enableAutoShutdownNotification bool = false

@description('Email address for shutdown notification')
param autoShutdownNotificationEmail string = ''

@description('Whether to enable auto-start schedule (weekdays only)')
param enableAutoStart bool = false

@description('Auto-start time in HHmm format (local timezone)')
param autoStartTime string = '0800'

@description('Timezone for auto-start schedule')
param autoStartTimezone string = 'AUS Eastern Standard Time'

@description('Days of the week to auto-start the VM')
param autoStartDays array = [
  'Monday'
  'Tuesday'
  'Wednesday'
  'Thursday'
  'Friday'
]

@description('Linux admin username on the VM')
param adminUsername string = 'devuser'

@description('Whether to install Entra ID SSH login extension')
param useEntraIdLogin bool = true

@description('Tenant ID to lock AADSSHLogin extension to. Required when useEntraIdLogin is true.')
param entraLoginTenantId string = ''

@description('Entra ID object ID of the developer. Gets VM Administrator Login role. Required when useEntraIdLogin is true.')
param entraLoginPrincipalId string = ''

@description('Resource ID of Key Vault for project secrets (empty = skip)')
param keyVaultResourceId string = ''

@description('Subnet CIDR range')
param subnetAddressPrefix string = '10.0.1.0/24'

@description('VNet CIDR range')
param vnetAddressPrefix string = '10.0.0.0/16'

@description('Deployment timestamp (auto-generated, do not set manually)')
param deploymentTimestamp string = utcNow('yyyy-MM-dd')

// ── Variables ──

var prefix = '${environment}-${regionShort}-devvm'
var vmName = 'vm-${prefix}-${developerName}'
var cloudInitRaw = loadTextContent('cloud-init/cloud-init.yaml')
var cloudInit1 = replace(cloudInitRaw, '__BOARD_HOSTNAME__', 'devvm-${developerName}')
var cloudInit2 = replace(cloudInit1, '__SHUTDOWN_START_HOUR__', substring(autoShutdownTime, 0, 2))
var cloudInitContent = replace(cloudInit2, '__SHUTDOWN_BACKSTOP_HOUR__', substring(backstopShutdownTime, 0, 2))
var commonTags = {
  project: 'devvm'
  environment: environment
  owner: developerName
  'managed-by': 'bicep'
  'auth-method': useEntraIdLogin ? 'entra-id' : 'ssh-key'
  created: deploymentTimestamp
}

// ── NSG Rules ──

var baseSecurityRules = [
  {
    name: 'AllowSSHInbound'
    properties: {
      priority: 100
      direction: 'Inbound'
      access: 'Allow'
      protocol: 'Tcp'
      sourceAddressPrefix: allowedSshSourceIP
      sourcePortRange: '*'
      destinationAddressPrefix: '*'
      destinationPortRange: '22'
    }
  }
  {
    name: 'DenyAllInbound'
    properties: {
      priority: 4096
      direction: 'Inbound'
      access: 'Deny'
      protocol: '*'
      sourceAddressPrefix: '*'
      sourcePortRange: '*'
      destinationAddressPrefix: '*'
      destinationPortRange: '*'
    }
  }
]

var httpsRule = enableDirectHttps ? [
  {
    name: 'AllowHTTPSInbound'
    properties: {
      priority: 200
      direction: 'Inbound'
      access: 'Allow'
      protocol: 'Tcp'
      sourceAddressPrefix: allowedSshSourceIP
      sourcePortRange: '*'
      destinationAddressPrefix: '*'
      destinationPortRange: '443'
    }
  }
] : []

// ── Module 1: NSG ──

module nsg 'br/public:avm/res/network/network-security-group:0.5.3' = {
  name: 'nsg-deployment'
  params: {
    name: 'nsg-${prefix}'
    location: location
    tags: commonTags
    securityRules: concat(baseSecurityRules, httpsRule)
  }
}

// ── Module 2: VNet + Subnet ──

module vnet 'br/public:avm/res/network/virtual-network:0.7.2' = {
  name: 'vnet-deployment'
  params: {
    name: 'vnet-${prefix}'
    location: location
    tags: commonTags
    addressPrefixes: [
      vnetAddressPrefix
    ]
    subnets: [
      {
        name: 'snet-${prefix}'
        addressPrefix: subnetAddressPrefix
        networkSecurityGroupResourceId: nsg.outputs.resourceId
      }
    ]
  }
}

// ── Module 3: Public IP (conditional) ──

module publicIp 'br/public:avm/res/network/public-ip-address:0.12.0' = if (enablePublicIp) {
  name: 'pip-deployment'
  params: {
    name: 'pip-${prefix}-${developerName}'
    location: location
    tags: commonTags
    skuName: 'Standard'
    publicIPAllocationMethod: 'Static'
    ddosSettings: null
    dnsSettings: {
      domainNameLabel: 'devvm-${developerName}'
    }
  }
}

// ── Module 4: VM ──

module vm 'br/public:avm/res/compute/virtual-machine:0.22.0' = {
  name: 'vm-deployment'
  params: {
    name: vmName
    location: location
    tags: commonTags

    // Compute
    vmSize: vmSku
    availabilityZone: -1
    osType: 'Linux'
    imageReference: {
      publisher: 'Canonical'
      offer: 'ubuntu-24_04-lts'
      sku: 'server'
      version: 'latest'
    }

    // OS Disk
    osDisk: {
      caching: 'ReadWrite'
      diskSizeGB: osDiskSizeGb
      managedDisk: {
        storageAccountType: osDiskSku
      }
      deleteOption: 'Delete'
    }

    // Admin & Auth
    adminUsername: adminUsername
    disablePasswordAuthentication: true
    publicKeys: [
      {
        keyData: adminSshPublicKey
        path: '/home/${adminUsername}/.ssh/authorized_keys'
      }
    ]

    // Networking (NIC created by AVM module)
    nicConfigurations: [
      {
        name: 'nic-${prefix}-${developerName}'
        tags: commonTags
        ipConfigurations: [
          {
            name: 'ipconfig01'
            subnetResourceId: vnet.outputs.subnetResourceIds[0]
            pipConfiguration: enablePublicIp ? {
              publicIPAddressResourceId: publicIp!.outputs.resourceId
            } : null
          }
        ]
        nicSuffix: '-nic-01'
        deleteOption: 'Delete'
      }
    ]

    // Identity
    managedIdentities: {
      systemAssigned: true
    }

    // Security
    securityType: 'TrustedLaunch'
    secureBootEnabled: true
    vTpmEnabled: true

    // Boot Diagnostics
    bootDiagnostics: true

    // Cloud-init
    customData: cloudInitContent

    // Patching
    patchMode: 'AutomaticByPlatform'
    bypassPlatformSafetyChecksOnUserSchedule: true

    // Entra ID SSH Extension (work tenant only)
    extensionAadJoinConfig: {
      enabled: useEntraIdLogin
      settings: useEntraIdLogin && !empty(entraLoginTenantId) ? {
        tenant_id: entraLoginTenantId
      } : {}
    }
  }
}

// ── Module 5: Auto-Shutdown ──

module autoShutdown './modules/auto-shutdown.bicep' = {
  name: 'auto-shutdown-deployment'
  params: {
    vmName: vm.outputs.name
    vmResourceId: vm.outputs.resourceId
    location: location
    shutdownTime: backstopShutdownTime
    timezone: autoShutdownTimezone
    enableNotification: enableAutoShutdownNotification
    notificationEmail: autoShutdownNotificationEmail
    tags: commonTags
  }
}

// ── Module 6: Auto-Start (conditional, uses Logic App) ──

module autoStart './modules/auto-start.bicep' = if (enableAutoStart) {
  name: 'auto-start-deployment'
  params: {
    vmName: vm.outputs.name
    vmResourceId: vm.outputs.resourceId
    location: location
    startTime: autoStartTime
    timezone: autoStartTimezone
    startDays: autoStartDays
    tags: commonTags
  }
}

// ── Module 7: Key Vault Secrets User role (conditional) ──

module kvRole './modules/keyvault-role.bicep' = if (keyVaultResourceId != '') {
  name: 'kv-role-assignment'
  scope: resourceGroup(split(keyVaultResourceId, '/')[2], split(keyVaultResourceId, '/')[4])
  params: {
    keyVaultName: last(split(keyVaultResourceId, '/'))
    principalId: vm.outputs.?systemAssignedMIPrincipalId ?? ''
  }
}

// ── Module 8: Entra ID RBAC – VM Administrator Login ──

module vmLoginRoles './modules/vm-login-roles.bicep' = if (useEntraIdLogin && !empty(entraLoginPrincipalId)) {
  name: 'vm-login-roles'
  params: {
    vmName: vm.outputs.name
    principalId: entraLoginPrincipalId
  }
}

// ── Outputs ──

output vmName string = vm.outputs.name
output vmResourceId string = vm.outputs.resourceId
output publicIpAddress string = enablePublicIp ? publicIp!.outputs.ipAddress : 'N/A'
output fqdn string = enablePublicIp ? 'devvm-${developerName}.${location}.cloudapp.azure.com' : 'N/A'
output sshCommand string = enablePublicIp ? 'ssh ${adminUsername}@devvm-${developerName}.${location}.cloudapp.azure.com' : 'Use az ssh vm or Bastion'
output principalId string = vm.outputs.?systemAssignedMIPrincipalId ?? ''
