targetScope = 'resourceGroup'

@description('Azure region for the Container Apps resources.')
param location string = resourceGroup().location

@description('Tags applied to all taggable resources in this module.')
param tags object = {}

@description('Deterministic name suffix shared across resources in this stack.')
param nameSuffix string

@description('Subnet delegated to Microsoft.App/environments.')
param infrastructureSubnetId string

@description('Log Analytics workspace resource ID.')
param logAnalyticsWorkspaceId string

@description('Log Analytics workspace customer ID.')
param logAnalyticsCustomerId string

@description('Log Analytics workspace shared key.')
@secure()
param logAnalyticsSharedKey string

@description('Azure Container Registry resource ID.')
param acrId string

@description('Azure Container Registry login server.')
param acrLoginServer string

@description('API Management service resource ID.')
param apimId string

@description('API Management service name.')
param apimName string

@description('Worker managed identity resource ID.')
param workerIdentityId string

@description('Worker managed identity principal ID.')
param workerPrincipalId string

@description('Worker managed identity client ID.')
param workerClientId string

@description('Worker image reference. Empty skips the job.')
param workerImage string

@description('Cron expression for the config sync job.')
param configSyncCron string

@description('Cosmos DB endpoint used by the worker and admin UI.')
param cosmosEndpoint string

@description('Cosmos DB database name used by the worker and admin UI.')
param cosmosDatabaseName string

@description('Cosmos DB config container name used by the worker and admin UI.')
param cosmosConfigContainerName string

@description('Admin UI image reference. Empty skips the container app.')
param adminUiImage string

@description('Expose the admin UI publicly. False keeps the environment internal-only.')
param adminUiPublic bool = false

@description('Admin UI managed identity resource ID.')
param adminUiIdentityId string

@description('Admin UI managed identity principal ID.')
param adminUiPrincipalId string

@description('Admin UI managed identity client ID.')
param adminUiClientId string

@description('Entra tenant ID surfaced to the admin UI BFF.')
param entraTenantId string

@description('Audience of the admin UI BFF API.')
param bffApiAudience string

@description('SPA client ID surfaced to the admin UI.')
param spaClientId string

@description('Admin group object ID surfaced to the admin UI BFF.')
param adminGroupObjectId string

@description('Cosmos DB team/subscription map container name.')
param cosmosMapContainerName string

@description('Serialized rate tier settings surfaced to the admin UI.')
param rateTiersJson string

@description('Serialized deployment alias settings surfaced to the admin UI.')
param aliasModelsJson string

var workerJobEnabled = !empty(workerImage)
var adminUiEnabled = !empty(adminUiImage)
var managedEnvironmentName = 'cae-${nameSuffix}'
var jobName = workerJobEnabled ? 'job-config-sync-${nameSuffix}' : ''
var adminUiName = adminUiEnabled ? 'ca-adminui-${nameSuffix}' : ''
var workerAcrPullRoleDefinitionId = subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '7f951dda-4ed3-4680-a7ca-43fe172d538d')
var apimContributorRoleDefinitionId = subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '312a565d-c81f-4fd8-895a-4e21e48d571c')
var jobsOperatorRoleDefinitionId = subscriptionResourceId('Microsoft.Authorization/roleDefinitions', 'b9a307c4-5aa3-4b52-ba60-2b17c136cd7b')
var logAnalyticsReaderRoleDefinitionId = subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '73c42c96-874c-492b-b04d-ab87d138a893')

resource managedEnvironment 'Microsoft.App/managedEnvironments@2024-10-02-preview' = {
  name: managedEnvironmentName
  location: location
  tags: tags
  properties: {
    vnetConfiguration: {
      infrastructureSubnetId: infrastructureSubnetId
      internal: !adminUiPublic
    }
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: logAnalyticsCustomerId
        sharedKey: logAnalyticsSharedKey
      }
    }
  }
}

resource workerAcrPull 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (workerJobEnabled) {
  name: guid(acrId, workerPrincipalId, 'worker-acrpull')
  scope: resourceGroup()
  properties: {
    principalId: workerPrincipalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: workerAcrPullRoleDefinitionId
  }
}

resource workerApimContributor 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (workerJobEnabled) {
  name: guid(apimId, workerPrincipalId, 'worker-apim-contributor')
  scope: resourceGroup()
  properties: {
    principalId: workerPrincipalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: apimContributorRoleDefinitionId
  }
}

