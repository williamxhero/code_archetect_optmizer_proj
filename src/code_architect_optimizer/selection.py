"""Deterministic branch delta selection and static Python dependency closure."""

from __future__ import annotations

import ast
import subprocess
import tokenize
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath


@dataclass
class ChangedSelection:
    paths: set[str] | None = None
    changed: set[str] = field(default_factory=set)
    base: str = ""


def _git(root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=root, capture_output=True, text=True,
        encoding="utf-8", errors="surrogateescape", timeout=30, check=True,
    )
    return result.stdout


def select_changed(repo_root: str) -> ChangedSelection:
    """Use the first usable default-branch merge base, or safely select all."""
    root = Path(repo_root)
    try:
        if Path(_git(root, "rev-parse", "--show-toplevel").strip()).resolve() != root:
            return ChangedSelection()
        # A pushed feature branch commonly tracks the same-name remote branch;
        # prefer default-branch refs so that upstream cannot make the delta empty.
        candidates = ["refs/remotes/origin/HEAD", "refs/remotes/origin/main",
                      "refs/heads/main", "refs/remotes/origin/master", "refs/heads/master"]
        try:
            candidates.append(_git(root, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}").strip())
        except subprocess.SubprocessError:
            pass
        base = ""
        for candidate in candidates:
            try:
                base = _git(root, "merge-base", "HEAD", candidate).strip()
            except subprocess.SubprocessError:
                continue
            if base:
                break
        if not base:
            return ChangedSelection()

        inventory = set(_git(root, "ls-files", "-z", "--cached").split("\0"))
        inventory.update(_git(root, "ls-files", "-z", "--others", "--exclude-standard").split("\0"))
        inventory = {path for path in inventory if path and _local_file(root, path)}
        changed: set[str] = set()
        for args in (
            ("diff", "--name-only", "-z", base, "HEAD", "--"),
            ("diff", "--name-only", "-z", "--cached", "HEAD", "--"),
            ("diff", "--name-only", "-z", "--"),
            ("ls-files", "-z", "--others", "--exclude-standard"),
        ):
            changed.update(path for path in _git(root, *args).split("\0") if path in inventory)
        paths = _dependency_closure(root, changed, inventory)
        return ChangedSelection(paths=paths, changed=changed, base=base)
    except (OSError, subprocess.SubprocessError, UnicodeError):
        return ChangedSelection()


def _local_file(root: Path, path: str) -> bool:
    candidate = root / path
    try:
        return candidate.is_file() and candidate.resolve().is_relative_to(root)
    except OSError:
        return False


def _dependency_closure(root: Path, changed: set[str], inventory: set[str]) -> set[str]:
    selected = set(changed)
    pending = sorted(changed)
    while pending:
        path = pending.pop()
        for dependency in sorted(_python_dependencies(root, path, inventory)):
            if dependency not in selected:
                selected.add(dependency)
                pending.append(dependency)
    return selected


def _python_dependencies(root: Path, path: str, inventory: set[str]) -> set[str]:
    if not path.endswith(".py"):
        return set()
    try:
        with tokenize.open(root / path) as source:
            tree = ast.parse(source.read())
    except (OSError, UnicodeError, SyntaxError):
        return set()

    parent = PurePosixPath(path).parent
    # Resolve only explicit repo-root/src imports, or sibling script imports.
    # Multiple matches are ambiguous, so do not guess from sys.path ordering.
    search_roots = {PurePosixPath("."), PurePosixPath("src")}
    if (parent / "__init__.py").as_posix() not in inventory:
        search_roots.add(parent)
    dependencies: set[str] = set()

    def resolve(module: str, roots: set[PurePosixPath]) -> None:
        if not module or any(not part.isidentifier() for part in module.split(".")):
            return
        relative = PurePosixPath(*module.split("."))
        matches: set[str] = set()
        for search_root in roots:
            stem = search_root / relative
            matches.update(candidate for candidate in (
                stem.with_suffix(".py").as_posix(), (stem / "__init__.py").as_posix(),
            ) if candidate in inventory)
        if len(matches) != 1:
            return
        match = matches.pop()
        dependencies.add(match)
        for package in PurePosixPath(match).parents:
            initializer = (package / "__init__.py").as_posix()
            if initializer in inventory:
                dependencies.add(initializer)

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                resolve(alias.name, search_roots)
        elif isinstance(node, ast.ImportFrom):
            roots = search_roots
            if node.level:
                anchor = parent
                valid = True
                for _ in range(node.level - 1):
                    if anchor == PurePosixPath("."):
                        valid = False
                        break
                    anchor = anchor.parent
                if not valid:
                    continue
                roots = {anchor}
            module = node.module or ""
            resolve(module, roots)
            for alias in node.names:
                if alias.name != "*":
                    resolve(f"{module}.{alias.name}" if module else alias.name, roots)
    return dependencies
