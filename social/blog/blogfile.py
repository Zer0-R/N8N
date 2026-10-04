"""File des articles de blog tirés des publications Instagram — carrousel ou photo seule (VocaBag Social).

Un dossier par carrousel dans carrousels/<id>/ :
  meta.json      état + données du carrousel (voir nouveau())
  1.jpg, 2.jpg…  images du carrousel (copiées depuis public/, qui est purgé après 14 jours)
  brouillon.md   corps de l'article rédigé (images en IMAGE_n), écrit par redacteur.py
  exemple.md     article existant donné en modèle au rédacteur
  redaction.log  sortie brute du dernier passage de Claude

Statuts : en_attente → redaction → pret → publie | rejete ; echec (après 2 essais ratés).
« Publier » = copie dans le dépôt vocabag-staging (branche staging) + commit local : l'article
arrive en prod au prochain déploiement (staging → master → deploy_prod.sh), jamais avant.
Utilisé par media-service/server.py (routes /blog/*) et par redacteur.py.
"""
import html
import json
import os
import re
import secrets
import shutil
import subprocess
import time
from datetime import datetime
from pathlib import Path

from PIL import Image

ICI = Path(__file__).resolve().parent
FILE = Path(os.environ.get('BLOG_DIR', ICI / 'carrousels'))
REPO = Path(os.environ.get('BLOG_REPO', '/var/www/vocabag-staging'))
ARTICLES = REPO / 'blog' / 'articles'
IMAGES_WEB = '/assets/images/blog'            # chemin public des images publiées
SITE_STAGING = 'https://staging.vocabag.com'
SITE_PROD = 'https://vocabag.com'
LARGEUR_WEB = 1200
# Fonds par langue (mêmes visuels que les vidéos du channel vocabag) : <code>.png, duel <a>_<b>.png
FONDS = Path(os.environ.get('BLOG_FONDS', '/var/www/muz-video-template/channels/vocabag/images/languages'))
COUV_L, COUV_H = 1200, 630                    # format des aperçus de partage (og:image)

# Code VocaBag → catégorie du blog (clés de $_catColors dans blog-index.php / blog/article.php).
CATEGORIES = {'ary': 'Darija', 'ar': 'Arabe', 'en': 'Anglais', 'de': 'Allemand', 'es': 'Espagnol',
              'tr': 'Turc', 'pt': 'Portugais', 'it': 'Italien', 'nl': 'Néerlandais', 'ru': 'Russe',
              'zh': 'Chinois', 'ko': 'Coréen'}
SLUG_OK = re.compile(r'^[a-z0-9]+(?:-[a-z0-9]+)*$')


# ---------------------------------------------------------------- stockage
def dossier(id_: str) -> Path:
    if not re.fullmatch(r'c\d{8}-[0-9a-f]{6}', id_ or ''):
        raise ValueError('identifiant invalide')
    d = FILE / id_
    if not d.is_dir():
        raise ValueError(f'carrousel {id_} introuvable')
    return d


def lire(id_: str) -> dict:
    return json.loads((dossier(id_) / 'meta.json').read_text())


def ecrire(meta: dict):
    p = FILE / meta['id'] / 'meta.json'
    tmp = p.with_suffix('.tmp')
    tmp.write_text(json.dumps(meta, ensure_ascii=False, indent=2))
    tmp.replace(p)


def tous() -> list:
    out = []
    for p in sorted(FILE.glob('c*/meta.json')):
        try:
            out.append(json.loads(p.read_text()))
        except (OSError, ValueError):
            pass
    return out


