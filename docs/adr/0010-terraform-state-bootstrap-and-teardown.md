# Terraform state, bootstrap and full teardown

`infra/bootstrap/` (local state, run once by hand) creates the state bucket and
this repository's CI roles; everything else is composed from `infra/modules/`
with S3 native locking (`use_lockfile`, Terraform 1.10 or later) and its own state
key. The bootstrap references the existing GitHub OIDC provider instead of
creating it. So that anyone can replicate and tear down the project, buckets
(including the state bucket) use `force_destroy`, ECR uses `force_delete`, and
nothing uses `prevent_destroy`; `scripts/deploy-infra.sh down` destroys the main
stack first and the bootstrap second.
