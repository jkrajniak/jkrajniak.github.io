#!/usr/bin/env python3
"""
Post-process existing Jekyll markdown posts to download external images.
Scans _posts/*.md for markdown image references (![...](http...)) and
downloads them locally to assets/images/posts/<slug>/.

Idempotent — re-running skips already-downloaded images.

Usage:
  uv run download_post_images.py --site-root ..
"""

import re
import sys
import time
import hashlib
import argparse
from pathlib import Path
from urllib.parse import urlparse

import httpx


def log(msg: str):
    print(msg, flush=True)


KNOWN_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg"}
IMG_PATTERN = re.compile(r"!\[([^\]]*)\]\(([^)]+)\)")
SLUG_FROM_FILENAME = re.compile(r"^\d{4}-\d{2}-\d{2}-(.+)\.md$")


def is_external_url(url: str) -> bool:
    return url.startswith("http://") or url.startswith("https://")


def resolve_local_name(url: str) -> str:
    parsed = urlparse(url)
    raw_name = parsed.path.strip("/").split("/")[-1] if parsed.path else "image"
    ext = Path(raw_name).suffix
    if not ext or ext not in KNOWN_IMAGE_EXTS:
        ext = ".png"
    url_hash = hashlib.md5(url.encode()).hexdigest()[:10]
    return f"{url_hash}{ext}"


def download_image(client: httpx.Client, url: str, dest_dir: Path) -> str | None:
    local_name = resolve_local_name(url)
    local_path = dest_dir / local_name

    if local_path.exists():
        return local_name

    short = url.split("/")[-1][:40]
    for attempt in range(3):
        try:
            resp = client.get(url, follow_redirects=True, timeout=30)
            if resp.status_code == 429:
                wait = max(int(resp.headers.get("retry-after", 0)), 60) * (attempt + 1)
                log(f"    Rate limited on {short}, cooling down {wait}s...")
                time.sleep(wait)
                continue
            resp.raise_for_status()
            dest_dir.mkdir(parents=True, exist_ok=True)
            local_path.write_bytes(resp.content)
            return local_name
        except (httpx.HTTPError, OSError) as e:
            if attempt < 2:
                time.sleep(5)
                continue
            log(f"    Failed: {short}: {e}")
            return None

    log(f"    Gave up after retries: {short}")
    return None


def extract_slug(filename: str) -> str:
    m = SLUG_FROM_FILENAME.match(filename)
    return m.group(1) if m else Path(filename).stem


def process_post(
    post_path: Path,
    assets_root: Path,
    client: httpx.Client,
    delay: float,
    dry_run: bool = False,
) -> tuple[int, int]:
    content = post_path.read_text(encoding="utf-8")
    slug = extract_slug(post_path.name)
    image_dir = assets_root / slug

    external_images = [
        (m.start(), m.group(0), m.group(1), m.group(2))
        for m in IMG_PATTERN.finditer(content)
        if is_external_url(m.group(2))
    ]

    if not external_images:
        return 0, 0

    downloaded, failed = 0, 0
    replacements: dict[str, str] = {}

    for i, (_, full_match, alt, url) in enumerate(external_images):
        if url in replacements:
            continue

        if dry_run:
            log(f"    [dry-run] Would download: {url}")
            downloaded += 1
            continue

        if i > 0:
            time.sleep(delay)

        local_name = download_image(client, url, image_dir)
        if local_name:
            new_path = f"/assets/images/posts/{slug}/{local_name}"
            replacements[url] = new_path
            downloaded += 1
        else:
            failed += 1

    if replacements and not dry_run:
        for old_url, new_path in replacements.items():
            content = content.replace(old_url, new_path)
        post_path.write_text(content, encoding="utf-8")

    return downloaded, failed


def main():
    parser = argparse.ArgumentParser(
        description="Download external images from existing Jekyll markdown posts"
    )
    parser.add_argument(
        "--site-root", default="..",
        help="Root of your Jekyll site (contains _posts/)",
    )
    parser.add_argument(
        "--delay", type=float, default=2.0,
        help="Delay in seconds between image downloads (default: 2.0)",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="List images that would be downloaded without actually downloading",
    )
    parser.add_argument(
        "--post", default=None,
        help="Process only a specific post file (e.g. 2020-04-28-my-post.md)",
    )
    args = parser.parse_args()

    site_root = Path(args.site_root)
    posts_dir = site_root / "_posts"
    assets_root = site_root / "assets" / "images" / "posts"

    if not posts_dir.exists():
        log(f"No _posts/ directory found at {posts_dir}")
        return

    if args.post:
        post_files = [posts_dir / args.post]
        if not post_files[0].exists():
            log(f"Post not found: {post_files[0]}")
            return
    else:
        post_files = sorted(posts_dir.glob("*.md"))

    if not post_files:
        log("No markdown files found.")
        return

    total_downloaded, total_failed, posts_updated = 0, 0, 0

    with httpx.Client() as client:
        for post_path in post_files:
            content = post_path.read_text(encoding="utf-8")
            has_external = bool(IMG_PATTERN.search(content) and
                                any(is_external_url(m.group(2))
                                    for m in IMG_PATTERN.finditer(content)))
            if not has_external:
                continue

            log(f"  {post_path.name}")
            downloaded, failed = process_post(
                post_path, assets_root, client, args.delay, args.dry_run,
            )
            total_downloaded += downloaded
            total_failed += failed
            if downloaded:
                posts_updated += 1

    log(f"\nDone!")
    action = "Would download" if args.dry_run else "Downloaded"
    log(f"  {action}: {total_downloaded} images across {posts_updated} posts")
    if total_failed:
        log(f"  Failed: {total_failed} (re-run to retry)")


if __name__ == "__main__":
    main()
