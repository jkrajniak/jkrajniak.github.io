#!/usr/bin/env python3
"""
dev.to → Jekyll Markdown Migrator
-----------------------------------
Uses the dev.to public API — no authentication needed for your own public posts.
Just provide your dev.to username.

Usage:
  uv run migrate_devto.py --username YOUR_USERNAME --output ..

Optional: if you have private/unpublished posts, get an API key from:
  dev.to → Settings → Account → DEV API Keys
and pass it with --api-key YOUR_KEY
"""

import re
import time
import hashlib
import argparse
from pathlib import Path
from datetime import datetime
from urllib.parse import urlparse

import httpx


DEVTO_CDN_HOSTS = {"dev-to-uploads.s3.amazonaws.com", "media2.dev.to"}
DEVTO_API = "https://dev.to/api"


def slugify(title: str) -> str:
    title = title.lower()
    title = re.sub(r"[^\w\s-]", "", title)
    title = re.sub(r"[\s_]+", "-", title)
    title = re.sub(r"^-+|-+$", "", title)
    return title


def fetch_articles(client: httpx.Client, username: str, api_key: str | None = None) -> list:
    headers = {"Accept": "application/vnd.forem.api-v1+json"}
    if api_key:
        headers["api-key"] = api_key

    articles = []
    page = 1

    while True:
        url = f"{DEVTO_API}/articles?username={username}&per_page=30&page={page}"
        resp = client.get(url, headers=headers)
        resp.raise_for_status()
        batch = resp.json()
        if not batch:
            break
        articles.extend(batch)
        print(f"  Fetched page {page} ({len(batch)} articles)")
        page += 1
        time.sleep(0.3)

    return articles


def fetch_article_body(client: httpx.Client, article_id: int, api_key: str | None = None) -> dict:
    headers = {"Accept": "application/vnd.forem.api-v1+json"}
    if api_key:
        headers["api-key"] = api_key

    url = f"{DEVTO_API}/articles/{article_id}"
    resp = client.get(url, headers=headers)
    resp.raise_for_status()
    return resp.json()


