// example.bicepparam -- copy to <name>.bicepparam and fill in your values.
//
// Bicepparam files are now optional "presets" for the wizard. Pass one with:
//
//     board up --preset infra/config/dev.bicepparam
//
// Anything you don't set falls back to wizard prompts or VM/policy defaults.
//
// Naming: VM = vm-<rg-suffix>-<developerName>, where rg-suffix is the
// resource group name with any leading 'rg-' stripped.

using '../main.bicep'

// ── Required ──

// Developer this VM is for. The wizard will still prompt; this is a default.
param developerName = 'jbloggs'

// Source IP/CIDR allowed to SSH. Use '*' for any (not recommended for prod).
param allowedSshSourceIP = '203.0.113.0/24'

// ── VM defaults ──

param vmSku = 'Standard_D2s_v6'
param osDiskSizeGb = 128
param osDiskSku = 'StandardSSD_LRS'

// ── Auto-shutdown / auto-start ──

param autoShutdownTime = '1900'
param backstopShutdownTime = '2200'
param autoShutdownTimezone = 'AUS Eastern Standard Time'
param enableAutoShutdownNotification = false
param autoShutdownNotificationEmail = ''
param enableAutoStart = false
param autoStartTime = '0800'
param autoStartTimezone = 'AUS Eastern Standard Time'

// ── Auth ──

// Entra ID login (recommended). Tenant ID and principal ID are filled in by
// the wizard from `az account show` and the developer's email.
param adminUsername = 'devuser'
param useEntraIdLogin = true
param entraLoginTenantId = ''
param entraLoginPrincipalId = ''
param adminSshPublicKey = ''  // unused with Entra ID

// ── Networking ──

param enablePublicIp = true
