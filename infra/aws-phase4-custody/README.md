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
- a writer EFS access point rooted at `/phase4`;
- a separate verifier EFS access point rooted at `/phase4`;
- an EFS filesystem policy that requires TLS, denies client root access, denies client access outside the two declared access points, grants writer mount/write through the writer access point, grants verifier mount-only access through the verifier access point, and denies write/root access through the verifier access point for every principal;
- a dedicated security group exposing TCP/2049 only to approved client security groups;
- a dedicated AWS Backup vault with governance-mode Vault Lock retention bounds;
- an AWS Backup plan and selection targeting only the custody EFS filesystem;
- a dedicated AWS Backup service role with the AWS-managed backup and restore service-role policies.

The mount-target security group deliberately contains no outbound rule. AWS documents that outbound rules are not used by EFS mount-target network interfaces; approved client hosts must instead permit outbound TCP/2049 to the mount-target security group.

The module intentionally does **not** create the acquisition compute host, VPC, subnets, writer/verifier IAM roles, or public ingress. Compute and role lifecycle should remain independent of the custody filesystem. The role ARNs are supplied as inputs so the EFS resource policy can bind the intended client grants to already-reviewed identities.

## Pinned toolchain

The reference is intentionally frozen to:

- Terraform `1.15.8`;
- HashiCorp AWS provider `6.60.0`.

`versions.tf` enforces those exact versions. The provider lock file must be generated and preserved by the first approved `terraform init`; this repository does not fabricate provider checksums without executing provider resolution.

## Preconditions

1. Terraform 1.15.8.
2. HashiCorp AWS provider 6.60.0.
3. An existing VPC.
4. At least two existing subnets in distinct Availability Zones; three are preferred for the selected Regional topology.
5. One or more client security groups belonging only to approved acquisition/verifier hosts.
6. One or more reviewed acquisition-writer IAM role ARNs.
7. One or more reviewed verifier IAM role ARNs. Writer and verifier role sets must be disjoint.
8. An AWS identity permitted to provision EFS, EC2 security-group rules, KMS, IAM service roles, and AWS Backup resources.
9. An approved retention policy. Defaults are engineering placeholders and must be reviewed before production retrieval.
10. An IAM review showing that no unintended principal can independently obtain EFS client permissions to this filesystem or use the writer access point from an approved client host.

The last condition is substantive. For EFS NFS client authorization, an allow in either an identity-based IAM policy or the file-system resource policy can authorize an action unless an applicable explicit deny overrides it. The resource policy in this module therefore uses EFS-supported access-point conditions to deny all client actions outside the two declared access points and to deny write/root access through the verifier access point for every principal. Those denies prevent direct mounts, undeclared-access-point mounts, and verifier-access-point writes even when another policy grants the underlying client action.

They do **not** prove that the writer access point is usable only by the supplied writer roles. A different principal that independently receives EFS `ClientMount`/`ClientWrite`, can reach the mount target, and mounts through the writer access point may still obtain access through its identity policy. Before production, review effective identity policies, permissions boundaries, session policies, organization controls where applicable, role trust policies, instance/task credentials, and client-host security-group membership. The approved client roles should carry only narrowly scoped EFS client permissions conditioned on the intended access point and filesystem. This residual trust boundary must be recorded as part of #49; it must not be hidden by describing the file-system policy as a complete principal allowlist.

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

writer_principal_arns = [
  "arn:aws:iam::123456789012:role/phase4-acquisition-writer",
]

verifier_principal_arns = [
  "arn:aws:iam::123456789012:role/phase4-custody-verifier",
]

