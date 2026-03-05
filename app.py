from __future__ import annotations

import os
import re
import time
import json
import shutil
import secrets
from typing import List, Dict, Any, Tuple

from flask import Flask, request, jsonify, Response, make_response

APP_TITLE_DEFAULT = "Vaayu | Border Collie — Brand Ambassador"
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def ensure_dirs() -> None:
    os.makedirs("data", exist_ok=True)
    os.makedirs(os.path.join("static", "images"), exist_ok=True)
    os.makedirs("source_images", exist_ok=True)


def copy_source_images() -> None:
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
            pass


def list_static_images() -> List[str]:
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


PORTFOLIO_META = [
    ("Golden Hour Sprint", "Lifestyle • Outdoor Campaigns", "Run, energy, freedom"),
    ("Treat Time ✨", "Food & Treats • Product Ready", "Perfect wait/take shots"),
    ("Close-Up Royale", "Hero Shot • Premium Campaigns", "That expressive face"),
    ("Cozy Brand Moment", "Home & Lifestyle • Soft Vibe", "Approachable warmth"),
    ("Championship Pose", "Obedience • Performance", "Focused, camera-still"),
    ("Adventure Ready", "Outdoor • Athletic Brands", "Confident and bold"),
    ("Snack Star 🌟", "Food Brand Hero", "Every treat brand's dream"),
    ("Show Ring Presence", "Conformation • Balance", "Effortless elegance"),
    ("Zoomies Mode", "Energy Drinks • Active Brands", "Pure joyful momentum"),
    ("The Gentle Giant", "Premium • Calm", "Soulful and trustworthy"),
    ("Coat Showcase", "Grooming Brands • Detail", "Black/white perfection"),
    ("Signature Look", "Iconic • Memorable", "The shot brands remember"),
    ("Fetch Champion", "Toy Brands • Sports", "Ball focus is unmatched"),
    ("Morning Light", "Wellness • Clean Brands", "Soft, bright, gorgeous"),
    ("Focus Mode", "Training • Discipline Brands", "Eye contact mastery"),
    ("Play Ready", "Interactive • Fun Brands", "Inviting and playful"),
]


def cute_caption(i: int) -> Dict[str, str]:
    if i < len(PORTFOLIO_META):
        t, s, tag = PORTFOLIO_META[i]
        return {"title": t, "sub": s, "tag": tag}
    return {"title": f"Vaayu Look #{i+1}", "sub": "Brand-ready • expressive", "tag": "Campaign Ready"}


def card_image(src: str, title: str, sub: str, tag: str, idx: int) -> str:
    delay = idx * 60
    return f"""
<figure class="card" style="animation-delay:{delay}ms" data-idx="{idx}">
  <div class="cardImgWrap">
    <img class="cardImg" data-full="{escape_html(src)}" src="{escape_html(src)}" alt="{escape_html(title)}" loading="lazy">
    <div class="cardOverlay">
      <span class="cardTag">{escape_html(tag)}</span>
      <button class="cardZoom" aria-label="View full size">↗</button>
    </div>
  </div>
  <figcaption class="cap">
    <div class="capTitle">{escape_html(title)}</div>
    <div class="capSub">{escape_html(sub)}</div>
  </figcaption>
</figure>
"""


def card_placeholder(msg: str) -> str:
    safe = escape_html(msg)
    return f"""
<figure class="card card--placeholder">
  <div class="cardImgWrap">
    <div class="placeholderImg">
      <div class="placeholderPaw">🐾</div>
      <div class="placeholderText">{safe}</div>
      <div class="placeholderSub">Drop photos into .\\source_images\\ then refresh</div>
    </div>
  </div>
  <figcaption class="cap">
    <div class="capTitle">Portfolio Loading…</div>
    <div class="capSub">Add photos to activate</div>
  </figcaption>
</figure>
"""


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
    admin_token = os.getenv("ADMIN_TOKEN", "")

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
        resp.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "img-src 'self' data: blob:; "
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
            "font-src 'self' https://fonts.gstatic.com; "
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
        return jsonify({
            "name": "Vaayu",
            "breed": "Border Collie",
            "positioning": "Brand ambassador — food brands, treats, toy brands, pet campaigns, UGC",
            "highlights": ["Camera confident", "Highly trainable", "Expressive face", "Repeatable cues"],
            "assets": {"hero": hero, "gallery": imgs},
            "contact": {"endpoint": "/api/contact"},
        })

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
        budget = str(data.get("budget", "")).strip()

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
            "budget": budget,
            "message": message,
            "ip": ip,
            "user_agent": request.headers.get("User-Agent", ""),
        }
        append_jsonl(contact_log, payload)
        return jsonify({"ok": True, "message": "Thank you! We'll be in touch within 24 hours 🐾"})

    @app.get("/admin")
    def admin():
        if not admin_token:
            return make_response("ADMIN_TOKEN not set.", 403)
        token = request.args.get("token", "")
        if token != admin_token:
            return make_response("Unauthorized.", 401)

        items = read_jsonl(contact_log, limit=100)
        items_html = []
        for it in reversed(items):
            items_html.append(f"""
<div class="acard">
  <div class="atop">
    <div><b>{escape_html(it.get('purpose',''))}</b> — {escape_html(it.get('name',''))} &lt;{escape_html(it.get('email',''))}&gt;</div>
    <div class="muted">{it.get('ts','')} • IP: {escape_html(it.get('ip',''))}</div>
  </div>
  <pre class="amsg">{escape_html(it.get('message',''))}</pre>
</div>""")

        html = f"""<!doctype html>
<html><head><meta charset="utf-8"/><title>Admin | Vaayu</title>
<style>body{{margin:0;background:#070a12;color:#f5f7ff;font-family:sans-serif;padding:22px}}
.muted{{color:rgba(245,247,255,.65);font-size:12px}}
.acard{{border:1px solid rgba(255,255,255,.12);background:rgba(255,255,255,.04);border-radius:16px;padding:14px;margin:12px 0}}
.atop{{display:flex;justify-content:space-between;gap:10px;flex-wrap:wrap}}
.amsg{{white-space:pre-wrap;word-break:break-word;margin:10px 0 0}}
</style></head><body>
<h1>Admin Inbox</h1>
<div class="muted">Last {len(items)} messages</div>
{''.join(items_html)}
</body></html>"""
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

    print("\n✅  Vaayu Portfolio — ready")
    print(f"➡️   Open: http://{host}:{port}")
    print("📸  Drop photos in: .\\source_images\\  (auto-loads on refresh)")
    if admin_token:
        print(f"🔐  Admin: http://{host}:{port}/admin?token=YOUR_TOKEN")
    print()
    return app


def render_404(title: str) -> str:
    return f"""<!doctype html>
<html><head><meta charset="utf-8"/><title>{escape_html(title)}</title>
<style>body{{margin:0;background:#060810;color:#f0f2ff;font-family:sans-serif;display:grid;place-items:center;height:100vh}}
a{{color:#fff;font-weight:900}}</style></head><body>
<div style="text-align:center"><h1 style="font-size:80px;margin:0">404</h1>
<p>This page ran off to fetch a ball.</p><a href="/">← Go Home</a></div>
</body></html>"""


def render_home(title: str, images: List[str], hero: str | None) -> str:
    gallery_cards: List[str] = []
    if not images:
        gallery_cards.append(card_placeholder("No photos yet"))
    else:
        for i, src in enumerate(images[:24]):
            cap = cute_caption(i)
            gallery_cards.append(card_image(src, cap["title"], cap["sub"], cap["tag"], i))

    hero_img = hero or ""
    hero_json = json.dumps(hero_img)

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<meta name="description" content="Vaayu — Border Collie brand ambassador. Available for food brands, toy brands, ads, UGC and campaigns."/>
<meta name="theme-color" content="#060810"/>
<title>{escape_html(title)}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Playfair+Display:ital,wght@0,700;0,900;1,700&family=DM+Sans:wght@300;400;500;700&display=swap" rel="stylesheet">

<style>
/* ─── TOKENS ─────────────────────────────────────────────────── */
:root {{
  --bg: #060810;
  --surface: rgba(255,255,255,.04);
  --border: rgba(255,255,255,.10);
  --text: #f0f2ff;
  --muted: rgba(240,242,255,.60);
  --accent: #c8a96e;   /* warm gold */
  --accent2: #7eb8f7;  /* sky blue */
  --r: 16px;
  --r2: 24px;
  --max: 1200px;
  --shadow: 0 20px 60px rgba(0,0,0,.6);
  --font-display: 'Playfair Display', Georgia, serif;
  --font-body: 'DM Sans', system-ui, sans-serif;
}}
*, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
html {{ scroll-behavior: smooth; }}
body {{
  font-family: var(--font-body);
  background: var(--bg);
  color: var(--text);
  overflow-x: hidden;
  background-image:
    radial-gradient(ellipse 1000px 600px at 10% 0%, rgba(200,169,110,.07) 0%, transparent 60%),
    radial-gradient(ellipse 800px 500px at 90% 20%, rgba(126,184,247,.06) 0%, transparent 55%);
}}
a {{ color: inherit; text-decoration: none; }}
img {{ display: block; }}
button {{ font-family: inherit; cursor: pointer; }}

