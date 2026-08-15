# Principal DevOps Engineer – Take-Home Technical Assessment

This repository demonstrates a small production-minded infrastructure workflow using **Terraform, Git, Python, and GitLab CI/CD**. The example provisions environment-specific Amazon S3 storage while emphasizing reusable code, secure defaults, controlled promotion, operational safety, and cost awareness.

## Repository structure

```text
.
├── .gitlab-ci.yml
├── .pre-commit-config.yaml
├── Makefile
├── README.md
├── config/
│   ├── dev.json
│   └── prod.json
├── scripts/
│   └── generate_tfvars.py
├── tests/
│   └── test_generate_tfvars.py
└── terraform/
    ├── modules/
    │   └── s3-storage/
    │       ├── main.tf
    │       ├── outputs.tf
    │       ├── variables.tf
    │       └── versions.tf
    └── environments/
        ├── dev/
        │   ├── backend.tf
        │   ├── dev.auto.tfvars.json
        │   ├── main.tf
        │   ├── outputs.tf
        │   ├── variables.tf
        │   └── versions.tf
        └── prod/
            ├── backend.tf
            ├── main.tf
            ├── outputs.tf
            ├── prod.auto.tfvars.json
            ├── variables.tf
            └── versions.tf
```

## 1. Assumptions

- AWS is the target cloud and S3 is the storage resource for the exercise.
- `dev` and `prod` are isolated by separate Terraform root modules and separate remote-state keys. In a larger organization I would prefer separate AWS accounts as an additional isolation boundary.
- The state bucket is bootstrap infrastructure created outside this module. An infrastructure stack should not normally create the backend in which its own state is stored.
- CI jobs obtain short-lived AWS credentials through GitLab OIDC and environment-specific IAM roles. Static AWS access keys should not be stored in the repository.
- S3 bucket names must be globally unique, so the root module appends the AWS account ID.
- The exercise is intentionally focused. Features such as cross-region replication, Object Lock, access logging, and customer-managed KMS keys are design options rather than unconditional defaults because they add cost and operational complexity.

## 2. Setup and local execution

### Prerequisites

- Terraform 1.10+
- Python 3.11+
- AWS credentials for an account in which you are authorized to create S3 resources

### Generate Terraform input files

```bash
python3 scripts/generate_tfvars.py config/dev.json \
  --output terraform/environments/dev/dev.auto.tfvars.json

python3 scripts/generate_tfvars.py config/prod.json \
  --output terraform/environments/prod/prod.auto.tfvars.json
```

Or use:

```bash
make generate
```

### Run Python quality checks

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
ruff check scripts tests
pytest -q
```

### Validate Terraform without a remote backend

```bash
terraform fmt -check -recursive terraform
terraform -chdir=terraform/environments/dev init -backend=false
terraform -chdir=terraform/environments/dev validate
terraform -chdir=terraform/environments/prod init -backend=false
terraform -chdir=terraform/environments/prod validate
```

### Plan/apply with a remote S3 backend

The backend block is intentionally empty so environment-specific values can come from CI/CD or a local backend configuration file rather than being hard-coded.

Example:

```bash
terraform -chdir=terraform/environments/dev init \
  -backend-config="bucket=<terraform-state-bucket>" \
  -backend-config="key=principal-devops-assessment/dev/terraform.tfstate" \
  -backend-config="region=us-west-2" \
  -backend-config="encrypt=true" \
  -backend-config="use_lockfile=true"

