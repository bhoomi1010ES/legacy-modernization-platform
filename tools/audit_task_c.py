import subprocess
import sys
from pathlib import Path

WORKTREE_PATH = Path("backend/repo_workspaces/phase6/aadd09e9-9381-46db-a4b8-d9b5c41fcf3a").resolve()
CANONICAL_REPO = Path("repo_workspaces/job_eb2bbaa9-90ee-4e9d-b340-5e025594126c").resolve()
EXPECTED_COMMIT = "531f76a56424cea4c2ebc773b8cd649536a7d8b0"
EXPECTED_BRANCH = "job/eb2bbaa9-90ee-4e9d-b340-5e025594126c/module/8a53e2d8-e298-5112-a9a7-cca8fe8cc3c3/attempt/4"

def run_git(repo_dir: Path, *args):
    res = subprocess.run(["git", "-C", str(repo_dir), *args], capture_output=True, text=True, check=True)
    return res.stdout.strip()

print("="*80)
print("TASK C: VERIFY GIT BRANCH, WORKTREE, BASE AND RESULT")
print("="*80)

print(f"1. Worktree Path: {WORKTREE_PATH}")
print(f"   Exists?: {WORKTREE_PATH.exists()}")
print(f"   Is Dir?: {WORKTREE_PATH.is_dir()}")

if WORKTREE_PATH.exists():
    wt_branch = run_git(WORKTREE_PATH, "branch", "--show-current")
    wt_head = run_git(WORKTREE_PATH, "rev-parse", "HEAD")
    print(f"   Active Branch: {wt_branch} (Matches expected?: {wt_branch == EXPECTED_BRANCH})")
    print(f"   HEAD Commit: {wt_head} (Matches expected?: {wt_head == EXPECTED_COMMIT})")

print(f"\n2. Canonical Repo: {CANONICAL_REPO}")
print(f"   Exists?: {CANONICAL_REPO.exists()}")

# Verify commit in canonical repo
commit_exists = run_git(CANONICAL_REPO, "cat-file", "-t", EXPECTED_COMMIT)
print(f"   Commit object type in git: {commit_exists}")

parent_commit = run_git(CANONICAL_REPO, "rev-parse", f"{EXPECTED_COMMIT}^")
print(f"   Parent/Base Commit: {parent_commit}")

commit_author = run_git(CANONICAL_REPO, "log", "-1", "--format=%an <%ae> at %ad", EXPECTED_COMMIT)
commit_msg = run_git(CANONICAL_REPO, "log", "-1", "--format=%B", EXPECTED_COMMIT)
print(f"   Commit Author/Date: {commit_author}")
print(f"   Commit Message: {commit_msg}")

diff_stat = run_git(CANONICAL_REPO, "diff", "--stat", f"{parent_commit}..{EXPECTED_COMMIT}")
print(f"\n3. Diff Stat:\n{diff_stat}")

changed_files = run_git(CANONICAL_REPO, "diff", "--name-only", f"{parent_commit}..{EXPECTED_COMMIT}").splitlines()
print(f"\n4. Changed Files ({len(changed_files)}):")
for f in changed_files:
    print(f"   - {f}")
    assert f.startswith("app/modules/app-utils_b30e84/"), f"File {f} is outside allowed target!"

full_diff = run_git(CANONICAL_REPO, "diff", f"{parent_commit}..{EXPECTED_COMMIT}")
print(f"\n5. Full Diff Size: {len(full_diff)} chars, {len(full_diff.splitlines())} lines")

# Secret & contamination check
forbidden = [".env", "aws", "token", "password", "secret", "private_key", "bearer"]
found_forbidden = []
for line in full_diff.splitlines():
    if line.startswith("+") and not line.startswith("+++"):
        low = line.lower()
        if any(w in low for w in ["sk-", "api_key", "password =", "secret ="]):
            found_forbidden.append(line)

print(f"   Secrets detected in diff?: {len(found_forbidden)} (Found: {found_forbidden})")
print(f"   All changed files strictly within app/modules/app-utils_b30e84?: True")

