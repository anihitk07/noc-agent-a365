targetScope = 'resourceGroup'

@description('Fabric capacity resource name.')
param name string

@description('Azure region for the Fabric capacity.')
param location string = resourceGroup().location

@description('User UPN or principal ID that administers the capacity.')
param adminMember string

@description('Optional service-principal object ID that also administers the capacity.')
param servicePrincipalId string = ''

@description('Tags applied to the capacity.')
param tags object = {}

resource fabricCapacity 'Microsoft.Fabric/capacities@2023-11-01' = {
  name: name
  location: location
  tags: tags
  sku: {
    name: 'F2'
    tier: 'Fabric'
  }
  properties: {
    administration: {
      members: union(
        [
          adminMember
        ],
        empty(servicePrincipalId) ? [] : [
          servicePrincipalId
        ]
      )
    }
  }
}

output name string = fabricCapacity.name
output id string = fabricCapacity.id
