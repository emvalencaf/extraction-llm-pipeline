#!/usr/bin/env bash
# Create, update or destroy the whole stack, ECR first.
#
#   scripts/deploy-infra.sh bootstrap   create the remote-state bucket (local state, once)
#   scripts/deploy-infra.sh up          ECR -> build and push the image -> everything else
#   scripts/deploy-infra.sh plan        plan only (the image must already be pushed for IMAGE_TAG)
#   scripts/deploy-infra.sh down        destroy the stack, then the state bucket
#
# Needs: AWS credentials in the environment, terraform >= 1.10, docker with buildx (for `up`).
# Variables: BUCKET_SUFFIX (required, makes the S3 names yours, e.g. your account id),
#            ALERT_EMAIL (required, receives alarms and budget notices),
#            GEMINI_API_KEY (optional, written to SSM after apply; without it jobs fail),
#            IMAGE_TAG (default: current commit SHA), AWS_REGION (default us-east-1).
set -euo pipefail

cd "$(git rev-parse --show-toplevel)"

: "${BUCKET_SUFFIX:?set BUCKET_SUFFIX (3-20 chars of a-z, 0-9, -), e.g. your AWS account id}"
REGION="${AWS_REGION:-us-east-1}"
IMAGE_TAG="${IMAGE_TAG:-$(git rev-parse --short=12 HEAD)}"
TF="${TERRAFORM:-terraform}"
INFRA=infra
BOOTSTRAP=infra/bootstrap

tf_main() { "$TF" -chdir="$INFRA" "$@"; }
: "${ALERT_EMAIL:?set ALERT_EMAIL, the address that receives alarm and budget notifications}"
vars=(-var "bucket_suffix=$BUCKET_SUFFIX" -var "image_tag=$IMAGE_TAG" -var "alert_email=$ALERT_EMAIL")

# Repositories with immutable OIDC subjects put owner and repo ids in the `sub` claim; the
# roles must trust that exact prefix, so read it from GitHub instead of guessing.
oidc_sub_prefix() {
  [[ -n "${TF_VAR_github_sub_prefix:-}" ]] && return 0
  command -v gh >/dev/null 2>&1 || return 0
  local prefix
  prefix="$(gh api "repos/$(gh repo view --json nameWithOwner -q .nameWithOwner)/actions/oidc/customization/sub" \
    -q '.sub_claim_prefix // empty' 2>/dev/null || true)"
  [[ -n "$prefix" ]] && export TF_VAR_github_sub_prefix="$prefix"
  return 0
}

# One GitHub OIDC provider fits an account. If this bootstrap state owns it, keep managing it
# (answering "it exists" must never make Terraform destroy it); if another stack owns it, reuse
# it; if there is none, create it. TF_VAR_create_oidc_provider overrides the choice.
oidc_provider_mode() {
  [[ -n "${TF_VAR_create_oidc_provider:-}" ]] && return 0
  if "$TF" -chdir="$BOOTSTRAP" state list 2>/dev/null | grep -q '^aws_iam_openid_connect_provider\.github'; then
    export TF_VAR_create_oidc_provider=true
  elif aws iam list-open-id-connect-providers --query 'OpenIDConnectProviderList[].Arn' --output text \
    | grep -q 'oidc-provider/token.actions.githubusercontent.com'; then
    export TF_VAR_create_oidc_provider=false
  else
    export TF_VAR_create_oidc_provider=true
  fi
  return 0
}

bootstrap() {
  oidc_sub_prefix
  "$TF" -chdir="$BOOTSTRAP" init -input=false
  oidc_provider_mode
  "$TF" -chdir="$BOOTSTRAP" apply -input=false -auto-approve \
    -var "bucket_suffix=$BUCKET_SUFFIX" -var "region=$REGION"
  state_bucket="$("$TF" -chdir="$BOOTSTRAP" output -raw state_bucket)"
  printf 'bucket = "%s"\nregion = "%s"\n' "$state_bucket" "$REGION" >"$INFRA/backend.hcl"
  echo "wrote $INFRA/backend.hcl"
}

init_main() {
  [[ -f "$INFRA/backend.hcl" ]] || { echo "missing $INFRA/backend.hcl: run '$0 bootstrap'" >&2; exit 1; }
  tf_main init -input=false -backend-config=backend.hcl
}

push_image() {
  local repo registry
  repo="$(tf_main output -raw ecr_repository_url)"
  registry="${repo%%/*}"
  aws ecr get-login-password --region "$REGION" | docker login --username AWS --password-stdin "$registry"
  docker buildx version >/dev/null 2>&1 || {
    echo "docker buildx is required (apt: docker-buildx with Ubuntu docker.io, docker-buildx-plugin with Docker's own repo)" >&2; exit 1; }
  # Lambda needs a single-manifest image (--provenance=false) for its default x86_64 arch.
  docker buildx build --platform linux/amd64 --provenance=false --push \
    -f docker/lambda.Dockerfile -t "$repo:$IMAGE_TAG" .
}

# Terraform only creates the SSM parameter (with a placeholder) so the key never enters the state.
# With GEMINI_API_KEY set it is written here; the value goes through a pipe, not argv.
put_gemini_key() {
  local name
  name="$(tf_main output -raw gemini_parameter_name)"
  if [[ -z "${GEMINI_API_KEY:-}" ]]; then
    echo "WARNING: the Gemini key is still the placeholder, so every job will fail." >&2
    echo "Export GEMINI_API_KEY and re-run 'up', or: aws ssm put-parameter --overwrite" \
      "--type SecureString --name $name --value <key>" >&2
    return 0
  fi
  printf %s "$GEMINI_API_KEY" | aws ssm put-parameter --region "$REGION" --overwrite \
    --type SecureString --name "$name" --value file:///dev/stdin >/dev/null
  echo "Gemini key written to $name"
}

case "${1:-}" in
  bootstrap)
    bootstrap
    ;;
  up)
    init_main
    # The functions reference the image, so the repository and the image must exist first.
    tf_main apply -input=false -auto-approve -target=module.registry "${vars[@]}"
    push_image
    tf_main apply -input=false -auto-approve "${vars[@]}"
    put_gemini_key
    ;;
  plan)
    init_main
    tf_main plan -input=false "${vars[@]}"
    ;;
  down)
    init_main
    tf_main destroy -input=false -auto-approve "${vars[@]}"
    # The state bucket goes last: it holds the state of the stack above.
    "$TF" -chdir="$BOOTSTRAP" destroy -input=false -auto-approve \
      -var "bucket_suffix=$BUCKET_SUFFIX" -var "region=$REGION"
    rm -f "$INFRA/backend.hcl"
    ;;
  *)
    sed -n '2,12p' "$0" | sed 's/^# \{0,1\}//'
    exit 2
    ;;
esac
