#!/usr/bin/env python3
"""vocabag-media — petit service local pour les workflows n8n « VocaBag Social ».

Rôles :
  POST /ingest   image brute (Telegram…) → JPEG normalisé, publié dans public/, renvoie URL + ratio
  POST /stage    fichier binaire (vidéo mp4 du Reel…) → copié dans public/, renvoie URL
  POST /render   {template, data} → HTML rendu par Chromium (Playwright) en 1080x1920 → JPEG public
                 (templates VocaBag + muz_question / muz_answer pour les stories quiz Muz Rappel)
  POST /muz/reel-story  {date?} → extrait < 60 s (coupé entre deux phrases) du Reel Muz Rappel du jour → MP4 public
  POST /detect-langues  {images, modele} → langue(s) enseignée(s) lues sur les images (Claude, ../blog/detection.py)
  POST /emojis  {mots, categorie, modele} → un émoji par mot, tous différents (Claude, ../blog/emojis.py)
  POST /blog/*   articles de blog tirés des carrousels (voir ../blog/blogfile.py) :
                 enqueue, rediger, publier, rejeter, reecrire — corps JSON
  GET  /health

Les fichiers de public/ sont servis par Apache sous PUBLIC_BASE_URL (Instagram/Pinterest vont les
chercher eux-mêmes). Noms aléatoires non devinables, purge automatique après RETENTION_DAYS.
Jamais d'URL Telegram (qui contient le token du bot) ne sort d'ici : n8n télécharge, on ré-héberge.

Écoute uniquement sur l'IP du pont Docker (n8n y accède via host.docker.internal) + jeton partagé.
"""
import html
import io
import json
import os
import secrets
import sys
import time
from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

from PIL import Image, ImageOps

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR.parent / 'blog'))
import blogfile  # noqa: E402
import detection  # noqa: E402
import emojis  # noqa: E402
ASSETS = BASE_DIR / 'assets'
PUBLIC_DIR = Path(os.environ.get('PUBLIC_DIR', BASE_DIR.parent / 'public'))
PUBLIC_BASE_URL = os.environ.get('PUBLIC_BASE_URL', 'https://staging.vocabag.com/social-media').rstrip('/')
TOKEN = os.environ.get('MEDIA_TOKEN', '')
HOST = os.environ.get('BIND_HOST', '172.17.0.1')
PORT = int(os.environ.get('BIND_PORT', '8791'))
RETENTION_DAYS = int(os.environ.get('RETENTION_DAYS', '14'))
MAX_BYTES = 150 * 1024 * 1024
BRAND = '#0f9f8e'

# Instagram (API) : ratio accepté pour un post/carrousel = 4:5 (0.8) … 1.91:1.
FEED_MIN_RATIO = 0.8
FEED_MAX_RATIO = 1.91


def _now_dir():
    d = PUBLIC_DIR / datetime.now().strftime('%Y%m')
    d.mkdir(parents=True, exist_ok=True)
    return d


def _public_url(path: Path) -> str:
    return f"{PUBLIC_BASE_URL}/{path.relative_to(PUBLIC_DIR).as_posix()}"


def _purge():
    limit = time.time() - RETENTION_DAYS * 86400
    for p in PUBLIC_DIR.rglob('*'):
        if p.is_file() and p.stat().st_mtime < limit:
            p.unlink(missing_ok=True)


def _save_jpeg(img: Image.Image) -> Path:
    out = _now_dir() / f"{secrets.token_urlsafe(18)}.jpg"
    img.save(out, 'JPEG', quality=92, optimize=True, progressive=True)
    out.chmod(0o644)
    return out


