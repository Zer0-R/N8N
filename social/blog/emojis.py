"""Choix des émojis du prompt carrousel (un par mot, tous différents).

Appelé par vocabag-media (POST /emojis) depuis le workflow « VocaBag Social - Prompt carrousel » : le
workflow fixe lui-même les émojis au lieu de laisser ChatGPT les choisir. Claude Code headless
(abonnement, modèle léger), sans aucun outil : il ne fait que lire la liste et répondre en JSON.
Réponse vérifiée (nombre, émojis valides, tous différents) ; un second essai si elle ne convient pas
(ou si Claude ne répond pas dans le délai).
"""
import json
import os
import re
import subprocess
import tempfile
import unicodedata

CLAUDE = os.environ.get('CLAUDE_BIN', '/root/.local/bin/claude')
DELAI = 60        # par essai ; 2 essais max = 120 s, sous le délai de 180 s du nœud n8n
MAX_MOTS = 20

CONSIGNE = """Choisis un émoji pour chaque mot de cette liste de vocabulaire (sens donné en français),
destinée à une image Instagram d'apprentissage de langues. Catégorie : {categorie}.

{liste}

Règles :
- exactement {n} émojis, dans le même ordre que la liste, un par mot ;
- tous différents ;
- l'émoji illustre le sens du mot de façon évidente (ex. « Chat » → 🐱, « Pluie » → 🌧️) ; pour un mot
  abstrait, le plus parlant possible ;
- un seul émoji Unicode standard par mot (pas de texte, pas de drapeau sauf si le mot est un pays).
{retour}
Réponds UNIQUEMENT avec ce JSON, sans rien d'autre :
{{"emojis": ["…", "…"]}}"""


def _est_emoji(s: str) -> bool:
    """Un émoji (séquences ZWJ, sélecteurs de variante, tons de peau, drapeaux, touches chiffrées), sans texte.

    Les plages d'émojis sont acceptées même si la table Unicode de Python ne connaît pas encore le caractère
    (Python 3.11 = Unicode 14 : 🪿 🫏 🪼 🩷… y sont « non attribués »).
    """
    if not s or len(s) > 14:
        return False
    if re.fullmatch('(?:[0-9#*]\ufe0f?\u20e3){1,3}', s):   # 1️⃣ #️⃣ *️⃣, et nombres jusqu'à 3 chiffres (2️⃣0️⃣ = « Vingt »)
        return True
    visible = False
    for c in s:
        o = ord(c)
        if c in '\u200d\ufe0f\ufe0e' or 0x1F3FB <= o <= 0x1F3FF or 0xE0020 <= o <= 0xE007F:
            continue
        if (0x1F000 <= o <= 0x1FAFF or 0x2600 <= o <= 0x27BF or 0x1F1E6 <= o <= 0x1F1FF
                or unicodedata.category(c) == 'So'):
            visible = True
            continue
        return False
    return visible


def _demander(consigne: str, modele: str) -> list:
    # Sans outil, sans serveur MCP, et SANS RÉFLEXION (MAX_THINKING_TOKENS=0) : avec la réflexion, haiku passait
    # 18 à 80 s (jusqu'à 9 500 jetons) à choisir 10 émojis ; sans, ~3 s pour un résultat équivalent (mesuré 2026-10-04).
    cmd = [CLAUDE, '-p', '--output-format', 'json', '--max-turns', '1', '--tools', '',
           '--strict-mcp-config', '--no-session-persistence']
    if modele:
        cmd += ['--model', modele]
    with tempfile.TemporaryDirectory(prefix='vb-emojis-') as tmp:
        r = subprocess.run(cmd, input=consigne, capture_output=True, text=True, timeout=DELAI, cwd=tmp,
                           env={**os.environ, 'MAX_THINKING_TOKENS': '0'})
    try:
        res = json.loads(r.stdout)
    except ValueError:
        raise RuntimeError(f'claude a quitté (code {r.returncode}) : {(r.stderr or r.stdout).strip()[:200]}')
    if res.get('is_error') or res.get('subtype') != 'success':
        raise RuntimeError(f"claude : {res.get('subtype')} — {str(res.get('result'))[:200]}")
    x = re.search(r'\{.*\}', res.get('result') or '', re.S)
    if not x:
        raise RuntimeError('réponse sans JSON')
    return [str(e).strip() for e in (json.loads(x.group(0)).get('emojis') or [])]


def choisir(mots: list, categorie: str = '', modele: str = 'haiku') -> dict:
    """mots : sens en français (un par ligne du prompt). → {'ok': True, 'emojis': [...]}"""
    mots = [str(m).strip()[:80] for m in mots][:MAX_MOTS]
    if not mots or not all(mots):
        raise ValueError('liste de mots vide')
    liste = '\n'.join(f'{i}. {m}' for i, m in enumerate(mots, 1))
    retour, probleme = '', ''
    for _ in range(2):
        try:
            emojis = _demander(CONSIGNE.format(categorie=categorie or '?', liste=liste, n=len(mots), retour=retour), modele)
        except subprocess.TimeoutExpired:
            probleme = f'pas de réponse de Claude en {DELAI} s'
            continue
        if len(emojis) != len(mots):
            probleme = f'{len(emojis)} émojis pour {len(mots)} mots'
        elif not all(_est_emoji(e) for e in emojis):
            probleme = 'réponse qui contient autre chose que des émojis : ' + ' '.join(e for e in emojis if not _est_emoji(e))[:60]
        elif len(set(emojis)) != len(emojis):
            probleme = 'émojis en double : ' + ' '.join(sorted({e for e in emojis if emojis.count(e) > 1}))
        else:
            return {'ok': True, 'emojis': emojis}
        retour = f'\nAttention, ta réponse précédente ne convenait pas ({probleme}). Corrige.\n'
    raise RuntimeError(probleme)
