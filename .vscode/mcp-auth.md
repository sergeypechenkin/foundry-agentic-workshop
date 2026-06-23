# MCP Server Authentication Configuration

This repository is configured to use **only** the following identity for all MCP server requests:

- **User Account**: `sergeype@oopslab.in`
- **Tenant ID**: `8902e1d8-1e36-476c-bac5-baa41187c44a` (Contoso tenant)
- **Auth Method**: Passwordless (device code / browser interactive)

## Setup Instructions

### 1. Azure CLI Authentication

Authenticate once with the correct identity:

```powershell
az logout
az login --tenant 8902e1d8-1e36-476c-bac5-baa41187c44a --use-device-code
```

Select **sergeype@oopslab.in** in the browser prompt. The token will be cached for MCP credential chain use.

### 2. Azure MCP Server Calls

When calling Azure MCP servers, always include these parameters:

```
auth-method: Credential
tenant: 8902e1d8-1e36-476c-bac5-baa41187c44a
```

Example:
```
mcp_azure_mcp_ser_subscription_list(
  auth-method: "Credential",
  tenant: "8902e1d8-1e36-476c-bac5-baa41187c44a"
)
```

### 3. Azure DevOps MCP Server

Configured in [mcp.json](./mcp.json):
- **Server**: `ado-remote-mcp`
- **URL**: `https://mcp.dev.azure.com/ContosoMortgage123`
- **Type**: HTTP (uses Azure CLI auth context)

Uses the same credential chain; no additional setup needed beyond Azure CLI login.

## Verification

To verify active identity at any time:

```powershell
az account show
```

Should show:
- `user.name`: `sergeype@oopslab.in`
- `tenantId`: `8902e1d8-1e36-476c-bac5-baa41187c44a`

## Multi-Tenant Switching

If you need to use a different tenant/user for testing:

1. Log out: `az logout`
2. Log in with the target identity
3. Update tenant parameter in MCP calls
4. Do **not** commit this change to `.vscode/mcp-auth.md`

Always restore the OopsLab identity before committing.
