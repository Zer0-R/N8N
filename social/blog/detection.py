"""Détection de la (des) langue(s) apprise(s) d'après les images, quand la légende Telegram n'en donne pas.

Appelé par vocabag-media (POST /detect-langues) depuis le workflow Carrousel. Claude Code headless
(abonnement, modèle léger par défaut) lit les premières images et renvoie 1 langue, ou 2 pour un
duel (ex. arabe littéraire vs darija, comme le genre « duel » de Vocabag Video). Seul outil : Read.
"""
import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

CLAUDE = os.environ.get('CLAUDE_BIN', '/root/.local/bin/claude')
CODES = {'ary': 'darija marocain (arabe dialectal marocain, souvent translittéré avec des chiffres : 3, 7, 9)',
         'ar': 'arabe littéraire (MSA / fusha)', 'en': 'anglais', 'de': 'allemand', 'es': 'espagnol',
         'pt': 'portugais (Brésil)', 'it': 'italien', 'nl': 'néerlandais', 'ru': 'russe', 'tr': 'turc',
         'zh': 'chinois', 'ko': 'coréen'}
MAX_IMAGES = 3
DELAI = 150

CONSIGNE = """Tu identifies la ou les langues ENSEIGNÉES dans une publication Instagram de VocaBag (appli
d'apprentissage de langues pour francophones). Lis avec l'outil Read : {fichiers}.
Le français sert en général de langue de traduction : ne le compte pas comme langue enseignée.

Codes possibles :
{codes}

- 1 langue : le cas normal.
- 2 langues : seulement si les images COMPARENT deux langues enseignées (même mot dans deux langues,
  titre « X vs Y », deux drapeaux…). Mets-les dans l'ordre où elles apparaissent.
- Darija vs arabe littéraire : le darija utilise des mots dialectaux (ex. bzaf, wach, daba, zwin, bghit)
  et souvent des chiffres dans la translittération ; l'arabe littéraire, des formes classiques.
- Si tu ne peux pas décider, renvoie une liste vide.

Réponds UNIQUEMENT avec ce JSON, sans rien d'autre :
{{"langues": ["code"], "confiance": "haute|moyenne|basse", "raison": "une phrase courte en français"}}"""


def detecter(urls: list, public_dir: Path, public_base_url: str, modele: str = 'haiku') -> dict:
    racine = public_dir.resolve()
    tmp = Path(tempfile.mkdtemp(prefix='vb-detect-'))
    try:
        noms = []
        for i, url in enumerate(urls[:MAX_IMAGES], 1):
            if not str(url).startswith(public_base_url + '/'):
                raise ValueError(f'image {i} : URL hors hébergement')
            src = (public_dir / url[len(public_base_url) + 1:]).resolve()
            if racine not in src.parents or not src.is_file():
                raise ValueError(f'image {i} introuvable')
            shutil.copyfile(src, tmp / f'{i}.jpg')
            noms.append(f'`{i}.jpg`')
        consigne = CONSIGNE.format(fichiers=', '.join(noms),
                                   codes='\n'.join(f'- {c} : {n}' for c, n in CODES.items()))
        cmd = [CLAUDE, '-p', '--output-format', 'json', '--max-turns', str(len(noms) + 3),
               '--allowedTools', 'Read',
               '--disallowedTools', 'Bash', 'Write', 'Edit', 'NotebookEdit', 'WebFetch', 'WebSearch', 'Task']
        if modele:
            cmd += ['--model', modele]
        r = subprocess.run(cmd, input=consigne, capture_output=True, text=True, timeout=DELAI, cwd=str(tmp))
        try:
            res = json.loads(r.stdout)
        except ValueError:
            raise RuntimeError(f'claude a quitté (code {r.returncode}) : {(r.stderr or r.stdout).strip()[:200]}')
        if res.get('is_error') or res.get('subtype') != 'success':
            raise RuntimeError(f"claude : {res.get('subtype')} — {str(res.get('result'))[:200]}")
        x = re.search(r'\{.*\}', res.get('result') or '', re.S)
        if not x:
            raise RuntimeError('réponse sans JSON')
        d = json.loads(x.group(0))
        langues = []
        for c in d.get('langues') or []:
            c = str(c).strip().lower()
            if c in CODES and c not in langues:
                langues.append(c)
        return {'ok': True, 'langues': langues[:2], 'confiance': str(d.get('confiance', ''))[:10],
                'raison': str(d.get('raison', ''))[:200]}
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
