"""Raiden CLI entrypoint — text-mode investigation and runbook execution.

Usage:
    raiden investigate "the api service is down" --project my-app
    raiden run restart_ecs_service --project my-app --param cluster=prod --param service=my-app
    raiden catalog list
"""
from __future__ import annotations

import click
from rich.console import Console
from rich.table import Table

from src.audit import AuditLogger
from src.executor import RunbookError, RunbookRunner
from src.investigator import Investigator
from src.resolver import AmbiguousMatchError, NoMatchError, Resolver

console = Console()


@click.group()
def cli() -> None:
    """Raiden — a voice-driven, local-first DevOps agent."""


@cli.command("catalog")
@click.argument("action", type=click.Choice(["list"]))
def catalog_cmd(action: str) -> None:
    resolver = Resolver()
    table = Table(title="Catalog")
    table.add_column("id")
    table.add_column("aliases")
    table.add_column("clouds")
    for entry in resolver.entries:
        providers = ", ".join(c.get("provider", "?") for c in entry.clouds)
        table.add_row(entry.id, ", ".join(entry.aliases), providers)
    console.print(table)


@cli.command("investigate")
@click.argument("problem_statement")
@click.option("--project", required=True, help="Project name/alias to resolve against the catalog")
@click.option("--model", default=None, help="Ollama model name (default: env RAIDEN_MODEL or llama3.1)")
def investigate_cmd(problem_statement: str, project: str, model: str | None) -> None:
    audit = AuditLogger()
    resolver = Resolver()
    try:
        entry = resolver.resolve(project)
    except (NoMatchError, AmbiguousMatchError) as e:
        console.print(f"[red]{e}[/red]")
        raise SystemExit(1)

    audit.log("resolve", query=project, resolved_to=entry.id)
    console.print(f"[bold]Resolved[/bold] '{project}' -> {entry.id}")

    kwargs = {"audit_logger": audit}
    if model:
        kwargs["model"] = model
    investigator = Investigator(**kwargs)

    with console.status(f"Investigating {entry.id}..."):
        result = investigator.investigate(entry, problem_statement)

    console.print(result.raw_answer)


@cli.command("run")
@click.argument("runbook_name")
@click.option("--project", required=True, help="Project name/alias to resolve against the catalog")
@click.option("--param", "params", multiple=True, help="key=value, repeatable")
def run_cmd(runbook_name: str, project: str, params: tuple[str, ...]) -> None:
    audit = AuditLogger()
    resolver = Resolver()
    try:
        entry = resolver.resolve(project)
    except (NoMatchError, AmbiguousMatchError) as e:
        console.print(f"[red]{e}[/red]")
        raise SystemExit(1)

    parsed_params: dict[str, str] = {}
    for p in params:
        if "=" not in p:
            console.print(f"[red]Invalid --param '{p}', expected key=value[/red]")
            raise SystemExit(1)
        key, value = p.split("=", 1)
        parsed_params[key] = value

    runner = RunbookRunner(audit_logger=audit)

    def confirm(message: str) -> bool:
        return click.confirm(message, default=False)

    try:
        output = runner.run(runbook_name, parsed_params, entry, confirm=confirm)
        console.print(f"[green]Done.[/green]\n{output}")
    except RunbookError as e:
        console.print(f"[red]{e}[/red]")
        raise SystemExit(1)


if __name__ == "__main__":
    cli()