# ---------------------------------------------------------------- /ingest
def ingest(raw: bytes, params: dict) -> dict:
    """Image quelconque → JPEG RGB, orientation EXIF appliquée, largeur max 1440 px.

    ratio_policy : 'none' (défaut, on ne touche pas au cadrage, on signale seulement)
                   'pad'  (trop haute → complétée en 4:5 sur fond blanc ; trop large → 1.91:1)
    """
    img = Image.open(io.BytesIO(raw))
    img = ImageOps.exif_transpose(img)
    if img.mode not in ('RGB',):
        bg = Image.new('RGB', img.size, 'white')
        bg.paste(img, mask=img.convert('RGBA').split()[-1])
        img = bg
    src_format = (Image.open(io.BytesIO(raw)).format or '').upper()
    w, h = img.size
    ratio = w / h
    warnings = []
    policy = params.get('ratio_policy', 'none')
    if ratio < FEED_MIN_RATIO - 0.005 or ratio > FEED_MAX_RATIO + 0.005:
        msg = f"ratio {w}x{h} ({ratio:.2f}) hors plage Instagram 4:5 … 1.91:1"
        if policy == 'pad':
            if ratio < FEED_MIN_RATIO:
                nw, nh = round(h * 0.8), h
            else:
                nw, nh = w, round(w / FEED_MAX_RATIO)
            canvas = Image.new('RGB', (nw, nh), 'white')
            canvas.paste(img, ((nw - w) // 2, (nh - h) // 2))
            img = canvas
            warnings.append(msg + ' → complétée par des bandes blanches')
        else:
            warnings.append(msg + ' → Instagram risque de la refuser')
    elif abs(ratio - 0.8) > 0.02 and abs(ratio - 0.75) > 0.02:
        warnings.append(f"ratio {ratio:.2f} (ni 4:5 ni 3:4) — acceptée mais recadrage visuel possible")
    if img.width > 1440:
        img = img.resize((1440, round(img.height * 1440 / img.width)), Image.LANCZOS)
    out = _save_jpeg(img)
    return {
        'url': _public_url(out),
        'width': img.width,
        'height': img.height,
        'ratio': round(img.width / img.height, 4),
        'source_format': src_format,
        'converted': src_format != 'JPEG',
        'warnings': warnings,
    }


# ---------------------------------------------------------------- /stage
def stage(raw: bytes, params: dict) -> dict:
    ext = params.get('ext', 'mp4').lower()
    if ext not in ('mp4', 'jpg', 'jpeg', 'png'):
        raise ValueError('extension refusée')
    out = _now_dir() / f"{secrets.token_urlsafe(18)}.{ext}"
    out.write_bytes(raw)
    out.chmod(0o644)
    return {'url': _public_url(out), 'bytes': len(raw)}


# ---------------------------------------------------------------- /render
_BROWSER = None
_PW = None


def _browser():
    global _BROWSER, _PW
    if _BROWSER is None or not _BROWSER.is_connected():
        from playwright.sync_api import sync_playwright
        _PW = sync_playwright().start()
        _BROWSER = _PW.chromium.launch(args=['--no-sandbox'])
    return _BROWSER


LANG_TAGS = {'ary': 'ar-MA', 'ar': 'ar', 'zh': 'zh-Hans', 'ko': 'ko', 'ru': 'ru', 'tr': 'tr',
             'en': 'en', 'de': 'de', 'es': 'es', 'pt': 'pt', 'it': 'it', 'nl': 'nl', 'fr': 'fr'}
RTL = {'ary', 'ar'}


def _word_block(word: str, code: str, size: int) -> str:
    """Mot dans son écriture native : lang + dir corrects, polices adaptées (jamais d'image IA)."""
    d = 'rtl' if code in RTL else 'ltr'
    return (f'<div class="native" lang="{LANG_TAGS.get(code, code)}" dir="{d}" '
            f'style="font-size:{size}px">{html.escape(word)}</div>')


def _fit(text: str, base: int, per_char_limit: int) -> int:
    n = max(1, len(text))
    return base if n <= per_char_limit else max(56, int(base * per_char_limit / n))


MUZ_VERT = '#169666'      # vert du logo Muz Rappel
MUZ_FOND = '#111c1e'      # fond de l'icône Muz Rappel


def build_html_muz(template: str, data: dict) -> str:
    """Stories quiz Muz Rappel : textes tirés tels quels de la base (extrait, options, référence)."""
    e = html.escape
    if template == 'muz_question':
        extrait = data.get('extrait', '')
        taille = 46 if len(extrait) <= 120 else 41 if len(extrait) <= 190 else 36
        options = ''.join(
            f'<div class="opt"><span class="l">{l}</span><span>{e(o)}</span></div>'
            for l, o in zip('ABC', (data.get('options') or [])[:3]))
        body = f"""
          <div class="kicker">Quiz du jour</div>
          <div class="card">
            <div class="label">Hadith</div>
            <div class="extrait" style="font-size:{taille}px">«&nbsp;{e(extrait)}&nbsp;»</div>
            <div class="question">{e(data.get('question', ''))}</div>
            <div class="opts">{options}</div>
          </div>
          <div class="hint">Réponds en message 💬<br>Réponse ce soir !</div>
          <div class="logo"><img src="file://{ASSETS}/muz-logo.png" alt=""></div>"""
    elif template == 'muz_answer':
        lettre, rep = e(data.get('bonne_lettre', '')), data.get('bonne_reponse', '')
        body = f"""
          <div class="kicker">Réponse du quiz</div>
          <div class="card">
            <div class="label">{e(data.get('question', ''))}</div>
            <div class="rep"><span class="l">{lettre}</span><span>{e(rep)}</span></div>
            {'<div class="src">' + e(data.get('rapporteur_phrase', '')) + '</div>' if data.get('rapporteur_phrase') else ''}
            <div class="src">{e(data.get('reference', ''))}</div>
            <div class="titre">{e(data.get('titre', ''))}</div>
          </div>
          <div class="hint">Tu avais trouvé ?<br>Qu'Allah nous accorde la science utile 🤲</div>
          <div class="logo"><img src="file://{ASSETS}/muz-logo.png" alt=""></div>"""
    else:
        raise ValueError(f'template inconnu : {template}')
    return f"""<!doctype html><html lang="fr"><head><meta charset="utf-8">
<style>
@font-face {{ font-family: 'Inter'; src: url('file://{ASSETS}/Inter.woff2') format('woff2'); font-weight: 100 900; }}
* {{ box-sizing: border-box; margin: 0; }}
html, body {{ width: 1080px; height: 1920px; }}
body {{
  font-family: 'Inter', 'Noto Sans', sans-serif;
  background: radial-gradient(circle at 25% 12%, #1f3a3a 0%, {MUZ_FOND} 55%, #0a1213 100%);
  color: #fff; display: flex; flex-direction: column; align-items: center; justify-content: center;
  gap: 40px; padding: 170px 70px 200px; text-align: center;
}}
.kicker {{ font-size: 54px; font-weight: 800; letter-spacing: .03em; text-transform: uppercase; color: #2BD49A; }}
.card {{ background: #fff; color: #1b2b2c; border-radius: 44px; padding: 52px 52px; width: 100%;
  box-shadow: 0 30px 80px rgba(0,0,0,.45); display: flex; flex-direction: column; gap: 28px; align-items: center;
  border-top: 14px solid {MUZ_VERT}; }}
.label {{ font-size: 40px; font-weight: 700; color: {MUZ_VERT}; text-transform: uppercase; letter-spacing: .04em; }}
.extrait {{ font-weight: 500; font-style: italic; line-height: 1.4; color: #1b2b2c; }}
.question {{ font-size: 50px; font-weight: 800; color: {MUZ_FOND}; line-height: 1.25; }}
.opts {{ width: 100%; display: flex; flex-direction: column; gap: 22px; }}
.opt, .rep {{ display: flex; align-items: center; gap: 28px; background: #eef7f3; border-radius: 28px;
  padding: 20px 30px; font-size: 44px; font-weight: 700; color: {MUZ_FOND}; text-align: left; }}
.l {{ flex: none; width: 76px; height: 76px; border-radius: 50%; background: {MUZ_VERT}; color: #fff;
  display: flex; align-items: center; justify-content: center; font-size: 42px; font-weight: 800; }}
.rep {{ font-size: 58px; background: #dff3ea; width: 100%; }}
.src {{ font-size: 36px; line-height: 1.4; color: #3a4f50; }}
.titre {{ font-size: 36px; font-weight: 700; color: {MUZ_VERT}; line-height: 1.35; }}
.hint {{ font-size: 44px; font-weight: 600; line-height: 1.4; }}
.logo {{ background: #fff; border-radius: 999px; padding: 16px 38px; }}
.logo img {{ height: 64px; display: block; }}
</style></head><body>
{body}
</body></html>"""


def build_html(template: str, data: dict) -> str:
    if template.startswith('muz_'):
        return build_html_muz(template, data)
    e = html.escape
    lang_name = e(data.get('langue_nom', ''))
    flag = e(data.get('drapeau', ''))
    code = data.get('langue_code', '')
    kicker = e(data.get('kicker', ''))
    if template == 'question':
        fr = data.get('traduction', '')
        body = f"""
          <div class="kicker">{kicker or 'Quiz du jour'} {flag}</div>
          <div class="card">
            <div class="q">Comment dit-on</div>
            <div class="big" style="font-size:{_fit(fr, 104, 11)}px">«&nbsp;{e(fr)}&nbsp;»</div>
            <div class="q">en <b>{lang_name}</b>&nbsp;?</div>
          </div>
          <div class="hint">Réponds-moi en message 💬<br>Réponse dans quelques heures !</div>"""
    elif template == 'answer':
        word = data.get('mot', '')
        body = f"""
          <div class="kicker">Réponse {flag}</div>
          <div class="card">
            <div class="q">«&nbsp;{e(data.get('traduction', ''))}&nbsp;» en {lang_name}</div>
            {_word_block(word, code, _fit(word, 150, 8))}
            {'<div class="translit">' + e(data.get('translitteration') or '') + '</div>' if data.get('translitteration') else ''}
          </div>
          <div class="hint">Tu avais trouvé ? 🎉</div>"""
    elif template == 'answer_duel':
        # Duel (comme le Reel « A vs B ») : le même sens dans les deux langues, chacune avec son drapeau.
        blocs = ''
        for m in (data.get('mots') or [])[:2]:
            mot = m.get('mot', '')
            blocs += (f'<div class="duel"><div class="q">{e(m.get("drapeau", ""))} {e(m.get("langue_nom", ""))}</div>'
                      f'{_word_block(mot, m.get("langue_code", ""), _fit(mot, 120, 8))}'
                      + (f'<div class="translit">{e(m.get("translitteration") or "")}</div>' if m.get('translitteration') else '')
                      + '</div>')
        body = f"""
          <div class="kicker">Réponse</div>
          <div class="card">
            <div class="q">«&nbsp;{e(data.get('traduction', ''))}&nbsp;»</div>
            {blocs}
          </div>
          <div class="hint">Tu avais trouvé les deux ? 🎉</div>"""
    elif template == 'cta':
        words = data.get('mots') or []
        chips = ''.join(
            f'<div class="chip"><span lang="{LANG_TAGS.get(w.get("langue_code",""), "")}" '
            f'dir="{"rtl" if w.get("langue_code") in RTL else "ltr"}">{e(w.get("mot",""))}</span>'
            f'<small>{e(w.get("traduction",""))}</small></div>' for w in words[:4])
        body = f"""
          <div class="kicker">Apprends ces mots</div>
          <div class="card">
            <div class="big" style="font-size:88px">sur VocaBag</div>
            {'<div class="chips">' + chips + '</div>' if chips else ''}
            <div class="q">Répétition espacée · quiz · 12 langues</div>
          </div>
          <div class="url">vocabag.com</div>
          <div class="hint">Lien en bio</div>"""
    else:
        raise ValueError(f'template inconnu : {template}')

    return f"""<!doctype html><html lang="fr"><head><meta charset="utf-8">
<style>
@font-face {{ font-family: 'Inter'; src: url('file://{ASSETS}/Inter.woff2') format('woff2'); font-weight: 100 900; }}
* {{ box-sizing: border-box; margin: 0; }}
html, body {{ width: 1080px; height: 1920px; }}
body {{
  font-family: 'Inter', 'Noto Sans', 'Noto Naskh Arabic', 'Noto Sans CJK SC', 'Noto Sans CJK KR', sans-serif;
  background: radial-gradient(circle at 20% 10%, #19c2ad 0%, {BRAND} 45%, #0a6f63 100%);
  color: #fff; display: flex; flex-direction: column; align-items: center; justify-content: center;
  gap: 56px; padding: 260px 80px 420px; text-align: center;
}}
.kicker {{ font-size: 52px; font-weight: 800; letter-spacing: .02em; text-transform: uppercase; opacity: .95; }}
.card {{ background: #fff; color: #0b3d37; border-radius: 48px; padding: 72px 64px; width: 100%;
  box-shadow: 0 30px 80px rgba(0,0,0,.25); display: flex; flex-direction: column; gap: 32px; align-items: center; }}
.q {{ font-size: 54px; font-weight: 600; color: #3a5a55; }}
.big {{ font-size: 104px; font-weight: 800; color: {BRAND}; line-height: 1.1; }}
.native {{ font-weight: 700; color: {BRAND}; line-height: 1.25; }}
.native:lang(ar), .native:lang(ar-MA) {{ font-family: 'Noto Naskh Arabic', 'Noto Sans Arabic', serif; }}
.native:lang(zh-Hans) {{ font-family: 'Noto Sans CJK SC', sans-serif; }}
.native:lang(ko) {{ font-family: 'Noto Sans CJK KR', sans-serif; }}
.translit {{ font-size: 56px; font-style: italic; color: #3a5a55; }}
.hint {{ font-size: 44px; font-weight: 600; opacity: .95; line-height: 1.4; }}
.url {{ font-size: 96px; font-weight: 900; background: #fff; color: {BRAND}; padding: 20px 56px; border-radius: 999px; }}
.duel {{ width: 100%; display: flex; flex-direction: column; align-items: center; gap: 8px;
  padding-top: 24px; border-top: 2px solid #e7f6f4; }}
.chips {{ display: flex; flex-wrap: wrap; gap: 20px; justify-content: center; }}
.chip {{ background: #e7f6f4; border-radius: 28px; padding: 18px 30px; display: flex; flex-direction: column; }}
.chip span {{ font-size: 56px; font-weight: 700; color: {BRAND}; }}
.chip span:lang(ar), .chip span:lang(ar-MA) {{ font-family: 'Noto Naskh Arabic', serif; }}
.chip span:lang(zh-Hans) {{ font-family: 'Noto Sans CJK SC', sans-serif; }}
.chip span:lang(ko) {{ font-family: 'Noto Sans CJK KR', sans-serif; }}
.chip small {{ font-size: 30px; color: #3a5a55; }}
.logo {{ position: absolute; bottom: 260px; left: 50%; transform: translateX(-50%);
  background: rgba(255,255,255,.92); border-radius: 999px; padding: 14px 34px; }}
.logo img {{ height: 64px; display: block; }}
</style></head><body>
{body}
<div class="logo"><img src="file://{ASSETS}/logo.png" alt=""></div>
</body></html>"""


def render(params: dict, payload: dict) -> dict:
    page_html = build_html(payload.get('template', ''), payload.get('data') or {})
    page = _browser().new_page(viewport={'width': 1080, 'height': 1920}, device_scale_factor=1)
    try:
        tmp_dir = BASE_DIR / 'tmp'
        tmp_dir.mkdir(exist_ok=True)
        tmp = tmp_dir / f"render_{secrets.token_hex(8)}.html"
        tmp.write_text(page_html, encoding='utf-8')
        page.goto(f'file://{tmp}')
        page.evaluate('document.fonts.ready')
        png = page.screenshot(type='png', full_page=False)
        tmp.unlink(missing_ok=True)
    finally:
        page.close()
    img = Image.open(io.BytesIO(png)).convert('RGB')
    out = _save_jpeg(img)
    return {'url': _public_url(out), 'width': img.width, 'height': img.height}


# ---------------------------------------------------------------- /muz/reel-story
# Story vidéo Muz Rappel : extrait (< 60 s, limite des stories Instagram/Facebook) du Reel publié le jour même.
MUZ_VIDEOS_DIR = Path(os.environ.get('MUZ_VIDEOS_DIR', '/var/www/muz-video-template/channels/muzrappel/videos'))
STORY_MAX_S = 59.0
BANDEAU_S = 4.5            # durée d'affichage du bandeau « vidéo complète » à la fin de l'extrait
BANDEAU_Y = 250            # en haut : les sous-titres karaoké sont au centre, la pub ebook en bas
FONT_BOLD = '/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf'


def _muz_bandeau() -> Path:
    """PNG transparent : « La vidéo complète est sur notre compte » (carte blanche, liseré vert Muz)."""
    from PIL import ImageDraw, ImageFont
    out = BASE_DIR / 'tmp' / 'muz_bandeau_v1.png'
    if out.exists():
        return out
    out.parent.mkdir(exist_ok=True)
    w, h, r = 900, 230, 44
    img = Image.new('RGBA', (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([0, 0, w - 1, h - 1], radius=r, fill=(255, 255, 255, 245))
    d.rounded_rectangle([0, 0, 22, h - 1], radius=11, fill=(0x16, 0x96, 0x66, 255))
    f1, f2 = ImageFont.truetype(FONT_BOLD, 62), ImageFont.truetype(FONT_BOLD, 50)
    for texte, font, y, col in (('La vidéo complète', f1, 38, (0x11, 0x1c, 0x1e, 255)),
                                 ('est sur notre compte', f2, 128, (0x16, 0x96, 0x66, 255))):
        tw = d.textlength(texte, font=font)
        d.text(((w + 22 - tw) / 2, y), texte, font=font, fill=col)
    img.save(out)
    return out


def _pauses(video: Path) -> list:
    """(début, fin) des silences de la voix — render.mp4 (sans musique) sert de repère pour couper entre deux phrases."""
    import re
    import subprocess
    out = subprocess.run(['ffmpeg', '-hide_banner', '-nostats', '-i', str(video), '-af',
                          'silencedetect=noise=-35dB:d=0.35', '-f', 'null', '-'],
                         capture_output=True, text=True, timeout=180).stderr
    debuts = [float(x) for x in re.findall(r'silence_start: ([0-9.]+)', out)]
    fins = [float(x) for x in re.findall(r'silence_end: ([0-9.]+)', out)]
    return list(zip(debuts, fins))


def muz_reel_story(payload: dict) -> dict:
    import subprocess
    from zoneinfo import ZoneInfo
    tz = ZoneInfo('Europe/Paris')
    jour = payload.get('date') or datetime.now(tz).strftime('%Y-%m-%d')
    finales = [p for p in MUZ_VIDEOS_DIR.glob('*/render_with_soundtrack.mp4')
               if datetime.fromtimestamp(p.stat().st_mtime, tz).strftime('%Y-%m-%d') == jour]
    if not finales:
        return {'absent': True, 'date': jour}
    finale = max(finales, key=lambda p: p.stat().st_mtime)
    duree = float(subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0',
                                  str(finale)], capture_output=True, text=True, timeout=60).stdout.strip() or 0)
    coupe = min(duree, STORY_MAX_S)
    if duree > STORY_MAX_S:
        repere = finale.with_name('render.mp4') if finale.with_name('render.mp4').exists() else finale
        # dernière pause qui commence avant la limite : on coupe juste après son début (fin de phrase)
        candidats = [d for d, f in _pauses(repere) if 20 <= d + 0.3 <= STORY_MAX_S]
        coupe = (max(candidats) + 0.3) if candidats else STORY_MAX_S
    fondu = max(0.0, coupe - 0.6)
    debut_bandeau = max(0.0, coupe - BANDEAU_S)
    out = _now_dir() / f"{secrets.token_urlsafe(18)}.mp4"
    # Bandeau « vidéo complète » en fondu sur les dernières secondes (l'extrait s'arrête en cours de vidéo).
    filtre = (f"[1:v]format=rgba,fade=t=in:st={debut_bandeau:.2f}:d=0.5:alpha=1[b];"
              f"[0:v][b]overlay=x=(W-w)/2:y={BANDEAU_Y}:shortest=1:enable='gte(t,{debut_bandeau:.2f})',"
              f"fade=t=out:st={fondu:.2f}:d=0.6[v]")
    subprocess.run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-y', '-i', str(finale),
                    '-loop', '1', '-i', str(_muz_bandeau()), '-t', f'{coupe:.2f}',
                    '-filter_complex', filtre, '-map', '[v]', '-map', '0:a',
                    '-af', f'afade=t=out:st={fondu:.2f}:d=0.6',
                    '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '23', '-c:a', 'aac', '-b:a', '128k',
                    '-movflags', '+faststart', str(out)], check=True, timeout=600)
    out.chmod(0o644)
    return {'absent': False, 'date': jour, 'dossier': finale.parent.name, 'duree_source': round(duree, 2),
            'duree': round(coupe, 2), 'url': _public_url(out), 'bytes': out.stat().st_size}