# ---------------------------------------------------------------- /blog/enqueue
def mettre_en_file(payload: dict, public_dir: Path, public_base_url: str) -> dict:
    """Carrousel publié sur Instagram → nouvelle entrée en_attente (idempotent sur source_ref)."""
    ref = str(payload.get('source_ref') or '').strip()
    if not ref:
        raise ValueError('source_ref manquant')
    for m in tous():
        if m.get('source_ref') == ref:
            return {'ok': True, 'id': m['id'], 'deja': True}
    urls = payload.get('images') or []
    if not urls:
        raise ValueError('aucune image')
    racine, sources = public_dir.resolve(), []
    for i, url in enumerate(urls, 1):
        if not str(url).startswith(public_base_url + '/'):
            raise ValueError(f'image {i} : URL hors hébergement ({url})')
        src = (public_dir / url[len(public_base_url) + 1:]).resolve()
        if racine not in src.parents or not src.is_file():
            raise ValueError(f'image {i} introuvable ({url})')
        sources.append((src, url))
    id_ = f"c{datetime.now():%Y%m%d}-{secrets.token_hex(3)}"
    d = FILE / id_
    d.mkdir(parents=True)
    images = []
    for i, (src, url) in enumerate(sources, 1):
        shutil.copyfile(src, d / f'{i}.jpg')
        images.append({'fichier': f'{i}.jpg', 'url_apercu': url})
    ecrire({
        'id': id_, 'source_ref': ref, 'cree_le': datetime.now().isoformat(timespec='seconds'),
        'statut': 'en_attente', 'essais': 0, 'erreur': '',
        'langue_code': payload.get('langue_apprise') or '', 'langue_description': payload.get('langue_description') or 'fr',
        'langues': [c for c in (payload.get('langues_apprises') or [payload.get('langue_apprise')]) if c][:2],   # 2 = duel
        'caption': payload.get('caption') or '', 'texte': payload.get('texte') or '',
        'permalink': payload.get('permalink') or '', 'images': images,
        'titre': '', 'slug': '', 'description': '', 'avertissements': [],
    })
    return {'ok': True, 'id': id_, 'images': len(images)}


# ---------------------------------------------------------------- lancement du rédacteur
_PROCS = []


def lancer_redaction(payload: dict) -> dict:
    """Lance redacteur.py en arrière-plan (la rédaction prend plusieurs minutes) ; il rappelle n8n."""
    FILE.mkdir(parents=True, exist_ok=True)
    conf = {'webhook': payload.get('webhook') or '', 'max': int(payload.get('max') or 5),
            'modele': payload.get('modele') or ''}
    if not conf['webhook']:
        raise ValueError('webhook manquant')
    (FILE / '.config.json').write_text(json.dumps(conf))
    _PROCS[:] = [p for p in _PROCS if p.poll() is None]      # récolte les rédacteurs terminés
    if _PROCS:
        return {'ok': True, 'lance': False, 'raison': 'rédaction déjà en cours'}
    for m in tous():                  # rédacteur coupé (redémarrage du service…) : on reprend ces carrousels
        if m['statut'] == 'redaction':
            m['statut'] = 'en_attente'
            ecrire(m)
    attente = [m for m in tous() if m['statut'] == 'en_attente']
    if not attente:
        return {'ok': True, 'lance': False, 'a_rediger': 0}
    log = open(FILE / 'redacteur.log', 'a')
    _PROCS.append(subprocess.Popen(['/usr/bin/python3', str(ICI / 'redacteur.py')], cwd=str(ICI),
                                   stdout=log, stderr=subprocess.STDOUT, start_new_session=True))
    return {'ok': True, 'lance': True, 'a_rediger': min(len(attente), conf['max'])}


def reecrire(id_: str) -> dict:
    m = lire(id_)
    if m['statut'] not in ('pret', 'echec', 'rejete', 'en_attente'):
        raise ValueError(f"statut « {m['statut']} » : réécriture impossible")
    m.update(statut='en_attente', essais=0, erreur='')
    ecrire(m)
    conf = json.loads((FILE / '.config.json').read_text()) if (FILE / '.config.json').exists() else {}
    r = lancer_redaction(conf) if conf.get('webhook') else {'lance': False}
    return {'ok': True, 'id': id_, 'titre': m.get('titre', ''), 'lance': r.get('lance', False)}


def rejeter(id_: str) -> dict:
    m = lire(id_)
    if m['statut'] == 'publie':
        raise ValueError('déjà publié')
    m['statut'] = 'rejete'
    ecrire(m)
    return {'ok': True, 'id': id_, 'titre': m.get('titre', '')}


# ---------------------------------------------------------------- publication (dépôt staging)
def slugs_pris(sauf_id: str = '') -> set:
    pris = {p.stem for p in ARTICLES.glob('*.md')}
    pris |= {m['slug'] for m in tous() if m.get('slug') and m['id'] != sauf_id and m['statut'] in ('pret', 'publie')}
    return pris


