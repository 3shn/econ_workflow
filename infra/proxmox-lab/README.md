# Proxmox Tiny LXC (Declarative)

Minimal Terraform/OpenTofu configuration that creates one low-resource, unprivileged LXC on Proxmox VE.

## Resource profile

- CPU: 1 core
- RAM: 256 MiB
- Swap: 128 MiB
- Disk: 4 GiB
- Network: 1 NIC on `vmbr0` (DHCP)
- Startup after create: disabled by default

## Prerequisites

1. Create an API token in Proxmox for automation (recommended over password auth).
2. Ensure an LXC template exists on the target node (see `template_file_id`).
3. Pick a free VMID.

## Usage

```bash
cd infra/proxmox-lab
cp terraform.tfvars.example terraform.tfvars
export TF_VAR_proxmox_api_token='root@pam!terraform=REPLACE_WITH_SECRET'

# OpenTofu
tofu init
tofu plan
tofu apply

# Terraform (same config)
# terraform init
# terraform plan
# terraform apply
```

Destroy when done:

```bash
tofu destroy
```

## Notes

- `proxmox_node_name`, `template_file_id`, and `datastore_id` must match your environment.
- The config uses `insecure = true` by default for self-signed TLS; switch to `false` once certs are trusted.
