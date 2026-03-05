from __future__ import annotations

import os
import re
import time
import json
import shutil
import secrets
from typing import List, Dict, Any, Tuple

from flask import Flask, request, jsonify, Response, make_response

APP_TITLE_DEFAULT = "Vaayu | Border Collie Brand Portfolio"
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


# -----------------------------
# Files / folders
# -----------------------------
def ensure_dirs() -> None:
    os.makedirs("data", exist_ok=True)
    os.makedirs(os.path.join("static", "images"), exist_ok=True)
    os.makedirs("source_images", exist_ok=True)


def copy_source_images() -> None:
    """Copy ./source_images/* -> ./static/images/* (jpg/png/webp)."""
    ensure_dirs()
    src_dir = "source_images"
    dst_dir = os.path.join("static", "images")
    allowed = (".jpg", ".jpeg", ".png", ".webp")

    for name in os.listdir(src_dir):
        if not name.lower().endswith(allowed):
            continue
        src = os.path.join(src_dir, name)
        dst = os.path.join(dst_dir, name)
        try:
            shutil.copy2(src, dst)
        except Exception:
            # ignore copy issues (file may already exist or be locked)
            pass


def list_static_images() -> List[str]:
    """Return web paths /static/images/.. sorted."""
    ensure_dirs()
    img_dir = os.path.join("static", "images")
    allowed = (".jpg", ".jpeg", ".png", ".webp")
    imgs = []
    for name in sorted(os.listdir(img_dir), key=lambda s: s.lower()):
        if name.lower().endswith(allowed):
            imgs.append(f"/static/images/{name}")
    return imgs


def escape_html(s: str) -> str:
    return (
        s.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#39;")
    )


# -----------------------------
# Contact storage (JSONL)
# -----------------------------
def read_jsonl(path: str, limit: int = 100) -> List[Dict[str, Any]]:
    if not os.path.exists(path):
        return []
    out: List[Dict[str, Any]] = []
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    out.append(json.loads(line))
                except Exception:
                    pass
    except Exception:
        return []
    return out[-limit:]