def slug_libre(slug: str, sauf_id: str = '') -> str:
    pris, base, n = slugs_pris(sauf_id), slug, 2
    while slug in pris:
        slug = f'{base}-{n}'
        n += 1
    return slug


def frontmatter(m: dict, date: str, image: str) -> str:
    q = lambda s: str(s).replace('"', '”').replace('\n', ' ').strip()
    return (f'---\ntitle: "{q(m["titre"])}"\nslug: {m["slug"]}\ndate: {date}\nlang: fr\n'
            f'description: "{q(m["description"])}"\nimage: "{image}"\n'
            f'category: {CATEGORIES.get(m["langue_code"], "Méthode")}\nsource: "instagram"\n---\n\n')


def corps_final(m: dict, corps: str, url_image) -> str:
    corps = re.sub(r'\(IMAGE_(\d+)\)', lambda x: f'({url_image(int(x.group(1)))})', corps).rstrip()
    if m.get('permalink'):
        corps += f"\n\n*Cet article prolonge notre publication sur [Instagram]({m['permalink']}).*"
    return corps + '\n'


def fond_langue(langues: list):
    """Fond de la couverture : duel « a_b.png » (dans un sens ou l'autre), sinon celui de la 1re langue."""
    noms = []
    if len(langues) >= 2:
        noms += [f'{langues[0]}_{langues[1]}.png', f'{langues[1]}_{langues[0]}.png']
    noms += [f'{c}.png' for c in langues]
    return next((FONDS / n for n in noms if (FONDS / n).is_file()), None)


def couverture(langues: list) -> Image.Image:
    """Couverture 1200x630 : haut du fond de la langue (drapeaux, monuments), sans l'image Instagram
    (celle-ci est dans le corps de l'article, en entier). Sans fond disponible : couleur VocaBag."""
    f = fond_langue(langues)
    if not f:
        return Image.new('RGB', (COUV_L, COUV_H), (15, 159, 142))
    bg = Image.open(f).convert('RGB')
    bg = bg.resize((COUV_L, round(bg.height * COUV_L / bg.width)), Image.LANCZOS)
    return bg.crop((0, 0, COUV_L, COUV_H)) if bg.height >= COUV_H else bg.resize((COUV_L, COUV_H), Image.LANCZOS)


def image_dans_corps(corps: str) -> str:
    """L'image 1 (la publication Instagram, en entier) va dans le corps : après l'introduction si
    le rédacteur ne l'a pas déjà placée."""
    if '(IMAGE_1)' in corps:
        return corps
    blocs = corps.strip().split('\n\n')
    i = next((k for k, b in enumerate(blocs) if b.startswith('#')), min(1, len(blocs)))
    blocs.insert(max(i, 1) if len(blocs) > 1 else len(blocs), '![Publication Instagram VocaBag](IMAGE_1)')
    return '\n\n'.join(blocs) + '\n'


def _git(*args):
    for essai in range(6):                  # index.lock pris par une autre opération git : on réessaie
        r = subprocess.run(['git', '-C', str(REPO), '-c', 'user.name=VocaBag blog (n8n)',
                            '-c', 'user.email=blog-bot@vocabag.com', *args],
                           capture_output=True, text=True, timeout=60)
        if r.returncode == 0:
            return r.stdout.strip()
        if 'index.lock' not in r.stderr or essai == 5:
            raise RuntimeError(f"git {args[0]} : {r.stderr.strip()[:300]}")
        time.sleep(2)


