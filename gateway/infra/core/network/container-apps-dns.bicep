targetScope = 'resourceGroup'

@description('Tags applied to all taggable resources in this module.')
param tags object = {}

@description('VNet resource ID to link this private DNS zone to.')
param vnetId string

@description('Container Apps managed environment default domain (only known after the environment is created).')
param defaultDomain string

@description('Container Apps managed environment static IP (only known after the environment is created).')
param staticIp string

resource containerAppsEnvDns 'Microsoft.Network/privateDnsZones@2024-06-01' = {
  name: defaultDomain
  location: 'global'
  tags: tags
}

resource containerAppsEnvDnsLink 'Microsoft.Network/privateDnsZones/virtualNetworkLinks@2024-06-01' = {
  parent: containerAppsEnvDns
  name: 'link-aca-env'
  location: 'global'
  tags: tags
  properties: {
    virtualNetwork: {
      id: vnetId
    }
    registrationEnabled: false
  }
}

resource containerAppsEnvDnsWildcard 'Microsoft.Network/privateDnsZones/A@2024-06-01' = {
  parent: containerAppsEnvDns
  name: '*'
  properties: {
    ttl: 3600
    aRecords: [
      {
        ipv4Address: staticIp
      }
    ]
  }
}

resource containerAppsEnvDnsRoot 'Microsoft.Network/privateDnsZones/A@2024-06-01' = {
  parent: containerAppsEnvDns
  name: '@'
  properties: {
    ttl: 3600
    aRecords: [
      {
        ipv4Address: staticIp
      }
    ]
  }
}

output zoneId string = containerAppsEnvDns.id
