#!/usr/bin/env python3
"""Create safe draft releases, remove internal assets and enforce retention."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import tempfile
from pathlib import Path


TAG_PREFIX = "maps-"


def gh(command: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(["gh", *command], text=True, capture_output=True)
    if check and result.returncode:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip())
    return result


def get_release(repo: str, tag: str) -> dict | None:
    result = gh(["api", f"repos/{repo}/releases/tags/{tag}"], check=False)
    if not result.returncode:
        return json.loads(result.stdout)
    releases = json.loads(gh(["api", f"repos/{repo}/releases?per_page=100"]).stdout)
    return next((release for release in releases if release["tag_name"] == tag), None)


def delete_release(repo: str, release: dict) -> None:
    gh(["api", "--method", "DELETE", f"repos/{repo}/releases/{release['id']}"])
    gh(
        ["api", "--method", "DELETE", f"repos/{repo}/git/refs/tags/{release['tag_name']}"],
        check=False,
    )


def release_assets(repo: str, release_id: int) -> list[dict]:
    assets: list[dict] = []
    page = 1
    while True:
        batch = json.loads(
            gh(
                [
                    "api",
                    f"repos/{repo}/releases/{release_id}/assets?per_page=100&page={page}",
                ]
            ).stdout
        )
        assets.extend(batch)
        if len(batch) < 100:
            return assets
        page += 1


def write_output(path: str | None, key: str, value: str) -> None:
    print(f"{key}={value}")
    if path:
        with Path(path).open("a", encoding="utf-8") as output:
            output.write(f"{key}={value}\n")


def prepare(args: argparse.Namespace) -> None:
    existing = get_release(args.repo, args.tag)
    if existing and not existing.get("draft"):
        write_output(args.github_output, "skip", "true")
        return
    if existing:
        delete_release(args.repo, existing)
    notes = (
        f"Automated regional PMTiles build from OpenFreeMap `{args.ofm_version}`.\n\n"
        "This release remains a draft until all shards and checksums pass."
    )
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False) as handle:
        handle.write(notes)
        notes_path = handle.name
    try:
        gh(
            [
                "release",
                "create",
                args.tag,
                "--repo",
                args.repo,
                "--target",
                args.target,
                "--draft",
                "--title",
                f"Regional maps {args.ofm_version}",
                "--notes-file",
                notes_path,
            ]
        )
    finally:
        Path(notes_path).unlink(missing_ok=True)
    write_output(args.github_output, "skip", "false")


def cleanup(args: argparse.Namespace) -> None:
    existing = get_release(args.repo, args.tag)
    if existing and existing.get("draft"):
        delete_release(args.repo, existing)
        print(f"deleted incomplete draft {args.tag}")


def remove_fragments(args: argparse.Namespace) -> None:
    existing = get_release(args.repo, args.tag)
    if not existing:
        raise ValueError(f"release {args.tag} not found")
    assets = release_assets(args.repo, existing["id"])
    for asset in assets:
        if asset["name"].startswith("manifest-shard-"):
            gh(["api", "--method", "DELETE", f"repos/{args.repo}/releases/assets/{asset['id']}"])
            print(f"deleted internal asset {asset['name']}")


def prune(args: argparse.Namespace) -> None:
    releases = json.loads(gh(["api", f"repos/{args.repo}/releases?per_page=100"]).stdout)
    published = sorted(
        (
            release
            for release in releases
            if release["tag_name"].startswith(TAG_PREFIX) and not release["draft"]
        ),
        key=lambda release: release.get("published_at") or "",
        reverse=True,
    )
    for release in published[args.keep :]:
        delete_release(args.repo, release)
        print(f"pruned {release['tag_name']}")


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser()
    commands = root.add_subparsers(dest="command", required=True)
    prepare_parser = commands.add_parser("prepare")
    prepare_parser.add_argument("--repo", required=True)
    prepare_parser.add_argument("--tag", required=True)
    prepare_parser.add_argument("--target", required=True)
    prepare_parser.add_argument("--ofm-version", required=True)
    prepare_parser.add_argument("--github-output", default=os.environ.get("GITHUB_OUTPUT"))
    prepare_parser.set_defaults(handler=prepare)
    cleanup_parser = commands.add_parser("cleanup")
    cleanup_parser.add_argument("--repo", required=True)
    cleanup_parser.add_argument("--tag", required=True)
    cleanup_parser.set_defaults(handler=cleanup)
    fragment_parser = commands.add_parser("remove-fragments")
    fragment_parser.add_argument("--repo", required=True)
    fragment_parser.add_argument("--tag", required=True)
    fragment_parser.set_defaults(handler=remove_fragments)
    prune_parser = commands.add_parser("prune")
    prune_parser.add_argument("--repo", required=True)
    prune_parser.add_argument("--keep", type=int, default=2)
    prune_parser.set_defaults(handler=prune)
    return root


def main() -> int:
    args = parser().parse_args()
    args.handler(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