backup_retention_days         = 365
vault_lock_min_retention_days = 35
vault_lock_max_retention_days = 3650
```

Account IDs in this example are placeholders. Do not commit credentials, private keys, tokens, session material, or other secrets merely to make the example executable.

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
- Terraform and the AWS provider resolve to the pinned versions;
- no existing EFS filesystem, backup vault, KMS key, role, or network policy will be destroyed or replaced;
- mount-target subnets are in distinct Availability Zones;
- only the approved client security groups can reach NFS/2049;
- the writer/verifier IAM role ARNs are correct and disjoint;
- undeclared access points and direct mounts are denied for client actions;
- write and root access through the verifier access point are denied for every principal;
- the intended writer roles receive `ClientMount` and `ClientWrite` through the writer access point;
- the intended verifier roles receive `ClientMount` through the verifier access point;
- no unintended identity policy grants usable client access through the writer access point;
- all intended client access requires TLS, IAM authorization, and an EFS mount target;
- client root access is denied;
- EFS and backup encryption use the dedicated customer-managed keys;
- `aws_efs_file_system.custody` retains `prevent_destroy = true`;
- backup retention lies inside Vault Lock bounds;
- the vault lock is governance mode. Do not switch to compliance mode without a separate irreversible-change review.

Apply only the reviewed plan:

```bash
terraform apply phase4-custody.tfplan
```

## Mount requirements

The acquisition and verifier hosts must have `amazon-efs-utils` installed and mount through TLS with IAM authorization and the role-appropriate access point. The module emits separate writer/verifier mount command templates.

Writer shape:

```text
sudo mount -t efs -o tls,iam,accesspoint=<writer-access-point> <file-system-id>:/ /mnt/neuroai-phase4-custody
```

Verifier shape:

```text
sudo mount -t efs -o tls,iam,accesspoint=<verifier-access-point> <file-system-id>:/ /mnt/neuroai-phase4-custody-readonly
```

The repository and custody roots must remain distinct. Production raw responses must never be copied into Git as part of deployment or troubleshooting.

Approved client host security groups must allow outbound TCP/2049 to the EFS mount-target security group. The mount-target security group itself permits inbound TCP/2049 only from the supplied approved client security groups.

## Access-control boundary

The module establishes two intended NFS client authorization classes at the EFS resource-policy layer:

- **acquisition writer** — supplied writer roles are granted `ClientMount` + `ClientWrite` through the writer access point;
- **read-only verifier** — supplied verifier roles are granted `ClientMount` through the verifier access point, while `ClientWrite` and `ClientRootAccess` are denied both to those roles and to every principal using that access point.

The policy also explicitly denies all EFS client actions when a request does not use either declared access point. This converts direct or undeclared-access-point access into an explicit deny instead of relying on the absence of a resource-policy allow.

Both access points enforce the same non-root POSIX identity. This is deliberate: verifier readability does not depend on the writer host's umask, while IAM client authorization remains the mutation boundary. The production preflight must still prove that the actual verifier role cannot create, write, truncate, rename, or delete evidence.

The writer access point remains an explicit external-IAM trust boundary. Because EFS evaluates identity and resource policies together, this module does not claim that naming writer roles in the file-system policy alone excludes every other identity. Production approval requires effective-policy review showing that no other principal can independently authorize usable client access through the writer access point.

The third logical role, **custody administrator**, remains outside the acquisition data path and must be created/recorded separately. It should control infrastructure operations such as backup restore and narrowly governed destructive actions without serving as the normal acquisition or verifier identity.

## Backup and restore gate

Provisioning success is not #49 completion. Before provider retrieval:

1. mount the writer access point from the intended execution host over TLS + IAM;
2. execute the storage-only atomic-write preflight using `scripts/preflight_science_custody.py prepare`;
3. start a fresh process/host context and execute `verify-persistence`;
4. mount the verifier access point under the verifier role and execute `assert-read-only`, preserving its JSON report outside the read-only mount;
5. verify that all five mutation classes are reported blocked and independently record the executing verifier role/session;
6. audit effective EFS client permissions for every identity available on approved client hosts and confirm no unintended principal can use the writer access point;
7. allow or initiate an AWS Backup recovery point;
8. restore the test tree to a separate EFS verification location;
9. compare every path, byte count, and SHA-256 against the primary preflight tree;
10. destroy/recreate the execution host or session and verify the primary tree remains intact;
11. record the real resource IDs, role ARNs, retention policy, policy-audit evidence, and evidence locations on #49.

Only after those controls and executable Phase 4 validation pass should the frozen two-provider scoped pilot run.

## Release boundary

This infrastructure is a restricted custody environment. `science/acquisition-rights-decision-v0.1.md` keeps raw Europe PMC responses internal and record-level Europe PMC derivatives case-reviewed. The custody filesystem and its backups must therefore remain non-public even if a later Crossref-only derivative is cleared for publication.
