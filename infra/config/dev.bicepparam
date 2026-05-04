// dev.bicepparam -- production-ready preset for the team dev resource group.
//
// Usage:
//     board up --preset infra/config/dev.bicepparam
//
// The preset only carries defaults that the wizard pre-fills. Each developer
// still gets prompted for their own developerName, and the resource group
// they're targeting must already exist with Contributor granted to them.

using '../main.bicep'

// ── Defaults the wizard pre-fills (board reads these via load_preset) ──
// resourceGroup is read by the wizard, not by Bicep itself.
// (Bicep deploys are scoped to whatever RG the CLI passes.)
//
// param resourceGroup = 'rg-dev-aue-devvm'   // wizard-only; ignored by Bicep
// param location = 'australiaeast'           // ignored -- derived from RG

// ── VM ──

param developerName = ''  // filled in by the wizard
param vmSku = 'Standard_D2s_v6'
param osDiskSizeGb = 128
param osDiskSku = 'StandardSSD_LRS'

// ── Network ──

param allowedSshSourceIP = '*'  // override per dev; CIDR strongly preferred
param enablePublicIp = true

// ── Schedules ──

param autoShutdownTime = '1900'
param backstopShutdownTime = '2200'
param autoShutdownTimezone = 'AUS Eastern Standard Time'
param enableAutoShutdownNotification = false
param autoShutdownNotificationEmail = ''
param enableAutoStart = true
param autoStartTime = '0800'
param autoStartTimezone = 'AUS Eastern Standard Time'

// ── Auth ──

param adminUsername = 'devuser'
param useEntraIdLogin = true
param entraLoginTenantId = ''
param entraLoginPrincipalId = ''
param adminSshPublicKey = ''