// NOTE: Preserved from the Terraform design. The worker needs broad APIM write access today because it updates
// named values and API configuration dynamically. Hardening this to a narrower custom role is deferred.
resource configSyncJob 'Microsoft.App/jobs@2024-10-02-preview' = if (workerJobEnabled) {
  name: jobName
  location: location
  tags: tags
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: {
      '${workerIdentityId}': {}
    }
  }
  properties: {
    environmentId: managedEnvironment.id
    configuration: {
      triggerType: 'Schedule'
      replicaTimeout: 1800
      replicaRetryLimit: 1
      scheduleTriggerConfig: {
        cronExpression: configSyncCron
        parallelism: 1
        replicaCompletionCount: 1
      }
      registries: [
        {
          server: acrLoginServer
          identity: workerIdentityId
        }
      ]
    }
    template: {
      containers: [
        {
          name: 'worker'
          image: workerImage
          env: [
            {
              name: 'APIM_NAME'
              value: apimName
            }
            {
              name: 'WORKER_CLIENT_ID'
              value: workerClientId
            }
            {
              name: 'COSMOS_ENDPOINT'
              value: cosmosEndpoint
            }
            {
              name: 'COSMOS_DATABASE'
              value: cosmosDatabaseName
            }
            {
              name: 'COSMOS_CONFIG_CONTAINER'
              value: cosmosConfigContainerName
            }
          ]
        }
      ]
    }
  }
}

resource adminUiAcrPull 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (adminUiEnabled) {
  name: guid(acrId, adminUiPrincipalId, 'adminui-acrpull')
  scope: resourceGroup()
  properties: {
    principalId: adminUiPrincipalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: workerAcrPullRoleDefinitionId
  }
}

resource adminUiJobsOperator 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (adminUiEnabled && workerJobEnabled) {
  name: guid(managedEnvironment.id, adminUiPrincipalId, 'adminui-jobs-operator')
  scope: resourceGroup()
  properties: {
    principalId: adminUiPrincipalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: jobsOperatorRoleDefinitionId
  }
}

// NOTE: Preserved from the Terraform design. The admin UI reads operational logs directly; a custom scoped reader
// role could reduce breadth later, but for now Log Analytics Reader matches the existing intent exactly.
resource adminUiLogAnalyticsReader 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (adminUiEnabled) {
  name: guid(logAnalyticsWorkspaceId, adminUiPrincipalId, 'adminui-law-reader')
  scope: resourceGroup()
  properties: {
    principalId: adminUiPrincipalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: logAnalyticsReaderRoleDefinitionId
  }
}

resource adminUiApp 'Microsoft.App/containerApps@2024-10-02-preview' = if (adminUiEnabled) {
  name: adminUiName
  location: location
  tags: tags
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: {
      '${adminUiIdentityId}': {}
    }
  }
  properties: {
    managedEnvironmentId: managedEnvironment.id
    configuration: {
      activeRevisionsMode: 'Single'
      registries: [
        {
          server: acrLoginServer
          identity: adminUiIdentityId
        }
      ]
      ingress: {
        external: adminUiPublic
        targetPort: 8080
        transport: 'auto'
      }
    }
    template: {
      containers: [
        {
          name: 'admin-ui'
          image: adminUiImage
          env: [
            {
              name: 'APIM_NAME'
              value: apimName
            }
            {
              name: 'ADMIN_UI_CLIENT_ID'
              value: adminUiClientId
            }
            {
              name: 'COSMOS_ENDPOINT'
              value: cosmosEndpoint
            }
            {
              name: 'COSMOS_DATABASE'
              value: cosmosDatabaseName
            }
            {
              name: 'COSMOS_CONFIG_CONTAINER'
              value: cosmosConfigContainerName
            }
            {
              name: 'COSMOS_MAP_CONTAINER'
              value: cosmosMapContainerName
            }
            {
              name: 'RATE_TIERS_JSON'
              value: rateTiersJson
            }
            {
              name: 'ALIAS_MODELS_JSON'
              value: aliasModelsJson
            }
            {
              name: 'ENTRA_TENANT_ID'
              value: entraTenantId
            }
            {
              name: 'BFF_API_AUDIENCE'
              value: bffApiAudience
            }
            {
              name: 'SPA_CLIENT_ID'
              value: spaClientId
            }
            {
              name: 'ADMIN_GROUP_OBJECT_ID'
              value: adminGroupObjectId
            }
            {
              name: 'CONFIG_SYNC_JOB_NAME'
              value: jobName
            }
          ]
        }
      ]
      scale: {
        minReplicas: 1
        maxReplicas: 2
      }
    }
  }
}

output environmentId string = managedEnvironment.id
output environmentName string = managedEnvironment.name
output jobName string = jobName
output adminUiName string = adminUiEnabled ? adminUiApp.name : ''
output adminUiFqdn string = adminUiEnabled ? 'https://${adminUiApp!.properties.configuration.ingress.fqdn}' : ''
