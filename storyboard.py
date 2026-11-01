"""Turns the crawled site into a scene-by-scene video script.
Uses Gemini (free tier) when a key is set; otherwise builds a basic script
from the site's own headings so the app still works with no key at all."""
import json
import requests

import config

ROLES = ["hook", "problem", "solution", "feature", "proof", "cta"]


def build_prompt(site, seconds):
    parts = []
    for pg in site["pages"]:
        parts.append(f"PAGE: {pg['url']}\nTITLE: {pg['title']}\n"
                     f"HEADINGS: {' | '.join(pg['headings'][:10])}\n"
                     f"TEXT: {' '.join(pg['paras'][:8])}")
    material = "\n\n".join(parts)[:7000]
    return f"""You are an award-winning direct-response video ad writer.
Write a {seconds}-second marketing video script for this business, using ONLY facts found
in the material below (never invent prices, awards, statistics or customers).

BUSINESS NAME: {site['name']}
WEBSITE: {site['host']}
DESCRIPTION: {site['description']}

{material}

Return JSON only, in exactly this shape:
{{"title": "short video title",
  "scenes": [
    {{"role": "hook|problem|solution|feature|proof|cta",
      "headline": "max 8 words, punchy, shown big on screen",
      "subtext": "max 16 words, shown smaller under the headline",
      "narration": "1-2 short spoken sentences, natural and confident, max 28 words"}}
  ]}}

Rules: 6 or 7 scenes. First scene role "hook" (stop the scroll with a bold question or claim).
Last scene role "cta" and must mention {site['host']}. Middle scenes cover the real
problem, the solution, and the best 2-3 features/benefits from the material.
Plain, vivid language. No emojis. No hashtags."""


def call_gemini(prompt):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{config.GEMINI_MODEL}:generateContent"
    r = requests.post(
        url, timeout=90,
        headers={"x-goog-api-key": config.GEMINI_API_KEY, "Content-Type": "application/json"},
        json={"contents": [{"parts": [{"text": prompt}]}],
              "generationConfig": {"responseMimeType": "application/json", "temperature": 0.8}})
    if r.status_code != 200:
        raise RuntimeError(f"Gemini error {r.status_code}: {r.text[:200]}")
    parts = r.json()["candidates"][0]["content"]["parts"]
    text = "".join(p.get("text", "") for p in parts if not p.get("thought"))
    return json.loads(text)


def clean(sb):
    scenes = []
    for s in sb.get("scenes", []):
        h = str(s.get("headline", "")).strip()
        if not h:
            continue
        scenes.append({"role": s.get("role", "feature") if s.get("role") in ROLES else "feature",
                       "headline": h[:90], "subtext": str(s.get("subtext", "")).strip()[:140],
                       "narration": str(s.get("narration", "")).strip()[:260]})
    if len(scenes) < 3:
        raise ValueError("too few scenes")
    return {"title": str(sb.get("title", "")).strip() or "Marketing video", "scenes": scenes[:8]}


def fallback(site):
    heads = []
    for pg in site["pages"]:
        heads += [h for h in pg["headings"] if 8 < len(h) < 80]
    paras = [p for pg in site["pages"] for p in pg["paras"]]
    name, host = site["name"], site["host"]
    desc = site["description"] or (paras[0] if paras else "")
    scenes = [{"role": "hook", "headline": heads[0] if heads else f"Meet {name}",
               "subtext": desc[:130], "narration": f"Meet {name}. {desc[:120]}"}]
    for i, h in enumerate(heads[1:5]):
        p = paras[i] if i < len(paras) else ""
        scenes.append({"role": "feature", "headline": h, "subtext": p[:120],
                       "narration": f"{h}. {p[:110]}".strip()})
    scenes.append({"role": "cta", "headline": f"Visit {host}", "subtext": f"Get started with {name} today.",
                   "narration": f"Ready to get started? Visit {host} today."})
    return {"title": f"{name} — promo", "scenes": scenes}


def assign_visuals(site, sb):
    pool = []
    shots, imgs = site["shots"], site["images"]
    if shots:
        pool.append(("shot", shots[0]))
    pool += [("image", i) for i in imgs]
    pool += [("shot", s) for s in shots[1:]]
    k = 0
    for sc in sb["scenes"]:
        if sc["role"] in ("hook", "cta") or not pool:
            sc["visual"] = None
            continue
        kind, name = pool[k % len(pool)]
        sc["visual"] = {"kind": kind, "file": name}
        k += 1
    return sb


def make_storyboard(site, seconds=45, log=print):
    sb, used = None, "basic"
    if config.GEMINI_API_KEY:
        try:
            log("Writing the script with Gemini…")
            sb = clean(call_gemini(build_prompt(site, seconds)))
            used = "gemini"
        except Exception as e:
            log(f"Gemini failed ({e}); using the basic script instead.")
    else:
        log("No GEMINI_API_KEY set; using the basic script from the site's headings.")
    if sb is None:
        sb = fallback(site)
    sb["writer"] = used
    return assign_visuals(site, sb)
