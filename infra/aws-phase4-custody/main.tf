data "aws_caller_identity" "current" {}

data "aws_partition" "current" {}

resource "aws_kms_key" "efs" {
  description             = "Encryption key for Phase 4 acquisition custody EFS"
  deletion_window_in_days = 30
  enable_key_rotation     = true
}

resource "aws_kms_alias" "efs" {
  name          = "alias/${var.name_prefix}-efs"
  target_key_id = aws_kms_key.efs.key_id
}

resource "aws_kms_key" "backup" {
  description             = "Encryption key for Phase 4 acquisition custody backups"
  deletion_window_in_days = 30
  enable_key_rotation     = true
}

resource "aws_kms_alias" "backup" {
  name          = "alias/${var.name_prefix}-backup"
  target_key_id = aws_kms_key.backup.key_id
}

resource "aws_security_group" "efs" {
  name_prefix = "${var.name_prefix}-efs-"
  description = "NFS access to Phase 4 acquisition custody"
  vpc_id      = var.vpc_id

  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_vpc_security_group_ingress_rule" "efs_from_clients" {
  for_each = var.client_security_group_ids

  security_group_id            = aws_security_group.efs.id
  referenced_security_group_id = each.value
  from_port                    = 2049
  to_port                      = 2049
  ip_protocol                  = "tcp"
  description                  = "NFS from approved acquisition/verifier clients"
}

resource "aws_efs_file_system" "custody" {
  creation_token   = "${var.name_prefix}-custody"
  encrypted        = true
  kms_key_id       = aws_kms_key.efs.arn
  performance_mode = "generalPurpose"
  throughput_mode  = "elastic"

  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_efs_mount_target" "custody" {
  for_each = toset(var.mount_subnet_ids)

  file_system_id  = aws_efs_file_system.custody.id
  subnet_id       = each.value
  security_groups = [aws_security_group.efs.id]
}

resource "aws_efs_access_point" "custody" {
  file_system_id = aws_efs_file_system.custody.id

  posix_user {
    uid = 1000
    gid = 1000
  }

  root_directory {
    path = "/phase4"

    creation_info {
      owner_uid   = 1000
      owner_gid   = 1000
      permissions = "0750"
    }
  }
}

resource "aws_efs_access_point" "verifier" {
  file_system_id = aws_efs_file_system.custody.id

  # Use the same enforced POSIX identity as the writer so read access does not
  # depend on the acquisition host's umask. IAM client authorization below is
  # the mutation boundary: verifier access is denied ClientWrite.
  posix_user {
    uid = 1000
    gid = 1000
  }

  root_directory {
    path = "/phase4"

    creation_info {
      owner_uid   = 1000
      owner_gid   = 1000
      permissions = "0750"
    }
  }
}

