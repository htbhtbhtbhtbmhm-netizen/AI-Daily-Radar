import os, sys, json, re, subprocess, hashlib, asyncio, calendar, datetime as dt
from urllib.parse import urlparse, urlunparse, parse_qsl, urlencode
import requests, feedparser
from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATE_FILE = os.path.join(ROOT, "state", "posted.json")
W, H = 1080, 1920
MAX_PER_RUN, MAX_PER_DAY, FRESH_HOURS = 2, 5, 24
WHITE, LIGHT = (255, 255, 255), (205, 230, 215)
UA = {"User-Agent": "Mozilla/5.0 (compatible; AIDailyRadar/1.0)"}
FONTS = ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf"]
VOICES = {"en": "en-US-GuyNeural", "es": "es-ES-AlvaroNeural", "fr": "fr-FR-HenriNeural", "ar": "ar-SA-HamedNeural"}
THEMES = [((10, 25, 70), (3, 8, 30), (0, 220, 255)), ((30, 10, 70), (10, 3, 30), (255, 120, 220)),
          ((5, 55, 50), (2, 22, 22), (120, 255, 200)), ((45, 45, 55), (5, 5, 10), (255, 200, 60))]

L = {
 "en": {"head": "AI NEWS", "digest": "AI DIGEST OF THE DAY", "official": "Official source", "only": "Official sources only",
        "dtitle": "AI news digest — {d}", "tag": "AI"},
 "es": {"head": "NOTICIAS DE IA", "digest": "RESUMEN DE IA DEL DÍA", "official": "Fuente oficial", "only": "Solo fuentes oficiales",
        "dtitle": "Resumen de noticias de IA — {d}", "tag": "IA"},
 "fr": {"head": "ACTU IA", "digest": "RÉSUMÉ IA DU JOUR", "official": "Source officielle", "only": "Sources officielles uniquement",
        "dtitle": "Résumé de l'actu IA — {d}", "tag": "IA"},
 "ar": {"head": "أخبار الذكاء الاصطناعي", "digest": "ملخص اليوم في الذكاء الاصطناعي", "official": "المصدر الرسمي",
        "only": "مصادر رسمية فقط", "dtitle": "ملخص أخبار الذكاء الاصطناعي — {d}", "tag": "الذكاء_الاصطناعي"},
}

NEG = re.compile(r"webinar|podcast|hiring|careers|customer stor|case study|event recap|register now|join us|giveaway|sweepstakes|newsletter", re.I)
POS = re.compile(r"introduc|launch|releas|announc|\bnew\b|\bmodels?\b|\bapi\b|\bagents?\b|open[- ]source|now available|\bavailable\b|update|benchmark|preview|\bgpt|gemini|claude|llama|gemma|nemotron|\bsdk\b|\bmcp\b", re.I)
AIK = re.compile(r"\b(ai|llms?|gpt\S*|gemini|claude|llama|gemma|genai|copilot|agentic)\b|generative|machine learning|neural|\bagents?\b|\bmodels?\b", re.I)


def h(key, n):
    return int(hashlib.md5(key.encode()).hexdigest(), 16) % n


def shape(s, lang):
    if lang == "ar":
        import arabic_reshaper
        from bidi.algorithm import get_display
        return get_display(arabic_reshaper.reshape(s))
    return s


def font(size):
    for p in FONTS:
        if os.path.exists(p):
            return ImageFont.truetype(p, size, layout_engine=ImageFont.Layout.BASIC)
    return ImageFont.load_default()


def fit(d, text, size, maxw):
    while size > 28:
        f = font(size)
        if d.textlength(text, font=f) <= maxw:
            return f
        size -= 4
    return font(28)


def center(d, y, text, size, fill):
    f = fit(d, text, size, W - 120)
    d.text(((W - d.textlength(text, font=f)) / 2, y), text, font=f, fill=fill)


def wrap(d, text, f, maxw, maxlines):
    lines, cur = [], ""
    for w in text.split():
        t = (cur + " " + w).strip()
        if d.textlength(t, font=f) <= maxw:
            cur = t
        else:
            lines.append(cur); cur = w
    lines.append(cur)
    if len(lines) > maxlines:
        lines = lines[:maxlines]; lines[-1] = lines[-1].rstrip(" .,") + "…"
    return lines


def trunc(s, n):
    return s if len(s) <= n else s[:n - 1].rstrip() + "…"


def canvas(key):
    c1, c2, acc = THEMES[h(key + "t", len(THEMES))]
    img = Image.new("RGB", (W, H)); d = ImageDraw.Draw(img)
    for y in range(H):
        t = y / H
        d.line([(0, y), (W, y)], fill=tuple(int(c1[i] + (c2[i] - c1[i]) * t) for i in range(3)))
    fr = h(key + "f", 3)
    if fr == 0: d.rectangle([60, 60, W - 60, H - 60], outline=WHITE, width=4)
    elif fr == 1: d.rectangle([0, 0, W, 40], fill=acc); d.rectangle([0, H - 40, W, H], fill=acc)
    else: d.rectangle([60, 60, 80, H - 60], fill=acc)
    return img, d, acc


