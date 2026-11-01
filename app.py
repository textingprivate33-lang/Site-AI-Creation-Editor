"""Site-AI-Creation-Editor: paste a URL, get a marketing video. Runs on your own PC.
Start with:  python app.py   then open http://localhost:5000"""
import json
import re
import threading
import uuid

from flask import Flask, jsonify, request, send_from_directory

import config
import crawler
import renderer
import storyboard

app = Flask(__name__, static_folder="static", static_url_path="/static")
JOBS = {}
HEAVY = threading.Lock()  # one heavy job at a time: kind to an 8 GB laptop


def start_job(fn, *args):
    jid = uuid.uuid4().hex[:8]
    JOBS[jid] = {"status": "running", "message": "Starting…", "result": None}

    def target():
        job = JOBS[jid]
        with HEAVY:
            try:
                job["result"] = fn(job, *args)
                job["status"] = "done"
            except Exception as e:  # shown to the user in the page
                job["status"] = "error"
                job["message"] = str(e)

    threading.Thread(target=target, daemon=True).start()
    return jid


def say(job):
    def _say(msg):
        job["message"] = msg
        print(msg, flush=True)
    return _say


def do_analyze(job, url, max_pages, seconds):
    pid = uuid.uuid4().hex[:8]
    wdir = config.WORK / pid
    log = say(job)
    site = crawler.crawl(url, wdir, max_pages=max_pages, log=log)
    sb = storyboard.make_storyboard(site, seconds=seconds, log=log)
    (wdir / "storyboard.json").write_text(json.dumps(sb, indent=2), encoding="utf-8")
    return {"project": pid, "site": site, "storyboard": sb}


def do_render(job, project, sb, voice):
    wdir = config.WORK / project
    site = json.loads((wdir / "site.json").read_text(encoding="utf-8"))
    slug = re.sub(r"[^a-z0-9]+", "-", site["name"].lower()).strip("-") or "video"
    out = config.OUTPUT / f"{slug}-{project}.mp4"
    renderer.render_video(site, sb, wdir, out, voice, progress=say(job))
    return {"video": f"/output/{out.name}"}


@app.get("/")
def index():
    return send_from_directory("static", "index.html")


@app.post("/api/analyze")
def analyze():
    d = request.get_json(force=True)
    url = (d.get("url") or "").strip()
    if not url:
        return jsonify(error="Enter a URL"), 400
    pages = max(1, min(int(d.get("max_pages", 4)), 8))
    seconds = max(20, min(int(d.get("seconds", 45)), 90))
    return jsonify(job=start_job(do_analyze, url, pages, seconds))


@app.post("/api/render")
def render():
    d = request.get_json(force=True)
    project = re.sub(r"[^a-f0-9]", "", d.get("project", ""))
    if not (config.WORK / project / "site.json").exists():
        return jsonify(error="Unknown project. Analyze a URL first."), 400
    voice = d.get("voice") or config.DEFAULT_VOICE
    return jsonify(job=start_job(do_render, project, d["storyboard"], voice))


@app.get("/api/job/<jid>")
def job(jid):
    return jsonify(JOBS.get(jid, {"status": "error", "message": "Unknown job"}))


@app.get("/work/<path:p>")
def work_files(p):
    return send_from_directory(config.WORK, p)


@app.get("/output/<path:p>")
def output_files(p):
    return send_from_directory(config.OUTPUT, p)


if __name__ == "__main__":
    print("Open http://localhost:5000 in your browser")
    app.run(host="127.0.0.1", port=5000, debug=False)