resource "aws_efs_file_system_policy" "custody" {
  file_system_id = aws_efs_file_system.custody.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid       = "DenyUnencryptedClientTransport"
        Effect    = "Deny"
        Principal = "*"
        Action = [
          "elasticfilesystem:ClientMount",
          "elasticfilesystem:ClientWrite",
          "elasticfilesystem:ClientRootAccess",
        ]
        Resource = aws_efs_file_system.custody.arn
        Condition = {
          Bool = {
            "aws:SecureTransport" = "false"
          }
        }
      },
      {
        Sid       = "DenyRootClientAccess"
        Effect    = "Deny"
        Principal = "*"
        Action    = "elasticfilesystem:ClientRootAccess"
        Resource  = aws_efs_file_system.custody.arn
      },
      {
        Sid       = "DenyClientAccessOutsideApprovedAccessPoints"
        Effect    = "Deny"
        Principal = "*"
        Action = [
          "elasticfilesystem:ClientMount",
          "elasticfilesystem:ClientWrite",
          "elasticfilesystem:ClientRootAccess",
        ]
        Resource = aws_efs_file_system.custody.arn
        Condition = {
          StringNotEquals = {
            "elasticfilesystem:AccessPointArn" = [
              aws_efs_access_point.custody.arn,
              aws_efs_access_point.verifier.arn,
            ]
          }
        }
      },
      {
        Sid       = "DenyWriteThroughVerifierAccessPoint"
        Effect    = "Deny"
        Principal = "*"
        Action = [
          "elasticfilesystem:ClientWrite",
          "elasticfilesystem:ClientRootAccess",
        ]
        Resource = aws_efs_file_system.custody.arn
        Condition = {
          StringEquals = {
            "elasticfilesystem:AccessPointArn" = aws_efs_access_point.verifier.arn
          }
        }
      },
      {
        Sid    = "AllowAcquisitionWriter"
        Effect = "Allow"
        Principal = {
          AWS = sort(tolist(var.writer_principal_arns))
        }
        Action = [
          "elasticfilesystem:ClientMount",
          "elasticfilesystem:ClientWrite",
        ]
        Resource = aws_efs_file_system.custody.arn
        Condition = {
          Bool = {
            "aws:SecureTransport"                      = "true"
            "elasticfilesystem:AccessedViaMountTarget" = "true"
          }
          StringEquals = {
            "elasticfilesystem:AccessPointArn" = aws_efs_access_point.custody.arn
          }
        }
      },
      {
        Sid    = "AllowReadOnlyVerifier"
        Effect = "Allow"
        Principal = {
          AWS = sort(tolist(var.verifier_principal_arns))
        }
        Action   = "elasticfilesystem:ClientMount"
        Resource = aws_efs_file_system.custody.arn
        Condition = {
          Bool = {
            "aws:SecureTransport"                      = "true"
            "elasticfilesystem:AccessedViaMountTarget" = "true"
          }
          StringEquals = {
            "elasticfilesystem:AccessPointArn" = aws_efs_access_point.verifier.arn
          }
        }
      },
      {
        Sid    = "DenyVerifierMutation"
        Effect = "Deny"
        Principal = {
          AWS = sort(tolist(var.verifier_principal_arns))
        }
        Action = [
          "elasticfilesystem:ClientWrite",
          "elasticfilesystem:ClientRootAccess",
        ]
        Resource = aws_efs_file_system.custody.arn
      },
    ]
  })
}

resource "aws_backup_vault" "custody" {
  name        = "${var.name_prefix}-vault"
  kms_key_arn = aws_kms_key.backup.arn
}

resource "aws_backup_vault_lock_configuration" "custody" {
  backup_vault_name  = aws_backup_vault.custody.name
  min_retention_days = var.vault_lock_min_retention_days
  max_retention_days = var.vault_lock_max_retention_days
}

resource "aws_iam_role" "backup" {
  name = "${var.name_prefix}-backup-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Principal = {
          Service = "backup.amazonaws.com"
        }
        Action = "sts:AssumeRole"
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "backup" {
  role       = aws_iam_role.backup.name
  policy_arn = "arn:${data.aws_partition.current.partition}:iam::aws:policy/service-role/AWSBackupServiceRolePolicyForBackup"
}

resource "aws_iam_role_policy_attachment" "restore" {
  role       = aws_iam_role.backup.name
  policy_arn = "arn:${data.aws_partition.current.partition}:iam::aws:policy/service-role/AWSBackupServiceRolePolicyForRestores"
}

resource "aws_backup_plan" "custody" {
  name = "${var.name_prefix}-daily"

  rule {
    rule_name         = "daily-efs-custody"
    target_vault_name = aws_backup_vault.custody.name
    schedule          = var.backup_schedule
    start_window      = 60
    completion_window = 360

    lifecycle {
      delete_after = var.backup_retention_days
    }
  }
}

resource "aws_backup_selection" "custody" {
  name         = "${var.name_prefix}-efs"
  iam_role_arn = aws_iam_role.backup.arn
  plan_id      = aws_backup_plan.custody.id
  resources    = [aws_efs_file_system.custody.arn]

  depends_on = [
    aws_iam_role_policy_attachment.backup,
    aws_iam_role_policy_attachment.restore,
  ]
}
