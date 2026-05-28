# Copilot Instructions

## Azure Resource Naming Convention

When creating Azure resources (resource groups, storage accounts, AI services, etc.), follow this naming pattern:

```
{type}-{project}-{env}-{region}-{instance}
```

| Segment    | Description                          | Examples                        |
|------------|--------------------------------------|---------------------------------|
| `type`     | Resource type abbreviation           | `rg`, `st`, `ai`, `kv`, `cosmos` |
| `project`  | Project or workload name             | `minion`                        |
| `env`      | Environment                          | `dev`, `stg`, `prod`            |
| `region`   | Azure region short code              | `swe` (Sweden Central), `eus`   |
| `instance` | Numeric instance identifier          | `001`, `002`, `003`             |

**Examples:**
- Resource group: `rg-minion-dev-swe-003`
- Storage account: `stminiondevswe003` (no hyphens — storage account limitation)
- Key Vault: `kv-minion-dev-swe-003`

Always use lowercase. For resources that don't allow hyphens (e.g. storage accounts), concatenate segments without separators.

## Authorization for Azure Resources

Use Entra managed identities or service principals for authentication. Assign the least privilege necessary to service principals or managed identities. For local development, use `az login` to authenticate with your user account, which should have appropriate permissions on the Azure resources.
example:

credential = DefaultAzureCredential(), not connection strings or keys.

