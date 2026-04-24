using '../main.bicep'

param location = 'australiaeast'
param environment = 'sandbox'
param regionShort = 'aue'
param developerName = 'jbloggs'
param vmSku = 'Standard_D2s_v6'
param osDiskSizeGb = 128
param osDiskSku = 'StandardSSD_LRS'
param adminSshPublicKey = ''                    // Not used with Entra ID
param allowedSshSourceIP = '203.0.113.0/24'       // Required -- no default (e.g. office IP range)
param enablePublicIp = true                      // Or false if using Bastion/VPN
param autoShutdownTime = '1900'
param autoShutdownTimezone = 'AUS Eastern Standard Time'
param enableAutoShutdownNotification = true
param autoShutdownNotificationEmail = 'you@example.com'
param enableAutoStart = true                     // Start VMs on weekday mornings
param autoStartTime = '0800'
param autoStartTimezone = 'AUS Eastern Standard Time'
param adminUsername = 'devuser'
param useEntraIdLogin = true
param entraLoginTenantId = ''                    // Your Entra ID tenant ID (az account show --query tenantId)
param entraLoginPrincipalId = ''                 // Developer's Entra object ID (az ad signed-in-user show --query id)
param vnetAddressPrefix = '10.1.0.0/16'         // Non-overlapping with existing VNets
param subnetAddressPrefix = '10.1.1.0/24'
