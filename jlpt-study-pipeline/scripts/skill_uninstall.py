#!/usr/bin/env python3
from __future__ import annotations

import argparse
import shutil
from pathlib import Path

from skill_install import default_target, project_root, skill_name


def uninstall_skill(target: Path, missing_ok: bool = False) -> Path:
    target = target.resolve()
    if not target.exists():
        if missing_ok:
            return target
        raise FileNotFoundError(f'{target} does not exist')
    if not target.is_dir():
        raise NotADirectoryError(str(target))
    shutil.rmtree(target)
    return target


def parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description='Uninstall this Codex skill from repo or user level.')
    parser.add_argument('--level', choices=['repo', 'user'], default='repo')
    parser.add_argument('--source', type=Path, default=project_root())
    parser.add_argument('--target', type=Path, help='Explicit installed skill directory to remove.')
    parser.add_argument('--repo-root', type=Path, help='Repo root for --level repo; defaults to nearest .codex parent or git root.')
    parser.add_argument('--codex-home', type=Path, help='Codex home for --level user; defaults to $CODEX_HOME or ~/.codex.')
    parser.add_argument('--missing-ok', action='store_true', help='Exit successfully if the skill is not installed.')
    parser.add_argument('--yes', action='store_true', help='Confirm removal without prompting.')
    parser.add_argument('--dry-run', action='store_true', help='Print the target without removing files.')
    return parser


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    source = args.source.resolve()
    target = args.target or default_target(source, args.level, args.repo_root, args.codex_home)
    if args.dry_run:
        print(target)
        return 0
    if not args.yes:
        answer = input(f'Remove {target}? [y/N] ')
        if answer.lower() not in {'y', 'yes'}:
            print('Cancelled')
            return 1
    removed = uninstall_skill(target, missing_ok=args.missing_ok)
    print(f'Uninstalled {skill_name(source)} from {removed}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
