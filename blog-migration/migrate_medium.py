#!/usr/bin/env python3
"""
Medium → Jekyll Markdown Migrator
-----------------------------------
Medium lets you export your data at:
  Settings → Security → Export content
You'll get a .zip. Extract it — your posts are in the `posts/` folder as HTML files.

Published posts  → <output>/_posts/
Draft posts      → <output>/_drafts/
Images           → <output>/assets/images/posts/<slug>/

Usage:
  pip install beautifulsoup4 markdownify httpx
  python migrate_medium.py --input ./medium-export/posts --output ./my-blog

Image downloads are idempotent — re-running skips already-downloaded images.
Medium CDN rate-limits aggressively; use --delay to slow down, or --skip-images
to migrate text first and download images on subsequent runs.
"""

import re
import time
import argparse
import hashlib
from pathlib import Path
from datetime import datetime
from urllib.parse import urlparse

try:
    from bs4 import BeautifulSoup
    from markdownify import markdownify as md
    import httpx
except ImportError:
    print("Missing dependencies. Run: pip install beautifulsoup4 markdownify httpx")
    raise


MEDIUM_CDN_HOST = "cdn-images-1.medium.com"
INITIAL_DELAY = 5.0


class ImageDownloader:
    """Handles downloading images with adaptive throttling to avoid 429s."""

    def __init__(self, client: httpx.Client, assets_root: Path):
        self.client = client
        self.assets_root = assets_root
        self.delay = INITIAL_DELAY
        self.total_downloaded = 0
        self.total_cached = 0
        self.total_failed = 0

    def _resolve_local_path(self, url: str, dest_dir: Path) -> tuple[str, Path]:
        parsed = urlparse(url)
        path_parts = parsed.path.strip("/").split("/")
        raw_name = path_parts[-1] if path_parts else "image"
        ext = Path(raw_name).suffix
        if not ext or ext not in {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg"}:
            ext = ".png"
        url_hash = hashlib.md5(url.encode()).hexdigest()[:10]
        local_name = f"{url_hash}{ext}"
        return local_name, dest_dir / local_name

    def download_one(self, url: str, dest_dir: Path) -> str | None:
        local_name, local_path = self._resolve_local_path(url, dest_dir)

        if local_path.exists():
            self.total_cached += 1
            return local_name

        short_name = url.split("/")[-1]
        for attempt in range(3):
            try:
                resp = self.client.get(url, follow_redirects=True, timeout=30)
                if resp.status_code == 429:
                    retry_after = int(resp.headers.get("retry-after", 0))
                    wait = max(retry_after, 120) * (attempt + 1)
                    self.delay = max(self.delay, 10)
                    print(f"    ⏳ Rate limited on {short_name}, cooling down {wait}s...")
                    time.sleep(wait)
                    continue
                resp.raise_for_status()
                local_path.write_bytes(resp.content)
                self.total_downloaded += 1
                return local_name
            except (httpx.HTTPError, OSError) as e:
                if attempt < 2:
                    time.sleep(10)
                    continue
                print(f"    ⚠ Failed: {short_name}: {e}")
                self.total_failed += 1
                return None
        self.total_failed += 1
        print(f"    ⚠ Gave up after retries: {short_name}")
        return None

    def download_for_post(self, soup: BeautifulSoup, slug: str) -> dict[str, str]:
        image_dir = self.assets_root / slug
        url_map: dict[str, str] = {}

        imgs = soup.find_all("img", src=re.compile(re.escape(MEDIUM_CDN_HOST)))
        if not imgs:
            return url_map

        image_dir.mkdir(parents=True, exist_ok=True)

        for i, img in enumerate(imgs):
            src = img["src"]
            if i > 0:
                time.sleep(self.delay)
            local_name = self.download_one(src, image_dir)
            if local_name:
                url_map[src] = f"/assets/images/posts/{slug}/{local_name}"

        return url_map

    def summary(self) -> str:
        parts = []
        if self.total_downloaded:
            parts.append(f"{self.total_downloaded} downloaded")
        if self.total_cached:
            parts.append(f"{self.total_cached} cached")
        if self.total_failed:
            parts.append(f"{self.total_failed} failed")
        return ", ".join(parts) if parts else "no images"


def slugify(title: str) -> str:
    title = title.lower()
    title = re.sub(r"[^\w\s-]", "", title)
    title = re.sub(r"[\s_]+", "-", title)
    title = re.sub(r"^-+|-+$", "", title)
    return title


def extract_date_from_filename(filename: str) -> str | None:
    """Medium export filenames start with a date like 2023-04-12_..."""
    match = re.match(r"(\d{4}-\d{2}-\d{2})", filename)
    return match.group(1) if match else None


def extract_date_from_html(soup: BeautifulSoup) -> str | None:
    """Published posts have <time class="dt-published" datetime="...">."""
    time_tag = soup.find("time", class_="dt-published")
    if not time_tag:
        return None
    dt_str = time_tag.get("datetime", "")
    if not dt_str:
        return None
    try:
        return datetime.fromisoformat(dt_str.replace("Z", "+00:00")).strftime("%Y-%m-%d")
    except ValueError:
        return None


def extract_date(soup: BeautifulSoup, filename: str) -> str:
    return (
        extract_date_from_html(soup)
        or extract_date_from_filename(filename)
        or datetime.today().strftime("%Y-%m-%d")
    )


def is_draft(soup: BeautifulSoup, filename: str) -> bool:
    """
    Detect drafts via two signals:
    1. Medium draft filenames start with 'draft_'
    2. Published posts have an <a class="p-canonical"> link in the footer — drafts don't
    """
    if filename.lower().startswith("draft_"):
        return True
    canonical = soup.find("a", class_="p-canonical")
    if canonical and canonical.get("href", ""):
        return False
    return True


MIN_BODY_LENGTH = 500


def is_comment(soup: BeautifulSoup) -> bool:
    """Medium exports comments/responses alongside real posts.
    Comments are short texts with no images or headings."""
    body_section = soup.find("section", attrs={"data-field": "body"})
    if not body_section:
        return False
    has_images = bool(body_section.find("img"))
    has_headings = bool(body_section.find(re.compile(r"^h[2-6]$")))
    text = body_section.get_text(strip=True)
    if not has_images and not has_headings and len(text) < MIN_BODY_LENGTH:
        return True
    return False


def convert_post(
    html_path: Path,
    posts_dir: Path,
    drafts_dir: Path,
    downloader: ImageDownloader | None,
):
    with open(html_path, "r", encoding="utf-8") as f:
        soup = BeautifulSoup(f.read(), "html.parser")

    if is_comment(soup):
        print(f"  ⊘ [comment] {html_path.name} — skipped")
        return None

    draft = is_draft(soup, html_path.name)

    # Title — Medium uses <h1 class="p-name"> in the <header>
    title_tag = soup.find("h1", class_="p-name")
    if not title_tag:
        title_tag = soup.find("h1")
    title = title_tag.get_text(strip=True) if title_tag else html_path.stem
    if title_tag:
        title_tag.decompose()

    # Subtitle — Medium puts it in <section data-field="subtitle">
    subtitle_section = soup.find("section", attrs={"data-field": "subtitle"})
    description = subtitle_section.get_text(strip=True) if subtitle_section else ""
    if subtitle_section:
        subtitle_section.decompose()

    # Tags — Medium tag links follow the pattern /tag/<tagname>
    tags = []
    for a in soup.select("a[href*='/tag/']"):
        text = a.get_text(strip=True)
        if text:
            tags.append(text)

    slug = slugify(title)

    # Download images before markdown conversion
    url_map = downloader.download_for_post(soup, slug) if downloader else {}

    # Rewrite image src attributes in the HTML before converting to markdown
    for old_url, new_path in url_map.items():
        for img in soup.find_all("img", src=old_url):
            img["src"] = new_path

    # Main content — Medium puts article body in <section data-field="body">
    body_section = soup.find("section", attrs={"data-field": "body"})
    article = body_section or soup.find("article") or soup.find("body")
    body_html = str(article) if article else str(soup)

    body_md = md(body_html, heading_style="ATX", bullets="-")
    body_md = re.sub(r"\n{3,}", "\n\n", body_md).strip()

    # Also remove the duplicate title that Medium puts as an <h3> graf--title
    body_md = re.sub(
        r"^###\s+" + re.escape(title) + r"\s*\n+", "", body_md, count=1
    )

    date_str = extract_date(soup, html_path.name)
    tags_yaml = "\n".join(f"  - {t}" for t in tags) if tags else ""
    tags_block = f"tags:\n{tags_yaml}" if tags_yaml else "tags: []"

    front_matter = f"""---
layout: post
title: "{title.replace('"', "'")}"
date: {date_str}
description: "{description.replace('"', "'")}"
{tags_block}
---

"""

    if draft:
        output_dir = drafts_dir
        output_filename = f"{slug}.md"
    else:
        output_dir = posts_dir
        output_filename = f"{date_str}-{slug}.md"

    output_path = output_dir / output_filename

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(front_matter + body_md)

    label = "DRAFT" if draft else "post"
    n_images = len(url_map)
    img_info = f" ({n_images} images)" if n_images else ""
    print(f"  ✓ [{label}] {html_path.name} → {output_filename}{img_info}")

    return draft


def main():
    parser = argparse.ArgumentParser(description="Migrate Medium export to Jekyll posts")
    parser.add_argument("--input", required=True, help="Path to Medium export posts/ folder")
    parser.add_argument("--output", default=".", help="Root of your Jekyll site (contains _posts/)")
    parser.add_argument(
        "--skip-images", action="store_true",
        help="Skip image downloading (migrate text only, images can be downloaded on re-run)",
    )
    parser.add_argument(
        "--delay", type=float, default=INITIAL_DELAY,
        help=f"Delay in seconds between image downloads (default: {INITIAL_DELAY})",
    )
    args = parser.parse_args()

    input_dir = Path(args.input)
    posts_dir = Path(args.output) / "_posts"
    drafts_dir = Path(args.output) / "_drafts"
    assets_root = Path(args.output) / "assets" / "images" / "posts"

    posts_dir.mkdir(parents=True, exist_ok=True)
    drafts_dir.mkdir(parents=True, exist_ok=True)
    assets_root.mkdir(parents=True, exist_ok=True)

    html_files = list(input_dir.glob("*.html"))
    if not html_files:
        print(f"No HTML files found in {input_dir}")
        return

    print(f"Found {len(html_files)} files. Converting...\n")

    published, drafts, comments, errors = 0, 0, 0, 0
    with httpx.Client() as client:
        downloader = None
        if not args.skip_images:
            downloader = ImageDownloader(client, assets_root)
            downloader.delay = args.delay

        for html_file in sorted(html_files):
            try:
                was_draft = convert_post(html_file, posts_dir, drafts_dir, downloader)
                if was_draft is None:
                    comments += 1
                elif was_draft:
                    drafts += 1
                else:
                    published += 1
            except Exception as e:
                print(f"  ✗ {html_file.name} — ERROR: {e}")
                errors += 1

    print("\nDone!")
    print(f"  {published} published posts → {posts_dir}")
    print(f"  {drafts} drafts           → {drafts_dir}")
    if comments:
        print(f"  {comments} comments        — skipped")
    if downloader:
        print(f"  Images: {downloader.summary()}")
        if downloader.total_failed:
            print("  Tip: re-run to retry failed images (already downloaded ones are cached)")
    elif args.skip_images:
        print("  Images: skipped (re-run without --skip-images to download)")
    if errors:
        print(f"  {errors} errors (check above)")


if __name__ == "__main__":
    main()