def publier(id_: str) -> dict:
    m = lire(id_)
    if m['statut'] == 'publie':
        return {'ok': True, 'deja': True, 'slug': m['slug'], 'url_staging': f"{SITE_STAGING}/blog/{m['slug']}"}
    if m['statut'] != 'pret':
        raise ValueError(f"statut « {m['statut']} » : rien à publier")
    branche = _git('symbolic-ref', '--short', 'HEAD')
    if branche != 'staging':
        raise RuntimeError(f"le dépôt {REPO} est sur la branche « {branche} » (attendu : staging)")
    d = FILE / id_
    m['slug'] = slug_libre(m['slug'], id_)
    slug = m['slug']
    corps = image_dans_corps((d / 'brouillon.md').read_text())
    utilisees = sorted({1} | {int(n) for n in re.findall(r'\(IMAGE_(\d+)\)', corps)})
    dest_img = REPO / IMAGES_WEB.lstrip('/') / slug
    dest_img.mkdir(parents=True, exist_ok=True)
    dest_img.chmod(0o755)
    for n in utilisees:
        img = Image.open(d / f'{n}.jpg').convert('RGB')
        if img.width > LARGEUR_WEB:
            img = img.resize((LARGEUR_WEB, round(img.height * LARGEUR_WEB / img.width)), Image.LANCZOS)
        out = dest_img / f'{n}.jpg'
        img.save(out, 'JPEG', quality=82, optimize=True, progressive=True)
        out.chmod(0o644)
    couv = dest_img / 'couverture.jpg'
    couverture(m.get('langues') or [m['langue_code']]).save(couv, 'JPEG', quality=85, optimize=True, progressive=True)
    couv.chmod(0o644)
    url = lambda n: f'{IMAGES_WEB}/{slug}/{n}.jpg'
    md = ARTICLES / f'{slug}.md'
    md.write_text(frontmatter(m, datetime.now().strftime('%Y-%m-%d'), f'{IMAGES_WEB}/{slug}/couverture.jpg')
                  + corps_final(m, corps, url))
    md.chmod(0o644)
    chemins = [str(md.relative_to(REPO)), str(dest_img.relative_to(REPO))]
    _git('add', '--', *chemins)
    # Chemins explicites : seuls l'article et ses images partent dans le commit, jamais le reste de l'index.
    _git('commit', '-m', f"blog: {m['titre']}\n\nArticle rédigé depuis la publication Instagram {m['source_ref']}, "
                         f"validé sur Telegram.", '--', *chemins)
    m.update(statut='publie', publie_le=datetime.now().isoformat(timespec='seconds'),
             commit=_git('rev-parse', '--short', 'HEAD'))
    ecrire(m)
    return {'ok': True, 'slug': slug, 'titre': m['titre'], 'commit': m['commit'],
            'url_staging': f'{SITE_STAGING}/blog/{slug}', 'url_prod': f'{SITE_PROD}/blog/{slug}'}


# ---------------------------------------------------------------- aperçu HTML (e-mail)
def _inline(s: str) -> str:
    out, pos = '', 0
    for x in re.finditer(r'!\[([^\]]*)\]\(([^)\s]+)\)|\[([^\]]+)\]\(([^)\s]+)\)|\*\*(.+?)\*\*|\*(.+?)\*', s):
        out += html.escape(s[pos:x.start()])
        pos = x.end()
        if x.group(2):
            out += (f'<img src="{html.escape(x.group(2))}" alt="{html.escape(x.group(1))}" '
                    f'style="max-width:100%;border-radius:8px;display:block;margin:12px 0">')
        elif x.group(4):
            href = x.group(4) if x.group(4).startswith('http') else SITE_PROD + x.group(4)
            out += f'<a href="{html.escape(href)}">{html.escape(x.group(3))}</a>'
        elif x.group(5):
            out += f'<strong>{html.escape(x.group(5))}</strong>'
        else:
            out += f'<em>{html.escape(x.group(6))}</em>'
    return out + html.escape(s[pos:])


def markdown_html(md: str) -> str:
    """Même sous-ensemble Markdown que simpleMarkdown() de blog/article.php."""
    out = []
    for b in re.split(r'\n{2,}', md.strip()):
        b = b.strip()
        if not b:
            continue
        t = re.match(r'^(#{1,3}) (.+)$', b)
        if t:
            out.append(f'<h{len(t.group(1))}>{html.escape(t.group(2))}</h{len(t.group(1))}>')
        elif b == '---':
            out.append('<hr>')
        elif b.startswith('- '):
            out.append('<ul>' + ''.join(f'<li>{_inline(l.strip()[2:])}</li>' for l in b.split('\n')
                                         if l.strip().startswith('- ')) + '</ul>')
        else:
            out.append('<p>' + _inline(b).replace('\n', '<br>') + '</p>')
    return '\n'.join(out)
