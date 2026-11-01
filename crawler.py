"""Reads a website with a real headless browser: the start page plus the most
useful internal pages. Collects text, colours, images, a logo and screenshots."""
import colorsys
import json
import re
from pathlib import Path
from urllib.parse import urlparse, urldefrag, urljoin

import requests
from PIL import Image

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")

PRIORITY = ["about", "product", "feature", "service", "solution", "pricing",
            "price", "how", "why", "work", "case", "customer", "story",
            "platform", "contact"]
SKIP = ["login", "signin", "sign-in", "signup", "sign-up", "cart", "privacy",
        "terms", "policy", "cookie", "account", "checkout", "wp-admin",
        "mailto:", "tel:", "javascript:"]
BAD_EXT = (".pdf", ".jpg", ".jpeg", ".png", ".gif", ".zip", ".mp4", ".svg",
           ".webp", ".docx", ".xlsx")

EXTRACT_JS = r"""
() => {
  const txt = (el) => (el.innerText || "").replace(/\s+/g, " ").trim();
  const meta = (n) => { const e = document.querySelector(
      'meta[name="' + n + '"],meta[property="' + n + '"]');
      return e ? (e.content || "").trim() : ""; };
  const uniq = (a) => [...new Set(a)];
  const headings = uniq([...document.querySelectorAll("h1,h2,h3")].map(txt)
      .filter(t => t.length > 3 && t.length < 140)).slice(0, 14);
  const paras = uniq([...document.querySelectorAll("p,li")].map(txt)
      .filter(t => t.length > 40 && t.length < 300)).slice(0, 14);
  const images = [...document.images].filter(i => i.naturalWidth >= 500 &&
      i.naturalHeight >= 280 && i.currentSrc).map(i => ({src: i.currentSrc,
      w: i.naturalWidth, h: i.naturalHeight, alt: i.alt || ""})).slice(0, 12);
  const logoEl = [...document.images].find(i =>
      /logo/i.test((i.className || "") + " " + (i.alt || "") + " " + (i.src || "")));
  const icon = document.querySelector('link[rel="apple-touch-icon"],link[rel~="icon"]');
  const colors = [];
  const grab = (sel, prop) => document.querySelectorAll(sel).forEach((e, i) => {
      if (i < 8) colors.push(getComputedStyle(e)[prop]); });
  grab("button, .btn, [class*=button], [class*=btn], a[class*=cta]", "backgroundColor");
  grab("h1, h2", "color");
  grab("a", "color");
  const links = [...document.querySelectorAll("a[href]")].map(a =>
      ({href: a.href, text: txt(a).slice(0, 40)}));
  return {title: document.title, description: meta("description") || meta("og:description"),
      siteName: meta("og:site_name"), ogImage: meta("og:image"),
      themeColor: meta("theme-color"), headings, paras, images,
      logo: logoEl ? logoEl.currentSrc : (icon ? icon.href : ""),
      colors, bodyBg: getComputedStyle(document.body).backgroundColor, links};
}
"""

SCROLL_JS = """async () => {
  for (let y = 0; y < document.body.scrollHeight && y < 6000; y += 600) {
    window.scrollTo(0, y); await new Promise(r => setTimeout(r, 120));
  }
  window.scrollTo(0, 0);
}"""


def normalize(url):
    url = url.strip()
    if not re.match(r"^https?://", url, re.I):
        local = re.match(r"^(localhost|127\.0\.0\.1)(:|/|$)", url, re.I)
        url = ("http://" if local else "https://") + url
    return url


def canon(url):
    u = urldefrag(url)[0].rstrip("/")
    return u.lower()


def host_of(url):
    return urlparse(url).netloc.lower().replace("www.", "")


def rank_links(links, base_url, seen):
    host = host_of(base_url)
    scored, got = [], set()
    for i, l in enumerate(links):
        href = urldefrag(urljoin(base_url, l["href"]))[0]
        low = href.lower()
        if host_of(href) != host or canon(href) in seen or canon(href) in got:
            continue
        if any(s in low for s in SKIP) or low.endswith(BAD_EXT):
            continue
        got.add(canon(href))
        key = (low + " " + l.get("text", "").lower())
        score = next((j for j, w in enumerate(PRIORITY) if w in key), 99)
        scored.append((score, i, href))
    scored.sort()
    return [h for _, _, h in scored[:12]]


def crawl(url, out_dir, max_pages=4, log=print):
    from playwright.sync_api import sync_playwright
    url = normalize(url)
    out_dir.mkdir(parents=True, exist_ok=True)
    pages, seen, queue = [], set(), [url]
    with sync_playwright() as p:
        try:
            browser = p.chromium.launch()
        except Exception as e:
            raise RuntimeError("Browser not installed. Run:  playwright install chromium") from e
        ctx = browser.new_context(viewport={"width": 1920, "height": 1080}, user_agent=UA)
        page = ctx.new_page()
        while queue and len(pages) < max_pages:
            u = queue.pop(0)
            if canon(u) in seen:
                continue
            seen.add(canon(u))
            log(f"Reading page {len(pages) + 1}: {u}")
            try:
                page.goto(u, wait_until="domcontentloaded", timeout=30000)
                try:
                    page.wait_for_load_state("networkidle", timeout=8000)
                except Exception:
                    pass
                page.evaluate(SCROLL_JS)
                page.wait_for_timeout(400)
                data = page.evaluate(EXTRACT_JS)
                shot = out_dir / f"shot_{len(pages)}.png"
                page.screenshot(path=str(shot))
            except Exception as e:
                log(f"Skipped {u}: {e}")
                if not pages and u == url:
                    raise RuntimeError(f"Could not open {u}: {e}")
                continue
            data["url"], data["shot"] = u, shot.name
            pages.append(data)
            if len(pages) == 1:
                queue = rank_links(data["links"], page.url, seen)
        browser.close()
    if not pages:
        raise RuntimeError("No pages could be read.")
    return build_site(pages, url, out_dir, log)


