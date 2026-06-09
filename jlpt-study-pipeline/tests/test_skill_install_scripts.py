import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))

import skill_install
import skill_uninstall


def make_source(tmp_path: Path) -> Path:
    source = tmp_path / 'jlpt-study-pipeline'
    (source / 'scripts').mkdir(parents=True)
    (source / 'templates').mkdir()
    (source / 'out').mkdir()
    (source / '.venv').mkdir()
    (source / 'scripts' / '__pycache__').mkdir()
    (source / 'SKILL.md').write_text('---\nname: jlpt-study-pipeline\ndescription: test\n---\n', encoding='utf-8')
    (source / 'requirements.txt').write_text('edge-tts\n', encoding='utf-8')
    (source / 'scripts' / 'tool.py').write_text('print(1)\n', encoding='utf-8')
    (source / 'scripts' / '__pycache__' / 'tool.pyc').write_bytes(b'cache')
    (source / 'templates' / 'note.j2').write_text('template\n', encoding='utf-8')
    (source / 'out' / 'generated.txt').write_text('skip\n', encoding='utf-8')
    (source / '.venv' / 'pyvenv.cfg').write_text('skip\n', encoding='utf-8')
    return source


def test_skill_name_from_manifest(tmp_path):
    source = make_source(tmp_path)

    assert skill_install.skill_name(source) == 'jlpt-study-pipeline'


def test_install_skill_copies_sources_and_excludes_generated_dirs(tmp_path):
    source = make_source(tmp_path)
    target = tmp_path / 'repo' / '.codex' / 'skills' / 'jlpt-study-pipeline'

    installed = skill_install.install_skill(source, target, force=False)

    assert installed == target
    assert (target / 'SKILL.md').exists()
    assert (target / 'scripts' / 'tool.py').exists()
    assert (target / 'templates' / 'note.j2').exists()
    assert not (target / 'out').exists()
    assert not (target / '.venv').exists()
    assert not (target / 'scripts' / '__pycache__').exists()


def test_install_refuses_existing_target_without_force(tmp_path):
    source = make_source(tmp_path)
    target = tmp_path / 'repo' / '.codex' / 'skills' / 'jlpt-study-pipeline'
    target.mkdir(parents=True)

    try:
        skill_install.install_skill(source, target, force=False)
    except FileExistsError as error:
        assert str(target) in str(error)
    else:
        raise AssertionError('expected FileExistsError')


def test_install_replaces_existing_target_with_force(tmp_path):
    source = make_source(tmp_path)
    target = tmp_path / 'repo' / '.codex' / 'skills' / 'jlpt-study-pipeline'
    target.mkdir(parents=True)
    (target / 'old.txt').write_text('old\n', encoding='utf-8')

    skill_install.install_skill(source, target, force=True)

    assert (target / 'SKILL.md').exists()
    assert not (target / 'old.txt').exists()


def test_default_repo_target_prefers_parent_codex_dir(tmp_path):
    source = make_source(tmp_path / 'workspace')
    repo_root = tmp_path / 'workspace'
    (repo_root / '.codex').mkdir()

    target = skill_install.default_target(source, level='repo', repo_root=None, codex_home=None)

    assert target == repo_root / '.codex' / 'skills' / 'jlpt-study-pipeline'


def test_default_user_target_uses_codex_home(tmp_path):
    source = make_source(tmp_path)
    codex_home = tmp_path / 'codex-home'

    target = skill_install.default_target(source, level='user', repo_root=None, codex_home=codex_home)

    assert target == codex_home / 'skills' / 'jlpt-study-pipeline'


def test_uninstall_removes_existing_skill_target(tmp_path):
    target = tmp_path / '.codex' / 'skills' / 'jlpt-study-pipeline'
    target.mkdir(parents=True)
    (target / 'SKILL.md').write_text('x\n', encoding='utf-8')

    removed = skill_uninstall.uninstall_skill(target, missing_ok=False)

    assert removed == target
    assert not target.exists()


def test_uninstall_missing_ok_returns_target(tmp_path):
    target = tmp_path / '.codex' / 'skills' / 'jlpt-study-pipeline'

    removed = skill_uninstall.uninstall_skill(target, missing_ok=True)

    assert removed == target
