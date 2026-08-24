targetScope = 'resourceGroup'

@description('Azure region for the Key Vault.')
param location string = resourceGroup().location

@description('Tags applied to all taggable resources in this module.')
param tags object = {}

@description('Deterministic name suffix shared across resources in this stack.')
param nameSuffix string

@description('Unique token used where Azure requires globally-unique names.')
param resourceToken string

@description('Subnet used for the Key Vault private endpoint.')
param privateEndpointSubnetId string

@description('Private DNS zone for privatelink.vaultcore.azure.net.')
param privateDnsZoneId string

var vaultName = toLower(take('kv${replace(nameSuffix, '-', '')}${resourceToken}', 24))

resource vault 'Microsoft.KeyVault/vaults@2024-11-01' = {
  name: vaultName
  location: location
  tags: tags
  properties: {
    tenantId: tenant().tenantId
    sku: {
      family: 'A'
      name: 'standard'
    }
    enableRbacAuthorization: true
    publicNetworkAccess: 'Disabled'
    networkAcls: {
      bypass: 'AzureServices'
      defaultAction: 'Deny'
    }
  }
}

resource privateEndpoint 'Microsoft.Network/privateEndpoints@2024-05-01' = {
  name: 'pe-kv-${nameSuffix}'
  location: location
  tags: tags
  properties: {
    subnet: {
      id: privateEndpointSubnetId
    }
    privateLinkServiceConnections: [
      {
        name: 'psc-kv'
        properties: {
          privateLinkServiceId: vault.id
          groupIds: [
            'vault'
          ]
        }
      }
    ]
  }
}

resource privateDnsZoneGroup 'Microsoft.Network/privateEndpoints/privateDnsZoneGroups@2024-05-01' = {
  parent: privateEndpoint
  name: 'default'
  properties: {
    privateDnsZoneConfigs: [
      {
        name: 'vault'
        properties: {
          privateDnsZoneId: privateDnsZoneId
        }
      }
    ]
  }
}

output vaultId string = vault.id
output vaultName string = vault.name
output vaultUri string = vault.properties.vaultUri