# ---------------------------------------------------------------- /blog/*
# Articles publiés sur vocabag.com (dépôt de PROD, lecture seule) : pour la newsletter hebdo.
BLOG_PROD_DIR = Path(os.environ.get('BLOG_PROD_DIR', '/var/www/vocabag/blog/articles'))


def articles_recents(payload: dict) -> dict:
    """Articles dont la date (frontmatter) tombe dans les `jours` derniers jours, du plus récent au plus ancien."""
    from datetime import date, timedelta
    jours = max(1, min(int(payload.get('jours') or 7), 60))
    debut, aujourd_hui = (date.today() - timedelta(days=jours)).isoformat(), date.today().isoformat()
    articles = []
    for f in BLOG_PROD_DIR.glob('*.md'):
        texte = f.read_text(encoding='utf-8', errors='replace')
        fin = texte.find('---', 3) if texte.startswith('---') else -1
        if fin < 0:
            continue
        meta = {}
        for ligne in texte[3:fin].splitlines():
            if ':' in ligne:
                k, v = ligne.split(':', 1)
                meta[k.strip()] = v.strip().strip('"')
        d = meta.get('date', '')[:10]
        if meta.get('slug') and meta.get('title') and debut < d <= aujourd_hui:
            articles.append({k: meta.get(k, '') for k in ('slug', 'title', 'description', 'date', 'category', 'image')})
    articles.sort(key=lambda a: (a['date'], a['slug']), reverse=True)
    return {'ok': True, 'jours': jours, 'articles': articles}