terraform -chdir=terraform/environments/dev plan
```

## 3. Terraform design

### Reusable module boundary

`terraform/modules/s3-storage` owns the resource-level implementation. Environment directories are thin composition layers that provide environment-specific inputs. This avoids copying S3 resources between `dev` and `prod` and gives another team a simple module interface.

The module exposes useful outputs (`bucket_id`, `bucket_arn`, and `bucket_domain_name`) that downstream infrastructure can consume.

### Secure defaults

The module enables the following controls:

- S3 versioning by default for recovery from accidental overwrites/deletes.
- Server-side encryption by default.
- Complete S3 public-access blocking.
- `BucketOwnerEnforced` object ownership, avoiding ACL-based access management.
- A bucket policy that denies non-TLS requests.
- `force_destroy = false` so a non-empty bucket is not silently destroyed by Terraform.
- Required operational tags for environment, owner, and management source.

`AES256` is the default encryption mode because S3-managed encryption avoids customer-managed KMS key charges and key-management overhead. If compliance requires stronger separation/control, the module accepts `encryption_algorithm = "aws:kms"` and a customer-managed `kms_key_arn`; S3 Bucket Keys are enabled in that mode to reduce KMS request cost.

### Environment isolation

The design isolates environments in three ways:

1. Separate Terraform root modules (`terraform/environments/dev` and `prod`).
2. Separate state keys (`.../dev/terraform.tfstate` and `.../prod/terraform.tfstate`).
3. Environment is encoded in the S3 bucket name and tags.

For a real enterprise platform, I would add separate AWS accounts and separate GitLab deployment roles for production and non-production.

### State and backend strategy

I would store Terraform state in a dedicated S3 backend bucket with:

- encryption enabled;
- bucket versioning for recovery;
- blocked public access;
- restricted IAM permissions;
- CloudTrail/audit visibility;
- native S3 state locking using `use_lockfile = true`.

State is separated by environment key instead of sharing one state file. This limits blast radius, makes ownership clearer, and allows different access controls for production.

No backend credentials or secret backend values are committed. CI supplies backend configuration and obtains AWS credentials dynamically.

### Promotion across environments

A merge request validates and plans both environments but does not deploy. Once reviewed and merged to the default branch:

- the `dev` plan can apply automatically;
- the exact production plan generated by the pipeline is retained as an artifact;
- production apply is a manual job and should additionally be protected by GitLab protected environments/approvers.

I prefer promotion of reviewed code and a saved plan artifact over running ad-hoc Terraform from engineer workstations.

### Drift management

The primary control is to make Terraform the authoritative path for infrastructure changes and restrict direct console changes using IAM where practical.

I would also run a scheduled read-only `terraform plan -detailed-exitcode` for each environment. Exit code `2` indicates drift/change and should open an alert or issue for investigation. Emergency manual changes should be documented and then reconciled into code with either an import/state operation or a follow-up change, rather than being left as permanent unmanaged drift.

### Lifecycle, retention, backup, and cost

Versioning improves recoverability but old versions can grow storage indefinitely. The module therefore expires noncurrent versions after a configurable period:

- dev example: 30 days;
- prod example: 180 days.

It also aborts incomplete multipart uploads after seven days to avoid paying for abandoned parts.

I intentionally did not force a storage-class transition. Whether Standard-IA, Intelligent-Tiering, Glacier, or another tier is cheaper depends on object size, access frequency, retrieval requirements, and retention. In production I would use S3 Storage Lens/usage metrics first, then add lifecycle transitions based on measured access patterns.

S3 versioning is recovery protection, not a complete backup strategy. For high-criticality data I would evaluate cross-account/cross-region replication, Object Lock, and a formal backup/restore policy based on RPO/RTO and compliance requirements.

## 4. Python utility

`scripts/generate_tfvars.py` reads a JSON configuration, validates it, applies documented defaults, and emits Terraform-compatible `.tfvars.json`.

Example input:

```json
{
  "environment": "dev",
  "resource_name": "platform-data",
  "owner": "data-platform",
  "tags": {
    "cost_center": "RND",
    "criticality": "medium"
  }
}
```

Example command:

```bash
python3 scripts/generate_tfvars.py config/dev.json -o dev.tfvars.json
```

Design choices:

- Standard library only at runtime; no dependency is needed merely to generate configuration.
- Validation is kept separate from file I/O and output generation, making the code straightforward to test and extend.
- Invalid JSON, missing fields, invalid environments, invalid retention, and incomplete KMS configuration return readable errors and non-zero exit codes.
- JSON `.tfvars` was chosen instead of generating HCL text because JSON can be serialized safely and deterministically without implementing an HCL renderer.
- Unknown fields are rejected so configuration typos fail early instead of silently reaching Terraform. Adding a supported attribute requires only adding it to the small supported-field schema plus the corresponding Terraform variable, keeping extension straightforward.

Tests cover defaults, environment validation, KMS validation, malformed JSON, and CLI output.

## 5. Git workflow

### Branching strategy

I recommend trunk-based development with short-lived feature branches:

- `main` is protected and always expected to be releasable.
- Engineers create small branches such as `feature/add-retention-policy` or `fix/state-locking`.
- Changes reach `main` only through merge requests.
- Long-lived `dev`/`release` branches are avoided because they tend to drift and make infrastructure promotion harder to reason about.

### Merge request expectations

A merge request should include:

- a concise description of the change and operational impact;
- linked work item/incident when applicable;
- successful format, validation, lint, tests, security/policy checks, and Terraform plans;
- explicit review of destructive/replacement actions in the plan;
- at least one qualified reviewer, with CODEOWNERS/extra approval for production-sensitive modules;
- updated README/runbook when behavior or operational procedures change.

### Release/promotion model

The same reviewed commit is promoted forward. Merge-request pipelines create plans for visibility. After merge, dev applies automatically; prod uses a manual protected deployment gate. For larger organizations I would promote immutable build/plan metadata and use protected environments with separation of duties.

### Hotfix and rollback

For an urgent production issue, create a short-lived hotfix branch from `main`, make the smallest safe change, run the same required pipeline controls, obtain expedited review, and merge. Emergency bypasses should be exceptional and auditable.

For rollback, prefer a new commit that reverts the bad change and then run Terraform plan/apply. For infrastructure, rollback is not always the same as application rollback: data deletion or an irreversible provider/API change may require a forward fix or state recovery. The Terraform plan must therefore be reviewed before rollback is applied.

### Merge vs. rebase vs. revert vs. reset

- **Merge:** Use when integrating an approved branch and preserving the branch relationship/history is useful. A merge commit is appropriate if the team values an explicit MR boundary.
- **Rebase:** Use on a local/private feature branch to bring it up to date with `main` and keep a clean linear history. Do not casually rebase shared branches because it rewrites commit IDs.
- **Revert:** Preferred way to undo a change already merged to a shared/protected branch. It creates a new auditable commit and does not rewrite history.
- **Reset:** Use primarily for local, unpublished cleanup (for example, moving a local branch pointer before pushing). Avoid `git reset --hard` on shared branches because it can destroy work and break traceability.

## 6. GitLab CI/CD design

The pipeline contains four logical stages: `validate`, `test`, `plan`, and `deploy`.

### Merge requests

Merge requests run:

- `terraform fmt -check`;
- `terraform init -backend=false` + `terraform validate` for dev and prod;
- Python linting with Ruff;
- Python tests with Pytest;
- Terraform plans for dev and prod when AWS/OIDC credentials are available.

Any failure in formatting, validation, tests, security/policy checks, or Terraform planning should block promotion.

### Default branch and development deployment

After the change is approved and merged to `main`, the pipeline repeats validation/plan and automatically applies the reviewed dev plan. This gives fast feedback in a lower-risk environment while preserving the controlled path through Git.

### Production deployment

Production is intentionally different:

- production deploy runs only from the default branch;
- it consumes the saved production `tfplan` artifact;
- `when: manual` provides the explicit deployment gate;
- in a real GitLab project I would mark production as a protected environment and restrict the manual action to an authorized approver/deployer group.

This prevents an unreviewed feature branch from deploying directly to production.

### Credentials and sensitive values

Secrets are never committed to Git. The preferred AWS authentication model is GitLab OIDC federation into least-privilege IAM roles, using separate roles/policies for dev and prod.

If CI/CD variables are required, sensitive values should be masked, protected, environment-scoped, and available only to protected branches/environments. Terraform state itself must also be treated as sensitive because providers can store resource attributes in state.

### Production-ready enhancements

Given more time, I would add:

- GitLab SAST and dependency scanning for Python/tooling dependencies;
- IaC security scanning (for example GitLab IaC scanning, Checkov, or tfsec);
- policy-as-code with OPA/Conftest or Sentinel-equivalent controls for mandatory tags, encryption, approved regions, and destructive actions;
- Infracost or cloud-native cost estimation/budget thresholds on merge requests;
- scheduled drift-detection pipelines;
- GitLab `CODEOWNERS`, protected environments, and required deployment approvals;
- provider dependency lock files committed and updated through reviewed automation;
- OIDC-to-AWS IAM role federation with no long-lived cloud keys;
- central reusable GitLab CI components/templates for many infrastructure repositories;
- notifications/change-management integration for production deployments.

## 7. Security, compliance, and operational trade-offs

The design tries to keep secure behavior automatic rather than relying on engineers to remember individual flags. Public access is blocked, TLS is enforced, encryption and versioning default on, deletion is conservative, and production deployment is gated.

At the same time, not every compliance control is enabled blindly. A dedicated KMS key, replication, Object Lock, long retention, and archive tiers can all be appropriate, but they introduce cost, access-management requirements, and recovery implications. Those should be driven by data classification, legal retention, RPO/RTO, and measured usage rather than enabled universally.

## 8. What I would do next

If this repository became a shared production platform, my next priorities would be:

1. Bootstrap a dedicated, tightly controlled state account/bucket and GitLab OIDC roles.
2. Add IaC security scanning and policy-as-code as required merge checks.
3. Add scheduled drift detection and alerting.
4. Add protected production environments and formal approval rules.
5. Add module integration tests in an ephemeral AWS test account.
6. Add documented import/migration procedures for existing S3 buckets.
7. Publish the storage module in an internal module registry with semantic versioning so multiple teams can consume pinned versions safely.