def card_news(it, lang, name, key, path):
    img, d, acc = canvas(key); s = L[lang]
    center(d, 200, shape(s["head"], lang), 70, acc)
    center(d, 300, it["date"], 50, LIGHT)
    center(d, 430, it["src"], 90, WHITE)
    f = font(72)
    y = 650
    for ln in wrap(d, it["title"], f, W - 180, 8):
        d.text((90, y), ln, font=f, fill=WHITE); y += 100
    center(d, 1560, shape(s["official"], lang), 48, LIGHT)
    center(d, 1630, it["host"], 46, acc)
    center(d, 1750, name, 54, LIGHT)
    img.save(path)
    return [s["head"], it["src"], it["title"]]


def card_digest(items, day, lang, name, key, path):
    img, d, acc = canvas(key); s = L[lang]
    center(d, 200, shape(s["digest"], lang), 64, acc)
    center(d, 290, day, 50, LIGHT)
    f = font(50); y = 450
    for i, it in enumerate(items[:6], 1):
        d.text((90, y), f"{i}. {it['src']}", font=font(40), fill=acc); y += 52
        for ln in wrap(d, it["title"], f, W - 180, 2):
            d.text((90, y), ln, font=f, fill=WHITE); y += 60
        y += 40
    center(d, 1650, shape(s["only"], lang), 48, LIGHT)
    center(d, 1750, name, 54, LIGHT)
    img.save(path)
    return [s["digest"]] + [f'{it["src"]}. {it["title"]}' for it in items[:6]]


def tts(text, lang, mp3):
    try:
        import edge_tts
        asyncio.run(edge_tts.Communicate(text, VOICES[lang]).save(mp3))
        return os.path.getsize(mp3) > 1000
    except Exception as e:
        print("tts failed:", e); return False


def duration(mp3):
    o = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", mp3],
                       capture_output=True, text=True)
    return float(o.stdout.strip())


def make_video(png, mp4, key, mp3=None):
    dur = min(55.0, duration(mp3) + 1.5) if mp3 else 8.0
    n = int(dur * 25); mv = h(key + "m", 3)
    ctr = "x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
    z = [f"z='min(zoom+0.0006,1.10)':{ctr}", f"z='if(eq(on,0),1.10,max(zoom-0.0006,1.0))':{ctr}",
         f"z=1.08:x='(iw-iw/zoom)*on/{n}':y='ih/2-(ih/zoom/2)'"][mv]
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-i", png] + (["-i", mp3] if mp3 else [])
    cmd += ["-vf", f"zoompan={z}:d={n}:s={W}x{H}:fps=25,format=yuv420p", "-t", str(dur), "-c:v", "libx264"]
    cmd += (["-map", "0:v", "-map", "1:a", "-c:a", "aac", "-b:a", "128k"] if mp3 else ["-an"])
    subprocess.run(cmd + [mp4], check=True)


def upload(mp4, title, desc, refresh_token):
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload
    creds = Credentials(None, refresh_token=refresh_token, token_uri="https://oauth2.googleapis.com/token",
                        client_id=os.environ["YT_CLIENT_ID"], client_secret=os.environ["YT_CLIENT_SECRET"],
                        scopes=["https://www.googleapis.com/auth/youtube.upload"])
    yt = build("youtube", "v3", credentials=creds)
    body = {"snippet": {"title": title[:95], "description": desc[:4900], "categoryId": "28"},
            "status": {"privacyStatus": "public", "selfDeclaredMadeForKids": False}}
    req = yt.videos().insert(part="snippet,status", body=body,
                             media_body=MediaFileUpload(mp4, mimetype="video/mp4", resumable=True))
    resp = None
    while resp is None:
        _, resp = req.next_chunk()
    return resp["id"]


# ---------- المصادر والتصفية ----------
def norm_url(u):
    p = urlparse(u.strip())
    q = [(k, v) for k, v in parse_qsl(p.query) if not k.lower().startswith(("utm_", "ref", "fbclid"))]
    return urlunparse((p.scheme, p.netloc.lower(), p.path.rstrip("/"), "", urlencode(q), ""))


def host_ok(link, domains):
    p = urlparse(link)
    hn = (p.hostname or "").lower()
    return p.scheme == "https" and any(hn == d or hn.endswith("." + d) for d in domains)


