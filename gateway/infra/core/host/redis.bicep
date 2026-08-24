targetScope = 'resourceGroup'

@description('Azure region for the Azure Managed Redis cluster.')
param location string = resourceGroup().location

@description('Tags applied to the Azure Managed Redis resources.')
param tags object = {}

@description('Deterministic name suffix shared across resources in this stack.')
param nameSuffix string

@description('Unique token used where Azure requires region-unique names.')
param resourceToken string

@description('Subnet used for the Redis private endpoint.')
param privateEndpointSubnetId string

@description('Private DNS zone for privatelink.redis.azure.net.')
param privateDnsZoneId string

@description('Run-ledger managed identity principal/object ID granted Redis data-plane access.')
param runLedgerPrincipalId string

@description('Azure Managed Redis SKU.')
param skuName string = 'Balanced_B0'

@description('Azure Managed Redis TLS port exposed to clients.')
param redisPort int = 10000

@description('Redis ACL permissions granted to the run-ledger identity.')
param runLedgerAccessString string = '+@all ~*'

var locationToken = toLower(replace(location, ' ', ''))
var cacheName = toLower(take('redis-${replace(nameSuffix, '-', '')}-${take(resourceToken, 6)}', 60))
var databaseName = 'default'
var assignmentName = 'runledger'

resource redis 'Microsoft.Cache/redisEnterprise@2025-07-01' = {
  name: cacheName
  location: location
  tags: tags
  sku: {
    name: skuName
  }
  properties: {
    encryption: {}
    highAvailability: 'Enabled'
    minimumTlsVersion: '1.2'
    publicNetworkAccess: 'Disabled'
  }
}

resource database 'Microsoft.Cache/redisEnterprise/databases@2025-07-01' = {
  parent: redis
  name: databaseName
  properties: {
    accessKeysAuthentication: 'Disabled'
    clientProtocol: 'Encrypted'
    clusteringPolicy: 'OSSCluster'
    deferUpgrade: 'NotDeferred'
    evictionPolicy: 'NoEviction'
    modules: []
    port: redisPort
  }
}

resource runLedgerAccess 'Microsoft.Cache/redisEnterprise/databases/accessPolicyAssignments@2026-05-01-preview' = {
  parent: database
  name: assignmentName
  properties: {
    accessPolicyName: 'default'
    accessString: runLedgerAccessString
    user: {
      objectId: runLedgerPrincipalId
    }
  }
}

resource privateEndpoint 'Microsoft.Network/privateEndpoints@2024-05-01' = {
  name: 'pe-redis-${nameSuffix}'
  location: location
  tags: tags
  properties: {
    subnet: {
      id: privateEndpointSubnetId
    }
    privateLinkServiceConnections: [
      {
        name: 'psc-redis'
        properties: {
          privateLinkServiceId: redis.id
          groupIds: [
            'redisEnterprise'
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
        name: 'redis'
        properties: {
          privateDnsZoneId: privateDnsZoneId
        }
      }
    ]
  }
}

output cacheId string = redis.id
output databaseId string = database.id
output hostName string = '${redis.name}.${locationToken}.redis.azure.net'
output port int = redisPort
