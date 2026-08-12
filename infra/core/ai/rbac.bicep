targetScope = 'resourceGroup'

@description('AI Services account name.')
param aiServicesAccountName string

@description('AI project name.')
param aiProjectName string

@description('Principal ID to grant project-scope RBAC to (e.g. the App Service system-assigned identity).')
param principalId string

@description('Principal type.')
param principalType string = 'ServicePrincipal'

@description('Azure AI Search service name the App Service identity needs data-plane read access to (Foundry IQ knowledge base MCP tool).')
param searchServiceName string = ''

// Foundry Agents API requires PROJECT-scope RBAC, not just account scope.
resource aiAccount 'Microsoft.CognitiveServices/accounts@2025-04-01-preview' existing = {
  name: aiServicesAccountName

  resource project 'projects' existing = {
    name: aiProjectName
  }
}

resource aiDeveloperRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: aiAccount::project
  name: guid(aiAccount::project.id, principalId, '64702f94-c441-49e6-a78b-ef80e0188fee')
  properties: {
    principalId: principalId
    principalType: principalType
    roleDefinitionId: resourceId('Microsoft.Authorization/roleDefinitions', '64702f94-c441-49e6-a78b-ef80e0188fee')
  }
}

resource cognitiveServicesUserRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: aiAccount::project
  name: guid(aiAccount::project.id, principalId, 'a97b65f3-24c7-4388-baec-2e87135dc908')
  properties: {
    principalId: principalId
    principalType: principalType
    roleDefinitionId: resourceId('Microsoft.Authorization/roleDefinitions', 'a97b65f3-24c7-4388-baec-2e87135dc908')
  }
}

// Foundry IQ (knowledge base MCP tool) queries Azure AI Search directly with
// the App Service's own credential -- it needs data-plane read access, which
// was previously missing (every MCP session.initialize() call failed with a
// silent auth error that anyio/mcp mis-surfaced as "Cancelled via cancel
// scope ...").
resource searchService 'Microsoft.Search/searchServices@2024-06-01-preview' existing = if (!empty(searchServiceName)) {
  name: searchServiceName
}

resource searchIndexDataReaderRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (!empty(searchServiceName)) {
  scope: searchService
  name: guid(searchService.id, principalId, '1407120a-92aa-4202-b7e9-c0e197c71c8f')
  properties: {
    principalId: principalId
    principalType: principalType
    roleDefinitionId: resourceId('Microsoft.Authorization/roleDefinitions', '1407120a-92aa-4202-b7e9-c0e197c71c8f') // Search Index Data Reader
  }
}
