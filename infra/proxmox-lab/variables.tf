variable "proxmox_endpoint" {
  description = "Proxmox VE API endpoint."
  type        = string
  default     = "https://192.168.86.61:8006/api2/json"
}

variable "proxmox_api_token" {
  description = "API token in the format USER@REALM!TOKEN_NAME=TOKEN_SECRET."
  type        = string
  sensitive   = true
}

variable "proxmox_insecure" {
  description = "Skip TLS verification for self-signed certs."
  type        = bool
  default     = true
}

variable "proxmox_node_name" {
  description = "Target Proxmox node name."
  type        = string
}

variable "vmid" {
  description = "Unique VMID for the container."
  type        = number
  default     = 9010
}

variable "hostname" {
  description = "Container hostname."
  type        = string
  default     = "lab-tiny-ct"
}

variable "template_file_id" {
  description = "Template file id available on the node, e.g. local:vztmpl/debian-12-standard_12.7-1_amd64.tar.zst."
  type        = string
}

variable "datastore_id" {
  description = "Storage backend for the root disk."
  type        = string
}

variable "bridge" {
  description = "Linux bridge for container NIC."
  type        = string
  default     = "vmbr0"
}

variable "start_after_create" {
  description = "Start container after provisioning."
  type        = bool
  default     = false
}

variable "ssh_public_keys" {
  description = "SSH public keys for root user."
  type        = list(string)
  default     = []
}