# ---------- brand extraction ----------

def parse_color(s):
    s = (s or "").strip().lower()
    m = re.match(r"rgba?\(([^)]+)\)", s)
    if m:
        parts = [p.strip() for p in re.split(r"[,\s/]+", m.group(1)) if p.strip()]
        try:
            r, g, b = [int(float(x)) for x in parts[:3]]
            a = float(parts[3]) if len(parts) > 3 else 1.0
        except ValueError:
            return None
        return None if a < 0.5 else (r, g, b)
    m = re.match(r"#([0-9a-f]{6}|[0-9a-f]{3})$", s)
    if m:
        h = m.group(1)
        if len(h) == 3:
            h = "".join(c * 2 for c in h)
        return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))
    return None


def pick_primary(pages):
    cands = []
    for pg in pages:
        if pg.get("themeColor"):
            cands.append(pg["themeColor"])
        cands += pg.get("colors", [])
    counts = {}
    for c in cands:
        rgb = parse_color(c)
        if not rgb:
            continue
        h, l, s = colorsys.rgb_to_hls(*[x / 255 for x in rgb])
        if s < 0.25 or l < 0.18 or l > 0.85:
            continue
        counts[rgb] = counts.get(rgb, 0) + 1
    if counts:
        return max(counts, key=counts.get)
    return (79, 70, 229)


def to_hex(rgb):
    return "#%02x%02x%02x" % tuple(rgb)


def make_palette(primary):
    h, l, s = colorsys.rgb_to_hls(*[x / 255 for x in primary])

    def hls(h_, l_, s_):
        return tuple(int(round(x * 255)) for x in colorsys.hls_to_rgb(h_, l_, s_))

    return {"primary": to_hex(primary),
            "bg1": to_hex(hls(h, 0.09, min(max(s, 0.3), 0.6))),
            "bg2": to_hex(hls(h, 0.22, min(max(s, 0.4), 0.75))),
            "accent": to_hex(hls(h, 0.62, max(s, 0.6))),
            "text": "#FFFFFF", "muted": "#C9D1E3"}


def brand_name(first, url):
    name = (first.get("siteName") or "").strip()
    if not name:
        parts = [p.strip() for p in re.split(r"\s[|\-–—:]\s", first.get("title", "")) if p.strip()]
        name = min(parts, key=len) if parts else ""
    if not name or len(name) > 32:
        name = host_of(url).split(".")[0].title()
    return name


def fetch_image(src, dest):
    try:
        r = requests.get(src, timeout=12, headers={"User-Agent": UA})
        r.raise_for_status()
        dest.write_bytes(r.content)
        with Image.open(dest) as im:
            im.load()
            return im.size
    except Exception:
        dest.unlink(missing_ok=True)
        return None


def build_site(pages, url, out_dir, log):
    first = pages[0]
    # images: og:image first, then biggest from every page
    cand, seen = [], set()
    if first.get("ogImage"):
        cand.append(urljoin(first["url"], first["ogImage"]))
    for pg in pages:
        for im in sorted(pg["images"], key=lambda i: -i["w"] * i["h"]):
            cand.append(im["src"])
    images = []
    for src in cand:
        if src in seen or src.startswith("data:") or len(images) >= 6:
            continue
        seen.add(src)
        dest = out_dir / f"img_{len(images)}.jpg"
        size = fetch_image(src, dest)
        if not size or size[0] < 400 or size[1] < 250:
            dest.unlink(missing_ok=True)
            continue
        with Image.open(dest) as im:
            im.convert("RGB").save(dest, quality=90)
        images.append(dest.name)
    logo = None
    if first.get("logo") and not first["logo"].startswith("data:"):
        dest = out_dir / "logo.png"
        size = fetch_image(urljoin(first["url"], first["logo"]), dest)
        if size and min(size) >= 48:
            with Image.open(dest) as im:
                im.convert("RGBA").save(dest)
            logo = dest.name
        else:
            dest.unlink(missing_ok=True)
    primary = pick_primary(pages)
    site = {
        "name": brand_name(first, url), "url": first["url"], "host": host_of(url),
        "description": first.get("description", ""),
        "palette": make_palette(primary), "logo": logo, "images": images,
        "shots": [pg["shot"] for pg in pages],
        "pages": [{"url": pg["url"], "title": pg["title"], "headings": pg["headings"],
                   "paras": pg["paras"]} for pg in pages],
    }
    (out_dir / "site.json").write_text(json.dumps(site, indent=2), encoding="utf-8")
    log(f"Found {len(images)} images, {len(pages)} pages, brand colour {site['palette']['primary']}")
    return site
