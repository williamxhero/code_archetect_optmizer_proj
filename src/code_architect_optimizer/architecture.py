"""Deterministic, best-effort local Python import dependency analysis."""

from __future__ import annotations

import ast
import os
import tokenize
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path, PurePosixPath


@dataclass(frozen=True)
class ArchitectureAnalysis:
    """Resolved local dependencies and canonical strongly connected groups."""

    dependencies: dict[str, set[str]]
    cycles: list[tuple[str, ...]]
    unresolved_imports: int = 0


def analyze_python_dependencies(
    repo_root: str | Path,
    *,
    excluded: Callable[[str], bool],
    selected_paths: set[str] | None = None,
) -> ArchitectureAnalysis:
    """Resolve unique local modules under the repository root and src layout.

    No code is imported or executed. Unresolved imports, recognized dynamic
    imports and unreadable/malformed files count as incomplete observations.
    """
    root = Path(repo_root).resolve()
    paths: list[Path] = []
    for directory, dirs, files in os.walk(root):
        parent = Path(directory)
        dirs[:] = sorted(d for d in dirs if not excluded((parent / d).relative_to(root).as_posix()))
        paths.extend(
            parent / name for name in sorted(files)
            if name.endswith(".py") and not excluded((parent / name).relative_to(root).as_posix())
            and (parent / name).resolve().is_relative_to(root)
        )
    modules: dict[str, set[str]] = defaultdict(set)
    module_parts: dict[str, tuple[str, ...]] = {}
    unresolved = 0
    for path in sorted(paths):
        relative = PurePosixPath(path.relative_to(root).as_posix())
        parts = list(relative.parts)
        if parts[-1] == "__init__.py":
            parts = parts[:-1]
        else:
            parts[-1] = parts[-1][:-3]
        if not parts or any(not part.isidentifier() for part in parts):
            unresolved += 1
            continue
        path_text = relative.as_posix()
        # src is a source root, not a package for resolving relative imports.
        canonical_parts = parts[1:] if parts[0] == "src" and len(parts) > 1 else parts
        module_parts[path_text] = tuple(canonical_parts)
        modules[".".join(parts)].add(path_text)
        modules[".".join(canonical_parts)].add(path_text)

    # Index the full allowed inventory before selection, so filtering cannot
    # turn an ambiguous alias into an apparently unique dependency.
    dependencies: dict[str, set[str]] = {
        path: set() for path in module_parts
        if selected_paths is None or path in selected_paths
    }
    for source in dependencies:
        parts = module_parts[source]
        source_path = root / source
        try:
            with tokenize.open(source_path) as handle:
                tree = ast.parse(handle.read(), filename=source)
        except (OSError, UnicodeError, SyntaxError):
            unresolved += 1
            continue
        package = parts if source_path.name == "__init__.py" else parts[:-1]
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    target = _resolve(alias.name, modules)
                    if target is None:
                        unresolved += 1
                    else:
                        dependencies[source].add(target)
            elif isinstance(node, ast.ImportFrom):
                if node.level > len(package):
                    unresolved += len(node.names)
                    continue
                base = list(package[: len(package) - node.level + 1]) if node.level else []
                if node.module:
                    base.extend(node.module.split("."))
                module = ".".join(base)
                for alias in node.names:
                    child = ".".join((*base, alias.name)) if alias.name != "*" else module
                    # An ambiguous child is not proof of a package attribute.
                    if len(modules.get(module, set())) > 1 or len(modules.get(child, set())) > 1:
                        unresolved += 1
                        continue
                    target = _resolve(child, modules) or _resolve(module, modules)
                    if target is None:
                        unresolved += 1
                    else:
                        dependencies[source].add(target)
            elif isinstance(node, ast.Call) and (
                isinstance(node.func, ast.Name) and node.func.id == "__import__"
                or isinstance(node.func, ast.Attribute) and node.func.attr == "import_module"
            ):
                unresolved += 1

    for source, targets in dependencies.items():
        omitted = targets - dependencies.keys()
        unresolved += len(omitted)
        dependencies[source] = targets - omitted

    return ArchitectureAnalysis(
        dependencies=dependencies,
        cycles=_canonical_cycles(dependencies),
        unresolved_imports=unresolved,
    )


def _resolve(module: str, modules: dict[str, set[str]]) -> str | None:
    matches = modules.get(module, set())
    if len(matches) != 1:
        return None
    parts = module.split(".")
    for length in range(1, len(parts)):
        parents = modules.get(".".join(parts[:length]), set())
        if len(parents) > 1 or any(not path.endswith("/__init__.py") for path in parents):
            return None
    return next(iter(matches))


def _canonical_cycles(graph: dict[str, set[str]]) -> list[tuple[str, ...]]:
    """Return stable SCC member groups using iterative traversal for deep graphs."""
    visited: set[str] = set()
    order: list[str] = []
    for node in sorted(graph):
        if node in visited:
            continue
        visited.add(node)
        stack = [(node, iter(sorted(graph[node])))]
        while stack:
            current, children = stack[-1]
            child = next(children, None)
            if child is None:
                order.append(current)
                stack.pop()
            elif child not in visited:
                visited.add(child)
                stack.append((child, iter(sorted(graph[child]))))

    reverse: dict[str, set[str]] = {node: set() for node in graph}
    for node, children in graph.items():
        for child in children:
            reverse[child].add(node)
    visited.clear()
    components: list[tuple[str, ...]] = []
    for node in reversed(order):
        if node in visited:
            continue
        pending = [node]
        visited.add(node)
        component: list[str] = []
        while pending:
            current = pending.pop()
            component.append(current)
            for child in sorted(reverse[current]):
                if child not in visited:
                    visited.add(child)
                    pending.append(child)
        if len(component) > 1 or node in graph[node]:
            components.append(tuple(sorted(component)))
    return sorted(components)


__all__ = ["ArchitectureAnalysis", "analyze_python_dependencies"]