def download_image(client: httpx.Client, url: str, dest_dir: Path) -> str | None:
    parsed = urlparse(url)
    path_parts = parsed.path.strip("/").split("/")
    raw_name = path_parts[-1] if path_parts else "image"
    ext = Path(raw_name).suffix
    if not ext or ext not in {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg"}:
        ext = ".png"

    url_hash = hashlib.md5(url.encode()).hexdigest()[:10]
    local_name = f"{url_hash}{ext}"
    local_path = dest_dir / local_name

    if local_path.exists():
        return local_name

    for attempt in range(3):
        try:
            resp = client.get(url, follow_redirects=True, timeout=30)
            if resp.status_code == 429:
                wait = 30 * (attempt + 1)
                print(f"    Rate limited, waiting {wait}s...")
                time.sleep(wait)
                continue
            resp.raise_for_status()
            local_path.write_bytes(resp.content)
            return local_name
        except (httpx.HTTPError, OSError) as e:
            if attempt < 2:
                time.sleep(5)
                continue
            print(f"    Failed to download {url}: {e}")
            return None
    return None


def is_devto_image(url: str) -> bool:
    parsed = urlparse(url)
    return any(host in parsed.hostname for host in DEVTO_CDN_HOSTS) if parsed.hostname else False


def download_images_from_markdown(
    client: httpx.Client,
    body_md: str,
    slug: str,
    assets_root: Path,
) -> str:
    """Find all dev.to image URLs in markdown and download them locally."""
    img_pattern = re.compile(r"!\[([^\]]*)\]\(([^)]+)\)")
    image_dir = assets_root / slug
    url_map: dict[str, str] = {}
    downloaded = 0

    for match in img_pattern.finditer(body_md):
        url = match.group(2)
        if not is_devto_image(url):
            continue

        if url not in url_map:
            image_dir.mkdir(parents=True, exist_ok=True)
            local_name = download_image(client, url, image_dir)
            if local_name:
                url_map[url] = f"/assets/images/posts/{slug}/{local_name}"
                downloaded += 1
                time.sleep(0.5)
            else:
                url_map[url] = url

    for old_url, new_path in url_map.items():
        body_md = body_md.replace(old_url, new_path)

    if downloaded:
        print(f"    Downloaded {downloaded} images")

    return body_md


def existing_post_slugs(posts_dir: Path, drafts_dir: Path) -> set[str]:
    slugs = set()
    for d in (posts_dir, drafts_dir):
        if not d.exists():
            continue
        for f in d.glob("*.md"):
            name = f.stem
            slug = re.sub(r"^\d{4}-\d{2}-\d{2}-", "", name)
            slugs.add(slug)
    return slugs


def convert_article(
    article: dict,
    full_data: dict,
    client: httpx.Client,
    posts_dir: Path,
    drafts_dir: Path,
    assets_root: Path,
    skip_images: bool = False,
):
    title = article.get("title", "Untitled")
    published_at = article.get("published_at", "")
    tags = article.get("tag_list", [])
    if isinstance(tags, str):
        tags = [t.strip() for t in tags.split(",") if t.strip()]
    description = article.get("description", "")
    canonical_url = article.get("url", "")
    cover_image = article.get("cover_image", "")

    date_str = published_at[:10] if published_at else datetime.today().strftime("%Y-%m-%d")
    slug = slugify(title)

    body_md = full_data.get("body_markdown", "")

    if body_md.startswith("---"):
        parts = body_md.split("---", 2)
        body_md = parts[2].strip() if len(parts) >= 3 else body_md

    if not skip_images:
        body_md = download_images_from_markdown(client, body_md, slug, assets_root)

        if cover_image and is_devto_image(cover_image):
            image_dir = assets_root / slug
            image_dir.mkdir(parents=True, exist_ok=True)
            local_name = download_image(client, cover_image, image_dir)
            if local_name:
                cover_image = f"/assets/images/posts/{slug}/{local_name}"

    tags_yaml = "\n".join(f"  - {t}" for t in tags) if tags else ""
    tags_block = f"tags:\n{tags_yaml}" if tags_yaml else "tags: []"
    canonical_line = f'canonical_url: "{canonical_url}"' if canonical_url else ""
    cover_line = f'image: "{cover_image}"' if cover_image else ""

    front_matter_lines = [
        "---",
        "layout: post",
        f'title: "{title.replace(chr(34), chr(39))}"',
        f"date: {date_str}",
        f'description: "{description.replace(chr(34), chr(39))}"',
        tags_block,
    ]
    if canonical_line:
        front_matter_lines.append(canonical_line)
    if cover_line:
        front_matter_lines.append(cover_line)
    front_matter_lines.append("---")

    front_matter = "\n".join(front_matter_lines) + "\n\n"

    output_dir = posts_dir
    output_filename = f"{date_str}-{slug}.md"
    output_path = output_dir / output_filename

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(front_matter + body_md)

    print(f"  + [{date_str}] {title} -> {output_filename}")


def main():
    parser = argparse.ArgumentParser(description="Migrate dev.to posts to Jekyll markdown")
    parser.add_argument("--username", required=True, help="Your dev.to username")
    parser.add_argument("--output", default=".", help="Root of your Jekyll site (contains _posts/)")
    parser.add_argument("--api-key", default=None, help="Optional dev.to API key (for private posts)")
    parser.add_argument(
        "--skip-images",
        action="store_true",
        help="Skip image downloading (text only)",
    )
    parser.add_argument(
        "--skip-existing",
        action="store_true",
        help="Skip articles whose slug already exists in _posts/ or _drafts/",
    )
    args = parser.parse_args()

    output_root = Path(args.output)
    posts_dir = output_root / "_posts"
    drafts_dir = output_root / "_drafts"
    assets_root = output_root / "assets" / "images" / "posts"

    posts_dir.mkdir(parents=True, exist_ok=True)
    drafts_dir.mkdir(parents=True, exist_ok=True)
    assets_root.mkdir(parents=True, exist_ok=True)

    known_slugs = set()
    if args.skip_existing:
        known_slugs = existing_post_slugs(posts_dir, drafts_dir)
        if known_slugs:
            print(f"Found {len(known_slugs)} existing posts/drafts, will skip matches.\n")

    with httpx.Client() as client:
        print(f"Fetching articles for @{args.username}...\n")
        articles = fetch_articles(client, args.username, args.api_key)

        if not articles:
            print("No articles found.")
            return

        print(f"\nFound {len(articles)} articles. Downloading and converting...\n")

        converted, skipped, errors = 0, 0, 0
        for article in articles:
            slug = slugify(article.get("title", ""))
            if slug in known_slugs:
                print(f"  ~ [{slug}] already exists, skipping")
                skipped += 1
                continue

            try:
                full_data = fetch_article_body(client, article["id"], args.api_key)
                time.sleep(0.3)
                convert_article(
                    article, full_data, client, posts_dir, drafts_dir, assets_root,
                    skip_images=args.skip_images,
                )
                converted += 1
            except Exception as e:
                print(f"  x {article.get('title', article['id'])} -- ERROR: {e}")
                errors += 1

    print(f"\nDone! {converted} posts written to {posts_dir}/")
    if skipped:
        print(f"  {skipped} skipped (already exist)")
    if errors:
        print(f"  {errors} errors (check above)")


if __name__ == "__main__":
    main()