def blog(action: str, payload: dict) -> dict:
    if action == 'recents':
        return articles_recents(payload)
    if action == 'enqueue':
        return blogfile.mettre_en_file(payload, PUBLIC_DIR, PUBLIC_BASE_URL)
    if action == 'rediger':
        return blogfile.lancer_redaction(payload)
    if action in ('publier', 'rejeter', 'reecrire'):
        return getattr(blogfile, action)(str(payload.get('id', '')))
    raise ValueError(f'action blog inconnue : {action}')


# ---------------------------------------------------------------- HTTP
class Handler(BaseHTTPRequestHandler):
    server_version = 'vocabag-media/1'

    def _send(self, code: int, obj: dict):
        body = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _params(self) -> dict:
        from urllib.parse import parse_qs, urlparse
        return {k: v[0] for k, v in parse_qs(urlparse(self.path).query).items()}

    def do_GET(self):
        if self.path.startswith('/health'):
            return self._send(200, {'ok': True})
        self._send(404, {'error': 'not found'})

    def do_POST(self):
        if not TOKEN or not secrets.compare_digest(self.headers.get('X-Media-Token', ''), TOKEN):
            return self._send(401, {'error': 'jeton invalide'})
        length = int(self.headers.get('Content-Length') or 0)
        if length <= 0 or length > MAX_BYTES:
            return self._send(413, {'error': 'corps vide ou trop gros'})
        raw = self.rfile.read(length)
        route = self.path.split('?')[0]
        try:
            _purge()
            if route == '/ingest':
                return self._send(200, ingest(raw, self._params()))
            if route == '/stage':
                return self._send(200, stage(raw, self._params()))
            if route == '/render':
                return self._send(200, render(self._params(), json.loads(raw)))
            if route == '/detect-langues':
                p = json.loads(raw)
                return self._send(200, detection.detecter(p.get('images') or [], PUBLIC_DIR, PUBLIC_BASE_URL,
                                                          p.get('modele', 'haiku')))
            if route == '/emojis':
                p = json.loads(raw)
                return self._send(200, emojis.choisir(p.get('mots') or [], p.get('categorie', ''), p.get('modele', 'haiku')))
            if route == '/muz/reel-story':
                return self._send(200, muz_reel_story(json.loads(raw or b'{}')))
            if route.startswith('/blog/'):
                return self._send(200, blog(route[6:], json.loads(raw)))
            return self._send(404, {'error': 'not found'})
        except Exception as exc:  # renvoyé tel quel à n8n, qui le relaie sur Telegram
            return self._send(400, {'error': f'{type(exc).__name__}: {exc}'})

    def log_message(self, fmt, *args):
        print(f"{self.address_string()} {fmt % args}", flush=True)


if __name__ == '__main__':
    PUBLIC_DIR.mkdir(parents=True, exist_ok=True)
    if not TOKEN:
        raise SystemExit('MEDIA_TOKEN manquant')
    # Serveur mono-thread volontaire : Playwright (API sync) n'est pas thread-safe, et le volume
    # (quelques images par jour) ne justifie pas plus.
    HTTPServer((HOST, PORT), Handler).serve_forever()
