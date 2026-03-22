#!/usr/bin/env python3
"""
Fetch tags from live Medium pages and update Jekyll post front matter.

Reads the Medium export HTML files to find canonical URLs,
scrapes the live pages for tags, then updates the corresponding
_posts/ or _drafts/ markdown files.

Usage:
  uv run python add_medium_tags.py --medium-dir ../_medium/posts --site-root ..
"""

import re
import time
import argparse
from pathlib import Path
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup


def slugify(title: str) -> str:
    title = title.lower()
    title = re.sub(r"[^\w\s-]", "", title)
    title = re.sub(r"[\s_]+", "-", title)
    title = re.sub(r"^-+|-+$", "", title)
    return title


def extract_canonical_url(html_path: Path) -> str | None:
    with open(html_path, "r", encoding="utf-8") as f:
        soup = BeautifulSoup(f.read(), "html.parser")
    link = soup.find("a", class_="p-canonical")
    if link and link.get("href"):
        return link["href"]
    return None


def extract_title(html_path: Path) -> str | None:
    with open(html_path, "r", encoding="utf-8") as f:
        soup = BeautifulSoup(f.read(), "html.parser")
    h1 = soup.find("h1", class_="p-name") or soup.find("h1")
    return h1.get_text(strip=True) if h1 else None


def fetch_tags_from_medium(client: httpx.Client, url: str) -> list[str]:
    """Fetch the live Medium page and extract tags from /tag/ links."""
    try:
        resp = client.get(url, follow_redirects=True, timeout=30)
        resp.raise_for_status()
    except httpx.HTTPError as e:
        print(f"    Failed to fetch {url}: {e}")
        return []

    soup = BeautifulSoup(resp.text, "html.parser")
    tags = []
    seen = set()
    for a in soup.find_all("a", href=re.compile(r"medium\.com/tag/")):
        text = a.get_text(strip=True)
        parsed = urlparse(a["href"])
        tag_slug = parsed.path.strip("/").split("/")[-1] if parsed.path else ""
        if text and tag_slug and tag_slug not in seen:
            seen.add(tag_slug)
            tags.append(text)
    return tags


def find_matching_post(slug: str, posts_dir: Path, drafts_dir: Path) -> Path | None:
    for d in (posts_dir, drafts_dir):
        if not d.exists():
            continue
        for f in d.glob("*.md"):
            post_slug = re.sub(r"^\d{4}-\d{2}-\d{2}-", "", f.stem)
            if post_slug == slug:
                return f
    return None


def update_tags_in_post(post_path: Path, tags: list[str]) -> bool:
    content = post_path.read_text(encoding="utf-8")

    if not content.startswith("---"):
        return False

    parts = content.split("---", 2)
    if len(parts) < 3:
        return False

    front_matter = parts[1]
    body = parts[2]

    tags_yaml = "\n".join(f"  - {t}" for t in tags)
    new_tags_block = f"tags:\n{tags_yaml}"

    front_matter = re.sub(r"tags:\s*\[\s*\]", new_tags_block, front_matter)
    front_matter = re.sub(
        r"tags:\n(?:\s+-\s+.*\n)*",
        new_tags_block + "\n",
        front_matter,
    )

    new_content = f"---{front_matter}---{body}"
    post_path.write_text(new_content, encoding="utf-8")
    return True


def main():
    parser = argparse.ArgumentParser(description="Add tags to Medium-migrated Jekyll posts")
    parser.add_argument("--medium-dir", required=True, help="Path to Medium export posts/ folder")
    parser.add_argument("--site-root", default=".", help="Root of Jekyll site")
    parser.add_argument("--delay", type=float, default=2.0, help="Delay between requests (seconds)")
    parser.add_argument("--dry-run", action="store_true", help="Print tags without modifying files")
    args = parser.parse_args()

    medium_dir = Path(args.medium_dir)
    site_root = Path(args.site_root)
    posts_dir = site_root / "_posts"
    drafts_dir = site_root / "_drafts"

    html_files = sorted(medium_dir.glob("*.html"))
    if not html_files:
        print(f"No HTML files found in {medium_dir}")
        return

    print(f"Found {len(html_files)} Medium export files.\n")

    updated, skipped, no_tags, errors = 0, 0, 0, 0

    with httpx.Client(
        headers={"User-Agent": "Mozilla/5.0 (compatible; blog-migrator/1.0)"},
    ) as client:
        for html_file in html_files:
            title = extract_title(html_file)
            if not title:
                print(f"  ? {html_file.name} — no title found, skipping")
                skipped += 1
                continue

            slug = slugify(title)
            post_path = find_matching_post(slug, posts_dir, drafts_dir)
            if not post_path:
                print(f"  ~ {html_file.name} — no matching post for slug '{slug}', skipping")
                skipped += 1
                continue

            canonical_url = extract_canonical_url(html_file)
            if not canonical_url:
                print(f"  ? {html_file.name} — no canonical URL, skipping")
                skipped += 1
                continue

            tags = fetch_tags_from_medium(client, canonical_url)
            time.sleep(args.delay)

            if not tags:
                print(f"  - [{slug}] no tags found on {canonical_url}")
                no_tags += 1
                continue

            tag_str = ", ".join(tags)
            if args.dry_run:
                print(f"  * [{slug}] tags: {tag_str}")
            else:
                if update_tags_in_post(post_path, tags):
                    print(f"  + [{slug}] -> {tag_str}")
                    updated += 1
                else:
                    print(f"  x [{slug}] failed to update {post_path.name}")
                    errors += 1

    print(f"\nDone!")
    if args.dry_run:
        print("  (dry run — no files modified)")
    else:
        print(f"  {updated} posts updated with tags")
    if skipped:
        print(f"  {skipped} skipped")
    if no_tags:
        print(f"  {no_tags} posts had no tags on Medium")
    if errors:
        print(f"  {errors} errors")


if __name__ == "__main__":
    main()