/* ─── SCROLLBAR ───────────────────────────────────────────────── */
::-webkit-scrollbar {{ width: 6px; background: var(--bg); }}
::-webkit-scrollbar-thumb {{ background: rgba(255,255,255,.15); border-radius: 99px; }}

/* ─── NAV ─────────────────────────────────────────────────────── */
.nav {{
  position: fixed; top: 0; left: 0; right: 0; z-index: 100;
  backdrop-filter: blur(20px) saturate(1.4);
  -webkit-backdrop-filter: blur(20px) saturate(1.4);
  background: linear-gradient(180deg, rgba(6,8,16,.92) 0%, rgba(6,8,16,.60) 100%);
  border-bottom: 1px solid var(--border);
}}
.navInner {{
  max-width: var(--max); margin: 0 auto;
  display: flex; align-items: center; justify-content: space-between;
  padding: 16px 24px;
}}
.brand {{ display: flex; align-items: center; gap: 12px; }}
.brandMark {{
  width: 36px; height: 36px; border-radius: 12px;
  background: linear-gradient(135deg, var(--accent), #a8833a);
  display: grid; place-items: center; font-size: 18px;
  box-shadow: 0 4px 16px rgba(200,169,110,.35);
}}
.brandText {{ font-family: var(--font-display); font-weight: 700; font-size: 20px; letter-spacing: -.3px; }}
.brandSub {{ font-size: 11px; color: var(--muted); letter-spacing: .5px; text-transform: uppercase; }}
.navLinks {{ display: flex; gap: 28px; }}
.navLinks a {{
  font-size: 13px; font-weight: 500; color: var(--muted); letter-spacing: .3px;
  transition: color .2s;
}}
.navLinks a:hover {{ color: var(--text); }}
@media(max-width:760px) {{ .navLinks {{ display: none; }} }}
.navCta {{
  padding: 10px 20px; border-radius: 99px;
  background: var(--accent); color: #0a0800; font-weight: 700; font-size: 13px;
  border: none; transition: transform .15s, box-shadow .15s;
  box-shadow: 0 4px 20px rgba(200,169,110,.30);
}}
.navCta:hover {{ transform: translateY(-1px); box-shadow: 0 8px 28px rgba(200,169,110,.45); }}
.hamburger {{
  display: none; width: 40px; height: 38px; border-radius: 12px;
  border: 1px solid var(--border); background: var(--surface);
  flex-direction: column; justify-content: center; gap: 5px; padding: 0 10px;
}}
.hamburger span {{ height: 1.5px; background: var(--text); border-radius: 99px; }}
@media(max-width:760px) {{ .hamburger {{ display: flex; }} .navCta {{ display: none; }} }}

/* ─── DRAWER ──────────────────────────────────────────────────── */
.drawer {{ position: fixed; inset: 0; pointer-events: none; z-index: 200; }}
.drawer[aria-hidden="false"] {{ pointer-events: auto; }}
.drawerBd {{ position: absolute; inset: 0; background: rgba(0,0,0,.6); opacity: 0; transition: opacity .25s; }}
.drawer[aria-hidden="false"] .drawerBd {{ opacity: 1; }}
.drawerPanel {{
  position: absolute; right: 0; top: 0; height: 100%;
  width: min(340px, 88vw); background: rgba(8,11,20,.97);
  border-left: 1px solid var(--border); padding: 20px;
  transform: translateX(100%); transition: transform .25s cubic-bezier(.4,0,.2,1);
}}
.drawer[aria-hidden="false"] .drawerPanel {{ transform: translateX(0); }}
.drawerTop {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; }}
.drawerClose {{
  width: 38px; height: 38px; border-radius: 12px;
  border: 1px solid var(--border); background: var(--surface); color: var(--text);
}}
.drawerLink {{
  display: block; padding: 14px 12px; border-radius: 14px;
  color: var(--muted); font-weight: 500; transition: all .15s;
}}
.drawerLink:hover {{ background: var(--surface); color: var(--text); }}

/* ─── HERO ────────────────────────────────────────────────────── */
.hero {{
  position: relative; min-height: 100svh; display: flex; flex-direction: column; justify-content: flex-end;
  overflow: hidden; padding-top: 70px;
}}
.heroBg {{
  position: absolute; inset: 0; z-index: 0;
}}
.heroImg {{
  position: absolute; inset: 0; width: 100%; height: 100%;
  object-fit: cover; object-position: center top;
  filter: brightness(.65) saturate(1.1);
}}
.heroGradient {{
  position: absolute; inset: 0;
  background: linear-gradient(
    180deg,
    rgba(6,8,16,0) 0%,
    rgba(6,8,16,.15) 40%,
    rgba(6,8,16,.70) 72%,
    rgba(6,8,16,.96) 100%
  );
}}
.heroFallback {{
  position: absolute; inset: 0;
  background:
    radial-gradient(ellipse 1200px 700px at 50% -10%, rgba(200,169,110,.18) 0%, transparent 55%),
    radial-gradient(ellipse 900px 600px at 80% 50%, rgba(126,184,247,.12) 0%, transparent 55%),
    linear-gradient(170deg, rgba(12,18,35,.9) 0%, rgba(6,8,16,1) 60%);
  display: flex; align-items: center; justify-content: center;
}}
.heroFallbackPaw {{ font-size: 120px; opacity: .15; }}
.heroContent {{
  position: relative; z-index: 2;
  max-width: var(--max); margin: 0 auto; width: 100%;
  padding: clamp(32px, 6vw, 64px) clamp(20px, 4vw, 40px);
}}
.heroBadge {{
  display: inline-flex; align-items: center; gap: 8px;
  padding: 7px 14px; border-radius: 99px;
  border: 1px solid rgba(200,169,110,.35);
  background: rgba(200,169,110,.10);
  color: var(--accent); font-size: 12px; font-weight: 700;
  letter-spacing: .6px; text-transform: uppercase; margin-bottom: 20px;
}}
.heroBadge::before {{ content: ''; width: 6px; height: 6px; border-radius: 99px; background: var(--accent); }}
.heroTitle {{
  font-family: var(--font-display);
  font-size: clamp(64px, 10vw, 120px);
  line-height: .92; letter-spacing: -2px; font-weight: 900;
  margin-bottom: 8px;
}}
.heroTitleItalic {{ font-style: italic; color: var(--accent); }}
.heroSub {{
  font-size: clamp(16px, 2.2vw, 20px); color: rgba(240,242,255,.80);
  max-width: 52ch; line-height: 1.55; margin-bottom: 28px; font-weight: 300;
}}
.heroCtas {{ display: flex; gap: 12px; flex-wrap: wrap; margin-bottom: 40px; }}
.btn {{
  display: inline-flex; align-items: center; gap: 8px;
  padding: 14px 24px; border-radius: 14px; font-weight: 700; font-size: 14px;
  border: none; transition: transform .15s, box-shadow .15s;
}}
.btn--primary {{
  background: var(--accent); color: #0a0800;
  box-shadow: 0 4px 24px rgba(200,169,110,.30);
}}
.btn--primary:hover {{ transform: translateY(-2px); box-shadow: 0 10px 32px rgba(200,169,110,.45); }}
.btn--ghost {{
  background: rgba(255,255,255,.08); color: var(--text);
  border: 1px solid rgba(255,255,255,.15);
}}
.btn--ghost:hover {{ background: rgba(255,255,255,.13); transform: translateY(-1px); }}
.btn--sm {{ padding: 10px 18px; font-size: 13px; border-radius: 12px; }}
.heroStats {{
  display: flex; gap: 24px; flex-wrap: wrap;
  padding-top: 28px; border-top: 1px solid rgba(255,255,255,.08);
}}
.heroStat {{ }}
.heroStatNum {{
  font-family: var(--font-display); font-size: 32px; font-weight: 700;
  color: var(--accent); line-height: 1;
}}
.heroStatLabel {{ font-size: 12px; color: var(--muted); margin-top: 4px; letter-spacing: .3px; }}

/* ─── SECTION ─────────────────────────────────────────────────── */
.page {{ max-width: var(--max); margin: 0 auto; padding: 0 clamp(16px, 3vw, 32px) 100px; }}
.section {{ padding-top: 100px; }}
.sectionEyebrow {{
  font-size: 11px; font-weight: 700; letter-spacing: 2px; text-transform: uppercase;
  color: var(--accent); margin-bottom: 12px;
}}
.sectionTitle {{
  font-family: var(--font-display); font-size: clamp(32px, 4vw, 52px);
  line-height: 1.05; letter-spacing: -1px; margin-bottom: 12px;
}}
.sectionDesc {{ color: var(--muted); font-size: 16px; line-height: 1.6; max-width: 55ch; font-weight: 300; }}
.sectionHead {{ margin-bottom: 40px; }}

