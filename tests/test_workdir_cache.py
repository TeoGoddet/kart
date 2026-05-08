"""Unit tests for AttachmentWorkdirIndex and WorkdirDiffCache.dirty_attachment_paths()."""
import os
import subprocess
from pathlib import Path
from unittest.mock import MagicMock

import pygit2
import pytest


def make_tidy_repo(workdir):
    """
    Set up a directory like a tidy-style kart repo:
    - workdir/.git -> workdir/.kart (pointer file)
    - workdir/.kart/ is a real git repo with bare=false (has a worktree)
    Returns a mock KartRepo suitable for AttachmentWorkdirIndex.
    """
    git_dir = workdir / ".kart"

    # Create a regular git repo in a temp location and move .git -> .kart
    env = os.environ.copy()
    env.pop("GIT_INDEX_FILE", None)  # Don't let kart's global override interfere

    subprocess.check_call(
        ["git", "init", str(workdir)],
        env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    dot_git = workdir / ".git"
    dot_git.rename(git_dir)
    # Create .git pointer file
    (workdir / ".git").write_text(f"gitdir: .kart\n")

    repo = MagicMock()
    repo.workdir_path = workdir
    repo.gitdir_file = lambda name: git_dir / name
    return repo


class TestAttachmentWorkdirIndex:
    def test_create_if_missing(self, tmp_path):
        from kart.workdir import AttachmentWorkdirIndex

        repo = make_tidy_repo(tmp_path)
        ai = AttachmentWorkdirIndex(repo)
        assert not ai.index_path.exists()

        ai.create_if_missing()
        assert ai.index_path.exists()

        # Second call should be a no-op
        ai.create_if_missing()
        assert ai.index_path.exists()

    def test_add_paths_to_index(self, tmp_path):
        from kart.workdir import AttachmentWorkdirIndex

        repo = make_tidy_repo(tmp_path)
        test_file = tmp_path / "LICENSE.txt"
        test_file.write_text("MIT License\n")

        ai = AttachmentWorkdirIndex(repo)
        ai.create_if_missing()
        ai.add_paths_to_index(["LICENSE.txt"])

        idx = pygit2.Index(str(ai.index_path))
        entries = list(idx)
        assert any(e.path == "LICENSE.txt" for e in entries)

    def test_git_diff_paths_empty_when_no_changes(self, tmp_path):
        from kart.workdir import AttachmentWorkdirIndex

        repo = make_tidy_repo(tmp_path)
        test_file = tmp_path / "LICENSE.txt"
        test_file.write_text("MIT License\n")

        ai = AttachmentWorkdirIndex(repo)
        ai.create_if_missing()
        ai.add_paths_to_index(["LICENSE.txt"])

        diff_paths = ai._git_diff_paths()
        assert diff_paths == []

    def test_git_diff_paths_detects_modification(self, tmp_path):
        from kart.workdir import AttachmentWorkdirIndex

        repo = make_tidy_repo(tmp_path)
        test_file = tmp_path / "LICENSE.txt"
        test_file.write_text("MIT License\n")

        ai = AttachmentWorkdirIndex(repo)
        ai.create_if_missing()
        ai.add_paths_to_index(["LICENSE.txt"])

        # Modify the file after indexing
        test_file.write_text("Modified!\n")

        diff_paths = ai._git_diff_paths()
        assert "LICENSE.txt" in diff_paths

    def test_git_ls_others_paths_detects_untracked(self, tmp_path):
        from kart.workdir import AttachmentWorkdirIndex

        repo = make_tidy_repo(tmp_path)
        ai = AttachmentWorkdirIndex(repo)
        ai.create_if_missing()

        untracked = tmp_path / "NOTES.txt"
        untracked.write_text("Notes\n")

        others = ai._git_ls_others_paths()
        assert "NOTES.txt" in others


class TestWorkdirDiffCache:
    def test_dirty_attachment_paths(self, tmp_path):
        from kart.workdir import AttachmentWorkdirIndex, WorkdirDiffCache

        repo = make_tidy_repo(tmp_path)
        test_file = tmp_path / "LICENSE.txt"
        test_file.write_text("Original\n")

        ai = AttachmentWorkdirIndex(repo)
        ai.create_if_missing()
        ai.add_paths_to_index(["LICENSE.txt"])

        test_file.write_text("Modified!\n")

        cache = WorkdirDiffCache(ai)
        dirty = cache.dirty_attachment_paths()
        assert "LICENSE.txt" in dirty
