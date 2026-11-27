#!/usr/bin/env python3
"""Reject commits that add Terraform plan or state files.

Plan files hold the input variables, tokens included, and the resource
attributes in plain text, and state files hold every managed attribute. Leak
scanners miss them: a plan is a zip archive under any name (tfplan, plan,
*.tfplan), which scanners skip unless the extension says archive. Files are
therefore recognized by their content, and every commit in the range is
checked, so that a file added and removed again within it is still caught.

Usage: artifacts.py <range>, where the range is understood by git rev-list.
"""

import io
import re
import subprocess
import sys
import zipfile

STATE_NAME = re.compile(r"\.tfstate(\.\d+)?(\.backup)?$")


def git(*args: str) -> bytes:
    return subprocess.run(["git", *args], check=True, capture_output=True).stdout


def is_plan(blob: bytes) -> bool:
    if not blob.startswith(b"PK"):
        return False
    try:
        with zipfile.ZipFile(io.BytesIO(blob)) as archive:
            return "tfplan" in archive.namelist()
    except zipfile.BadZipFile:
        return False


def is_state(path: str, blob: bytes) -> bool:
    if STATE_NAME.search(path):
        return True
    head = blob[:4096]
    return (
        head.lstrip().startswith(b"{")
        and b'"terraform_version"' in head
        and b'"lineage"' in head
    )


def offending(commit: str) -> list[tuple[str, str]]:
    names = git(
        "diff-tree",
        "--root",
        "--no-commit-id",
        "-r",
        "-z",
        "--diff-merges=first-parent",
        "--diff-filter=AMR",
        "--name-only",
        commit,
    )
    found = []
    for path in filter(None, names.decode("utf-8", "surrogateescape").split("\0")):
        blob = git("cat-file", "blob", f"{commit}:{path}")
        if is_plan(blob):
            found.append((path, "Terraform plan"))
        elif is_state(path, blob):
            found.append((path, "Terraform state"))
    return found


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__.strip().splitlines()[-1], file=sys.stderr)
        return 2
    commits = git("rev-list", sys.argv[1]).decode().split()
    failed = False
    for commit in commits:
        for path, kind in offending(commit):
            failed = True
            print(
                f"::error file={path}::{kind} file committed in {commit[:7]}. "
                "It can contain credentials in plain text: remove it from the "
                "history and rotate the credentials it held."
            )
    if not failed:
        print(f"No Terraform plan or state files in {len(commits)} commit(s).")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