/* ─── PORTFOLIO GRID ──────────────────────────────────────────── */
.grid {{
  display: grid; gap: 16px;
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
}}
.card {{
  border-radius: var(--r2); overflow: hidden;
  border: 1px solid var(--border); background: rgba(255,255,255,.02);
  cursor: pointer; transition: transform .25s, box-shadow .25s;
  animation: fadeUp .5s both;
}}
@keyframes fadeUp {{
  from {{ opacity: 0; transform: translateY(24px); }}
  to {{ opacity: 1; transform: translateY(0); }}
}}
.card:hover {{ transform: translateY(-4px); box-shadow: 0 24px 50px rgba(0,0,0,.4); }}
.cardImgWrap {{ position: relative; overflow: hidden; aspect-ratio: 4/3; }}
.cardImg {{
  width: 100%; height: 100%; object-fit: cover;
  transition: transform .5s cubic-bezier(.2,0,0,1);
}}
.card:hover .cardImg {{ transform: scale(1.05); }}
.cardOverlay {{
  position: absolute; inset: 0;
  background: linear-gradient(180deg, transparent 50%, rgba(0,0,0,.6) 100%);
  display: flex; justify-content: space-between; align-items: flex-end; padding: 14px;
  opacity: 0; transition: opacity .25s;
}}
.card:hover .cardOverlay {{ opacity: 1; }}
.cardTag {{
  font-size: 11px; font-weight: 700; letter-spacing: .8px; text-transform: uppercase;
  color: var(--accent); background: rgba(0,0,0,.6); padding: 4px 10px; border-radius: 99px;
  border: 1px solid rgba(200,169,110,.3);
}}
.cardZoom {{
  width: 34px; height: 34px; border-radius: 10px;
  background: rgba(255,255,255,.15); border: 1px solid rgba(255,255,255,.2);
  color: white; font-size: 16px;
  display: grid; place-items: center;
}}
.cap {{ padding: 14px 16px; }}
.capTitle {{ font-weight: 700; font-size: 15px; margin-bottom: 4px; }}
.capSub {{ font-size: 12px; color: var(--muted); }}
.card--placeholder .placeholderImg {{
  aspect-ratio: 4/3; background: rgba(255,255,255,.03);
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  gap: 10px;
}}
.placeholderPaw {{ font-size: 48px; opacity: .3; }}
.placeholderText {{ font-weight: 700; color: var(--muted); }}
.placeholderSub {{ font-size: 12px; color: rgba(255,255,255,.3); }}

/* ─── SKILLS ──────────────────────────────────────────────────── */
.skillsGrid {{ display: grid; gap: 14px; grid-template-columns: repeat(auto-fill, minmax(240px, 1fr)); }}
.skillCard {{
  padding: 22px; border-radius: var(--r2); border: 1px solid var(--border);
  background: var(--surface); position: relative; overflow: hidden;
  transition: border-color .2s, transform .2s;
}}
.skillCard:hover {{ border-color: rgba(200,169,110,.35); transform: translateY(-3px); }}
.skillCard::before {{
  content: ''; position: absolute; top: 0; left: 0; right: 0; height: 2px;
  background: linear-gradient(90deg, var(--accent), transparent);
  opacity: 0; transition: opacity .2s;
}}
.skillCard:hover::before {{ opacity: 1; }}
.skillIcon {{ font-size: 28px; margin-bottom: 12px; }}
.skillTitle {{ font-weight: 700; font-size: 16px; margin-bottom: 6px; }}
.skillBody {{ font-size: 13px; color: var(--muted); line-height: 1.5; }}

/* ─── GAMES SECTION ───────────────────────────────────────────── */
.gamesGrid {{ display: grid; gap: 20px; }}
@media(min-width: 900px) {{ .gamesGrid {{ grid-template-columns: 1fr 1fr; }} }}
.gameCard {{
  border: 1px solid var(--border); background: var(--surface);
  border-radius: var(--r2); overflow: hidden;
}}
.gameCard--wide {{ grid-column: 1 / -1; }}
.gameHeader {{ padding: 18px 20px 0; }}
.gameTitle {{ font-family: var(--font-display); font-size: 20px; font-weight: 700; margin-bottom: 4px; }}
.gameDesc {{ font-size: 13px; color: var(--muted); }}
.gameBody {{ padding: 14px 20px 20px; }}
.gameControls {{
  display: flex; gap: 10px; align-items: center; flex-wrap: wrap; margin-bottom: 14px;
}}
.scoreBadge {{
  padding: 8px 14px; border-radius: 99px;
  border: 1px solid var(--border); background: rgba(255,255,255,.05);
  font-weight: 700; font-size: 13px; font-variant-numeric: tabular-nums;
  min-width: 90px; text-align: center;
}}
.scoreBadge.gold {{ border-color: rgba(200,169,110,.4); color: var(--accent); }}

/* ─── FETCH GAME ──────────────────────────────────────────────── */
.fetchScene {{
  position: relative; height: 280px; border-radius: var(--r);
  background: linear-gradient(180deg, #0d1628 0%, #0a1020 60%, #0e1a14 100%);
  overflow: hidden; border: 1px solid var(--border);
}}
.fetchGrass {{
  position: absolute; left: 0; right: 0; bottom: 0; height: 64px;
  background: linear-gradient(180deg, #1a3d1a 0%, #0e2010 100%);
  border-top: 2px solid rgba(80,180,80,.2);
}}
.fetchPath {{
  position: absolute; left: 0; right: 0; bottom: 32px; height: 2px;
  background: repeating-linear-gradient(90deg, rgba(255,255,255,.12) 0px, rgba(255,255,255,.12) 10px, transparent 10px, transparent 22px);
}}
.fetchSky {{
  position: absolute; top: 0; left: 0; right: 0; height: 60%;
  background: radial-gradient(ellipse at 50% 0%, rgba(126,184,247,.12) 0%, transparent 65%);
}}
#fetchBall {{
  position: absolute; font-size: 26px;
  bottom: 46px; left: 60px;
  will-change: transform;
  filter: drop-shadow(0 4px 8px rgba(0,0,0,.5));
  cursor: pointer; user-select: none;
  transition: none;
}}
#fetchDog {{
  position: absolute; font-size: 32px;
  bottom: 36px; left: 20px;
  will-change: transform;
  filter: drop-shadow(0 4px 8px rgba(0,0,0,.4));
  user-select: none;
}}
.fetchFlag {{
  position: absolute; right: 24px; bottom: 44px; font-size: 22px; opacity: .8;
}}
.fetchCloud {{
  position: absolute; font-size: 28px; opacity: .12;
  animation: drift linear infinite;
}}
@keyframes drift {{ from {{ transform: translateX(-60px); }} to {{ transform: translateX(110vw); }} }}

/* ─── SPIN GAME ───────────────────────────────────────────────── */
.spinScene {{
  position: relative; height: 280px; border-radius: var(--r);
  background: radial-gradient(ellipse at 50% 30%, rgba(200,169,110,.10) 0%, rgba(6,8,16,1) 70%);
  display: flex; align-items: center; justify-content: center;
  overflow: hidden; border: 1px solid var(--border);
}}
.spinRing {{
  position: absolute;
  border-radius: 50%; border: 1px solid rgba(200,169,110,.08);
}}
.spinAvatar {{
  width: 160px; height: 160px; border-radius: 50%;
  overflow: hidden; border: 2px solid rgba(200,169,110,.35);
  box-shadow: 0 0 40px rgba(200,169,110,.20), 0 0 0 6px rgba(200,169,110,.05);
  position: relative; z-index: 2; will-change: transform;
  background: rgba(0,0,0,.3);
  display: grid; place-items: center;
}}
.spinAvatar img {{ width: 100%; height: 100%; object-fit: cover; }}
.spinAvatarFallback {{ font-size: 64px; }}
.spinTrail {{
  position: absolute; border-radius: 50%;
  border: 2px solid rgba(200,169,110,0);
  will-change: transform, opacity;
  pointer-events: none;
}}
.spinGlow {{
  position: absolute; width: 200px; height: 200px; border-radius: 50%;
  background: radial-gradient(circle, rgba(200,169,110,.25) 0%, transparent 70%);
  pointer-events: none; will-change: opacity;
}}
.spinSpeedMeter {{
  position: absolute; bottom: 16px; left: 50%; transform: translateX(-50%);
  display: flex; gap: 4px; align-items: flex-end;
}}
.speedBar {{
  width: 6px; border-radius: 3px;
  background: rgba(255,255,255,.12); transition: height .1s, background .1s;
}}

