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

@description('Object ID of the group/user granted OAuth identity-passthrough access to noc-topology-agent/noc-comms-agent (e.g. the noc-iq-demo-teams-users AAD group). Leave empty to skip -- see docs/PRIMER_MCP_CANCEL_SCOPE_BUG.md for why this must be PROJECT scope, not account scope.')
param teamsUsersPrincipalId string = ''

@description('Principal type of teamsUsersPrincipalId.')
param teamsUsersPrincipalType string = 'Group'

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

// Persisted Prompt Agents (noc-topology-agent/noc-comms-agent) use Agent-Service-
// managed OAuth identity passthrough: the CALLING TEAMS USER's own OAuth grant is
// what Agent Service checks, so each Teams user (or, as here, the group they
// belong to) needs this role at PROJECT scope specifically -- an assignment
// scoped only to the parent account is silently not honored by this data-plane
// check, the exact same failure class documented in
// docs/PRIMER_MCP_CANCEL_SCOPE_BUG.md for the old toolbox design. Cross-tenant
// token exchange is not supported for this feature.
resource foundryAgentConsumerRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (!empty(teamsUsersPrincipalId)) {
  scope: aiAccount::project
  name: guid(aiAccount::project.id, teamsUsersPrincipalId, 'eed3b665-ab3a-47b6-8f48-c9382fb1dad6')
  properties: {
    principalId: teamsUsersPrincipalId
    principalType: teamsUsersPrincipalType
    roleDefinitionId: resourceId('Microsoft.Authorization/roleDefinitions', 'eed3b665-ab3a-47b6-8f48-c9382fb1dad6') // Foundry Agent Consumer
  }
}

// The toolbox MCP endpoint (every tool call the calling Teams user's OBO identity
// makes) is a SEPARATE data-plane check from foundryAgentConsumerRole above --
// discovered live when Foundry Agent Consumer alone still 403'd on the MCP
// "Cancelled via cancel scope" path. See docs/TROUBLESHOOTING.md "Foundry project
// RBAC: the caller of the Responses API needs its own role".
resource teamsUsersAiDeveloperRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (!empty(teamsUsersPrincipalId)) {
  scope: aiAccount::project
  name: guid(aiAccount::project.id, teamsUsersPrincipalId, '64702f94-c441-49e6-a78b-ef80e0188fee')
  properties: {
    principalId: teamsUsersPrincipalId
    principalType: teamsUsersPrincipalType
    roleDefinitionId: resourceId('Microsoft.Authorization/roleDefinitions', '64702f94-c441-49e6-a78b-ef80e0188fee') // Azure AI Developer
  }
}

// Foundry Project Runtime User is the role that actually matters for a DIRECT
// (non-agent_reference) Responses API call -- confirmed by inspecting every
// candidate role's dataActions live: it's the only one whose dataActions
// include Microsoft.CognitiveServices/accounts/AIServices/responses/*, the
// exact action `openai_client.responses.create(...)` hits in agent.py. The two
// roles below it are kept as belt-and-suspenders (tried first, live, before
// this one was found) -- a future cleanup pass could drop them if reconfirmed
// unnecessary, but they're cheap to keep and remove any doubt.
resource teamsUsersFoundryProjectRuntimeUserRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (!empty(teamsUsersPrincipalId)) {
  scope: aiAccount::project
  name: guid(aiAccount::project.id, teamsUsersPrincipalId, '142bfaed-a13f-4c2d-bed2-6db62c4a1009')
  properties: {
    principalId: teamsUsersPrincipalId
    principalType: teamsUsersPrincipalType
    roleDefinitionId: resourceId('Microsoft.Authorization/roleDefinitions', '142bfaed-a13f-4c2d-bed2-6db62c4a1009') // Foundry Project Runtime User
  }
}

resource teamsUsersCognitiveServicesOpenAiUserRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (!empty(teamsUsersPrincipalId)) {
  scope: aiAccount::project
  name: guid(aiAccount::project.id, teamsUsersPrincipalId, '5e0bd9bd-7b93-4f28-af87-19fc36ad61bd')
  properties: {
    principalId: teamsUsersPrincipalId
    principalType: teamsUsersPrincipalType
    roleDefinitionId: resourceId('Microsoft.Authorization/roleDefinitions', '5e0bd9bd-7b93-4f28-af87-19fc36ad61bd') // Cognitive Services OpenAI User
  }
}

resource teamsUsersCognitiveServicesUserRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (!empty(teamsUsersPrincipalId)) {
  scope: aiAccount::project
  name: guid(aiAccount::project.id, teamsUsersPrincipalId, 'a97b65f3-24c7-4388-baec-2e87135dc908')
  properties: {
    principalId: teamsUsersPrincipalId
    principalType: teamsUsersPrincipalType
    roleDefinitionId: resourceId('Microsoft.Authorization/roleDefinitions', 'a97b65f3-24c7-4388-baec-2e87135dc908') // Cognitive Services User
  }
}
