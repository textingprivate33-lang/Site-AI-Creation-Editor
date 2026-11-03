"""Turns the crawled site into a scene-by-scene video script.
Uses Gemini (free tier) when a key is set; otherwise builds a basic script
from the site's own text so the app still works with no key at all."""
import json
import re
import requests

import config

ROLES = ["hook", "problem", "solution", "feature", "proof", "partner", "cta"]
NO_VISUAL = ("hook", "partner", "cta")
AUDIENCES = {
    "general": "a general audience",
    "customers": "everyday customers who would use the product",
    "businesses": "business owners and vendors who would use it to serve their own customers",
    "logistics": "logistics and delivery companies, fleets and other businesses who could partner or collaborate",
}
GENERIC = {"the problem", "the solution", "how it works", "who it's for", "who its for", "features",
           "key features", "pricing", "about", "about us", "contact", "contact us", "faq", "testimonials",
           "get started", "our mission", "why us", "benefits", "overview", "what we do"}


def smart_trim(text, limit, end="…"):
    """Shorten without cutting a word or sentence in half."""
    text = " ".join(str(text or "").split())
    if len(text) <= limit:
        return text
    cut = text[:limit]
    ends = [m.end() for m in re.finditer(r"[.!?](?=\s|$)", cut)]
    if ends and ends[-1] >= limit * 0.5:
        return cut[:ends[-1]].strip()
    clauses = [m.start() for m in re.finditer(r"[,;:]|\s[—–-]\s", cut)]
    if clauses and clauses[-1] >= limit * 0.55:
        return cut[:clauses[-1]].rstrip(" ,;:-–—")
    cut = cut.rsplit(" ", 1)[0] if " " in cut else cut
    return cut.rstrip(" ,;:-–—") + end


def contact_text():
    return "; ".join(f"{k}: {v}" for k, v in config.CONTACTS) or "none set"


def build_prompt(site, seconds, message, audience):
    parts = []
    for pg in site["pages"]:
        parts.append(f"PAGE: {pg['url']}\nTITLE: {pg['title']}\n"
                     f"HEADINGS: {' | '.join(pg['headings'][:10])}\n"
                     f"TEXT: {' '.join(pg['paras'][:8])}")
    material = "\n\n".join(parts)[:7000]
    aud = AUDIENCES.get(audience, AUDIENCES["general"])
    want_partner = bool(message) or audience == "logistics"
    partner_rule = (
        'Include exactly ONE scene with role "partner", placed right before the final "cta" scene. '
        "It invites the audience to collaborate and clearly delivers the OWNER'S MESSAGE below. "
        "Only promise what the owner's message or the site material supports."
        if want_partner else 'Do not include a "partner" scene.')
    return f"""You are an award-winning direct-response video ad writer.
Write a {seconds}-second marketing video script for this business, using ONLY facts found in the
material below or in the owner's message (never invent prices, awards, statistics, customers or partners).

BUSINESS NAME: {site['name']}
WEBSITE: {site['host']}
DESCRIPTION: {site['description']}
TARGET AUDIENCE: {aud}
OWNER'S MESSAGE (must come across clearly): {message or 'none'}
CONTACT DETAILS SHOWN ON SCREEN IN THE LAST SCENE: {contact_text()}

{material}

Return JSON only, in exactly this shape:
{{"title": "short video title",
  "scenes": [
    {{"role": "hook|problem|solution|feature|proof|partner|cta",
      "headline": "max 8 words, punchy, shown big on screen",
      "subtext": "max 16 words, shown smaller under the headline",
      "narration": "1-2 short spoken sentences, natural and confident, max 28 words"}}
  ]}}

Rules:
- 6 to 8 scenes. First scene role "hook" (stop the scroll with a bold question or claim).
- Middle scenes cover the real problem, the solution, and the best 2-3 benefits from the material.
- {partner_rule}
- Last scene role "cta": mention {site['host']}. If contact details are set, the narration should say the
  contact details are on screen. Never read an email address or handle out loud.
- Headlines must say something specific. Never use bare section names like "The Problem" or "How it works".
- Write for the target audience. Plain, vivid language. No emojis. No hashtags."""


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


