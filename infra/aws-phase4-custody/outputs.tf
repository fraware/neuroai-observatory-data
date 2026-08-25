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
  description = "Writer access point whose root is /phase4."
  value       = aws_efs_access_point.custody.id
}

output "efs_verifier_access_point_id" {
  description = "Read-only verifier access point whose root is /phase4."
  value       = aws_efs_access_point.verifier.id
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
  description = "Writer mount template retained for compatibility. IAM authorization and TLS are mandatory."
  value       = "sudo mount -t efs -o tls,iam,accesspoint=${aws_efs_access_point.custody.id} ${aws_efs_file_system.custody.id}:/ /mnt/neuroai-phase4-custody"
}

output "writer_mount_command_template" {
  description = "Acquisition-writer mount template using IAM authorization, TLS, and the writer access point."
  value       = "sudo mount -t efs -o tls,iam,accesspoint=${aws_efs_access_point.custody.id} ${aws_efs_file_system.custody.id}:/ /mnt/neuroai-phase4-custody"
}

output "verifier_mount_command_template" {
  description = "Read-only verifier mount template using IAM authorization, TLS, and the verifier access point."
  value       = "sudo mount -t efs -o tls,iam,accesspoint=${aws_efs_access_point.verifier.id} ${aws_efs_file_system.custody.id}:/ /mnt/neuroai-phase4-custody-readonly"
}
