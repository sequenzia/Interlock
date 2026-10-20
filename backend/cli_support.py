"""Typer settings shared by the ``interlock`` command and the modules behind it.

Every module behind a subcommand exposes ``command``, a Typer command whose
signature is its flag list, and a ``main`` that runs it alone through
``run_standalone``, so ``python -m backend.<module>`` and ``interlock <command>``
take the same flags and run the same code. ``backend/cli.py`` registers each
``command`` under its subcommand name and never grows flags of its own.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

import typer

from backend.paths import REPO_DIR


def new_app(*, add_completion: bool = False, **kwargs: Any) -> typer.Typer:
    """A Typer app with the house settings; ``kwargs`` are Typer's own (``name``, ``help``)."""
    return typer.Typer(
        rich_markup_mode="markdown",
        context_settings={"help_option_names": ["-h", "--help"]},
        # A traceback must never print the environment: it carries TYPESAFE_API_KEY.
        pretty_exceptions_show_locals=False,
        add_completion=add_completion,
        **kwargs,
    )


def standalone_app(command: Callable[..., None]) -> typer.Typer:
    """One module's ``command`` as an app of its own, what ``python -m backend.<module>`` runs."""
    app = new_app()
    app.command()(command)
    return app


def run_standalone(command: Callable[..., None], argv: Sequence[str] | None = None) -> None:
    """Run one module's ``command`` on its own; ``argv`` defaults to the process arguments."""
    standalone_app(command)(args=argv)


def repo_relative(path: Path) -> str:
    """``path`` as the docs write it, relative to the repo root, for ``show_default``."""
    return str(path.relative_to(REPO_DIR))