/* ─── HERDING GAME ────────────────────────────────────────────── */
#herdCanvas {{
  width: 100%; border-radius: var(--r);
  border: 1px solid var(--border);
  background: #08100f;
  cursor: crosshair;
}}

/* ─── CONTACT ─────────────────────────────────────────────────── */
.contactWrap {{
  display: grid; gap: 40px;
  grid-template-columns: 1fr;
}}
@media(min-width: 900px) {{ .contactWrap {{ grid-template-columns: 1fr 1.6fr; }} }}
.contactInfo {{ }}
.contactInfoTitle {{
  font-family: var(--font-display); font-size: 28px; font-weight: 700;
  margin-bottom: 16px; line-height: 1.1;
}}
.contactInfoBody {{ color: var(--muted); font-size: 15px; line-height: 1.65; font-weight: 300; }}
.contactHighlights {{ margin-top: 24px; display: flex; flex-direction: column; gap: 10px; }}
.contactHL {{
  display: flex; align-items: center; gap: 12px;
  font-size: 14px; font-weight: 500;
}}
.contactHL span:first-child {{ font-size: 18px; }}
.contactForm {{
  background: rgba(255,255,255,.02); border: 1px solid var(--border);
  border-radius: var(--r2); padding: 28px;
}}
.formGrid {{ display: grid; gap: 14px; }}
.formRow {{ display: grid; gap: 14px; grid-template-columns: 1fr 1fr; }}
@media(max-width: 600px) {{ .formRow {{ grid-template-columns: 1fr; }} }}
.formLabel span {{
  display: block; font-size: 11px; font-weight: 700; letter-spacing: .8px;
  text-transform: uppercase; color: var(--muted); margin-bottom: 8px;
}}
.formInput, .formTextarea, .formSelect {{
  width: 100%; padding: 12px 14px; border-radius: 12px;
  border: 1px solid rgba(255,255,255,.12); background: rgba(0,0,0,.25);
  color: var(--text); font-family: var(--font-body); font-size: 14px;
  outline: none; transition: border-color .15s;
}}
.formInput:focus, .formTextarea:focus, .formSelect:focus {{
  border-color: rgba(200,169,110,.5);
}}
.formTextarea {{ min-height: 110px; resize: vertical; }}
.formSelect option {{ background: #0d1220; }}
.formSubmit {{
  width: 100%; padding: 14px; border-radius: 14px;
  background: var(--accent); color: #0a0800; font-weight: 700; font-size: 15px;
  border: none; transition: transform .15s, box-shadow .15s;
  box-shadow: 0 4px 20px rgba(200,169,110,.25);
}}
.formSubmit:hover:not(:disabled) {{ transform: translateY(-2px); box-shadow: 0 8px 30px rgba(200,169,110,.4); }}
.formSubmit:disabled {{ opacity: .6; cursor: not-allowed; }}
.formToast {{
  min-height: 20px; font-size: 14px; font-weight: 600; text-align: center;
  transition: opacity .3s;
}}
.formToast.ok {{ color: rgba(150,255,190,.9); }}
.formToast.bad {{ color: rgba(255,160,160,.9); }}

/* ─── MODAL ───────────────────────────────────────────────────── */
.modal {{ position: fixed; inset: 0; z-index: 500; display: none; align-items: center; justify-content: center; }}
.modal[aria-hidden="false"] {{ display: flex; }}
.modalBd {{ position: absolute; inset: 0; background: rgba(0,0,0,.80); backdrop-filter: blur(6px); cursor: pointer; }}
.modalPanel {{
  position: relative; z-index: 1; width: min(90vw, 960px); max-height: 88vh;
  border-radius: var(--r2); border: 1px solid var(--border);
  background: rgba(10,13,24,.96); box-shadow: var(--shadow);
  display: flex; flex-direction: column; overflow: hidden;
}}
.modalClose {{
  position: absolute; top: 14px; right: 14px; z-index: 2;
  width: 36px; height: 36px; border-radius: 10px;
  border: 1px solid var(--border); background: rgba(255,255,255,.08);
  color: var(--text); font-size: 16px; display: grid; place-items: center;
}}
.modalImg {{ width: 100%; max-height: 80vh; object-fit: contain; display: block; }}

/* ─── FOOTER ──────────────────────────────────────────────────── */
footer {{
  border-top: 1px solid var(--border);
  background: rgba(6,8,16,.8);
  backdrop-filter: blur(10px);
}}
.footerInner {{
  max-width: var(--max); margin: 0 auto;
  padding: 28px clamp(16px, 3vw, 32px);
  display: flex; justify-content: space-between; align-items: center;
  gap: 16px; flex-wrap: wrap;
}}
.footerBrand {{ font-family: var(--font-display); font-size: 22px; font-weight: 700; }}
.footerTagline {{ font-size: 13px; color: var(--muted); margin-top: 4px; }}
.footerLinks {{ display: flex; gap: 10px; flex-wrap: wrap; }}

/* ─── UTILITIES ───────────────────────────────────────────────── */
.muted {{ color: var(--muted); }}
</style>
</head>

<body>

<!-- NAV -->
<header class="nav" id="nav">
  <div class="navInner">
    <a class="brand" href="#top">
      <div class="brandMark">🐾</div>
      <div>
        <div class="brandText">Vaayu</div>
        <div class="brandSub">Border Collie Ambassador</div>
      </div>
    </a>
    <nav class="navLinks">
      <a href="#portfolio">Portfolio</a>
      <a href="#skills">Skills</a>
      <a href="#games">Games</a>
      <a href="#contact">Contact</a>
    </nav>
    <a class="navCta btn" href="#contact">Book Now</a>
    <button class="hamburger" id="hamburger" aria-label="Menu" aria-expanded="false">
      <span></span><span></span><span></span>
    </button>
  </div>
</header>

<!-- DRAWER -->
<div class="drawer" id="drawer" aria-hidden="true">
  <div class="drawerPanel">
    <div class="drawerTop">
      <div style="font-family:var(--font-display);font-weight:700;font-size:18px">Menu</div>
      <button class="drawerClose" id="drawerClose">✕</button>
    </div>
    <a class="drawerLink" href="#portfolio">Portfolio</a>
    <a class="drawerLink" href="#skills">Skills & Fit</a>
    <a class="drawerLink" href="#games">Interactive Games</a>
    <a class="drawerLink" href="#contact">Book Vaayu</a>
  </div>
  <div class="drawerBd" id="drawerBd"></div>
</div>

<!-- HERO -->
<section class="hero" id="top">
  <div class="heroBg">
    {f'<img class="heroImg" src="{escape_html(hero_img)}" alt="Vaayu">' if hero_img else ''}
    <div class="heroGradient"></div>
    {'' if hero_img else '<div class="heroFallback"><div class="heroFallbackPaw">🐾</div></div>'}
  </div>
  <div class="heroContent">
    <div class="heroBadge">Available for campaigns</div>
    <h1 class="heroTitle">
      Meet<br><span class="heroTitleItalic">Vaayu.</span>
    </h1>
    <p class="heroSub">
      A camera-confident, highly trainable Border Collie built for premium pet campaigns.
      Food brands, toy brands, UGC, ads — Vaayu delivers every shot, every take.
    </p>
    <div class="heroCtas">
      <a class="btn btn--primary" href="#contact">Book a Shoot →</a>
      <a class="btn btn--ghost" href="#portfolio">View Portfolio</a>
      <a class="btn btn--ghost btn--sm" href="/media-kit" target="_blank" rel="noopener">Media Kit</a>
    </div>
    <div class="heroStats">
      <div class="heroStat">
        <div class="heroStatNum">A+</div>
        <div class="heroStatLabel">Trainability</div>
      </div>
      <div class="heroStat">
        <div class="heroStatNum">100%</div>
        <div class="heroStatLabel">Camera Ready</div>
      </div>
      <div class="heroStat">
        <div class="heroStatNum">24h</div>
        <div class="heroStatLabel">Response Time</div>
      </div>
      <div class="heroStat">
        <div class="heroStatNum">∞</div>
        <div class="heroStatLabel">Personality</div>
      </div>
    </div>
  </div>
</section>

<!-- PAGE WRAPPER -->
<div class="page">

  <!-- PORTFOLIO -->
  <section class="section" id="portfolio">
    <div class="sectionHead">
      <div class="sectionEyebrow">Portfolio</div>
      <h2 class="sectionTitle">Every Shot, <em>Perfectly Composed.</em></h2>
      <p class="sectionDesc">Click any photo to view full size. Each look is styled, repeatable, and campaign-ready.</p>
    </div>
    <div class="grid" id="galleryGrid">
      {''.join(gallery_cards)}
    </div>
  </section>

  <!-- SKILLS -->
  <section class="section" id="skills">
    <div class="sectionHead">
      <div class="sectionEyebrow">Why Vaayu</div>
      <h2 class="sectionTitle">Built for <em>Your Brand.</em></h2>
      <p class="sectionDesc">Vaayu's unique combination of intelligence, expressiveness, and calm under camera makes every shoot effortless.</p>
    </div>
    <div class="skillsGrid">
      <div class="skillCard">
        <div class="skillIcon">🍖</div>
        <div class="skillTitle">Food & Treat Brands</div>
        <div class="skillBody">Mastered "wait / take / release" on cue. Perfect tasting reels, unboxing shots, and slow-motion snack moments.</div>
      </div>
      <div class="skillCard">
        <div class="skillIcon">🎾</div>
        <div class="skillTitle">Toy & Play Brands</div>
        <div class="skillBody">Fetch energy, tug focus, and chase excitement — every toy interaction is pure, genuine, and photogenic.</div>
      </div>
      <div class="skillCard">
        <div class="skillIcon">🎬</div>
        <div class="skillTitle">Repeatable Cues</div>
        <div class="skillBody">Multiple takes are no problem. Same pose, same expression, same energy — reliable across a full shoot day.</div>
      </div>
      <div class="skillCard">
        <div class="skillIcon">👁️</div>
        <div class="skillTitle">Camera Confidence</div>
        <div class="skillBody">Holds eye contact, stays still, and brings expression. No flash shyness, no distraction from lenses or crew.</div>
      </div>
      <div class="skillCard">
        <div class="skillIcon">🏆</div>
        <div class="skillTitle">Show & Sport</div>
        <div class="skillBody">Agility trained. Perfect posture for conformation-style shots. Athleticism and grace on demand.</div>
      </div>
      <div class="skillCard">
        <div class="skillIcon">❤️</div>
        <div class="skillTitle">Audience Connect</div>
        <div class="skillBody">Expressive face, soulful eyes, iconic black-and-white coat. Audiences stop scrolling for Vaayu.</div>
      </div>
    </div>
  </section>

  <!-- GAMES -->
  <section class="section" id="games">
    <div class="sectionHead">
      <div class="sectionEyebrow">Interactive</div>
      <h2 class="sectionTitle">Play with <em>Vaayu.</em></h2>
      <p class="sectionDesc">Three mini-games that bring Vaayu's personality to life. Scroll down and play!</p>
    </div>

    <div class="gamesGrid">

      <!-- FETCH GAME -->
      <div class="gameCard">
        <div class="gameHeader">
          <div class="gameTitle">🎾 Fetch!</div>
          <div class="gameDesc">Click "Throw" or tap the ball. Watch Vaayu chase it down with full-body physics.</div>
        </div>
        <div class="gameBody">
          <div class="gameControls">
            <button class="btn btn--primary btn--sm" id="throwBtn">Throw Ball 🎾</button>
            <button class="btn btn--ghost btn--sm" id="resetFetchBtn">Reset</button>
            <div class="scoreBadge gold" id="fetchScore">Fetches: 0</div>
            <div class="scoreBadge" id="fetchStreak">Streak: 0</div>
          </div>
          <div class="fetchScene" id="fetchScene">
            <div class="fetchSky"></div>
            <div class="fetchCloud" style="top:12px;font-size:24px;animation-duration:22s;animation-delay:0s">☁️</div>
            <div class="fetchCloud" style="top:28px;font-size:18px;animation-duration:30s;animation-delay:-12s">☁️</div>
            <div class="fetchGrass"></div>
            <div class="fetchPath"></div>
            <div class="fetchFlag">🏁</div>
            <div id="fetchBall">🎾</div>
            <div id="fetchDog">🐕</div>
          </div>
          <div style="font-size:12px;color:var(--muted);margin-top:10px">
            Tip: try clicking the ball too! Each catch builds a streak.
          </div>
        </div>
      </div>

      <!-- SPIN GAME -->
      <div class="gameCard">
        <div class="gameHeader">
          <div class="gameTitle">🌀 Spin Trick</div>
          <div class="gameDesc">Click Vaayu rapidly to build spin momentum. Keep the combo going for max power!</div>
        </div>
        <div class="gameBody">
          <div class="gameControls">
            <button class="btn btn--primary btn--sm" id="spinBoostBtn">Spin! 🌀</button>
            <button class="btn btn--ghost btn--sm" id="spinResetBtn">Reset</button>
            <div class="scoreBadge gold" id="spinPower">Power: 0</div>
            <div class="scoreBadge" id="spinCombo">Combo ×1</div>
          </div>
          <div class="spinScene" id="spinScene">
            <div class="spinRing" style="width:260px;height:260px"></div>
            <div class="spinRing" style="width:200px;height:200px"></div>
            <div class="spinRing" style="width:140px;height:140px"></div>
            <div class="spinGlow" id="spinGlow"></div>
            <div class="spinAvatar" id="spinAvatar">
              {f'<img id="spinImg" src="{escape_html(hero_img)}" alt="Vaayu">' if hero_img else '<div class="spinAvatarFallback">🐕</div>'}
            </div>
            <div class="spinSpeedMeter" id="speedMeter"></div>
          </div>
          <div style="font-size:12px;color:var(--muted);margin-top:10px">
            Click fast to combo! The glow intensifies with speed.
          </div>
        </div>
      </div>

      <!-- HERDING GAME -->
      <div class="gameCard gameCard--wide">
        <div class="gameHeader">
          <div class="gameTitle">🐑 Herding Championship</div>
          <div class="gameDesc">Click canvas to focus it, then use Arrow Keys or WASD to move Vaayu. Herd all 6 sheep into the pen to win! Arrow keys won't scroll the page while playing.</div>
        </div>
        <div class="gameBody">
          <div class="gameControls">
            <button class="btn btn--primary btn--sm" id="herdStartBtn">Start Game</button>
            <button class="btn btn--ghost btn--sm" id="herdResetBtn">Reset</button>
            <div class="scoreBadge gold" id="herdScore">In Pen: 0 / 6</div>
            <div class="scoreBadge" id="herdTime">Time: 0s</div>
            <div class="scoreBadge" id="herdBest">Best: --</div>
          </div>
          <canvas id="herdCanvas" width="1000" height="440" tabindex="0"></canvas>
          <div style="font-size:12px;color:var(--muted);margin-top:10px">
            🐑 Sheep flee from Vaayu. Herd them gently into the golden pen →
          </div>
        </div>
      </div>

    </div>
  </section>

  <!-- CONTACT -->
  <section class="section" id="contact">
    <div class="sectionHead">
      <div class="sectionEyebrow">Book Vaayu</div>
      <h2 class="sectionTitle">Let's Create <em>Something Amazing.</em></h2>
    </div>
    <div class="contactWrap">
      <div class="contactInfo">
        <div class="contactInfoTitle">Ready to work with<br>the best in the business?</div>
        <div class="contactInfoBody">
          Vaayu is available for brand campaigns, product shoots, video ads, UGC content, and show appearances.
          Get in touch and we'll respond within 24 hours with availability, rates, and a custom media kit.
        </div>
        <div class="contactHighlights">
          <div class="contactHL"><span>📸</span><span>Brand Photography & Video</span></div>
          <div class="contactHL"><span>📱</span><span>UGC & Social Media Content</span></div>
          <div class="contactHL"><span>🎬</span><span>TV & Digital Advertising</span></div>
          <div class="contactHL"><span>🏆</span><span>Shows & Live Appearances</span></div>
          <div class="contactHL"><span>🤝</span><span>Long-Term Brand Ambassadorship</span></div>
          <div class="contactHL"><span>⚡</span><span>24-Hour Response Guaranteed</span></div>
        </div>
      </div>
      <div class="contactForm">
        <form id="contactForm" class="formGrid" autocomplete="on">
          <div class="formRow">
            <label class="formLabel">
              <span>Your Name</span>
              <input class="formInput" name="name" required minlength="2" placeholder="Jane Smith">
            </label>
            <label class="formLabel">
              <span>Email Address</span>
              <input class="formInput" name="email" type="email" required placeholder="jane@brand.com">
            </label>
          </div>
          <div class="formRow">
            <label class="formLabel">
              <span>Inquiry Type</span>
              <select class="formSelect" name="purpose">
                <option>Brand Campaign</option>
                <option>Food / Treat Brand</option>
                <option>Toy Brand</option>
                <option>Video Advertisement</option>
                <option>UGC / Social Content</option>
                <option>Show Appearance</option>
                <option>Ambassador Partnership</option>
                <option>Other</option>
              </select>
            </label>
            <label class="formLabel">
              <span>Estimated Budget</span>
              <select class="formSelect" name="budget">
                <option value="">Prefer not to say</option>
                <option>Under ₹10,000</option>
                <option>₹10,000 – ₹50,000</option>
                <option>₹50,000 – ₹2,00,000</option>
                <option>₹2,00,000+</option>
                <option>Let's discuss</option>
              </select>
            </label>
          </div>
          <label class="formLabel">
            <span>Tell us about the project</span>
            <textarea class="formTextarea" name="message" required minlength="10" maxlength="2000"
              placeholder="Tell us about deliverables, shoot dates, usage rights, number of shots needed…"></textarea>
          </label>
          <button class="formSubmit" type="submit" id="contactSubmit">Send Inquiry →</button>
          <div class="formToast" id="formToast"></div>
          <div style="font-size:11px;color:var(--muted);text-align:center">
            Inquiries stored locally at <code style="font-size:11px">data/contact_messages.jsonl</code>
          </div>
        </form>
      </div>
    </div>
  </section>

</div><!-- /page -->

<!-- MODAL -->
<div class="modal" id="modal" aria-hidden="true">
  <div class="modalBd" id="modalBd"></div>
  <div class="modalPanel">
    <button class="modalClose" id="modalClose">✕</button>
    <img class="modalImg" id="modalImg" alt="">
  </div>
</div>

<footer>
  <div class="footerInner">
    <div>
      <div class="footerBrand">Vaayu</div>
      <div class="footerTagline">Border Collie · Brand Ambassador · Camera Ready</div>
    </div>
    <div class="footerLinks">
      <a class="btn btn--primary btn--sm" href="#contact">Book Now</a>
      <a class="btn btn--ghost btn--sm" href="/media-kit" target="_blank">Media Kit</a>
    </div>
  </div>
</footer>

<script>
/* ═══════════════════════════════════════
   NAV & DRAWER
═══════════════════════════════════════ */
(function() {{
  var hamburger = document.getElementById('hamburger');
  var drawer = document.getElementById('drawer');
  var drawerClose = document.getElementById('drawerClose');
  var drawerBd = document.getElementById('drawerBd');

  function openDrawer() {{
    drawer.setAttribute('aria-hidden', 'false');
    hamburger.setAttribute('aria-expanded', 'true');
    document.body.style.overflow = 'hidden';
  }}
  function closeDrawer() {{
    drawer.setAttribute('aria-hidden', 'true');
    hamburger.setAttribute('aria-expanded', 'false');
    document.body.style.overflow = '';
  }}

  if (hamburger) hamburger.addEventListener('click', function() {{
    drawer.getAttribute('aria-hidden') === 'false' ? closeDrawer() : openDrawer();
  }});
  if (drawerClose) drawerClose.addEventListener('click', closeDrawer);
  if (drawerBd) drawerBd.addEventListener('click', closeDrawer);
  if (drawer) drawer.addEventListener('click', function(e) {{
    if (e.target && e.target.classList && e.target.classList.contains('drawerLink')) closeDrawer();
  }});

  document.addEventListener('click', function(e) {{
    var a = e.target && e.target.closest && e.target.closest('a[href^="#"]');
    if (!a) return;
    var href = a.getAttribute('href');
    if (!href || href === '#') return;
    var el = document.querySelector(href);
    if (!el) return;
    e.preventDefault();
    el.scrollIntoView({{ behavior: 'smooth', block: 'start' }});
  }});
}})();

/* ═══════════════════════════════════════
   GALLERY MODAL
═══════════════════════════════════════ */
(function() {{
  var modal = document.getElementById('modal');
  var modalImg = document.getElementById('modalImg');
  var modalBd = document.getElementById('modalBd');
  var modalClose = document.getElementById('modalClose');
  var grid = document.getElementById('galleryGrid');

  function open(src) {{
    modalImg.src = src;
    modal.setAttribute('aria-hidden', 'false');
    document.body.style.overflow = 'hidden';
  }}
  function close() {{
    modal.setAttribute('aria-hidden', 'true');
    modalImg.src = '';
    document.body.style.overflow = '';
  }}

  if (grid) grid.addEventListener('click', function(e) {{
    var img = e.target && e.target.closest && e.target.closest('.card');
    if (!img) return;
    var cardImg = img.querySelector('.cardImg');
    if (cardImg) open(cardImg.dataset.full || cardImg.src);
  }});
  if (modalBd) modalBd.addEventListener('click', close);
  if (modalClose) modalClose.addEventListener('click', close);
  document.addEventListener('keydown', function(e) {{
    if (e.key === 'Escape' && modal && modal.getAttribute('aria-hidden') === 'false') close();
  }});
}})();

/* ═══════════════════════════════════════
   FETCH GAME
═══════════════════════════════════════ */
(function() {{
  var throwBtn = document.getElementById('throwBtn');
  var resetBtn = document.getElementById('resetFetchBtn');
  var ball = document.getElementById('fetchBall');
  var dog = document.getElementById('fetchDog');
  var scene = document.getElementById('fetchScene');
  var scoreEl = document.getElementById('fetchScore');
  var streakEl = document.getElementById('fetchStreak');

  var score = 0;
  var streak = 0;
  var throwing = false;
  var raf = null;

  // Physics state
  var bx = 0, by = 0;      // ball position (relative offset from start)
  var dx = 0, dy = 0;      // dog position
  var bvx = 0, bvy = 0;    // ball velocity
  var dvx = 0, dvy = 0;    // dog velocity

  var phase = 'idle'; // idle | thrown | chasing | returning
  var targetX = 0;
  var GROUND = 0; // ball rests at by=0

  function sceneWidth() {{ return scene ? scene.clientWidth : 600; }}

  function resetState() {{
    throwing = false; phase = 'idle';
    bx = 0; by = 0; bvx = 0; bvy = 0;
    dx = 0; dy = 0; dvx = 0; dvy = 0;
    applyBall(0, 0); applyDog(0, 0);
    ball.style.transition = 'none';
    dog.style.transition = 'none';
    if (raf) {{ cancelAnimationFrame(raf); raf = null; }}
  }}

  function applyBall(x, y) {{
    ball.style.transform = 'translate(' + x + 'px, ' + (-y) + 'px)';
  }}
  function applyDog(x, y) {{
    dog.style.transform = 'translate(' + x + 'px, ' + (-y) + 'px) scaleX(' + (x < bx - 10 ? -1 : 1) + ')';
  }}

  function throw_() {{
    if (phase !== 'idle') return;
    var w = sceneWidth();
    targetX = Math.max(w * 0.55, w - 120);
    bx = 0; by = 0;
    bvx = targetX / 45; // will land in ~45 frames at 60fps
    bvy = 14; // upward arc
    phase = 'thrown';
    if (!raf) loop();
  }}

  function loop() {{
    raf = requestAnimationFrame(loop);
    var GRAVITY = 0.7;
    var FRICTION = 0.985;

    if (phase === 'thrown') {{
      bvx *= FRICTION;
      bvy -= GRAVITY;
      bx += bvx; by += bvy;
      if (by <= GROUND && bvx < 1.5) {{
        // ball landed
        by = 0; bvx = 0; bvy = 0;
        applyBall(bx, 0);
        phase = 'chasing';
        // dog starts chasing
      }} else if (by < GROUND) {{
        by = GROUND;
        bvy = Math.abs(bvy) * 0.45; // bounce
      }}
      applyBall(bx, Math.max(0, by));
      // dog wags in place while ball in air
      applyDog(dx + Math.sin(Date.now()/100)*1.5, 0);
    }}

    if (phase === 'chasing') {{
      // dog rushes to ball
      var diff = bx - dx;
      dvx += (diff > 0 ? 1 : -1) * 0.9;
      dvx *= 0.88;
      dx += dvx;
      applyDog(dx, Math.abs(Math.sin(Date.now()/80)) * 4); // bounce while running
      if (Math.abs(diff) < 8) {{
        // caught!
        score++;
        streak++;
        scoreEl.textContent = 'Fetches: ' + score;
        streakEl.textContent = 'Streak: ' + streak + (streak > 2 ? ' 🔥' : '');
        phase = 'returning';
        dvx = 0;
      }}
    }}

    if (phase === 'returning') {{
      // dog returns ball to start
      var rdiff = 0 - dx;
      dvx += (rdiff > 0 ? 1 : -1) * 0.6;
      dvx *= 0.90;
      dx += dvx;
      bx = dx + 20; // ball follows dog mouth
      applyDog(dx, Math.abs(Math.sin(Date.now()/80)) * 3);
      applyBall(bx, 0);
      if (Math.abs(rdiff) < 10) {{
        // back home
        dx = 0; bx = 0; dvx = 0;
        applyDog(0,0); applyBall(0,0);
        phase = 'idle';
        // celebrate bounce
        dog.animate([
          {{transform:'translate(0px,-10px) scaleX(1)'}},
          {{transform:'translate(0px,0px) scaleX(1)'}}
        ], {{duration:300,easing:'cubic-bezier(.2,.9,.2,1)'}});
      }}
    }}
  }}

  if (throwBtn) throwBtn.addEventListener('click', throw_);
  if (ball) ball.addEventListener('click', throw_);
  if (resetBtn) resetBtn.addEventListener('click', function() {{
    resetState(); score = 0; streak = 0;
    scoreEl.textContent = 'Fetches: 0';
    streakEl.textContent = 'Streak: 0';
  }});
}})();

/* ═══════════════════════════════════════
   SPIN TRICK GAME
═══════════════════════════════════════ */
(function() {{
  var avatar = document.getElementById('spinAvatar');
  var boostBtn = document.getElementById('spinBoostBtn');
  var resetBtn = document.getElementById('spinResetBtn');
  var powerEl = document.getElementById('spinPower');
  var comboEl = document.getElementById('spinCombo');
  var glow = document.getElementById('spinGlow');
  var meterEl = document.getElementById('speedMeter');
  if (!avatar) return;

  var angle = 0;
  var omega = 0; // angular velocity
  var combo = 0;
  var lastClick = 0;
  var BARS = 10;

  // Build speed bars
  if (meterEl) {{
    for (var i = 0; i < BARS; i++) {{
      var b = document.createElement('div');
      b.className = 'speedBar';
      b.style.height = (8 + i * 4) + 'px';
      meterEl.appendChild(b);
    }}
  }}

  function boost() {{
    var now = performance.now();
    var dt = now - lastClick;
    lastClick = now;
    var mult = dt < 200 ? 1.6 : (dt < 400 ? 1.2 : 0.9);
    omega += 0.35 * mult;
    if (omega > 8) omega = 8;
    if (Math.abs(omega) > 1.2) combo++;
    else combo = 0;
    comboEl.textContent = 'Combo ×' + (combo + 1);
    avatar.animate([
      {{transform: 'rotate(' + angle + 'rad) scale(1.06)'}},
      {{transform: 'rotate(' + angle + 'rad) scale(1)'}}
    ], {{duration: 180, easing: 'ease-out'}});
  }}

  function reset_() {{
    angle = 0; omega = 0; combo = 0;
    powerEl.textContent = 'Power: 0';
    comboEl.textContent = 'Combo ×1';
    avatar.style.transform = 'rotate(0rad)';
    if (glow) glow.style.opacity = '0';
  }}

  function tick() {{
    omega *= 0.976; // friction
    if (Math.abs(omega) < 0.003) omega = 0;
    angle += omega;
    avatar.style.transform = 'rotate(' + angle + 'rad)';

    var power = Math.min(999, Math.floor(Math.abs(omega) * 140));
    powerEl.textContent = 'Power: ' + power;

    // glow intensity
    if (glow) {{
      var g = Math.min(1, Math.abs(omega) / 5);
      glow.style.opacity = g.toFixed(2);
      var hue = 30 + (Math.abs(omega) / 8) * 40; // gold to orange
      glow.style.background = 'radial-gradient(circle, hsla(' + hue + ',80%,55%,' + (g*0.5) + ') 0%, transparent 70%)';
    }}

    // speed bars
    if (meterEl) {{
      var bars = meterEl.querySelectorAll('.speedBar');
      var filled = Math.round((Math.abs(omega) / 8) * BARS);
      bars.forEach(function(b, i) {{
        if (i < filled) {{
          b.style.background = 'hsl(' + (50 - i*4) + ',90%,55%)';
        }} else {{
          b.style.background = 'rgba(255,255,255,.12)';
        }}
      }});
    }}

    requestAnimationFrame(tick);
  }}

  if (boostBtn) boostBtn.addEventListener('click', boost);
  if (avatar) avatar.addEventListener('click', boost);
  if (resetBtn) resetBtn.addEventListener('click', reset_);
  requestAnimationFrame(tick);
}})();

/* ═══════════════════════════════════════
   HERDING GAME
═══════════════════════════════════════ */
(function() {{
  var canvas = document.getElementById('herdCanvas');
  if (!canvas) return;
  var ctx = canvas.getContext('2d');
  var W = canvas.width, H = canvas.height;
  var startBtn = document.getElementById('herdStartBtn');
  var resetBtn = document.getElementById('herdResetBtn');
  var scoreEl = document.getElementById('herdScore');
  var timeEl = document.getElementById('herdTime');
  var bestEl = document.getElementById('herdBest');

  var HERO_SRC = {hero_json};
  var heroImg = new Image();
  if (HERO_SRC) heroImg.src = HERO_SRC;

  var PEN = {{ x: W - 190, y: H/2 - 100, w: 160, h: 200 }};
  var TOTAL_SHEEP = 6;

  var keys = new Set();
  var herdFocused = false;
  var SCROLL_KEYS = new Set(['arrowup','arrowdown','arrowleft','arrowright',' ']);

  canvas.addEventListener('focus', function() {{ herdFocused = true; }});
  canvas.addEventListener('blur', function() {{ herdFocused = false; }});
  canvas.addEventListener('click', function() {{ canvas.focus(); }});
  canvas.addEventListener('mouseenter', function() {{ herdFocused = true; }});
  canvas.addEventListener('mouseleave', function() {{ herdFocused = false; }});

  document.addEventListener('keydown', function(e) {{
    var k = (e.key||'').toLowerCase();
    if (herdFocused && SCROLL_KEYS.has(k)) e.preventDefault();
    keys.add(k);
  }}, {{ passive: false }});
  document.addEventListener('keyup', function(e) {{
    keys.delete((e.key||'').toLowerCase());
  }});

  function clamp(v,a,b){{ return Math.max(a,Math.min(b,v)); }}
  function dist(ax,ay,bx,by){{ return Math.hypot(ax-bx, ay-by); }}

  var state = {{
    running: false, won: false,
    inPen: 0, elapsed: 0, bestTime: null,
    vaayu: {{ x: 100, y: H/2, r: 24, speed: 4.0 }},
    sheep: []
  }};
  var lastTime = 0;

  function makeSheep() {{
    var arr = [];
    for (var i = 0; i < TOTAL_SHEEP; i++) {{
      arr.push({{
        x: 180 + Math.random() * 380,
        y: 60 + Math.random() * (H - 120),
        r: 18,
        vx: (Math.random() - 0.5) * 1.4,
        vy: (Math.random() - 0.5) * 1.4,
        inPen: false,
        wobble: Math.random() * Math.PI * 2
      }});
    }}
    return arr;
  }}

  function reset() {{
    state.running = false; state.won = false;
    state.inPen = 0; state.elapsed = 0;
    state.vaayu.x = 100; state.vaayu.y = H/2;
    state.sheep = makeSheep();
    scoreEl.textContent = 'In Pen: 0 / ' + TOTAL_SHEEP;
    timeEl.textContent = 'Time: 0s';
    lastTime = 0;
    drawFrame(0);
  }}

  function updateVaayu(dt) {{
    var v = state.vaayu;
    var dx = 0, dy = 0;
    if (keys.has('arrowup') || keys.has('w')) dy -= 1;
    if (keys.has('arrowdown') || keys.has('s')) dy += 1;
    if (keys.has('arrowleft') || keys.has('a')) dx -= 1;
    if (keys.has('arrowright') || keys.has('d')) dx += 1;
    if (dx || dy) {{
      var len = Math.hypot(dx, dy); dx /= len; dy /= len;
      v.x += dx * v.speed;
      v.y += dy * v.speed;
    }}
    v.x = clamp(v.x, v.r + 8, W - v.r - 8);
    v.y = clamp(v.y, v.r + 8, H - v.r - 8);
  }}

  function updateSheep(dt) {{
    var v = state.vaayu;
    for (var i = 0; i < state.sheep.length; i++) {{
      var s = state.sheep[i];
      if (s.inPen) {{ s.wobble += 0.03; continue; }}
      s.wobble += 0.04;

      var d = dist(s.x, s.y, v.x, v.y);
      var fleeR = 140;
      if (d < fleeR) {{
        // flee from vaayu with panic
        var strength = (1 - d/fleeR) * 0.55;
        var fx = (s.x - v.x) / (d + 0.001);
        var fy = (s.y - v.y) / (d + 0.001);
        s.vx += fx * strength;
        s.vy += fy * strength;
      }} else {{
        // wander randomly
        s.vx += (Math.random() - 0.5) * 0.05;
        s.vy += (Math.random() - 0.5) * 0.05;
      }}

      // flock: slight cohesion with neighbors
      for (var j = 0; j < state.sheep.length; j++) {{
        if (i === j || state.sheep[j].inPen) continue;
        var nd = dist(s.x,s.y,state.sheep[j].x,state.sheep[j].y);
        if (nd < 36 && nd > 0) {{
          // separation
          s.vx += (s.x - state.sheep[j].x) / nd * 0.12;
          s.vy += (s.y - state.sheep[j].y) / nd * 0.12;
        }}
      }}

      // speed limit
      var spd = Math.hypot(s.vx, s.vy);
      if (spd > 2.8) {{ s.vx = (s.vx/spd)*2.8; s.vy = (s.vy/spd)*2.8; }}

      s.x += s.vx; s.y += s.vy;
      s.vx *= 0.92; s.vy *= 0.92;

      if (s.x < s.r+8) {{ s.x = s.r+8; s.vx *= -0.7; }}
      if (s.x > W-s.r-8) {{ s.x = W-s.r-8; s.vx *= -0.7; }}
      if (s.y < s.r+8) {{ s.y = s.r+8; s.vy *= -0.7; }}
      if (s.y > H-s.r-8) {{ s.y = H-s.r-8; s.vy *= -0.7; }}

      // check pen
      if (s.x > PEN.x && s.x < PEN.x+PEN.w && s.y > PEN.y && s.y < PEN.y+PEN.h) {{
        s.inPen = true;
        s.vx = (Math.random()-0.5)*0.5;
        s.vy = (Math.random()-0.5)*0.5;
        state.inPen++;
        scoreEl.textContent = 'In Pen: ' + state.inPen + ' / ' + TOTAL_SHEEP;
      }}
    }}
  }}

  function drawRoundRect(x,y,w,h,r) {{
    var rr = Math.min(r,w/2,h/2);
    ctx.beginPath();
    ctx.moveTo(x+rr,y);
    ctx.arcTo(x+w,y,x+w,y+h,rr);
    ctx.arcTo(x+w,y+h,x,y+h,rr);
    ctx.arcTo(x,y+h,x,y,rr);
    ctx.arcTo(x,y,x+w,y,rr);
    ctx.closePath();
  }}

  function drawFrame(ts) {{
    ctx.clearRect(0,0,W,H);

    // background gradient
    var bg = ctx.createLinearGradient(0,0,0,H);
    bg.addColorStop(0,'#0a1a0e');
    bg.addColorStop(1,'#06100a');
    ctx.fillStyle = bg;
    ctx.fillRect(0,0,W,H);

    // grass texture (dots)
    ctx.save();
    ctx.globalAlpha = 0.06;
    ctx.fillStyle = '#80ff80';
    for (var gx=0;gx<W;gx+=22) for (var gy=0;gy<H;gy+=22) {{
      ctx.beginPath(); ctx.arc(gx+Math.sin(gx*0.3)*3,gy,1.5,0,Math.PI*2); ctx.fill();
    }}
    ctx.restore();

    // pen glow
    ctx.save();
    ctx.shadowColor = 'rgba(200,169,110,0.3)';
    ctx.shadowBlur = 30;
    ctx.fillStyle = 'rgba(200,169,110,0.08)';
    drawRoundRect(PEN.x,PEN.y,PEN.w,PEN.h,20);
    ctx.fill();
    ctx.restore();

    ctx.save();
    ctx.strokeStyle = 'rgba(200,169,110,0.5)';
    ctx.lineWidth = 2;
    drawRoundRect(PEN.x,PEN.y,PEN.w,PEN.h,20);
    ctx.stroke();
    ctx.fillStyle = 'rgba(200,169,110,0.80)';
    ctx.font = '700 14px DM Sans, sans-serif';
    ctx.fillText('PEN', PEN.x+12, PEN.y+24);
    ctx.restore();

    // sheep in pen
    ctx.save();
    ctx.font = '22px serif';
    for (var i=0;i<state.sheep.length;i++) {{
      var s = state.sheep[i];
      if (!s.inPen) continue;
      ctx.globalAlpha = 0.9;
      ctx.fillText('🐑', s.x+Math.sin(s.wobble)*2-11, s.y+8);
    }}
    ctx.restore();

    // sheep out
    ctx.save();
    ctx.font = '24px serif';
    for (var i=0;i<state.sheep.length;i++) {{
      var s = state.sheep[i];
      if (s.inPen) continue;
      ctx.globalAlpha = 1.0;
      // shadow
      ctx.save();
      ctx.globalAlpha = 0.2;
      ctx.fillStyle = '#000';
      ctx.beginPath(); ctx.ellipse(s.x, s.y+s.r+2, s.r*0.8, 5, 0, 0, Math.PI*2);
      ctx.fill();
      ctx.restore();
      ctx.fillText('🐑', s.x+Math.sin(s.wobble)*1.5-12, s.y+8);
    }}
    ctx.restore();

    // vaayu / dog
    var vx = state.vaayu.x, vy = state.vaayu.y, vr = state.vaayu.r;
    // shadow
    ctx.save();
    ctx.globalAlpha = 0.25;
    ctx.fillStyle = '#000';
    ctx.beginPath(); ctx.ellipse(vx, vy+vr+2, vr*0.9, 6, 0, 0, Math.PI*2);
    ctx.fill();
    ctx.restore();

    if (HERO_SRC && heroImg.complete && heroImg.naturalWidth > 0) {{
      ctx.save();
      ctx.beginPath(); ctx.arc(vx, vy, vr, 0, Math.PI*2); ctx.clip();
      ctx.drawImage(heroImg, vx-vr, vy-vr, vr*2, vr*2);
      ctx.restore();
      ctx.save();
      ctx.strokeStyle = 'rgba(200,169,110,0.75)';
      ctx.lineWidth = 2;
      ctx.beginPath(); ctx.arc(vx, vy, vr, 0, Math.PI*2); ctx.stroke();
      ctx.restore();
    }} else {{
      ctx.save();
      ctx.font = '30px serif';
      ctx.fillText('🐕', vx-15, vy+10);
      ctx.restore();
    }}

    // win
    if (state.won) {{
      ctx.save();
      ctx.fillStyle = 'rgba(200,169,110,0.95)';
      ctx.font = '700 32px Playfair Display, serif';
      ctx.textAlign = 'center';
      ctx.fillText('🏆 Vaayu wins! All sheep herded!', W/2, H/2);
      ctx.font = '500 18px DM Sans, sans-serif';
      ctx.fillStyle = 'rgba(240,242,255,.8)';
      ctx.fillText('Time: ' + state.elapsed.toFixed(1) + 's', W/2, H/2 + 36);
      ctx.restore();
    }}

    if (!state.running) return;
    // win check
    if (state.inPen >= TOTAL_SHEEP && !state.won) {{
      state.won = true;
      state.running = false;
      var t = state.elapsed;
      if (!state.bestTime || t < state.bestTime) {{
        state.bestTime = t;
        bestEl.textContent = 'Best: ' + t.toFixed(1) + 's';
      }}
    }}
  }}

  function gameLoop(ts) {{
    if (!state.running) return;
    if (lastTime) {{
      var dt = (ts - lastTime) / 1000;
      state.elapsed += dt;
      timeEl.textContent = 'Time: ' + state.elapsed.toFixed(1) + 's';
      updateVaayu(dt);
      updateSheep(dt);
    }}
    lastTime = ts;
    drawFrame(ts);
    requestAnimationFrame(gameLoop);
  }}

  if (startBtn) startBtn.addEventListener('click', function() {{
    if (!state.running && !state.won) {{
      state.running = true;
      lastTime = 0;
      requestAnimationFrame(gameLoop);
    }}
  }});
  if (resetBtn) resetBtn.addEventListener('click', reset);

  heroImg.onload = function() {{ drawFrame(0); }};
  reset();
}})();

/* ═══════════════════════════════════════
   CONTACT FORM
═══════════════════════════════════════ */
(function() {{
  var form = document.getElementById('contactForm');
  var toast = document.getElementById('formToast');
  var submit = document.getElementById('contactSubmit');
  if (!form) return;

  function setToast(msg, ok) {{
    toast.textContent = msg;
    toast.className = 'formToast ' + (ok ? 'ok' : 'bad');
  }}

  form.addEventListener('submit', async function(e) {{
    e.preventDefault();
    submit.disabled = true;
    submit.textContent = 'Sending…';
    var fd = new FormData(form);
    var payload = {{
      name: String(fd.get('name') || ''),
      email: String(fd.get('email') || ''),
      purpose: String(fd.get('purpose') || 'Brand Campaign'),
      budget: String(fd.get('budget') || ''),
      message: String(fd.get('message') || '')
    }};
    try {{
      var res = await fetch('/api/contact', {{
        method: 'POST',
        headers: {{ 'Content-Type': 'application/json' }},
        body: JSON.stringify(payload)
      }});
      var data = await res.json().catch(function() {{ return {{}}; }});
      if (!res.ok) {{
        setToast((data.errors && data.errors.join(' ')) || data.error || 'Something went wrong.', false);
      }} else {{
        setToast(data.message || 'Sent! 🐾', true);
        form.reset();
      }}
    }} catch(err) {{
      setToast('Network error. Please try again.', false);
    }} finally {{
      submit.disabled = false;
      submit.textContent = 'Send Inquiry →';
      setTimeout(function() {{ setToast('', true); }}, 5000);
    }}
  }});
}})();
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
