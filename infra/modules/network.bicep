// Shared network for one resource group. Created once per RG by the CLI
// (board.azure.deployment.ensure_network) on first deploy; reused by every
// subsequent board into the same RG.
//
// CIDRs are intentionally hardcoded — multi-CIDR support is out of scope.

@description('Naming prefix derived from the resource group name (rgName minus any leading "rg-").')
param prefix string

@description('Azure region. Defaults to the resource group location.')
param location string = resourceGroup().location

@description('Tags applied to vnet + subnet. Pre-merged by the caller (built-in + extraTags).')
param tags object = {}

var vnetAddressPrefix = '10.0.0.0/16'
var subnetAddressPrefix = '10.0.1.0/24'

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
  }
}

output vnetName string = vnet.outputs.name
output vnetResourceId string = vnet.outputs.resourceId
output subnetName string = subnet.outputs.name
output subnetResourceId string = subnet.outputs.resourceId
