# AWS reference deployment for Phase 4 custody

This directory is a **reference provisioning target**, not evidence that production custody has been deployed. It implements the storage side of `science/durable-custody-architecture-v0.1.md` for AWS using a Regional encrypted Amazon EFS filesystem and an independently encrypted AWS Backup vault.

Selected reference region: `eu-west-3` (Paris). The region is configurable, but changing it changes the operational deployment record required by #49.

## Why EFS

The current acquisition implementation requires a durable POSIX filesystem with stable paths, immediate byte-for-byte reads, and same-filesystem temporary-file replacement. Regional EFS is used as the active custody tier because it exposes NFS/POSIX semantics and stores data redundantly across Availability Zones. The backup tier is AWS Backup, which natively protects EFS and supports restore to a new or existing EFS filesystem.

This module does not treat EFS or AWS Backup documentation as proof that the acquisition code's exact atomic-write/restart assumptions hold in the deployed environment. #49 still requires the storage-only preflight, backup/restore byte comparison, and live interruption/restart drill.

## Resources created

- two customer-managed KMS keys: one for EFS and one for the backup vault;
- a Regional encrypted EFS filesystem with Terraform destroy protection;
- one EFS mount target for every supplied subnet;
- an EFS access point rooted at `/phase4`;
- an EFS filesystem policy denying unencrypted client mount transport;
- a dedicated security group exposing TCP/2049 only to approved client security groups;
- a dedicated AWS Backup vault with governance-mode Vault Lock retention bounds;
- an AWS Backup plan and selection targeting only the custody EFS filesystem;
- a dedicated AWS Backup service role with the AWS-managed backup and restore service-role policies.

The module intentionally does **not** create the acquisition compute host, VPC, subnets, user identities, or public ingress. Those controls should be provisioned independently so that custody storage is not coupled to one execution host.

## Preconditions

1. Terraform >= 1.6.
2. AWS provider matching `~> 6.60`.
3. An existing VPC.
4. At least two existing subnets in distinct Availability Zones; three are preferred for the selected Regional topology.
5. One or more client security groups belonging only to approved acquisition/verifier hosts.
6. An AWS identity permitted to provision EFS, EC2 security-group rules, KMS, IAM service roles, and AWS Backup resources.
7. An approved retention policy. Defaults are engineering placeholders and must be reviewed before production retrieval.

## Example variables

Create a local `terraform.tfvars` outside version control or provide variables through an approved secret-free deployment mechanism:

```hcl
aws_region = "eu-west-3"
vpc_id     = "vpc-..."

mount_subnet_ids = [
  "subnet-...",
  "subnet-...",
  "subnet-...",
]

client_security_group_ids = [
  "sg-...",
]

backup_retention_days          = 365
vault_lock_min_retention_days  = 35
vault_lock_max_retention_days  = 3650
```

Do not commit account IDs, credentials, private keys, tokens, or other secrets merely to make the example executable.

## Review and deployment sequence

Before any `apply`:

```bash
terraform fmt -check -recursive
terraform init
terraform validate
terraform plan -out=phase4-custody.tfplan
```

Review the plan manually. In particular verify:

- the provider region and account are the intended deployment target;
- no existing EFS filesystem, backup vault, KMS key, role, or network policy will be destroyed or replaced;
- mount-target subnets are in distinct Availability Zones;
- only the approved client security groups can reach NFS/2049;
- EFS and backup encryption use the dedicated customer-managed keys;
- `aws_efs_file_system.custody` retains `prevent_destroy = true`;
- backup retention lies inside Vault Lock bounds;
- the vault lock is governance mode. Do not switch to compliance mode without a separate irreversible-change review.

Apply only the reviewed plan:

```bash
terraform apply phase4-custody.tfplan
```

The generated provider lock file should be preserved with the deployment record once an approved environment performs `terraform init`; this repository does not fabricate one without executing provider resolution.

## Mount requirements

The acquisition host must have `amazon-efs-utils` installed and mount through TLS using the generated access-point ID. `terraform output mount_command_template` emits the intended shape.

The mount point must be outside the repository checkout, for example:

```text
/mnt/neuroai-phase4-custody
```

The repository and custody roots must remain distinct. Production raw responses must never be copied into Git as part of a deployment or troubleshooting step.

## Access-control boundary

This module constrains network access but does not by itself establish the three logical identities required by the architecture:

- acquisition writer;
- read-only verifier/auditor;
- custody administrator.

Those identities must be created and recorded before #49 can close. The final host-side file ownership and IAM/NFS authorization policy must demonstrate that the verifier cannot mutate the primary or restored custody evidence.

## Backup and restore gate

Provisioning success is not #49 completion. Before provider retrieval:

1. mount the EFS access point from the intended execution host over TLS;
2. execute the exact storage-only atomic-write preflight in `science/durable-custody-architecture-v0.1.md`;
3. allow or initiate an AWS Backup recovery point;
4. restore the test tree to a separate EFS verification location;
5. compare every path, byte count, and SHA-256 against the primary preflight tree;
6. destroy/recreate the execution host or session and verify the primary tree remains intact;
7. record the real resource IDs, identities, retention policy, and evidence locations on #49.

Only after those controls and executable Phase 4 validation pass should the frozen two-provider scoped pilot run.

## Release boundary

This infrastructure is a restricted custody environment. `science/acquisition-rights-decision-v0.1.md` keeps raw Europe PMC responses internal and record-level Europe PMC derivatives case-reviewed. The custody filesystem and its backups must therefore remain non-public even if a later Crossref-only derivative is cleared for publication.
