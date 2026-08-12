"""Read-only CLI tool wrappers for the investigator. GCP and AWS supported.

Every function here must be non-destructive: describe/list/logs only.
No credentials for write operations are ever available in this process.
"""

import subprocess

from scripts._shell import resolve


def _run(cmd):
    cmd = [resolve(cmd[0]), *cmd[1:]]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    return {
        "cmd": " ".join(cmd),
        "returncode": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
    }


def gcloud_run_describe(service, region, project_id):
    return _run(
        [
            "gcloud", "run", "services", "describe", service,
            "--region", region, "--project", project_id,
            "--format", "json",
        ]
    )


def gcloud_logging_read(project_id, filter_str, limit=50):
    return _run(
        [
            "gcloud", "logging", "read", filter_str,
            "--project", project_id, "--limit", str(limit),
            "--format", "json",
        ]
    )


def aws_ecs_describe_service(cluster, service, region):
    return _run(
        [
            "aws", "ecs", "describe-services",
            "--cluster", cluster, "--services", service,
            "--region", region,
        ]
    )


def aws_ecs_list_tasks(cluster, service, region):
    return _run(
        [
            "aws", "ecs", "list-tasks",
            "--cluster", cluster, "--service-name", service,
            "--region", region,
        ]
    )


def aws_logs_tail(log_group, region, since="30m"):
    return _run(
        [
            "aws", "logs", "tail", log_group,
            "--region", region, "--since", since,
        ]
    )


def gh_run_list(repo, limit=10):
    return _run(
        ["gh", "run", "list", "--repo", repo, "--limit", str(limit), "--json",
         "status,conclusion,createdAt,headBranch,event"]
    )
