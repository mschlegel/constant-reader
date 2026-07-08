"""Static site builder: content/*.md + pages/*.md -> docs/ (GitHub Pages root)."""
import json
import shutil
from datetime import date
from pathlib import Path

import markdown
import yaml
from jinja2 import Environment, FileSystemLoader

ROOT = Path(__file__).parent
CONTENT_DIR = ROOT / "content"
PAGES_DIR = ROOT / "pages"
STATIC_DIR = ROOT / "static"
TEMPLATES_DIR = ROOT / "templates"
OUT_DIR = ROOT / "docs"

MD_EXTENSIONS = ["extra", "sane_lists", "toc"]


def load_doc(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    _, frontmatter, body = text.split("---", 2)
    meta = yaml.safe_load(frontmatter)
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

    articles = sorted(
        (load_doc(p) for p in CONTENT_DIR.glob("*.md")),
        key=lambda a: a["date"],
        reverse=True,
    )
    pages = [load_doc(p) for p in PAGES_DIR.glob("*.md")]

    nav_pages = [{"slug": p["slug"], "title": p["title"]} for p in pages]

    article_tmpl = env.get_template("article.html")
    for article in articles:
        out = OUT_DIR / article["slug"]
        out.mkdir(parents=True, exist_ok=True)
        (out / "index.html").write_text(
            article_tmpl.render(page=article, config=config, nav_pages=nav_pages),
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

    print(f"Built {len(articles)} articles, {len(pages)} pages -> {OUT_DIR}")


if __name__ == "__main__":
    main()
