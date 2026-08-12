#!/usr/bin/env bash
# Verify catalog resources actually exist in the cloud accounts they claim to.
# Intended to run nightly (see .github/workflows/drift-check.yml) and on demand.
#
# Usage:
#   ./scripts/catalog-drift.sh catalog/myproject.yaml
#   ./scripts/catalog-drift.sh          # checks every catalog/*.yaml (except _schema/example)
set -euo pipefail

check_file() {
  local file="$1"
  echo "== Checking $file =="

  python3 - "$file" <<'PYEOF'
import sys
import yaml

with open(sys.argv[1]) as f:
    data = yaml.safe_load(f)

for cloud in data.get("clouds", []):
    provider = cloud.get("provider")
    for svc in cloud.get("services", []):
        print(f"{provider}\t{svc.get('type')}\t{cloud.get('account_id')}\t"
              f"{svc.get('cluster','')}\t{svc.get('service','')}\t{cloud.get('regions',[''])[0]}")
PYEOF
}

drift_found=0

check_and_verify_ecs() {
  local cluster="$1" service="$2" region="$3"
  if ! aws ecs describe-services --cluster "$cluster" --services "$service" --region "$region" \
        --query 'services[0].status' --output text >/dev/null 2>&1; then
    echo "  DRIFT: ECS service '$service' in cluster '$cluster' ($region) not found"
    drift_found=1
  fi
}

check_and_verify_cloud_run() {
  local service="$1" region="$2"
  if ! gcloud run services describe "$service" --region "$region" --format='value(status.url)' >/dev/null 2>&1; then
    echo "  DRIFT: Cloud Run service '$service' ($region) not found"
    drift_found=1
  fi
}

files=("$@")
if [ ${#files[@]} -eq 0 ]; then
  mapfile -t files < <(find catalog -maxdepth 1 -name '*.yaml' ! -name '_schema.yaml' ! -name 'example-project.yaml')
fi

for f in "${files[@]}"; do
  while IFS=$'\t' read -r provider svc_type account cluster service region; do
    case "$svc_type" in
      ecs)
        check_and_verify_ecs "$cluster" "$service" "$region" ;;
      cloud_run)
        check_and_verify_cloud_run "$service" "$region" ;;
      *)
        : # no automated check for this service type yet
        ;;
    esac
  done < <(check_file "$f")
done

if [ "$drift_found" -ne 0 ]; then
  echo "Catalog drift detected. Fix the catalog or the cloud resources before relying on it."
  exit 1
fi
echo "No drift detected."

