variable "gcp_project" {
  description = "GCP Project ID"
  type        = string
}

variable "gcp_region" {
  description = "GCP Region"
  type        = string
  default     = "us-central1"
}

variable "gcp_zone" {
  description = "GCP Zone for GKE"
  type        = string
  default     = "us-central1-a"
}

variable "environment" {
  description = "Deployment environment (dev | staging | prod)"
  type        = string
  default     = "dev"
  validation {
    condition     = contains(["dev", "staging", "prod"], var.environment)
    error_message = "Environment must be dev, staging, or prod."
  }
}

variable "min_node_count" {
  description = "Minimum GKE nodes"
  type        = number
  default     = 2
}

variable "max_node_count" {
  description = "Maximum GKE nodes (for 50K TPS scaling)"
  type        = number
  default     = 20
}

variable "db_password" {
  description = "PostgreSQL password (use Secret Manager reference in prod)"
  type        = string
  sensitive   = true
}
