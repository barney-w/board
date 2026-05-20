// Shared network + NSG for one resource group. Created once per RG by the
// CLI (board.azure.deployment.ensure_network) on first deploy; reused by every
// subsequent board into the same RG.
//
// CIDRs are intentionally hardcoded — multi-CIDR support is out of scope.
//
// The NSG lives at subnet level (not per-VM) so all boards in the RG share
// one ingress ruleset. The SSH source IP is set by the FIRST board that
// triggers ensure_network; subsequent boards reuse the existing rules unless
// the user explicitly updates them out-of-band.

@description('Naming prefix derived from the resource group name (rgName minus any leading "rg-").')
param prefix string

@description('Azure region. Defaults to the resource group location.')
param location string = resourceGroup().location

@description('Tags applied to vnet + subnet + NSG. Pre-merged by the caller (built-in + extraTags).')
param tags object = {}

@description('Source IP address or CIDR allowed to SSH into any board in this RG. Applied at subnet level.')
param allowedSshSourceIP string

@description('Whether to allow direct HTTPS access (port 443) for browser IDE reverse proxy. Applied at subnet level.')
param enableDirectHttps bool = false

var vnetAddressPrefix = '10.0.0.0/16'
var subnetAddressPrefix = '10.0.1.0/24'

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

module nsg 'br/public:avm/res/network/network-security-group:0.5.3' = {
  name: 'nsg-${prefix}-deployment'
  params: {
    name: 'nsg-${prefix}'
    location: location
    tags: tags
    securityRules: concat(baseSecurityRules, httpsRule)
  }
}

module vnet 'br/public:avm/res/network/virtual-network:0.7.2' = {
  name: 'vnet-${prefix}-deployment'
  params: {
    name: 'vnet-${prefix}'
    location: location
    tags: tags
    addressPrefixes: [vnetAddressPrefix]
    subnets: []  // intentionally empty — subnet added by the AVM child module below
  }
}

module subnet 'br/public:avm/res/network/virtual-network/subnet:0.1.3' = {
  name: 'snet-${prefix}-deployment'
  params: {
    virtualNetworkName: vnet.outputs.name
    name: 'snet-${prefix}'
    addressPrefix: subnetAddressPrefix
    networkSecurityGroupResourceId: nsg.outputs.resourceId
  }
}

output vnetName string = vnet.outputs.name
output vnetResourceId string = vnet.outputs.resourceId
output subnetName string = subnet.outputs.name
output subnetResourceId string = subnet.outputs.resourceId
output nsgName string = nsg.outputs.name
output nsgResourceId string = nsg.outputs.resourceId
