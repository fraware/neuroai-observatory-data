output "aws_region" {
  description = "Region containing the custody resources."
  value       = var.aws_region
}

output "efs_file_system_id" {
  description = "Regional encrypted EFS file system ID."
  value       = aws_efs_file_system.custody.id
}

output "efs_file_system_arn" {
  description = "Regional encrypted EFS file system ARN."
  value       = aws_efs_file_system.custody.arn
}

output "efs_dns_name" {
  description = "EFS DNS name."
  value       = aws_efs_file_system.custody.dns_name
}

output "efs_access_point_id" {
  description = "Access point whose root is /phase4."
  value       = aws_efs_access_point.custody.id
}

output "efs_security_group_id" {
  description = "Security group permitting NFS only from approved client security groups."
  value       = aws_security_group.efs.id
}

output "backup_vault_name" {
  description = "AWS Backup vault name."
  value       = aws_backup_vault.custody.name
}

output "backup_vault_arn" {
  description = "AWS Backup vault ARN."
  value       = aws_backup_vault.custody.arn
}

output "backup_plan_id" {
  description = "AWS Backup plan ID selecting the custody EFS file system."
  value       = aws_backup_plan.custody.id
}

output "mount_command_template" {
  description = "Template mount command. The acquisition host must use amazon-efs-utils and TLS."
  value       = "sudo mount -t efs -o tls,accesspoint=${aws_efs_access_point.custody.id} ${aws_efs_file_system.custody.id}:/ /mnt/neuroai-phase4-custody"
}
