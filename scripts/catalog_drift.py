"""Verify that resources listed in a catalog entry actually exist in the cloud.

Read-only: only describes/lists resources, never creates or modifies anything.
Supports GCP Cloud Run and AWS ECS services.
"""

import argparse
import subprocess
import sys

import yaml

from scripts._shell import resolve


def _gcloud_run_service_exists(service, region, project_id):
    result = subprocess.run(
        [
            resolve("gcloud"), "run", "services", "describe", service,
            "--region", region, "--project", project_id,
            "--format", "value(metadata.name)",
        ],
        capture_output=True, text=True, timeout=30,
    )
    return result.returncode == 0, result.stderr.strip()


def _aws_ecs_service_exists(cluster, service, region):
    result = subprocess.run(
        [
            resolve("aws"), "ecs", "describe-services",
            "--cluster", cluster, "--services", service,
            "--region", region,
            "--query", "services[?status=='ACTIVE']",
            "--output", "json",
        ],
        capture_output=True, text=True, timeout=30,
    )
    if result.returncode != 0:
        return False, result.stderr.strip()
    if result.stdout.strip() in ("", "[]"):
        return False, f"ECS service '{service}' not found (or not ACTIVE) in cluster '{cluster}'"
    return True, ""


def _check_gcp_cloud(cloud):
    project_id = cloud["project_id"]
    findings = []
    for region in cloud.get("regions", []):
        for service_cfg in cloud.get("services", []):
            if service_cfg.get("type") != "cloud_run":
                continue
            service = service_cfg["service"]
            ok, detail = _gcloud_run_service_exists(service, region, project_id)
            findings.append({
                "resource": f"cloud_run:{service}",
                "region": region,
                "ok": ok,
                "detail": detail,
            })
    return findings


def _check_aws_cloud(cloud):
    findings = []
    for region in cloud.get("regions", []):
        for service_cfg in cloud.get("services", []):
            if service_cfg.get("type") != "ecs":
                continue
            cluster = service_cfg["cluster"]
            service = service_cfg["service"]
            ok, detail = _aws_ecs_service_exists(cluster, service, region)
            findings.append({
                "resource": f"ecs:{cluster}/{service}",
                "region": region,
                "ok": ok,
                "detail": detail,
            })
    return findings


_PROVIDER_CHECKERS = {
    "gcp": _check_gcp_cloud,
    "aws": _check_aws_cloud,
}


def check_catalog_entry(entry):
    """Returns a list of drift findings: [{resource, region, ok, detail}]."""
    findings = []
    for cloud in entry.get("clouds", []):
        checker = _PROVIDER_CHECKERS.get(cloud.get("provider"))
        if checker is None:
            continue
        findings.extend(checker(cloud))
    return findings


def main():
    parser = argparse.ArgumentParser(description="Check catalog entries for drift against real cloud resources")
    parser.add_argument("catalog_paths", nargs="+", help="Path(s) to catalog/*.yaml file(s)")
    args = parser.parse_args()

    any_drift = False
    for path in args.catalog_paths:
        with open(path, "r", encoding="utf-8") as f:
            entry = yaml.safe_load(f)

        print(f"== {entry['id']} ({path}) ==")
        findings = check_catalog_entry(entry)
        if not findings:
            print("  (no supported cloud resources to check)")
            continue

        for finding in findings:
            status = "OK" if finding["ok"] else "DRIFT"
            print(f"  [{status}] {finding['resource']} region={finding['region']}")
            if not finding["ok"]:
                any_drift = True
                print(f"    {finding['detail']}")

    sys.exit(1 if any_drift else 0)


if __name__ == "__main__":
    main()
