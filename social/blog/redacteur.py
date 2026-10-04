#!/usr/bin/env python3
"""Rédige les brouillons d'articles des carrousels en attente avec Claude Code (abonnement, sans API).

Lancé en arrière-plan par vocabag-media (POST /blog/rediger, appelé par n8n chaque soir).
Pour chaque carrousel en_attente (max N) : `claude -p` lit les images, vérifie les mots dans la base
VocaBag (mots.py, lecture seule), renvoie l'article → brouillon.md, puis rappel du webhook n8n
« Blog prêt » qui envoie l'e-mail et le message Telegram à valider.

Claude n'a que deux outils : Read, et `python3 mots.py …`. Aucune écriture, aucun accès web.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import time
import traceback
import urllib.request
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import blogfile as bf  # noqa: E402

CLAUDE = os.environ.get('CLAUDE_BIN', '/root/.local/bin/claude')
MOTS = bf.ICI / 'mots.py'
CONSIGNE = bf.ICI / 'consigne.md'
DELAI = 20 * 60
ESSAIS_MAX = 2
NOMS = {'ary': 'darija marocain', 'ar': 'arabe littéraire', 'en': 'anglais', 'de': 'allemand', 'es': 'espagnol',
        'pt': 'portugais (Brésil)', 'it': 'italien', 'nl': 'néerlandais', 'ru': 'russe', 'tr': 'turc',
        'zh': 'chinois', 'ko': 'coréen'}


def log(*a):
    print(datetime.now().strftime('%Y-%m-%d %H:%M:%S'), *a, flush=True)


def articles_existants(categorie: str) -> list:
    out = []
    for p in bf.ARTICLES.glob('*.md'):
        t = p.read_text(errors='ignore')[:1500]
        titre = re.search(r'^title:\s*"?(.+?)"?\s*$', t, re.M)
        cat = re.search(r'^category:\s*(.+?)\s*$', t, re.M)
        out.append((0 if cat and cat.group(1) == categorie else 1, p.stem, titre.group(1) if titre else p.stem, p))
    return sorted(out)


def consigne(m: dict, d: Path) -> str:
    cat = bf.CATEGORIES.get(m['langue_code'], 'Méthode')
    existants = articles_existants(cat)
    modele = next((a[3] for a in existants if a[0] == 0), bf.ARTICLES / '10-expressions-darija.md')
    shutil.copyfile(modele, d / 'exemple.md')
    langues = m.get('langues') or ([m['langue_code']] if m['langue_code'] else [])
    if len(langues) == 2:
        langue_nom = (f"DUEL {NOMS[langues[0]]} vs {NOMS[langues[1]]} — article comparatif : chaque mot est donné "
                      f"dans les deux langues, vérifié avec l'outil pour chacune")
    else:
        langue_nom = NOMS.get(langues[0], '') if langues else 'non précisée — déduis-la des images'
    return CONSIGNE.read_text().format(
        images=', '.join(f"`{i['fichier']}` (image {n})" for n, i in enumerate(m['images'], 1)),
        langue_nom=langue_nom,
        langue_code=' et '.join(f'`{c}`' for c in langues) or '`ary`',
        caption=m['caption'].strip() or '(aucune)',
        texte_instagram='\n'.join('  > ' + l for l in (m['texte'].strip() or '(aucune)').splitlines()),
        mots_py=MOTS,
        articles='\n'.join(f'  - {a[1]} — {a[2]}' for a in existants[:40]),
    )


def analyser(texte: str, nb_images: int) -> dict:
    """Réponse de Claude → titre/slug/description/corps ; lève ValueError si inutilisable."""
    texte = re.sub(r'^```(?:markdown|md)?\s*\n|\n```\s*$', '', texte.strip())
    if texte.startswith('ERREUR'):
        raise ValueError('Claude a refusé : ' + texte[:300])
    x = re.search(r'^---\s*\n(.*?)\n---\s*\n(.*)$', texte, re.S)
    if not x:
        raise ValueError('pas d’en-tête --- … ---')
    champs = dict(re.findall(r'^(\w+):\s*"?(.*?)"?\s*$', x.group(1), re.M))
    titre, slug, desc = champs.get('title', '').strip(), champs.get('slug', '').strip(), champs.get('description', '').strip()
    corps = x.group(2).strip()
    if not (titre and desc and bf.SLUG_OK.match(slug) and len(slug) <= 80):
        raise ValueError(f'en-tête incomplet ou slug invalide ({slug!r})')
    mots = len(re.findall(r'\w+', corps))
    if mots < 150:
        raise ValueError(f'article trop court ({mots} mots)')
    avert = []
    for n in re.findall(r'\(IMAGE_(\d+)\)', corps):
        if not 1 <= int(n) <= nb_images:
            raise ValueError(f'IMAGE_{n} n’existe pas ({nb_images} images)')
    liens = re.findall(r'\]\((/blog/[^)\s]+)\)', corps)
    connus = {p.stem for p in bf.ARTICLES.glob('*.md')}
    avert += [f'lien interne inconnu : {l}' for l in liens if l.split('/')[-1] not in connus]
    if re.search(r'^\s*\d+\. ', corps, re.M):
        avert.append('liste numérotée « 1. » : le site l’affichera comme du texte simple')
    if re.search(r'^\s*[|>]', corps, re.M):
        avert.append('tableau ou citation : non pris en charge par le site')
    if re.search(r'^# ', corps, re.M):
        avert.append('titre « # » dans le corps')
    return {'titre': titre, 'slug': slug, 'description': desc, 'corps': corps + '\n', 'mots': mots,
            'avertissements': avert}


def rediger(m: dict, modele: str) -> dict:
    d = bf.FILE / m['id']
    cmd = [CLAUDE, '-p', '--output-format', 'json', '--max-turns', '40',
           '--allowedTools', 'Read', f'Bash(python3 {MOTS}:*)',
           '--disallowedTools', 'Write', 'Edit', 'NotebookEdit', 'WebFetch', 'WebSearch', 'Task']
    if modele:
        cmd += ['--model', modele]
    r = subprocess.run(cmd, input=consigne(m, d), capture_output=True, text=True, timeout=DELAI, cwd=str(d))
    (d / 'redaction.log').write_text(r.stdout + '\n--- stderr ---\n' + r.stderr)
    try:
        res = json.loads(r.stdout)
    except ValueError:
        raise RuntimeError(f'claude a quitté (code {r.returncode}) : {(r.stderr or r.stdout).strip()[:300]}')
    if res.get('is_error') or res.get('subtype') != 'success':
        raise RuntimeError(f"claude : {res.get('subtype')} — {str(res.get('result'))[:300]}")
    return analyser(res.get('result') or '', len(m['images']))


def rappeler(webhook: str, payload: dict):
    req = urllib.request.Request(webhook, method='POST', data=json.dumps(payload).encode(),
                                 headers={'Content-Type': 'application/json',
                                          'X-Media-Token': os.environ.get('MEDIA_TOKEN', '')})
    for essai in range(3):
        try:
            with urllib.request.urlopen(req, timeout=30):
                return
        except Exception as exc:  # noqa: BLE001
            log('webhook échec', essai + 1, exc)
            time.sleep(10)


def apercu(m: dict, corps: str) -> str:
    urls = {n: i['url_apercu'] for n, i in enumerate(m['images'], 1)}
    return bf.corps_final(m, corps, lambda n: urls.get(n, ''))


def main():
    conf = json.loads((bf.FILE / '.config.json').read_text())
    # Un échec non définitif remet le carrousel en_attente : il sera retenté au prochain passage.
    for m in [m for m in bf.tous() if m['statut'] == 'en_attente'][:conf['max']]:
        m['statut'] = 'redaction'
        bf.ecrire(m)
        log('rédaction', m['id'], m['source_ref'])
        try:
            a = rediger(m, conf.get('modele', ''))
            m.update(titre=a['titre'], description=a['description'], avertissements=a['avertissements'],
                     slug=bf.slug_libre(a['slug'], m['id']), statut='pret', erreur='',
                     redige_le=datetime.now().isoformat(timespec='seconds'))
            (bf.FILE / m['id'] / 'brouillon.md').write_text(a['corps'])
            bf.ecrire(m)
            corps = apercu(m, bf.image_dans_corps(a['corps']))
            # Chemin de la couverture telle qu'elle sera publiée (fond de la langue, générée par publier()).
            couverture = f"{bf.IMAGES_WEB}/{m['slug']}/couverture.jpg"
            rappeler(conf['webhook'], {
                'ok': True, 'id': m['id'], 'titre': m['titre'], 'slug': m['slug'], 'description': m['description'],
                'categorie': bf.CATEGORIES.get(m['langue_code'], 'Méthode'), 'mots': a['mots'],
                'avertissements': m['avertissements'], 'permalink': m['permalink'],
                'markdown': bf.frontmatter(m, '(date de publication)', couverture) + corps,
                'html': bf.markdown_html(corps),
            })
            log('prêt', m['id'], m['slug'])
        except Exception as exc:  # noqa: BLE001
            traceback.print_exc()
            m['essais'] = m.get('essais', 0) + 1
            m['erreur'] = str(exc)[:500]
            definitif = m['essais'] >= ESSAIS_MAX or str(exc).startswith('Claude a refusé')
            m['statut'] = 'echec' if definitif else 'en_attente'
            bf.ecrire(m)
            rappeler(conf['webhook'], {'ok': False, 'id': m['id'], 'erreur': m['erreur'], 'definitif': definitif,
                                       'permalink': m['permalink']})


if __name__ == '__main__':
    main()
