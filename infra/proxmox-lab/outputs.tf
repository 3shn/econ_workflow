output "container_vmid" {
  description = "VMID assigned to the tiny LXC."
  value       = var.vmid
}

output "container_node" {
  description = "Proxmox node where the tiny LXC is created."
  value       = var.proxmox_node_name
}
