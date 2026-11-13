"""Deterministic helpers for control.skill. Python 3.9+, Git; gh for remote operations."""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys

class ControlError(Exception):
    pass

def run(args, cwd, binary=False, ok=(0,)):
    p = subprocess.run(args, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if p.returncode not in ok:
        # Do not echo credentials, URLs or subprocess output.
        raise ControlError("Command failed: " + args[0] + " " + args[1] + " (exit " + str(p.returncode) + ")")
    return p.stdout if binary else p.stdout.decode("utf-8", errors="strict").strip()

def git(root, *args, binary=False):
    return run(["git", *args], root, binary=binary)

def path_ok(value):
    if not isinstance(value, str) or not value or "\\" in value or ":" in value:
        return False
    p = PurePosixPath(value)
    return not p.is_absolute() and all(x not in ("", ".", "..") for x in value.split("/"))

def blocked(path):
    parts = path.lower().split("/")
    bad_dirs = {".git", ".ssh", ".aws", ".azure", ".venv", "venv", "node_modules",
                "__pycache__", ".cache", ".docx_work"}
    base = parts[-1]
    return (bool(set(parts) & bad_dirs) or base.startswith(("~$", ".env"))
            or base in {"auth.json", "credentials", "credentials.json", "id_rsa", "id_ed25519"}
            or base.endswith((".pem", ".key", ".pfx", ".p12", ".pyc", ".tmp", ".log")))

def allowed(path, cfg):
    if not path_ok(path) or blocked(path):
        return False
    return any(path == pat or (pat.endswith("/**") and path.startswith(pat[:-2]))
               for pat in cfg["allow"])

def load(root):
    root = Path(root).resolve()
    f = root / ".control" / "project.json"
    if f.is_symlink() or f.parent.is_symlink():
        raise ControlError("Configuration cannot be a symlink")
    cfg = json.loads(f.read_text(encoding="utf-8-sig"))
    if cfg.get("schema_version") != 1 or cfg.get("enabled") is not True:
        raise ControlError("Project not enabled or unsupported configuration")
    if cfg.get("mode") not in ("local", "cloud"):
        raise ControlError("Invalid mode")
    if not cfg.get("allow"):
        raise ControlError("Empty allowlist")
    for pat in cfg["allow"]:
        base = pat[:-3] if isinstance(pat, str) and pat.endswith("/**") else pat
        if not path_ok(base) or "*" in base or "?" in base:
            raise ControlError("Invalid allowlist path")
    top = Path(git(root, "rev-parse", "--show-toplevel")).resolve()
    if top != root:
        raise ControlError("Root must be the independent repository root")
    return root, cfg

def credential_check(data):
    # Heuristics, not a proof. Binary document content still requires source review.
    patterns = [rb"-----BEGIN [A-Z ]*PRIVATE KEY-----",
                rb"(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,})",
                rb"AKIA[0-9A-Z]{16}",
                rb"sk-(?:proj-)?[A-Za-z0-9_-]{32,}"]
    if any(re.search(p, data) for p in patterns):
        raise ControlError("Possible credential detected; file content not printed")
    if data.startswith(b"version https://git-lfs.github.com/spec/v1"):
        raise ControlError("LFS pointer requires separate object verification")
    if len(data) > 50 * 1024 * 1024:
        raise ControlError("File exceeds conservative 50 MiB upload limit; review storage method")

def safe_file(root, rel):
    p = root / rel
    for parent in [p, *p.parents]:
        if parent == root:
            break
        if parent.is_symlink() or (hasattr(parent, "is_junction") and parent.is_junction()):
            raise ControlError("Links/junctions are not eligible: " + rel)
    try:
        p.resolve().relative_to(root)
    except ValueError:
        raise ControlError("File escapes project")
    return p

def candidates(root):
    raw = git(root, "ls-files", "-z", "--cached", "--others", "--exclude-standard", binary=True)
    return sorted(set(s.decode("utf-8") for s in raw.split(b"\0") if s))

def history(root, cfg):
    refs = git(root, "rev-list", "--all").splitlines()
    seen_trees, seen_blobs = set(), set()
    for commit in refs:
        tree = git(root, "rev-parse", commit + "^{tree}")
        if tree in seen_trees:
            continue
        seen_trees.add(tree)
        for record in git(root, "ls-tree", "-r", "-z", commit, binary=True).split(b"\0"):
            if not record:
                continue
            meta, raw_path = record.split(b"\t", 1)
            mode, typ, oid = meta.decode().split()
            rel = raw_path.decode("utf-8")
            if mode not in ("100644", "100755") or typ != "blob":
                raise ControlError("History includes link/submodule: " + rel)
            if not allowed(rel, cfg):
                raise ControlError("History contains excluded path: " + rel)
            if oid not in seen_blobs:
                size = int(git(root, "cat-file", "-s", oid))
                if size > 50 * 1024 * 1024:
                    raise ControlError("Oversized historical blob: " + rel)
                credential_check(git(root, "cat-file", "blob", oid, binary=True))
                seen_blobs.add(oid)
    return {"commits": len(refs), "blobs": len(seen_blobs)}

def inspect(root, cfg, with_history=False):
    selected, excluded = [], []
    for rel in candidates(root):
        if not allowed(rel, cfg):
            excluded.append(rel)
            continue
        p = safe_file(root, rel)
        if p.exists():
            if not p.is_file():
                raise ControlError("Not a regular file: " + rel)
            data = p.read_bytes()
            credential_check(data)
            selected.append({"path": rel, "bytes": len(data)})
    result = {"eligible": selected, "excluded": excluded,
              "bytes": sum(x["bytes"] for x in selected)}
    if with_history:
        result["history"] = history(root, cfg)
    return result

def checkpoint(root, cfg, message, paths=None):
    if not message.strip():
        raise ControlError("Commit message required")
    if not paths:
        raise ControlError("Explicit task-owned paths required; manual edits are opt-in")
    paths = sorted(set(paths))
    for rel in paths:
        if not allowed(rel, cfg):
            raise ControlError("Selected path outside approved scope: " + rel)
        p = safe_file(root, rel)
        if p.exists():
            if not p.is_file():
                raise ControlError("Select individual files, not directories: " + rel)
            credential_check(p.read_bytes())
    # Never absorb pre-staged out-of-scope files.
    staged = git(root, "diff", "--cached", "--name-only", "-z", binary=True)
    for rel in staged.split(b"\0"):
        if rel and rel.decode() not in paths:
            raise ControlError("Staged file not selected for this task; preserve index and review")
    # Literal pathspecs avoid treating brackets or wildcards in real filenames as patterns.
    for pos in range(0, len(paths), 100):
        git(root, "add", "-A", "--", *[":(literal)" + p for p in paths[pos:pos+100]])
    diff = git(root, "diff", "--cached", "--name-only")
    if not diff:
        return {"status": "unchanged"}
    git(root, "commit", "-m", message)
    return {"status": "saved", "commit": git(root, "rev-parse", "HEAD")}

def remote_info(root, cfg):
    if cfg["mode"] != "cloud":
        raise ControlError("Local mode forbids remote actions")
    url = cfg.get("remote") or ""
    m = re.fullmatch(r"https://github\.com/([A-Za-z0-9-]+)/([A-Za-z0-9_.-]+?)(?:\.git)?", url)
    if not m:
        raise ControlError("Expected credential-free GitHub HTTPS URL")
    if git(root, "remote", "get-url", "origin").removesuffix(".git") != url.removesuffix(".git"):
        raise ControlError("Origin differs from configured repository")
    run(["gh", "auth", "status"], root)
    repo = m.group(1) + "/" + m.group(2)
    info = json.loads(run(["gh", "repo", "view", repo, "--json", "nameWithOwner,isPrivate"], root))
    if info.get("isPrivate") is not True or info.get("nameWithOwner", "").lower() != repo.lower():
        raise ControlError("Repository identity/privacy verification failed")
    branch = git(root, "symbolic-ref", "--quiet", "--short", "HEAD")
    return branch

def verify_remote(root, cfg):
    branch = remote_info(root, cfg)
    head = git(root, "rev-parse", "HEAD")
    line = git(root, "ls-remote", "--exit-code", "origin", "refs/heads/" + branch)
    if line.split()[0] != head:
        raise ControlError("Remote head does not match local head")
    tags = git(root, "tag", "--list", "control-final-*").splitlines()
    for tag in tags:
        value = git(root, "rev-parse", "refs/tags/" + tag)
        remote = git(root, "ls-remote", "--exit-code", "origin", "refs/tags/" + tag)
        if remote.split()[0] != value:
            raise ControlError("Final tag not synchronized")
    return {"status": "github-synced", "commit": head, "branch": branch, "final_tags": tags}

def sync(root, cfg):
    branch = remote_info(root, cfg)
    inspect(root, cfg, True)
    # Push only committed HEAD. Unrelated manual working-tree edits stay local.
    git(root, "push", "--", "origin", "HEAD:refs/heads/" + branch)
    for tag in git(root, "tag", "--list", "control-final-*").splitlines():
        git(root, "push", "--", "origin", "refs/tags/" + tag)
    return verify_remote(root, cfg)

def cleanup_preview(root, cfg, requested=False):
    if not requested:
        return {"status": "disabled", "deletes_nothing": True,
                "required_next": "User must explicitly request cleanup for this invocation"}
    blockers = []
    if not cfg.get("completed"):
        blockers.append("Project not explicitly completed")
    if git(root, "status", "--porcelain"):
        blockers.append("Uncommitted or untracked files require review")
    ignored = git(root, "ls-files", "--others", "--ignored", "--exclude-standard", "-z", binary=True)
    if ignored:
        blockers.append("Ignored files need manual review before any deletion")
    outputs = []
    for rel in cfg.get("deliverables", []):
        if not allowed(rel, cfg):
            raise ControlError("Deliverable outside approved scope")
        p = safe_file(root, rel)
        if not p.is_file():
            raise ControlError("Missing deliverable: " + rel)
        git(root, "ls-files", "--error-unmatch", "--", ":(literal)" + rel)
        outputs.append({"path": rel, "sha256": hashlib.sha256(p.read_bytes()).hexdigest()})
    if not outputs:
        blockers.append("No final deliverables")
    if cfg["mode"] == "cloud":
        proof = verify_remote(root, cfg)
        if not proof["final_tags"]:
            blockers.append("No synchronized final tag")
    else:
        blockers.append("Local-only mode: retain Git history")
    return {"deletes_nothing": True, "owned_workspace": cfg.get("owned_workspace") is True,
            "blockers": blockers, "deliverables": outputs,
            "required_next": "Verify external final export, review ALL files, archive remote, then bounded host cleanup"}

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root", required=True)
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("inspect"); s.add_argument("--history", action="store_true")
    s = sub.add_parser("checkpoint"); s.add_argument("--message", required=True)
    s.add_argument("--paths", nargs="+", required=True)
    s = sub.add_parser("cleanup-preview")
    s.add_argument("--requested", action="store_true", help="Only after explicit user cleanup request")
    for name in ["sync", "verify-remote", "handoff"]:
        sub.add_parser(name)
    a = p.parse_args()
    try:
        root, cfg = load(a.root)
        if a.cmd == "inspect":
            result = inspect(root, cfg, a.history)
        elif a.cmd == "checkpoint":
            result = checkpoint(root, cfg, a.message, a.paths)
        elif a.cmd == "sync":
            result = sync(root, cfg)
        elif a.cmd == "verify-remote":
            result = verify_remote(root, cfg)
        elif a.cmd == "cleanup-preview":
            result = cleanup_preview(root, cfg, a.requested)
        else:
            result = {"mode": cfg["mode"], "repository": cfg.get("remote"),
                      "commit": git(root, "rev-parse", "HEAD"),
                      "read_first": ["AGENTS.md", "PROJECT_STATE.md", ".agents/skills/control/SKILL.md"],
                      "cloud": cfg.get("cloud", {})}
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except (ControlError, OSError, ValueError, KeyError) as e:
        print(json.dumps({"error": str(e)}, ensure_ascii=False), file=sys.stderr)
        return 2
    return 0

if __name__ == "__main__":
    sys.exit(main())

