# Infrastructure Inventory

Use this as a small, declarative "source of truth" for practical operations data:

- What assets exist (`assets`)
- Which networks/IP ranges exist (`networks`)
- Which services run where (`services`)
- How to access components (`access`)

## Why this structure

1. Stable IDs first.
   Every record has an `id`; relationships use IDs instead of free-text names.
2. Separate concerns.
   Network definitions live in `networks`, runtime hosts/VMs in `assets`, endpoints in `services`.
3. Machine-checkable.
   Keep it in TOML and run a validator before committing changes.
4. Low overhead.
   One file, one validator, no external dependency.

## Files

- `proxmox_inventory.template.toml`: starter template
- `../scripts/validate_inventory.py`: validator

## Usage

```bash
cp inventory/proxmox_inventory.template.toml inventory/proxmox_inventory.toml
python3 scripts/validate_inventory.py inventory/proxmox_inventory.toml
```

