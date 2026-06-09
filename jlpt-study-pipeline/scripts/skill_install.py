#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
from pathlib import Path

EXCLUDED_NAMES = {
    '.git',
    '.pytest_cache',
    '.venv',
    '__pycache__',
    'out',
}
EXCLUDED_SUFFIXES = {'.pyc', '.pyo'}


def project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def skill_name(source_root: Path) -> str:
    manifest = source_root / 'SKILL.md'
    in_frontmatter = False
    for line in manifest.read_text(encoding='utf-8').splitlines():
        stripped = line.strip()
        if stripped == '---':
            if not in_frontmatter:
                in_frontmatter = True
                continue
            break
        if in_frontmatter and stripped.startswith('name:'):
            return stripped.split(':', 1)[1].strip().strip('"\'')
    raise ValueError(f'Could not find name in {manifest}')


def nearest_codex_root(start: Path) -> Path | None:
    for path in [start, *start.parents]:
        if (path / '.codex').is_dir():
            return path
    return None


def git_root(start: Path) -> Path | None:
    try:
        result = subprocess.run(
            ['git', 'rev-parse', '--show-toplevel'],
            cwd=start,
            check=True,
            capture_output=True,
            text=True,
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        return None
    return Path(result.stdout.strip()).resolve()


def default_target(
    source_root: Path,
    level: str,
    repo_root: Path | None = None,
    codex_home: Path | None = None,
) -> Path:
    source_root = source_root.resolve()
    name = skill_name(source_root)
    if level == 'repo':
        root = repo_root or nearest_codex_root(source_root) or git_root(source_root) or source_root.parent
        return root.resolve() / '.codex' / 'skills' / name
    if level == 'user':
        home = codex_home or Path(os.environ.get('CODEX_HOME', Path.home() / '.codex'))
        return home.expanduser().resolve() / 'skills' / name
    raise ValueError(f'Unsupported level: {level}')


def ignore_names(_directory: str, names: list[str]) -> set[str]:
    ignored = set()
    for name in names:
        if name in EXCLUDED_NAMES or Path(name).suffix in EXCLUDED_SUFFIXES:
            ignored.add(name)
    return ignored


def install_skill(source_root: Path, target: Path, force: bool = False) -> Path:
    source_root = source_root.resolve()
    target = target.resolve()
    if not (source_root / 'SKILL.md').is_file():
        raise FileNotFoundError(f'Missing SKILL.md in {source_root}')
    if target.exists():
        if not force:
            raise FileExistsError(f'{target} already exists; rerun with --force to replace it')
        shutil.rmtree(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source_root, target, ignore=ignore_names)
    return target


def parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description='Install this Codex skill to repo or user level.')
    parser.add_argument('--level', choices=['repo', 'user'], default='repo')
    parser.add_argument('--source', type=Path, default=project_root())
    parser.add_argument('--target', type=Path, help='Explicit skill target directory.')
    parser.add_argument('--repo-root', type=Path, help='Repo root for --level repo; defaults to nearest .codex parent or git root.')
    parser.add_argument('--codex-home', type=Path, help='Codex home for --level user; defaults to $CODEX_HOME or ~/.codex.')
    parser.add_argument('--force', action='store_true', help='Replace an existing installed skill directory.')
    parser.add_argument('--dry-run', action='store_true', help='Print the target without copying files.')
    return parser


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    source = args.source.resolve()
    target = args.target or default_target(source, args.level, args.repo_root, args.codex_home)
    if args.dry_run:
        print(target)
        return 0
    installed = install_skill(source, target, force=args.force)
    print(f'Installed {skill_name(source)} to {installed}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
