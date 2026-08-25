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

variable "writer_principal_arns" {
  description = "IAM role ARNs permitted to mount the writer access point and perform EFS client writes."
  type        = set(string)

  validation {
    condition = (
      length(var.writer_principal_arns) > 0 &&
      alltrue([
        for arn in var.writer_principal_arns :
        can(regex("^arn:[^:]+:iam::[0-9]{12}:role/.+$", arn))
      ])
    )
    error_message = "writer_principal_arns must contain one or more full IAM role ARNs."
  }
}

variable "verifier_principal_arns" {
  description = "IAM role ARNs permitted to mount the read-only verifier access point."
  type        = set(string)

  validation {
    condition = (
      length(var.verifier_principal_arns) > 0 &&
      alltrue([
        for arn in var.verifier_principal_arns :
        can(regex("^arn:[^:]+:iam::[0-9]{12}:role/.+$", arn))
      ])
    )
    error_message = "verifier_principal_arns must contain one or more full IAM role ARNs."
  }
}

check "writer_and_verifier_principals_are_disjoint" {
  assert {
    condition = length(
      setintersection(var.writer_principal_arns, var.verifier_principal_arns)
    ) == 0
    error_message = "Writer and verifier IAM principal sets must be disjoint."
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

check "backup_retention_within_vault_lock_bounds" {
  assert {
    condition = (
      var.vault_lock_min_retention_days >= 1 &&
      var.vault_lock_max_retention_days >= var.vault_lock_min_retention_days &&
      var.vault_lock_max_retention_days <= 36500 &&
      var.backup_retention_days >= var.vault_lock_min_retention_days &&
      var.backup_retention_days <= var.vault_lock_max_retention_days
    )
    error_message = "Backup retention must fall within valid Vault Lock minimum/maximum bounds."
  }
}

variable "tags" {
  description = "Additional resource tags. Do not place secrets or credentials in tags."
  type        = map(string)
  default     = {}
}
