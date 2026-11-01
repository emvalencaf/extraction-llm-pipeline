#!/usr/bin/env bash
# Create, update or destroy the whole stack, ECR first.
#
#   scripts/deploy-infra.sh bootstrap   create the remote-state bucket (local state, once)
#   scripts/deploy-infra.sh up          ECR -> build and push the image -> everything else
#   scripts/deploy-infra.sh plan        plan only (the image must already be pushed for IMAGE_TAG)
#   scripts/deploy-infra.sh down        destroy the stack, then the state bucket
#
# Needs: AWS credentials in the environment, terraform >= 1.10, docker (for `up`).
# Variables: BUCKET_SUFFIX (required, makes the S3 names yours, e.g. your account id),
#            ALERT_EMAIL (required, receives alarms and budget notices),
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

bootstrap() {
  "$TF" -chdir="$BOOTSTRAP" init -input=false
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
  # Lambda needs a single-manifest image. BuildKit adds a provenance manifest unless told
  # not to; the legacy builder (no buildx) never does and rejects the flag.
  build_flags=()
  if docker buildx version >/dev/null 2>&1; then build_flags+=(--provenance=false); fi
  docker build ${build_flags[@]+"${build_flags[@]}"} -f docker/lambda.Dockerfile -t "$repo:$IMAGE_TAG" .
  docker push "$repo:$IMAGE_TAG"
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
    echo "Set the Gemini key: aws ssm put-parameter --overwrite --type SecureString" \
      "--name \"\$(terraform -chdir=$INFRA output -raw gemini_parameter_name)\" --value <key>"
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
