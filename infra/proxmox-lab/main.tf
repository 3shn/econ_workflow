terraform {
  required_version = ">= 1.6.0"

  required_providers {
    proxmox = {
      source = "bpg/proxmox"
    }
  }
}

provider "proxmox" {
  endpoint  = var.proxmox_endpoint
  api_token = var.proxmox_api_token
  insecure  = var.proxmox_insecure
}

resource "proxmox_virtual_environment_container" "tiny" {
  node_name    = var.proxmox_node_name
  vm_id        = var.vmid
  unprivileged = true
  started      = var.start_after_create

  description = "Tiny lab LXC managed declaratively"

  operating_system {
    template_file_id = var.template_file_id
    type             = "debian"
  }

  initialization {
    hostname = var.hostname

    ip_config {
      ipv4 {
        address = "dhcp"
      }
    }

    user_account {
      keys = var.ssh_public_keys
    }
  }

  network_interface {
    name   = "eth0"
    bridge = var.bridge
  }

  cpu {
    cores = 1
  }

  memory {
    dedicated = 256
    swap      = 128
  }

  disk {
    datastore_id = var.datastore_id
    size         = 4
  }

  tags = ["iac", "lab", "tiny"]
}
