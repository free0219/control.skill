"""Offline behavioral tests; never contacts GitHub or changes a real project."""
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("control", Path(__file__).with_name("control.py"))
c = importlib.util.module_from_spec(spec); spec.loader.exec_module(c)

class ControlTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="control-test-")
        self.root = Path(self.temp.name).resolve()
        self.assertEqual(self.root.parent, Path(tempfile.gettempdir()).resolve())
        c.run(["git", "init", "-b", "main"], self.root)
        c.git(self.root, "config", "user.name", "Control Test")
        c.git(self.root, "config", "user.email", "test@example.invalid")
        (self.root / ".control").mkdir()
        self.cfg = dict(schema_version=1, enabled=True, mode="local",
                        owned_workspace=True,
                        allow=[".control/project.json", "report.docx", "sources/**"],
                        deliverables=["report.docx"], remote=None, completed=False)
        self.savecfg()
        (self.root / "report.docx").write_bytes(b"original document bytes")
    def checkpoint(self, message, paths=None):
        selected = paths if paths is not None else [p for p in c.candidates(self.root) if c.allowed(p, self.cfg)]
        return c.checkpoint(self.root, self.cfg, message, selected)
    def test_manual_edits_not_absorbed(self):
        self.checkpoint("baseline")
        (self.root / "report.docx").write_bytes(b"manual edit")
        (self.root / "sources").mkdir()
        (self.root / "sources/task.txt").write_text("codex task")
        self.checkpoint("task", ["sources/task.txt"])
        self.assertEqual(c.git(self.root, "show", "HEAD:report.docx", binary=True), b"original document bytes")
        self.assertIn("report.docx", c.git(self.root, "status", "--porcelain"))
    def test_staged_manual_edit_preserved(self):
        self.checkpoint("baseline")
        (self.root / "report.docx").write_bytes(b"manual staged edit")
        c.git(self.root, "add", "report.docx")
        with self.assertRaises(c.ControlError):
            self.checkpoint("task", [".control/project.json"])
        self.assertEqual(c.git(self.root, "show", ":report.docx", binary=True), b"manual staged edit")
    def test_explicit_paths_required(self):
        with self.assertRaises(c.ControlError):
            c.checkpoint(self.root, self.cfg, "must not infer ownership")
    def test_cleanup_default_disabled(self):
        with patch.object(c, "git", side_effect=AssertionError("must not inspect for cleanup")):
            self.assertEqual(c.cleanup_preview(self.root, self.cfg)["status"], "disabled")
    def test_sync_preserves_manual_worktree_changes(self):
        self.checkpoint("baseline")
        (self.root / "report.docx").write_bytes(b"manual local change")
        actual_git = c.git
        pushed = []
        def fake_git(root, *args, **kwargs):
            if args[0] == "push":
                pushed.append(args)
                return ""
            if args[0] == "ls-remote":
                return actual_git(root, "rev-parse", "HEAD") + "\trefs/heads/main"
            return actual_git(root, *args, **kwargs)
        with patch.object(c, "remote_info", return_value="main"), patch.object(c, "git", side_effect=fake_git):
            self.assertEqual(c.sync(self.root, self.cfg)["status"], "github-synced")
        self.assertEqual(len(pushed), 1)
        self.assertEqual((self.root / "report.docx").read_bytes(), b"manual local change")
        self.assertEqual(c.git(self.root, "show", "HEAD:report.docx", binary=True), b"original document bytes")
    def test_legacy_cloud_push_without_environment(self):
        self.cfg.update(mode="cloud", cloud={"status": "not_verified"})
        self.savecfg(); self.checkpoint("legacy")
        _, cfg = c.load(self.root)
        result = c.handoff(self.root, cfg)
        self.assertTrue(result["cloud_push_enabled"])
        self.assertFalse(result["cloud_execution_enabled"])
        self.assertEqual(result["cloud"], self.cfg["cloud"])
        self.assertNotIn("cloud_execution", json.loads((self.root / ".control/project.json").read_text()))
    def test_execution_and_push_are_independent(self):
        self.checkpoint("baseline")
        for mode in ("local", "cloud"):
            for enabled in (False, True):
                self.cfg.update(mode=mode, cloud_execution={"enabled": enabled})
                self.savecfg()
                _, cfg = c.load(self.root)
                result = c.handoff(self.root, cfg)
                self.assertEqual(result["cloud_push_enabled"], mode == "cloud")
                self.assertEqual(result["cloud_execution_enabled"], enabled)
    def test_invalid_execution_flag_rejected(self):
        for value in (None, True, {}, {"enabled": "false"}, {"enabled": 1}):
            self.cfg["cloud_execution"] = value; self.savecfg()
            with self.assertRaises(c.ControlError):
                c.load(self.root)
    def test_target_branch_from_work_checkout(self):
        self.checkpoint("baseline")
        c.git(self.root, "checkout", "-b", "work")
        self.cfg.update(mode="cloud", remote="https://github.com/test-owner/test-repo", branch="main")
        c.git(self.root, "remote", "add", "origin", self.cfg["remote"])
        actual_run = c.run
        def fake_run(args, root, **kwargs):
            if args[:3] == ["gh", "repo", "view"]:
                return json.dumps({"nameWithOwner": "test-owner/test-repo", "isPrivate": True})
            if args[:3] == ["gh", "auth", "status"]:
                return ""
            return actual_run(args, root, **kwargs)
        with patch.object(c, "run", side_effect=fake_run):
            self.assertEqual(c.remote_info(self.root, self.cfg), "main")
            self.cfg.pop("branch")
            self.assertEqual(c.remote_info(self.root, self.cfg), "work")
    def test_invalid_target_branch_rejected(self):
        for value in ("", "../main", "main~1", 1):
            self.cfg["branch"] = value; self.savecfg()
            with self.assertRaises(c.ControlError):
                c.load(self.root)
    def test_push_and_verify_use_same_target(self):
        self.checkpoint("baseline")
        self.cfg.update(mode="cloud", branch="main", cloud_execution={"enabled": False})
        actual_git = c.git
        seen = []
        def fake_git(root, *args, **kwargs):
            if args[0] in ("push", "ls-remote"):
                seen.append(args)
                return actual_git(root, "rev-parse", "HEAD") + "\trefs/heads/main"
            return actual_git(root, *args, **kwargs)
        with patch.object(c, "remote_info", return_value="main"), patch.object(c, "git", side_effect=fake_git):
            self.assertEqual(c.sync(self.root, self.cfg)["branch"], "main")
        self.assertIn(("push", "--", "origin", "HEAD:refs/heads/main"), seen)
        self.assertIn(("ls-remote", "--exit-code", "origin", "refs/heads/main"), seen)
    def tearDown(self):
        # Git files can be readonly on Windows; TemporaryDirectory supports chmod retry.
        self.temp.cleanup()
    def savecfg(self):
        (self.root / ".control/project.json").write_text(json.dumps(self.cfg), encoding="utf-8")
    def test_checkpoint_and_restore_bytes(self):
        first = self.checkpoint("baseline")["commit"]
        (self.root / "report.docx").write_bytes(b"updated")
        self.checkpoint("update")
        restored = c.git(self.root, "show", first + ":report.docx", binary=True)
        self.assertEqual(restored, b"original document bytes")
        self.assertEqual(self.checkpoint("no change")["status"], "unchanged")
    def test_outside_files_not_staged(self):
        (self.root / "personal.txt").write_text("private")
        self.checkpoint("baseline")
        self.assertNotIn("personal.txt", c.git(self.root, "ls-files"))
    def test_staged_outside_rejected(self):
        (self.root / "personal.txt").write_text("private")
        c.git(self.root, "add", "personal.txt")
        with self.assertRaises(c.ControlError):
            self.checkpoint("must fail")
        self.assertIn("personal.txt", c.git(self.root, "diff", "--cached", "--name-only"))
    def test_history_excluded_even_after_removal(self):
        self.checkpoint("baseline")
        (self.root / "personal.txt").write_text("private")
        c.git(self.root, "add", "personal.txt"); c.git(self.root, "commit", "-m", "old")
        c.git(self.root, "rm", "personal.txt"); c.git(self.root, "commit", "-m", "removed")
        with self.assertRaises(c.ControlError):
            c.history(self.root, self.cfg)
    def test_historical_secret(self):
        self.checkpoint("baseline")
        (self.root / "report.docx").write_bytes(b"ghp_" + b"A" * 40)
        c.git(self.root, "add", "report.docx"); c.git(self.root, "commit", "-m", "bad")
        (self.root / "report.docx").write_bytes(b"clean")
        c.git(self.root, "add", "report.docx"); c.git(self.root, "commit", "-m", "clean")
        with self.assertRaises(c.ControlError):
            c.history(self.root, self.cfg)
    def test_local_cannot_sync(self):
        with patch.object(c, "run", side_effect=AssertionError("must not execute remote command")):
            with self.assertRaises(c.ControlError):
                c.remote_info(self.root, self.cfg)
    def test_paths_and_credentials(self):
        for path in ["../a", "/root/a", "C:/a", "sources/../a"]:
            self.assertFalse(c.allowed(path, self.cfg))
        for path in ["sources/.env", "sources/id_rsa", "sources/.git/config"]:
            self.assertFalse(c.allowed(path, self.cfg))
        with self.assertRaises(c.ControlError):
            c.credential_check(b"-----BEGIN " + b"PRIVATE KEY-----")
        with self.assertRaises(c.ControlError):
            c.credential_check(b"version https://git-lfs.github.com/spec/v1\n")
    def test_literal_filename(self):
        self.cfg["allow"].append("a[1].txt"); self.savecfg()
        (self.root / "a[1].txt").write_text("literal")
        (self.root / "a1.txt").write_text("not selected")
        self.checkpoint("literal")
        names = c.git(self.root, "ls-files").splitlines()
        self.assertIn("a[1].txt", names); self.assertNotIn("a1.txt", names)
    def test_cleanup_preserves_local_history(self):
        self.checkpoint("baseline")
        result = c.cleanup_preview(self.root, self.cfg, requested=True)
        self.assertTrue(result["deletes_nothing"])
        self.assertIn("Local-only mode: retain Git history", result["blockers"])
        self.assertTrue((self.root / ".git").is_dir())
    def test_nested_root_refused(self):
        nested = self.root / "sub"; (nested / ".control").mkdir(parents=True)
        (nested / ".control/project.json").write_text(json.dumps(self.cfg))
        with self.assertRaises(c.ControlError):
            c.load(nested)
    def test_public_remote_refused(self):
        self.cfg.update(mode="cloud", remote="https://github.com/test-owner/test-repo")
        def fake_run(args, root, **kwargs):
            if args[:3] == ["gh", "repo", "view"]:
                return json.dumps({"nameWithOwner": "test-owner/test-repo", "isPrivate": False})
            return ""
        with patch.object(c, "git", return_value=self.cfg["remote"]), patch.object(c, "run", side_effect=fake_run):
            with self.assertRaises(c.ControlError):
                c.remote_info(self.root, self.cfg)
    def test_mismatching_remote_commit(self):
        def fake_git(root, *args, **kwargs):
            return "a" * 40 if args[0] == "rev-parse" else "b" * 40 + "\trefs/heads/main"
        with patch.object(c, "remote_info", return_value="main"), patch.object(c, "git", side_effect=fake_git):
            with self.assertRaises(c.ControlError):
                c.verify_remote(self.root, self.cfg)

if __name__ == "__main__":
    unittest.main(verbosity=2)

