variable "aws_region" {
  description = "AWS region for the custody environment. eu-west-3 is the selected Phase 4 reference region."
  type        = string
  default     = "eu-west-3"
}

variable "name_prefix" {
  description = "Prefix for custody resources."
  type        = string
  default     = "neuroai-phase4"
}

variable "vpc_id" {
  description = "Existing VPC in which EFS mount targets will be created."
  type        = string
}

variable "mount_subnet_ids" {
  description = "Existing subnet IDs for EFS mount targets. Supply subnets in at least two distinct Availability Zones; three are preferred for a Regional file system."
  type        = list(string)

  validation {
    condition     = length(distinct(var.mount_subnet_ids)) >= 2
    error_message = "mount_subnet_ids must contain at least two distinct subnets."
  }
}

variable "client_security_group_ids" {
  description = "Security groups attached to approved acquisition/verifier hosts that may mount the custody filesystem over NFS."
  type        = set(string)

  validation {
    condition     = length(var.client_security_group_ids) > 0
    error_message = "At least one approved client security group is required."
  }
}

variable "backup_retention_days" {
  description = "Retention for scheduled EFS recovery points."
  type        = number
  default     = 365

  validation {
    condition     = var.backup_retention_days >= 35 && var.backup_retention_days <= 3650
    error_message = "backup_retention_days must be between 35 and 3650 days."
  }
}

variable "backup_schedule" {
  description = "AWS Backup schedule expression. Default is daily at 05:00 UTC."
  type        = string
  default     = "cron(0 5 ? * * *)"
}

variable "vault_lock_min_retention_days" {
  description = "Minimum recovery-point retention enforced by Backup Vault Lock."
  type        = number
  default     = 35
}

variable "vault_lock_max_retention_days" {
  description = "Maximum recovery-point retention enforced by Backup Vault Lock."
  type        = number
  default     = 3650
}

variable "tags" {
  description = "Additional resource tags. Do not place secrets or credentials in tags."
  type        = map(string)
  default     = {}
}