def parse_feed(content, src, now):
    out = []
    feed = feedparser.parse(content)
    for e in feed.entries:
        link, title = e.get("link", ""), re.sub(r"\s+", " ", e.get("title", "")).strip()
        t = e.get("published_parsed") or e.get("updated_parsed")
        if not (link and title and t):
            continue
        pub = dt.datetime.fromtimestamp(calendar.timegm(t), dt.timezone.utc)
        if not (now - dt.timedelta(hours=FRESH_HOURS) <= pub <= now + dt.timedelta(hours=1)):
            continue
        if not host_ok(link, src["domains"]):
            continue                                   # حارس الثقة: نطاق رسمي فقط
        if NEG.search(title):
            continue
        summ = re.sub(r"<[^>]+>", " ", e.get("summary", ""))[:300]
        if src["mode"] == "filter" and not (AIK.search(title + " " + summ) and POS.search(title)):
            continue
        url = norm_url(link)
        out.append({"key": "n:" + hashlib.sha1(url.encode()).hexdigest()[:16], "src": src["name"], "title": title,
                    "url": link, "host": urlparse(link).hostname.replace("www.", ""), "pub": pub,
                    "date": pub.strftime("%Y-%m-%d"), "prio": src.get("prio", 1)})
    return out


def collect(now, check=False):
    items = []
    for src in json.load(open(os.path.join(ROOT, "sources.json"), encoding="utf-8")):
        try:
            r = requests.get(src["url"], headers=UA, timeout=25)
            r.raise_for_status()
            got = parse_feed(r.content, src, now)
            if check: print(f'OK   {src["name"]}: {len(got)} fresh items')
            items += got
        except Exception as e:
            print(f'FAIL {src["name"]}: {e}')          # مصدر معطّل لا يوقف الباقي
    return sorted(items, key=lambda x: (-x["prio"], -x["pub"].timestamp()))


def main():
    if "--demo" in sys.argv:
        it = {"src": "OpenAI", "title": "Introducing a new model that can reason across text, images and code for developers", "host": "openai.com", "date": "2026-10-06"}
        for lang in ("en", "ar"):
            card_news(it, lang, "AI Daily Radar", "k1", f"/tmp/ai_news_{lang}.png")
        card_digest([it, dict(it, src="Hugging Face"), dict(it, src="NVIDIA")], "2026-10-06", "en", "AI Daily Radar", "k2", "/tmp/ai_dig.png")
        make_video("/tmp/ai_news_en.png", "/tmp/ai.mp4", "k1"); print("demo ok"); return
    now = dt.datetime.now(dt.timezone.utc); today = str(now.date())
    if "--check" in sys.argv:
        collect(now, check=True); return
    state = json.load(open(STATE_FILE))
    channels = json.load(open(os.path.join(ROOT, "channels.json"), encoding="utf-8"))
    open(os.path.join(ROOT, "state", "heartbeat.txt"), "w").write(today)
    items = collect(now)
    for ch in channels:
        token = os.environ.get("YT_REFRESH_" + ch["id"].upper())
        if not token:
            print("no token for", ch["id"]); continue
        lang, name = ch["lang"], ch["name"]
        st = state.setdefault(ch["id"], {"ids": [], "day": today, "count": 0, "today": []})
        if st["day"] != today:
            st["day"], st["count"], st["today"] = today, 0, []
        todo = [("item", it["key"], it) for it in items if it["key"] not in st["ids"]]
        if now.hour >= 19 and len(st["today"]) >= 3 and f"dig:{today}" not in st["ids"]:
            todo.append(("digest", f"dig:{today}", st["today"]))
        done = 0
        for kind, key, p in todo:                       # لا شيء جديد = لا نشر
            if done >= MAX_PER_RUN or st["count"] >= MAX_PER_DAY and kind == "item":
                continue
            try:
                if kind == "item":
                    lines = card_news(p, lang, name, key, "/tmp/c.png")
                    title = f'{p["src"]}: {p["title"]}'
                    desc = f'{p["src"]}: {p["title"]}\n{L[lang]["official"]}: {p["url"]}\n\n{ch.get("desc_footer", "")}\n#AI #{re.sub(r"\W", "", p["src"])} #{L[lang]["tag"]}'
                else:
                    lines = card_digest(p, today, lang, name, key, "/tmp/c.png")
                    title = L[lang]["dtitle"].format(d=today)
                    desc = "\n".join(f'{i}. {x["src"]}: {x["title"]}\n{x["url"]}' for i, x in enumerate(p[:6], 1)) + f'\n\n{L[lang]["only"]}\n{ch.get("desc_footer", "")}\n#AI'
                mp3 = "/tmp/c.mp3" if (os.environ.get("VOICE") == "1" and tts(". ".join(lines), lang, "/tmp/c.mp3")) else None
                make_video("/tmp/c.png", "/tmp/c.mp4", key, mp3)
                vid = upload("/tmp/c.mp4", title, desc, token)
                print("posted", ch["id"], key, vid)
                st["ids"] = (st["ids"] + [key])[-600:]; done += 1
                if kind == "item":
                    st["count"] += 1
                    st["today"].append({"src": p["src"], "title": p["title"], "url": p["url"]})
            except Exception as e:
                print("post failed:", key, e)
    json.dump(state, open(STATE_FILE, "w"))


if __name__ == "__main__":
    main()