def reorder(scenes):
    hook = [s for s in scenes if s["role"] == "hook"][:1]
    cta = [s for s in scenes if s["role"] == "cta"][-1:]
    partner = [s for s in scenes if s["role"] == "partner"][:1]
    used = {id(s) for s in hook + cta + partner}
    return hook + [s for s in scenes if id(s) not in used] + partner + cta


def clean(sb):
    scenes = []
    for s in sb.get("scenes", []):
        h = str(s.get("headline", "")).strip()
        if not h:
            continue
        role = s.get("role") if s.get("role") in ROLES else "feature"
        scenes.append({"role": role, "headline": smart_trim(h, 90),
                       "subtext": smart_trim(s.get("subtext", ""), 140),
                       "narration": smart_trim(s.get("narration", ""), 260, end=".")})
    if len(scenes) < 3:
        raise ValueError("too few scenes")
    return {"title": str(sb.get("title", "")).strip() or "Marketing video", "scenes": reorder(scenes)[:9]}


def cta_scene(site):
    has = bool(config.CONTACTS)
    return {"role": "cta", "headline": f"Visit {site['host']}",
            "subtext": "Get in touch or visit the site." if has else f"Get started with {site['name']} today.",
            "narration": f"Ready to get started? Visit {site['host']}." + (" Our contact details are on screen." if has else "")}


def first_sentence(text, limit=70):
    s = re.split(r"(?<=[.!?])\s", " ".join(text.split()))[0]
    return smart_trim(s.rstrip(".!?"), limit)


def fallback(site, message, audience):
    heads = []
    for pg in site["pages"]:
        for h in pg["headings"]:
            if 8 < len(h) < 80 and h.strip().lower().rstrip("?") not in GENERIC and h not in heads:
                heads.append(h)
    paras = [p for pg in site["pages"] for p in pg["paras"]]
    name = site["name"]
    desc = site["description"] or (paras[0] if paras else "")
    scenes = [{"role": "hook", "headline": heads[0] if heads else f"Meet {name}",
               "subtext": smart_trim(desc, 110),
               "narration": f"Meet {name}. {smart_trim(desc, 130, end='.')}".strip()}]
    feats = heads[1:4]
    i = 0
    while len(feats) < 3 and i < len(paras):
        feats.append(first_sentence(paras[i]))
        i += 1
    for k, h in enumerate(feats[:3]):
        p = paras[k] if k < len(paras) else ""
        sub = smart_trim(p, 110)
        scenes.append({"role": "feature", "headline": h, "subtext": sub,
                       "narration": f"{h.rstrip('.')}. {smart_trim(p, 110, end='.')}".strip()})
    if message or audience == "logistics":
        msg = message or f"Interested in working with {name}? Get in touch."
        scenes.append({"role": "partner",
                       "headline": "Let's build together" if audience == "logistics" else "Let's work together",
                       "subtext": smart_trim(msg, 120), "narration": smart_trim(msg, 200, end=".")})
    scenes.append(cta_scene(site))
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
        if sc["role"] in NO_VISUAL or not pool:
            sc["visual"] = None
            continue
        kind, name = pool[k % len(pool)]
        sc["visual"] = {"kind": kind, "file": name}
        k += 1
    return sb


def make_storyboard(site, seconds=45, message="", audience="general", log=print):
    message = " ".join((message or "").split())[:500]
    audience = audience if audience in AUDIENCES else "general"
    sb, used = None, "basic"
    if config.GEMINI_API_KEY:
        try:
            log("Writing the script with Gemini…")
            sb = clean(call_gemini(build_prompt(site, seconds, message, audience)))
            if sb["scenes"][-1]["role"] != "cta":
                sb["scenes"].append(cta_scene(site))
            used = "gemini"
        except Exception as e:
            log(f"Gemini failed ({e}); using the basic script instead.")
    else:
        log("No GEMINI_API_KEY set; using the basic script from the site's text.")
    if sb is None:
        sb = fallback(site, message, audience)
    sb["writer"] = used
    return assign_visuals(site, sb)