def append_jsonl(path: str, obj: Dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")


# -----------------------------
# Cute captions (NO filenames)
# -----------------------------
def cute_caption(i: int) -> Dict[str, str]:
    presets = [
        ("Beach Day Smile", "Lifestyle • clean coat contrast"),
        ("Toy Tester Mode", "Playful • perfect for toy ads"),
        ("Close-Up Charm", "Expressive face • camera-ready"),
        ("Cozy Cuddle Shot", "Soft vibe • home/lifestyle brands"),
        ("Training Champion", "Obedience • focused performance"),
        ("Adventure Pup", "Outdoors • athletic & confident"),
        ("Snack Time Star", "Food/treat campaigns ready"),
        ("Show Pose", "Balance • posture • calm confidence"),
        ("Happy Zoomies", "Energy • fun • engagement"),
        ("Gentle Hero", "Premium look • calm expression"),
        ("Fluffy Spotlight", "Coat texture • high-quality shot"),
        ("Signature Look", "Iconic black/white contrast"),
    ]
    if i < len(presets):
        t, s = presets[i]
        return {"title": t, "sub": s}
    return {"title": f"Vaayu Look #{i+1}", "sub": "Brand-ready • expressive • photogenic"}


def card_image(src: str, title: str, sub: str) -> str:
    # IMPORTANT: No filename shown anywhere; title/sub only.
    return f"""
<figure class="card">
  <img class="cardImg" data-full="{escape_html(src)}" src="{escape_html(src)}" alt="{escape_html(title)}">
  <figcaption class="cap">
    <div class="capTitle">{escape_html(title)}</div>
    <div class="capSub">{escape_html(sub)}</div>
  </figcaption>
</figure>
"""


def card_placeholder(msg: str) -> str:
    safe = escape_html(msg)
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="800">
      <defs><linearGradient id="g" x1="0" x2="1">
        <stop offset="0" stop-color="#0b0f19"/><stop offset="1" stop-color="#1a2442"/></linearGradient></defs>
      <rect width="1200" height="800" fill="url(#g)"/>
      <text x="50%" y="50%" fill="rgba(255,255,255,.88)" font-size="44"
        text-anchor="middle" dominant-baseline="middle" font-family="Arial, sans-serif">{safe}</text>
      <text x="50%" y="58%" fill="rgba(255,255,255,.58)" font-size="20"
        text-anchor="middle" dominant-baseline="middle" font-family="Arial, sans-serif">Put photos in .\\source_images then refresh</text>
    </svg>"""
    data = "data:image/svg+xml;charset=utf-8," + svg.replace("\n", "").replace("\r", "")
    return f"""
<figure class="card">
  <img class="cardImg" data-full="{data}" src="{data}" alt="{safe}">
  <figcaption class="cap">
    <div class="capTitle">{safe}</div>
    <div class="capSub">Portfolio auto-loads from .\\source_images</div>
  </figcaption>
</figure>
"""


# -----------------------------
# Flask app
# -----------------------------
def create_app() -> Flask:
    ensure_dirs()
    copy_source_images()

    host = os.getenv("HOST", "127.0.0.1")
    port = int(os.getenv("PORT", "5000"))
    env = os.getenv("FLASK_ENV", os.getenv("ENV", "production")).lower()
    debug = env == "development"

    site_title = os.getenv("SITE_TITLE", APP_TITLE_DEFAULT)
    secret_key = os.getenv("SECRET_KEY", "dev-" + secrets.token_hex(16))
    rate_limit_per_minute = int(os.getenv("RATE_LIMIT_PER_MINUTE", "30"))
    contact_log = os.getenv("CONTACT_LOG", "data/contact_messages.jsonl")
    admin_token = os.getenv("ADMIN_TOKEN", "")  # optional

    app = Flask(__name__, static_folder="static")
    app.config["SECRET_KEY"] = secret_key

    rate_bucket: Dict[Tuple[str, int], int] = {}

    def client_ip() -> str:
        xf = request.headers.get("X-Forwarded-For")
        if xf:
            return xf.split(",")[0].strip()
        return request.remote_addr or "unknown"

    def is_rate_limited(ip: str) -> bool:
        bucket = int(time.time() // 60)
        key = (ip, bucket)
        rate_bucket[key] = rate_bucket.get(key, 0) + 1
        if len(rate_bucket) > 2000:
            cutoff = bucket - 30
            for k in list(rate_bucket.keys()):
                if k[1] < cutoff:
                    rate_bucket.pop(k, None)
        return rate_bucket[key] > rate_limit_per_minute

    @app.after_request
    def security_headers(resp: Response):
        resp.headers["X-Content-Type-Options"] = "nosniff"
        resp.headers["X-Frame-Options"] = "DENY"
        resp.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        resp.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
        # Single-file uses inline styles/scripts -> allow unsafe-inline for local
        resp.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "img-src 'self' data: blob:; "
            "style-src 'self' 'unsafe-inline'; "
            "script-src 'self' 'unsafe-inline'; "
            "connect-src 'self'; "
            "base-uri 'self'; "
            "frame-ancestors 'none';"
        )
        return resp

    @app.get("/healthz")
    def healthz():
        return jsonify({"status": "ok"})

    @app.get("/api/images")
    def api_images():
        copy_source_images()
        return jsonify({"images": list_static_images()})

    @app.get("/media-kit")
    def media_kit():
        copy_source_images()
        imgs = list_static_images()
        hero = imgs[0] if imgs else None
        return jsonify(
            {
                "name": "Vaayu",
                "breed": "Border Collie",
                "positioning": "Brand ambassador for food brands, treats, toy brands, and pet campaigns",
                "assets": {"hero": hero, "gallery": imgs},
                "contact": {"endpoint": "/api/contact"},
            }
        )

    @app.post("/api/contact")
    def api_contact():
        ip = client_ip()
        if is_rate_limited(ip):
            return jsonify({"ok": False, "error": "Too many requests. Try again in a minute."}), 429

        data = request.get_json(silent=True) or {}
        name = str(data.get("name", "")).strip()
        email = str(data.get("email", "")).strip()
        purpose = str(data.get("purpose", "Brand Inquiry")).strip()
        message = str(data.get("message", "")).strip()

        errors = []
        if len(name) < 2:
            errors.append("Name must be at least 2 characters.")
        if not EMAIL_RE.match(email):
            errors.append("Please enter a valid email.")
        if len(message) < 10:
            errors.append("Message must be at least 10 characters.")
        if len(message) > 2000:
            errors.append("Message must be less than 2000 characters.")
        if errors:
            return jsonify({"ok": False, "errors": errors}), 400

        payload = {
            "ts": int(time.time()),
            "name": name,
            "email": email,
            "purpose": purpose,
            "message": message,
            "ip": ip,
            "user_agent": request.headers.get("User-Agent", ""),
        }
        append_jsonl(contact_log, payload)
        return jsonify({"ok": True, "message": "Thanks! Your request was received. We’ll reply soon 🐾"})

    @app.get("/admin")
    def admin():
        if not admin_token:
            return make_response("ADMIN_TOKEN not set. Set it to enable /admin.", 403)
        token = request.args.get("token", "")
        if token != admin_token:
            return make_response("Unauthorized.", 401)

        items = read_jsonl(contact_log, limit=100)
        items_html = []
        for it in reversed(items):
            items_html.append(
                f"""
                <div class="acard">
                  <div class="atop">
                    <div><b>{escape_html(it.get('purpose',''))}</b> — {escape_html(it.get('name',''))} &lt;{escape_html(it.get('email',''))}&gt;</div>
                    <div class="muted">{it.get('ts','')} • IP: {escape_html(it.get('ip',''))}</div>
                  </div>
                  <pre class="amsg">{escape_html(it.get('message',''))}</pre>
                </div>
                """
            )

        html = f"""<!doctype html>
<html><head><meta charset="utf-8"/><meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>Admin | Vaayu</title>
<style>
body{{margin:0;background:#070a12;color:#f5f7ff;font-family:Arial,sans-serif;padding:22px}}
.wrap{{max-width:980px;margin:0 auto}}
.muted{{color:rgba(245,247,255,.65);font-size:12px}}
.acard{{border:1px solid rgba(255,255,255,.12);background:rgba(255,255,255,.04);border-radius:16px;padding:14px;margin:12px 0}}
.atop{{display:flex;justify-content:space-between;gap:10px;flex-wrap:wrap}}
.amsg{{white-space:pre-wrap;word-break:break-word;margin:10px 0 0}}
</style>
</head><body><div class="wrap">
<h1>Admin Inbox</h1>
<div class="muted">Showing last {len(items)} messages • File: <code>{escape_html(contact_log)}</code></div>
{''.join(items_html)}
</div></body></html>"""
        return Response(html, mimetype="text/html")

    @app.get("/")
    def home():
        copy_source_images()
        images = list_static_images()
        hero = images[0] if images else None
        return Response(render_home(site_title, images, hero), mimetype="text/html")

    @app.errorhandler(404)
    def not_found(_):
        return Response(render_404(site_title), status=404, mimetype="text/html")

    print("\n✅ Vaayu Portfolio ready")
    print(f"➡️  Open: http://{host}:{port}")
    print("📸 Put photos in: .\\source_images\\  (refresh after adding)")
    if admin_token:
        print(f"🔐 Admin: http://{host}:{port}/admin?token=YOUR_TOKEN")
    print("")
    return app


def render_404(title: str) -> str:
    return f"""<!doctype html>
<html><head><meta charset="utf-8"/><meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>{escape_html(title)}</title>
<style>
body{{margin:0;background:#070a12;color:#f5f7ff;font-family:Arial,sans-serif;display:grid;place-items:center;height:100vh;padding:20px}}
.card{{max-width:720px;width:100%;border:1px solid rgba(255,255,255,.12);border-radius:20px;background:rgba(255,255,255,.04);padding:22px}}
a{{display:inline-block;margin-top:12px;padding:10px 14px;border-radius:14px;background:#fff;color:#0b0f19;font-weight:900;text-decoration:none}}
.muted{{color:rgba(245,247,255,.7)}}
</style></head><body>
<div class="card">
<h1>404</h1>
<div class="muted">This page ran away to fetch a ball.</div>
<a href="/">Go Home</a>
</div>
</body></html>"""


def render_home(title: str, images: List[str], hero: str | None) -> str:
    # Gallery cards with cute captions ONLY
    gallery_cards: List[str] = []
    if not images:
        gallery_cards.append(card_placeholder("Add Vaayu photos to .\\source_images\\"))
    else:
        for i, src in enumerate(images[:24]):
            cap = cute_caption(i)
            gallery_cards.append(card_image(src, cap["title"], cap["sub"]))

    hero_img = hero or ""

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<meta name="theme-color" content="#0b0f19"/>
<title>{escape_html(title)}</title>

<style>
:root{{
  --bg:#070a12; --text:#f5f7ff; --muted:rgba(245,247,255,.72);
  --line:rgba(255,255,255,.10); --shadow: 0 12px 40px rgba(0,0,0,.55);
  --r:18px; --r2:26px; --max:1150px;
}}
*{{box-sizing:border-box}}
html,body{{height:100%}}
body{{
  margin:0; font-family: ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Arial;
  color:var(--text);
  background:
    radial-gradient(900px 500px at 20% 10%, rgba(120,165,255,.12), transparent 60%),
    radial-gradient(800px 450px at 80% 0%, rgba(255,255,255,.08), transparent 60%),
    linear-gradient(180deg, var(--bg), #060815 80%);
}}
a{{color:inherit;text-decoration:none}}
.page{{max-width:var(--max); margin:0 auto; padding:0 18px 80px}}
.muted{{color:var(--muted)}}
code,kbd{{background:rgba(255,255,255,.06); padding:.15rem .35rem; border-radius:10px; border:1px solid var(--line)}}
kbd{{padding:.12rem .35rem}}

header.nav{{
  position:sticky; top:0; z-index:50; backdrop-filter: blur(10px);
  background: linear-gradient(180deg, rgba(7,10,18,.85), rgba(7,10,18,.35));
  border-bottom:1px solid var(--line);
}}
.navInner{{max-width:var(--max); margin:0 auto; display:flex; align-items:center; justify-content:space-between; padding:14px 18px}}
.brand{{display:flex; align-items:center; gap:10px}}
.dot{{width:12px; height:12px; border-radius:999px; background: linear-gradient(135deg,#fff,#9fb7ff); box-shadow:0 0 22px rgba(160,190,255,.35)}}
.brandName{{font-weight:1100}}
.brandTag{{font-size:12px; color:var(--muted); display:none}}
@media(min-width:820px){{ .brandTag{{display:inline-block}} }}
.links{{display:none; gap:18px}}
.links a{{font-weight:900; color:var(--muted)}}
.links a:hover{{color:var(--text)}}
@media(min-width:820px){{ .links{{display:flex}} }}

.hamburger{{width:44px; height:42px; border-radius:14px; border:1px solid var(--line); background:rgba(255,255,255,.04);
display:flex; flex-direction:column; justify-content:center; gap:5px; padding:0 12px; cursor:pointer}}
.hamburger span{{height:2px; background:rgba(255,255,255,.75); border-radius:10px}}
@media(min-width:820px){{ .hamburger{{display:none}} }}

.drawer{{position:fixed; inset:0; pointer-events:none}}
.drawer[aria-hidden="false"]{{pointer-events:auto}}
.drawerBackdrop{{position:absolute; inset:0; background:rgba(0,0,0,.55); opacity:0; transition:opacity .22s ease}}
.drawer[aria-hidden="false"] .drawerBackdrop{{opacity:1}}
.drawerPanel{{position:absolute; right:0; top:0; height:100%; width:min(380px,86vw); background:rgba(11,15,25,.94);
border-left:1px solid var(--line); transform:translateX(100%); transition:transform .22s ease; padding:18px}}
.drawer[aria-hidden="false"] .drawerPanel{{transform:translateX(0)}}
.drawerTop{{display:flex; align-items:center; justify-content:space-between; margin-bottom:12px}}
.drawerTitle{{font-weight:1100}}
.drawerClose{{width:40px; height:40px; border-radius:14px; border:1px solid var(--line); background:rgba(255,255,255,.05); color:var(--text); cursor:pointer}}
.drawerLink{{display:block; padding:14px 12px; border-radius:14px; border:1px solid transparent; color:var(--muted); font-weight:1000}}
.drawerLink:hover{{border-color:var(--line); background:rgba(255,255,255,.04); color:var(--text)}}

.hero{{position:relative; border-radius: var(--r2); overflow:hidden; margin:18px 0 0; border:1px solid var(--line); box-shadow:var(--shadow)}}
.heroBg{{position:absolute; inset:0}}
.heroImg{{position:absolute; inset:0; width:100%; height:100%; object-fit:cover; filter:brightness(.72) saturate(1.05)}}
.heroFallback{{position:absolute; inset:0; background:
  radial-gradient(900px 520px at 20% 25%, rgba(160,190,255,.20), transparent 60%),
  radial-gradient(800px 480px at 80% 15%, rgba(255,255,255,.11), transparent 55%),
  linear-gradient(180deg, rgba(15,21,35,.95), rgba(7,10,18,.96));
}}
.heroContent{{position:relative; z-index:2; padding:clamp(26px,5vw,56px); min-height:560px; display:flex; flex-direction:column; justify-content:flex-end}}
.kicker{{display:inline-flex; align-self:flex-start; padding:8px 12px; border-radius:999px; border:1px solid var(--line);
background:rgba(255,255,255,.06); color:rgba(255,255,255,.88); font-weight:1000; font-size:13px}}
.heroTitle{{font-size:clamp(44px,6vw,78px); line-height:1.02; margin:14px 0 10px; letter-spacing:-.8px; font-weight:1200}}
.heroSub{{max-width:60ch; color:rgba(245,247,255,.82); font-size:clamp(15px,2vw,18px); line-height:1.5; margin:0 0 18px}}
.heroCtas{{display:flex; gap:12px; flex-wrap:wrap}}
.btn{{display:inline-flex; align-items:center; justify-content:center; padding:12px 16px; border-radius:16px;
border:1px solid rgba(255,255,255,.22); background:rgba(255,255,255,.92); color:#0b0f19; font-weight:1100; cursor:pointer;
transition: transform .14s ease}}
.btn:hover{{transform:translateY(-1px)}}
.btn.ghost{{background:rgba(255,255,255,.06); color:var(--text); border-color: rgba(255,255,255,.16)}}
.btn.small{{padding:10px 12px; border-radius:14px}}
.stats{{display:grid; gap:10px; grid-template-columns: repeat(3, minmax(0,1fr)); margin-top:18px; max-width:560px}}
.stat{{padding:12px; border-radius:16px; border:1px solid var(--line); background:rgba(11,15,25,.55)}}
.statNum{{font-size:22px; font-weight:1200}}
.statLabel{{font-size:12px; color:var(--muted)}}

.section{{padding:60px 0 0}}
.sectionHead h2{{margin:0 0 10px; font-size:32px; letter-spacing:-.3px}}
.sectionHead p{{margin:0}}

.grid{{display:grid; gap:14px; grid-template-columns:1fr; margin-top:18px}}
@media(min-width:720px){{ .grid{{grid-template-columns: repeat(2,1fr)}} }}
@media(min-width:1060px){{ .grid{{grid-template-columns: repeat(3,1fr)}} }}

.card{{border-radius: var(--r); overflow:hidden; border:1px solid var(--line); background:rgba(255,255,255,.03);
box-shadow: 0 10px 30px rgba(0,0,0,.25); cursor:pointer}}
.cardImg{{width:100%; height:260px; object-fit:cover; display:block; filter:saturate(1.05)}}
.cap{{padding:12px}}
.capTitle{{font-weight:1200}}
.capSub{{font-size:12px; color:var(--muted)}}

.pillGrid{{display:grid; gap:12px; margin-top:18px; grid-template-columns:1fr}}
@media(min-width:900px){{ .pillGrid{{grid-template-columns: repeat(4,1fr)}} }}
.pillCard{{border:1px solid var(--line); background: rgba(255,255,255,.03); border-radius: var(--r); padding:14px}}
.pillTitle{{font-weight:1200}}
.pillBody{{color:var(--muted); font-size:13px; margin-top:6px}}

.games{{display:grid; gap:14px; margin-top:18px}}
.game{{border:1px solid var(--line); background: rgba(255,255,255,.03); border-radius: var(--r2); overflow:hidden}}
.gameHead{{padding:16px 16px 0}}
.gameBody{{padding:16px}}
.row{{display:flex; gap:10px; align-items:center; flex-wrap:wrap}}
.scorePill{{padding:10px 12px; border-radius:999px; border:1px solid var(--line); background:rgba(255,255,255,.05); font-weight:1100}}

.stage{{position:relative; margin-top:14px; border-radius: var(--r2); border:1px solid var(--line);
background: linear-gradient(180deg, rgba(15,21,35,.55), rgba(11,15,25,.35)); height: 360px; display:flex; align-items:center; justify-content:center; overflow:hidden}}
.stageGlow{{position:absolute; inset:-40%; background: radial-gradient(circle at 40% 30%, rgba(160,190,255,.20), transparent 55%); filter: blur(10px)}}

.spinAvatar {{
  width: 240px; height: 240px; border-radius: 999px;
  border: 1px solid rgba(255,255,255,.18);
  background: rgba(0,0,0,.18);
  overflow: hidden;
  box-shadow: 0 12px 30px rgba(0,0,0,.35);
  display:grid; place-items:center;
}}
.spinAvatar img{{width:100%;height:100%;object-fit:cover; display:block}}

.fetchArena{{position:relative; margin-top:14px; border-radius: var(--r2); border:1px solid var(--line);
background: linear-gradient(180deg, rgba(15,21,35,.55), rgba(11,15,25,.35)); height: 280px; overflow:hidden}}
.ground{{position:absolute; left:0; right:0; bottom:0; height:72px; background: linear-gradient(180deg, rgba(255,255,255,.10), rgba(255,255,255,.02));
border-top:1px solid rgba(255,255,255,.08)}}
.ball{{position:absolute; left:70px; bottom:60px; font-size:28px; will-change: transform; cursor:pointer}}
.dog{{position:absolute; left:30px; bottom:44px; font-size:30px; will-change: transform;}}
.flag{{position:absolute; right:30px; bottom:48px; font-size:26px; opacity:.95}}

.canvas{{width:100%; border-radius: var(--r2); border:1px solid var(--line); background: rgba(0,0,0,.18); margin-top:14px}}

.cardWide{{border:1px solid var(--line); background: rgba(255,255,255,.03); border-radius: var(--r2); padding:16px; margin-top:18px}}
.form{{display:flex; flex-direction:column; gap:12px}}
.formRow{{display:grid; gap:12px; grid-template-columns:1fr}}
@media(min-width:820px){{ .formRow{{grid-template-columns:1fr 1fr}} }}
label span{{display:block; font-size:12px; color:var(--muted); margin-bottom:8px; font-weight:1200}}
input, textarea, select{{width:100%; padding:12px; border-radius:14px; border:1px solid rgba(255,255,255,.12); background: rgba(0,0,0,.18); color: var(--text); outline:none}}
textarea{{min-height:120px; resize:vertical}}
.toast{{min-height:20px; font-weight:1200}}
.toast.ok{{color:rgba(170,255,210,.92)}}
.toast.bad{{color:rgba(255,190,190,.92)}}

.modal{{position:fixed; inset:0; display:none}}
.modal[aria-hidden="false"]{{display:block}}
.modalBackdrop{{position:absolute; inset:0; background: rgba(0,0,0,.65)}}
.modalPanel{{position:absolute; left:50%; top:50%; transform: translate(-50%, -50%); width: min(980px, 92vw); max-height: 88vh;
border-radius: var(--r2); border:1px solid var(--line); background: rgba(11,15,25,.95); box-shadow: var(--shadow); padding: 14px; display:flex; flex-direction:column; gap:10px}}
.modalClose{{align-self:flex-end; width:44px; height:42px; border-radius:14px; border:1px solid var(--line); background: rgba(255,255,255,.05); color: var(--text); cursor:pointer}}
.modalImg{{width:100%; max-height:72vh; object-fit:contain; border-radius:16px; border:1px solid rgba(255,255,255,.10)}}

footer{{border-top:1px solid var(--line); background: rgba(7,10,18,.55); margin-top:60px}}
.footerInner{{max-width:var(--max); margin:0 auto; padding:20px 18px; display:flex; justify-content:space-between; align-items:center; gap:12px; flex-wrap:wrap}}
.footerTitle{{font-weight:1200}}
</style>
</head>

<body>
<header class="nav">
  <div class="navInner">
    <a class="brand" href="#top">
      <span class="dot"></span>
      <span class="brandName">Vaayu</span>
      <span class="brandTag">Border Collie • Brand Ambassador • Performer</span>
    </a>

    <nav class="links">
      <a href="#portfolio">Portfolio</a>
      <a href="#skills">Skills</a>
      <a href="#games">Games</a>
      <a href="#book">Book</a>
    </nav>

    <button class="hamburger" id="hamburger" aria-label="Open menu" aria-expanded="false">
      <span></span><span></span><span></span>
    </button>
  </div>

  <div class="drawer" id="drawer" aria-hidden="true">
    <div class="drawerPanel">
      <div class="drawerTop">
        <div class="drawerTitle">Menu</div>
        <button class="drawerClose" id="drawerClose" aria-label="Close menu">✕</button>
      </div>
      <a class="drawerLink" href="#portfolio">Portfolio</a>
      <a class="drawerLink" href="#skills">Skills</a>
      <a class="drawerLink" href="#games">Games</a>
      <a class="drawerLink" href="#book">Book Vaayu</a>
    </div>
    <div class="drawerBackdrop" id="drawerBackdrop"></div>
  </div>
</header>

<main class="page" id="top">
  <section class="hero">
    <div class="heroBg">
      {("<img class='heroImg' src='" + escape_html(hero_img) + "' alt='Vaayu hero'>") if hero_img else ""}
      <div class="heroFallback"></div>
    </div>

    <div class="heroContent">
      <div class="kicker">✨ Food Brands • Toy Brands • Ads • UGC</div>
      <div class="heroTitle">Vaayu</div>
      <div class="heroSub">
        Smart, athletic, expressive, and camera-confident — a Border Collie built for premium pet campaigns.
      </div>

      <div class="heroCtas">
        <a class="btn" href="#book">Work With Vaayu</a>
        <a class="btn ghost" href="#games">Play the Games</a>
        <a class="btn ghost" href="/media-kit" target="_blank" rel="noopener">Media Kit JSON</a>
      </div>

      <div class="stats">
        <div class="stat"><div class="statNum">A+</div><div class="statLabel">Trainability</div></div>
        <div class="stat"><div class="statNum">3</div><div class="statLabel">Mini games</div></div>
        <div class="stat"><div class="statNum">∞</div><div class="statLabel">Cuteness</div></div>
      </div>
    </div>
  </section>

  <section class="section" id="portfolio">
    <div class="sectionHead">
      <h2>Portfolio</h2>
      <p class="muted">Gallery shows cute titles only — no filenames. Click any photo to zoom.</p>
    </div>

    <div class="grid" id="galleryGrid">
      {''.join(gallery_cards)}
    </div>
  </section>

  <section class="section" id="skills">
    <div class="sectionHead">
      <h2>Brand Ambassador Fit</h2>
      <p class="muted">Perfect for food brands + toy brands — repeatable cues + expressive visuals.</p>
    </div>

    <div class="pillGrid">
      <div class="pillCard"><div class="pillTitle">Food / Treats</div><div class="pillBody">Great “wait / take / release” shots + tasting reels</div></div>
      <div class="pillCard"><div class="pillTitle">Toys</div><div class="pillBody">Fetch energy + focus = perfect product demos</div></div>
      <div class="pillCard"><div class="pillTitle">Trainability</div><div class="pillBody">Repeatable performance for multiple takes</div></div>
      <div class="pillCard"><div class="pillTitle">Camera Confidence</div><div class="pillBody">Eye contact + expressive face</div></div>
    </div>
  </section>

  <section class="section" id="games">
    <div class="sectionHead">
      <h2>Interactive Games</h2>
      <p class="muted">Fun mini-games that showcase Vaayu’s personality and skill.</p>
    </div>

    <div class="games">
      <!-- SPIN POWER GAME (momentum) -->
      <div class="game">
        <div class="gameHead">
          <h3>Spin Power 🌀</h3>
          <p class="muted">Click “Boost Spin” rapidly to build momentum. Combo increases at high speed.</p>
        </div>
        <div class="gameBody">
          <div class="row">
            <button class="btn small" id="spinBoostBtn">Boost Spin</button>
            <button class="btn small ghost" id="spinResetBtn">Reset</button>
            <div class="scorePill" id="spinPower">Power: 0</div>
            <div class="scorePill" id="spinCombo">Combo: 0</div>
          </div>

          <div class="stage">
            <div class="spinAvatar" id="spinAvatar">
              {("<img id='spinAvatarImg' src='" + escape_html(hero_img) + "' alt='Vaayu'>") if hero_img else "<div style='font-size:64px'>🐾</div>"}
            </div>
            <div class="stageGlow"></div>
          </div>
        </div>
      </div>

      <!-- FETCH -->
      <div class="game">
        <div class="gameHead">
          <h3>Fetch 🎾</h3>
          <p class="muted">Throw the ball. Vaayu runs. Score increases.</p>
        </div>
        <div class="gameBody">
          <div class="row">
            <button class="btn small" id="throwBtn">Throw Ball</button>
            <button class="btn small ghost" id="resetFetchBtn">Reset</button>
            <div class="scorePill" id="fetchScore">Fetch: 0</div>
          </div>

          <div class="fetchArena" id="fetchArena">
            <div class="ground"></div>
            <div class="ball" id="ball">🎾</div>
            <div class="dog" id="dog">🐶</div>
            <div class="flag" id="flag">🏁</div>
          </div>
        </div>
      </div>

      <!-- HERD -->
      <div class="game">
        <div class="gameHead">
          <h3>Herding 🐑</h3>
          <p class="muted">Click the canvas, then use arrows/WASD. Page won’t scroll while playing.</p>
        </div>
        <div class="gameBody">
          <div class="row">
            <button class="btn small" id="herdStartBtn">Start</button>
            <button class="btn small ghost" id="herdResetBtn">Reset</button>
            <div class="scorePill" id="herdScore">In Pen: 0</div>
          </div>

          <canvas class="canvas" id="herdCanvas" width="900" height="420" tabindex="0"></canvas>

          <div class="muted" style="margin-top:10px;font-size:12px">
            Tip: Click inside the canvas first to capture arrow keys.
          </div>
        </div>
      </div>
    </div>
  </section>

  <section class="section" id="book">
    <div class="sectionHead">
      <h2>Contact / Brand Inquiry</h2>
      <p class="muted">For food brands, toy brands, ads, UGC, and show inquiries.</p>
    </div>

    <div class="cardWide">
      <form id="contactForm" class="form" autocomplete="on">
        <div class="formRow">
          <label><span>Name</span><input name="name" required minlength="2" placeholder="Your name"></label>
          <label><span>Email</span><input name="email" type="email" required placeholder="you@brand.com"></label>
        </div>

        <label>
          <span>Purpose</span>
          <select name="purpose">
            <option>Brand Inquiry</option>
            <option>Food Brand</option>
            <option>Toy Brand</option>
            <option>Show Inquiry</option>
            <option>Advertisement</option>
            <option>Collaboration</option>
          </select>
        </label>

        <label><span>Message</span><textarea name="message" required minlength="10" maxlength="2000" placeholder="Tell us about deliverables, dates, usage rights…"></textarea></label>

        <div class="row">
          <button class="btn" type="submit" id="contactSubmit">Send Request</button>
          <div class="toast" id="toast"></div>
        </div>

        <div class="muted" style="margin-top:6px;font-size:12px">
          Local mode: saved to <code>data/contact_messages.jsonl</code>
        </div>
      </form>
    </div>
  </section>
</main>

<!-- Modal -->
<div class="modal" id="modal" aria-hidden="true">
  <div class="modalBackdrop" id="modalBackdrop"></div>
  <div class="modalPanel">
    <button class="modalClose" id="modalClose">✕</button>
    <img class="modalImg" id="modalImg" alt="Vaayu photo"/>
    <div class="muted" style="font-size:12px">Tip: press Esc to close</div>
  </div>
</div>

<footer>
  <div class="footerInner">
    <div>
      <div class="footerTitle">Vaayu</div>
      <div class="muted">Brand-ready • Camera-confident • Smart & gentle</div>
    </div>
    <div class="row">
      <a class="btn small" href="#book">Contact</a>
      <a class="btn small ghost" href="#games">Play</a>
    </div>
  </div>
</footer>

<script>
/* NAV */
(() => {
  const $ = (id) => document.getElementById(id);
  const drawer = $("drawer");
  const hamburger = $("hamburger");
  const drawerClose = $("drawerClose");
  const drawerBackdrop = $("drawerBackdrop");

  function openDrawer() {
    drawer.setAttribute("aria-hidden","false");
    hamburger.setAttribute("aria-expanded","true");
    document.body.style.overflow = "hidden";
  }
  function closeDrawer() {
    drawer.setAttribute("aria-hidden","true");
    hamburger.setAttribute("aria-expanded","false");
    document.body.style.overflow = "";
  }

  hamburger?.addEventListener("click", () => {
    const isHidden = drawer.getAttribute("aria-hidden") !== "false";
    isHidden ? openDrawer() : closeDrawer();
  });
  drawerClose?.addEventListener("click", closeDrawer);
  drawerBackdrop?.addEventListener("click", closeDrawer);

  drawer?.addEventListener("click", (e) => {
    const t = e.target;
    if (t && t.classList && t.classList.contains("drawerLink")) closeDrawer();
  });

  document.addEventListener("click", (e) => {
    const a = e.target.closest?.("a[href^='#']");
    if (!a) return;
    const href = a.getAttribute("href");
    if (!href || href === "#") return;
    const el = document.querySelector(href);
    if (!el) return;
    e.preventDefault();
    el.scrollIntoView({ behavior: "smooth", block: "start" });
  });
})();

/* GALLERY MODAL */
(() => {
  const modal = document.getElementById("modal");
  const modalImg = document.getElementById("modalImg");
  const modalBackdrop = document.getElementById("modalBackdrop");
  const modalClose = document.getElementById("modalClose");
  const grid = document.getElementById("galleryGrid");

  function open(src) {
    modal.setAttribute("aria-hidden","false");
    modalImg.src = src;
    document.body.style.overflow = "hidden";
  }
  function close() {
    modal.setAttribute("aria-hidden","true");
    modalImg.src = "";
    document.body.style.overflow = "";
  }

  grid?.addEventListener("click", (e) => {
    const img = e.target.closest?.("img.cardImg");
    if (!img) return;
    open(img.dataset.full || img.src);
  });

  modalBackdrop?.addEventListener("click", close);
  modalClose?.addEventListener("click", close);
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && modal.getAttribute("aria-hidden") === "false") close();
  });
})();

/* SPIN POWER (momentum spinner) */
(() => {
  const avatar = document.getElementById("spinAvatar");
  const boostBtn = document.getElementById("spinBoostBtn");
  const resetBtn = document.getElementById("spinResetBtn");
  const powerEl = document.getElementById("spinPower");
  const comboEl = document.getElementById("spinCombo");
  if (!avatar) return;

  let angle = 0;
  let omega = 0;
  let combo = 0;
  let lastBoost = 0;

  function boost() {
    const now = performance.now();
    const dt = now - lastBoost;
    lastBoost = now;

    const clickBonus = dt < 250 ? 1.25 : (dt < 450 ? 1.0 : 0.85);
    omega += 0.30 * clickBonus;

    if (Math.abs(omega) > 1.0) combo += 1;
    else combo = 0;

    comboEl.textContent = "Combo: " + combo;
    avatar.animate(
      [{ transform: "scale(1)" }, { transform: "scale(1.03)" }, { transform: "scale(1)" }],
      { duration: 200, easing: "cubic-bezier(.2,.9,.2,1)" }
    );
  }

  function reset() {
    angle = 0;
    omega = 0;
    combo = 0;
    powerEl.textContent = "Power: 0";
    comboEl.textContent = "Combo: 0";
    avatar.style.transform = "rotate(0rad)";
  }

  boostBtn?.addEventListener("click", boost);
  avatar?.addEventListener("click", boost);
  resetBtn?.addEventListener("click", reset);

  function tick() {
    omega *= 0.985;                 // friction
    if (Math.abs(omega) < 0.002) omega = 0;
    angle += omega;

    avatar.style.transform = `rotate(${angle}rad)`;
    const power = Math.floor(Math.min(999, Math.abs(omega) * 120));
    powerEl.textContent = "Power: " + power;

    requestAnimationFrame(tick);
  }
  requestAnimationFrame(tick);
})();

/* FETCH */
(() => {
  const throwBtn = document.getElementById("throwBtn");
  const resetFetchBtn = document.getElementById("resetFetchBtn");
  const ball = document.getElementById("ball");
  const dog = document.getElementById("dog");
  const arena = document.getElementById("fetchArena");
  const fetchScoreEl = document.getElementById("fetchScore");

  let score = 0;
  let isThrowing = false;

  function setTransform(el, x, y) { el.style.transform = `translate(${x}px, ${y}px)`; }
  function reset() {
    isThrowing = false;
    setTransform(ball, 0, 0);
    setTransform(dog, 0, 0);
  }

  function throwBall() {
    if (!arena || !ball || !dog || isThrowing) return;
    isThrowing = true;

    const w = arena.clientWidth;
    const targetX = Math.max(240, w - 210);
    const arcTop = -120;

    ball.animate(
      [
        { transform: "translate(0px, 0px)" },
        { transform: `translate(${targetX * 0.55}px, ${arcTop}px)` },
        { transform: `translate(${targetX}px, 0px)` }
      ],
      { duration: 900, easing: "cubic-bezier(.2,.9,.2,1)" }
    );
    setTimeout(() => setTransform(ball, targetX, 0), 880);

    dog.animate(
      [
        { transform: "translate(0px, 0px)" },
        { transform: `translate(${targetX}px, 0px)` },
        { transform: "translate(0px, 0px)" }
      ],
      { duration: 1650, easing: "cubic-bezier(.2,.9,.2,1)" }
    );

    setTimeout(() => {
      score += 1;
      fetchScoreEl.textContent = "Fetch: " + score;
      reset();
    }, 1700);
  }

  throwBtn?.addEventListener("click", throwBall);
  resetFetchBtn?.addEventListener("click", reset);
  ball?.addEventListener("click", throwBall);
})();

/* HERDING: Vaayu photo + sheep emoji + prevent arrow scroll when focused */
(() => {
  const startBtn = document.getElementById("herdStartBtn");
  const resetBtn = document.getElementById("herdResetBtn");
  const scoreEl = document.getElementById("herdScore");
  const canvas = document.getElementById("herdCanvas");
  if (!canvas) return;

  const ctx = canvas.getContext("2d");
  const W = canvas.width, H = canvas.height;
  const pen = { x: W - 170, y: H/2 - 90, w: 140, h: 180 };

  // Load Vaayu image directly (no hidden <img> required)
  const vaayuSrc = {json.dumps(hero_img)};  // injected by Python
  const vaayuImg = new Image();
  if (vaayuSrc) vaayuImg.src = vaayuSrc;

  // Only capture arrow keys while canvas is active
  let herdActiveKeys = false;
  canvas.addEventListener("mouseenter", () => herdActiveKeys = true);
  canvas.addEventListener("mouseleave", () => herdActiveKeys = false);
  canvas.addEventListener("focus", () => herdActiveKeys = true);
  canvas.addEventListener("blur", () => herdActiveKeys = false);
  canvas.addEventListener("click", () => canvas.focus());

  const keys = new Set();
  const SCROLL_KEYS = new Set(["arrowup","arrowdown","arrowleft","arrowright"," "]);

  document.addEventListener("keydown", (e) => {
    const k = (e.key || "").toLowerCase();
    if (herdActiveKeys && SCROLL_KEYS.has(k)) e.preventDefault(); // ✅ no page scroll
    keys.add(k);
  }, { passive: false });

  document.addEventListener("keyup", (e) => {
    keys.delete((e.key || "").toLowerCase());
  });

  function clamp(v, a, b) { return Math.max(a, Math.min(b, v)); }
  function dist(ax, ay, bx, by) { const dx=ax-bx, dy=ay-by; return Math.hypot(dx,dy); }

  const state = {
    running: false,
    inPen: 0,
    vaayu: { x: 120, y: H/2, r: 22, speed: 3.8 },
    sheep: []
  };

  function makeSheep(n=5) {
    const arr = [];
    for (let i=0;i<n;i++){
      arr.push({
        x: 280 + Math.random()*260,
        y: 80 + Math.random()*(H-160),
        r: 16,
        vx: (Math.random()*2-1)*1.2,
        vy: (Math.random()*2-1)*1.2,
        inPen: false
      });
    }
    return arr;
  }

  function reset() {
    state.running = false;
    state.inPen = 0;
    state.vaayu.x = 120; state.vaayu.y = H/2;
    state.sheep = makeSheep(5);
    scoreEl.textContent = "In Pen: 0";
    draw();
  }

  function updateVaayu() {
    const v = state.vaayu;
    let dx=0, dy=0;
    const up = keys.has("w") || keys.has("arrowup");
    const down = keys.has("s") || keys.has("arrowdown");
    const left = keys.has("a") || keys.has("arrowleft");
    const right = keys.has("d") || keys.has("arrowright");

    if (up) dy -= 1;
    if (down) dy += 1;
    if (left) dx -= 1;
    if (right) dx += 1;

    if (dx || dy) {
      const len = Math.hypot(dx, dy);
      dx /= len; dy /= len;
      v.x += dx * v.speed;
      v.y += dy * v.speed;
    }

    v.x = clamp(v.x, v.r + 8, W - v.r - 8);
    v.y = clamp(v.y, v.r + 8, H - v.r - 8);
  }

  function updateSheep() {
    const v = state.vaayu;
    for (const s of state.sheep) {
      if (s.inPen) continue;

      const d = dist(s.x, s.y, v.x, v.y);
      if (d < 170) {
        const fx = (s.x - v.x) / (d + 0.0001);
        const fy = (s.y - v.y) / (d + 0.0001);
        s.vx += fx * 0.20;
        s.vy += fy * 0.20;
      } else {
        s.vx += (Math.random()*2 - 1) * 0.03;
        s.vy += (Math.random()*2 - 1) * 0.03;
      }

      const maxV = 2.2;
      const vlen = Math.hypot(s.vx, s.vy);
      if (vlen > maxV) { s.vx = (s.vx/vlen)*maxV; s.vy = (s.vy/vlen)*maxV; }

      s.x += s.vx; s.y += s.vy;

      if (s.x < s.r + 8) { s.x = s.r + 8; s.vx *= -0.8; }
      if (s.x > W - s.r - 8) { s.x = W - s.r - 8; s.vx *= -0.8; }
      if (s.y < s.r + 8) { s.y = s.r + 8; s.vy *= -0.8; }
      if (s.y > H - s.r - 8) { s.y = H - s.r - 8; s.vy *= -0.8; }

      const inside = s.x > pen.x && s.x < pen.x + pen.w && s.y > pen.y && s.y < pen.y + pen.h;
      if (inside) {
        s.inPen = true;
        state.inPen += 1;
        scoreEl.textContent = "In Pen: " + state.inPen;
      }
    }
  }

  function roundRect(x, y, w, h, r){
    const rr = Math.min(r, w/2, h/2);
    ctx.beginPath();
    ctx.moveTo(x+rr, y);
    ctx.arcTo(x+w, y, x+w, y+h, rr);
    ctx.arcTo(x+w, y+h, x, y+h, rr);
    ctx.arcTo(x, y+h, x, y, rr);
    ctx.arcTo(x, y, x+w, y, rr);
    ctx.closePath();
  }

  function drawVaayuPhoto(x, y, r){
    if (!vaayuSrc || !vaayuImg.complete || vaayuImg.naturalWidth === 0) {
      ctx.save(); ctx.font = "28px Arial"; ctx.fillText("🐶", x-14, y+12); ctx.restore();
      return;
    }
    ctx.save();
    ctx.beginPath();
    ctx.arc(x, y, r, 0, Math.PI*2);
    ctx.clip();
    const size = r * 2.2;
    ctx.drawImage(vaayuImg, x - size/2, y - size/2, size, size);
    ctx.restore();

    ctx.save();
    ctx.strokeStyle = "rgba(160,190,255,0.8)";
    ctx.lineWidth = 2;
    ctx.beginPath(); ctx.arc(x, y, r, 0, Math.PI*2); ctx.stroke();
    ctx.restore();
  }

  function draw(){
    ctx.clearRect(0,0,W,H);

    // grid
    ctx.save();
    ctx.globalAlpha = 0.08;
    ctx.strokeStyle = "#ffffff";
    for (let x=0;x<W;x+=40){ ctx.beginPath(); ctx.moveTo(x,0); ctx.lineTo(x,H); ctx.stroke(); }
    for (let y=0;y<H;y+=40){ ctx.beginPath(); ctx.moveTo(0,y); ctx.lineTo(W,y); ctx.stroke(); }
    ctx.restore();

    // pen
    ctx.save();
    ctx.fillStyle = "rgba(160,190,255,0.10)";
    ctx.strokeStyle = "rgba(160,190,255,0.45)";
    ctx.lineWidth = 2;
    roundRect(pen.x, pen.y, pen.w, pen.h, 16);
    ctx.fill(); ctx.stroke();
    ctx.fillStyle = "rgba(245,247,255,0.75)";
    ctx.font = "900 14px Arial";
    ctx.fillText("PEN", pen.x + 12, pen.y + 24);
    ctx.restore();

    // vaayu
    drawVaayuPhoto(state.vaayu.x, state.vaayu.y, state.vaayu.r);

    // sheep emoji sprites
    for (const s of state.sheep){
      ctx.save();
      ctx.font = "28px Arial";
      ctx.globalAlpha = s.inPen ? 0.85 : 1.0;
      ctx.fillText("🐑", s.x - 14, s.y + 12);
      ctx.restore();
    }

    if (state.inPen >= 5){
      ctx.save();
      ctx.fillStyle = "rgba(170,255,210,0.95)";
      ctx.font = "1000 28px Arial";
      ctx.fillText("Vaayu wins! 🐾", 26, 42);
      ctx.restore();
    }
  }

  function loop(){
    if (!state.running) return;
    updateVaayu();
    updateSheep();
    draw();
    requestAnimationFrame(loop);
  }

  startBtn?.addEventListener("click", () => {
    if (!state.running){
      state.running = true;
      loop();
    }
  });
  resetBtn?.addEventListener("click", reset);

  vaayuImg.onload = () => draw();
  reset();
})();

/* CONTACT */
(() => {
  const form = document.getElementById("contactForm");
  const toast = document.getElementById("toast");
  const submit = document.getElementById("contactSubmit");
  if (!form) return;

  function setToast(msg, ok=true){
    toast.textContent = msg;
    toast.classList.remove("ok","bad");
    toast.classList.add(ok ? "ok" : "bad");
  }

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    submit.disabled = true;

    const fd = new FormData(form);
    const payload = {
      name: String(fd.get("name") || ""),
      email: String(fd.get("email") || ""),
      purpose: String(fd.get("purpose") || "Brand Inquiry"),
      message: String(fd.get("message") || "")
    };

    try{
      const res = await fetch("/api/contact", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });

      const data = await res.json().catch(() => ({}));
      if (!res.ok){
        const msg = data?.errors?.join(" ") || data?.error || "Something went wrong.";
        setToast(msg, false);
      } else {
        setToast(data?.message || "Sent!", true);
        form.reset();
      }
    } catch {
      setToast("Network error. Please try again.", false);
    } finally {
      submit.disabled = false;
      setTimeout(() => setToast(""), 4500);
    }
  });
})();
</script>
</body>
</html>
"""


if __name__ == "__main__":
    app = create_app()
    host = os.getenv("HOST", "127.0.0.1")
    port = int(os.getenv("PORT", "5000"))
    env = os.getenv("FLASK_ENV", os.getenv("ENV", "production")).lower()
    debug = env == "development"
    app.run(host=host, port=port, debug=debug)