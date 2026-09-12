"""Static site builder: content/*.md + pages/*.md -> docs/ (GitHub Pages root)."""
import json
import re
import shutil
from datetime import date
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import markdown
import yaml
from jinja2 import Environment, FileSystemLoader

ROOT = Path(__file__).parent
CONTENT_DIR = ROOT / "content"
PAGES_DIR = ROOT / "pages"
STATIC_DIR = ROOT / "static"
PUBLIC_DIR = ROOT / "public"
TEMPLATES_DIR = ROOT / "templates"
OUT_DIR = ROOT / "docs"

MD_EXTENSIONS = ["extra", "sane_lists", "toc"]

# Only these Amazon path shapes are affiliate-linkable (search results, product
# detail pages). Reference links like /gp/help/... must not get a tag stapled on.
AFFILIATE_PATH_PREFIXES = ("/s", "/dp/", "/gp/product/", "/gp/aw/d/")
URL_RE = re.compile(r'https?://[^\s)"\'<>]+')


def _is_amazon_affiliate_url(parts) -> bool:
    host = parts.netloc.lower()
    if host != "amazon.com" and not host.endswith(".amazon.com"):
        return False
    return parts.path.startswith(AFFILIATE_PATH_PREFIXES)


def apply_affiliate_tag(text: str, tag: str) -> str:
    """Rewrite the tag= query param on every Amazon affiliate link at build time,
    regardless of what tag (if any) is literally written in the markdown source.
    This is what lets one site_config.json edit retag the whole corpus."""

    def _replace(match: "re.Match[str]") -> str:
        url = match.group(0)
        parts = urlsplit(url)
        if not _is_amazon_affiliate_url(parts):
            return url
        query = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if k != "tag"]
        query.append(("tag", tag))
        return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))

    return URL_RE.sub(_replace, text)


TOPIC_STOPWORDS = {
    "the", "a", "an", "of", "in", "on", "for", "to", "and", "or", "vs", "what",
    "is", "are", "with", "by", "best", "stephen", "king", "you", "your", "how",
    "why", "book", "books", "guide", "complete", "every", "makes", "real",
}


def _topic_words(article: dict) -> set:
    text = article["slug"].replace("-", " ") + " " + article["title"]
    return {w for w in re.findall(r"[a-z0-9']+", text.lower()) if len(w) > 2 and w not in TOPIC_STOPWORDS}


def compute_related(articles: list, n: int = 3) -> dict:
    """Deterministic 'related articles' by shared topic words in slug/title.
    Ties broken by newest first, then slug — no manual tagging required, so this
    keeps working for every future article the content pipeline writes."""
    words = {a["slug"]: _topic_words(a) for a in articles}
    related = {}
    for a in articles:
        scored = sorted(
            (b for b in articles if b["slug"] != a["slug"]),
            key=lambda b: (-len(words[a["slug"]] & words[b["slug"]]), -b["date"].toordinal(), b["slug"]),
        )
        related[a["slug"]] = scored[:n]
    return related


def load_doc(path: Path, affiliate_tag: str) -> dict:
    text = path.read_text(encoding="utf-8")
    _, frontmatter, body = text.split("---", 2)
    meta = yaml.safe_load(frontmatter)
    body = apply_affiliate_tag(body, affiliate_tag)
    meta["html"] = markdown.markdown(body.strip(), extensions=MD_EXTENSIONS)
    meta["slug"] = meta.get("slug", path.stem)
    return meta


def main():
    config = json.loads((ROOT / "site_config.json").read_text(encoding="utf-8"))
    env = Environment(loader=FileSystemLoader(str(TEMPLATES_DIR)))

    if OUT_DIR.exists():
        shutil.rmtree(OUT_DIR)
    OUT_DIR.mkdir()
    if STATIC_DIR.exists():
        shutil.copytree(STATIC_DIR, OUT_DIR / "static")
    if PUBLIC_DIR.exists():
        for f in PUBLIC_DIR.iterdir():
            if f.is_file():
                shutil.copy(f, OUT_DIR / f.name)

    affiliate_tag = config["affiliate_tag"]
    articles = sorted(
        (load_doc(p, affiliate_tag) for p in CONTENT_DIR.glob("*.md")),
        key=lambda a: a["date"],
        reverse=True,
    )
    pages = [load_doc(p, affiliate_tag) for p in PAGES_DIR.glob("*.md")]

    nav_pages = [{"slug": p["slug"], "title": p["title"]} for p in pages]

    related_by_slug = compute_related(articles)

    article_tmpl = env.get_template("article.html")
    for article in articles:
        out = OUT_DIR / article["slug"]
        out.mkdir(parents=True, exist_ok=True)
        (out / "index.html").write_text(
            article_tmpl.render(
                page=article,
                config=config,
                nav_pages=nav_pages,
                related=related_by_slug[article["slug"]],
            ),
            encoding="utf-8",
        )

    page_tmpl = env.get_template("page.html")
    for page in pages:
        out = OUT_DIR / page["slug"]
        out.mkdir(parents=True, exist_ok=True)
        (out / "index.html").write_text(
            page_tmpl.render(page=page, config=config, nav_pages=nav_pages),
            encoding="utf-8",
        )

    index_tmpl = env.get_template("index.html")
    (OUT_DIR / "index.html").write_text(
        index_tmpl.render(articles=articles, config=config, nav_pages=nav_pages),
        encoding="utf-8",
    )

    urls = [config["site_url"] + "/"] + [
        f"{config['site_url']}/{doc['slug']}/" for doc in articles + pages
    ]
    sitemap = ['<?xml version="1.0" encoding="UTF-8"?>', '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for url in urls:
        sitemap.append(f"  <url><loc>{url}</loc></url>")
    sitemap.append("</urlset>")
    (OUT_DIR / "sitemap.xml").write_text("\n".join(sitemap), encoding="utf-8")

    (OUT_DIR / "robots.txt").write_text(
        f"User-agent: *\nAllow: /\nSitemap: {config['site_url']}/sitemap.xml\n",
        encoding="utf-8",
    )

    (OUT_DIR / ".nojekyll").write_text("", encoding="utf-8")

    if config.get("custom_domain"):
        (OUT_DIR / "CNAME").write_text(config["custom_domain"], encoding="utf-8")

    print(f"Built {len(articles)} articles, {len(pages)} pages -> {OUT_DIR}")


if __name__ == "__main__":
    main()
