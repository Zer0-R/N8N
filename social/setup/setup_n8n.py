#!/usr/bin/env python3
"""Prépare n8n pour « VocaBag Social » via l'API publique n8n (idempotent).

  1. crée les Data Tables manquantes (vb_textes, vb_ctas, vb_hashtags, vb_journal, vb_tampon_album, vb_story_mots)
  2. insère les lignes d'exemple dans les 3 tables de descriptions si elles sont vides
  3. crée le credential « VocaBag media (X-Media-Token) » (jeton lu dans /etc/vocabag-media.env),
     et « Gmail - contact.vocabag (SMTP) » (brouillons de blog ; identifiants lus dans le .env VocaBag)
  4. supprime les anciens workflows remplacés par la fusion (ANCIENS dans build_workflows.py)
  5. écrit ../workflows/import/*.json avec les vrais ids de credentials (prêts pour `n8n import:workflow`)

Usage : N8N_API_KEY=… python3 setup_n8n.py
"""
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

API = os.environ.get('N8N_API', 'http://localhost:5678/api/v1')
KEY = os.environ.get('N8N_API_KEY', '')
ROOT = Path(__file__).resolve().parent.parent

S, N = 'string', 'number'
TABLES = {
    'vb_textes':       [('langue_description', S), ('langue_apprise', S), ('texte', S), ('derniere_utilisation', S), ('format', S)],
    'vb_ctas':         [('langue_description', S), ('texte', S), ('derniere_utilisation', S)],
    'vb_hashtags':     [('langue_description', S), ('langue_apprise', S), ('hashtags', S), ('derniere_utilisation', S)],
    'vb_journal':      [(c, S) for c in ('plateforme', 'type', 'statut', 'post_id', 'permalink', 'langue_description',
                                          'langue_apprise', 'texte_id', 'cta_id', 'hashtags_id', 'source', 'source_ref',
                                          'erreur', 'date_publication')],
    'vb_tampon_album': [('media_group_id', S), ('message_id', N), ('file_id', S), ('kind', S), ('caption', S), ('recu_le', S)],
    'vb_story_mots':   [('vocabulary_id', N), ('mot', S), ('langue_apprise', S), ('traduction', S),
                        ('translitteration', S), ('derniere_utilisation', S), ('statut', S), ('jour', S)],
}

# Lignes d'exemple : 3 en français + 3 en anglais par table. langue_apprise vide = ligne générique (repli).
# Aucun témoignage ni fonctionnalité inventés : répétition espacée, quiz, 12 langues, offre gratuite = réels.
SEED = {
    'vb_textes': [
        ('fr', '', "Apprendre une langue, ce n'est pas tout retenir d'un coup : c'est revoir le bon mot au bon moment 🧠"),
        ('fr', 'darija', "Tu veux parler darija comme au Maroc ? 🇲🇦 Voici quelques mots du quotidien, avec leur translittération pour bien les prononcer."),
        ('fr', 'chinois', "Le chinois te paraît impossible ? Commence par quelques caractères utiles 🇨🇳 Chaque mot est accompagné de sa prononciation."),
        ('en', '', "Learning a language isn't about memorizing everything at once — it's about reviewing the right word at the right time 🧠"),
        ('en', 'arabe', "Starting Arabic? 🇸🇦 Here are a few essential words, with transliteration so you can say them right away."),
        ('en', 'chinois', "Chinese looks hard? Start with a few useful characters 🇨🇳 Each one comes with its pronunciation."),
    ],
    'vb_ctas': [
        ('fr', "📲 Apprends ces mots avec la répétition espacée sur VocaBag — lien en bio."),
        ('fr', "🎯 Quiz, révisions intelligentes et 12 langues : essaie VocaBag gratuitement (lien en bio)."),
        ('fr', "💾 Enregistre ce post pour le réviser, puis continue sur VocaBag — lien en bio."),
        ('en', "📲 Learn these words with spaced repetition on VocaBag — link in bio."),
        ('en', "🎯 Quizzes, smart reviews and 12 languages: try VocaBag for free (link in bio)."),
        ('en', "💾 Save this post to review it later, then keep going on VocaBag — link in bio."),
    ],
    'vb_hashtags': [
        ('fr', '', "#vocabag #apprendreunelangue #vocabulaire #langues #polyglotte #apprendre"),
        ('fr', 'darija', "#vocabag #darija #darijamarocaine #maroc #apprendreledarija #vocabulaire"),
        ('fr', 'chinois', "#vocabag #chinois #apprendrelechinois #mandarin #hanzi #vocabulaire"),
        ('en', '', "#vocabag #languagelearning #vocabulary #polyglot #learnalanguage #studygram"),
        ('en', 'arabe', "#vocabag #learnarabic #arabic #arabiclanguage #arabicvocabulary #languagelearning"),
        ('en', 'chinois', "#vocabag #learnchinese #mandarin #chinesecharacters #hanzi #languagelearning"),
    ],
}


def call(method, path, body=None):
    req = urllib.request.Request(API + path, method=method, headers={
        'X-N8N-API-KEY': KEY, 'Content-Type': 'application/json', 'Accept': 'application/json'},
        data=json.dumps(body).encode() if body is not None else None)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            txt = r.read().decode()
            return json.loads(txt) if txt else {}
    except urllib.error.HTTPError as e:
        raise SystemExit(f'{method} {path} → HTTP {e.code} : {e.read().decode()[:500]}')


def seed_rows(table):
    rows = SEED[table]
    if table == 'vb_ctas':
        return [{'langue_description': l, 'texte': t, 'derniere_utilisation': ''} for l, t in rows]
    champ = 'texte' if table == 'vb_textes' else 'hashtags'
    return [{'langue_description': l, 'langue_apprise': a, champ: t, 'derniere_utilisation': ''} for l, a, t in rows]


def main():
    if not KEY:
        raise SystemExit('N8N_API_KEY manquant (Settings → n8n API dans l’interface n8n)')

    existing = {t['name']: t for t in call('GET', '/data-tables?limit=250').get('data', [])}
    for name, cols in TABLES.items():
        if name in existing:
            print(f'= table {name} existe déjà')
            continue
        t = call('POST', '/data-tables', {'name': name, 'columns': [{'name': c, 'type': ty} for c, ty in cols]})
        existing[name] = t
        print(f'+ table {name} créée ({t.get("id")})')
    for name in SEED:
        tid = existing[name]['id']
        rows = call('GET', f'/data-tables/{tid}/rows?limit=1').get('data', [])
        if rows:
            print(f'= {name} contient déjà des lignes, pas d’exemples ajoutés')
            continue
        call('POST', f'/data-tables/{tid}/rows', {'data': seed_rows(name), 'returnType': 'count'})
        print(f'+ {name} : {len(SEED[name])} lignes d’exemple')

    creds = {}
    deja = {c['name']: c for c in call('GET', '/credentials?limit=250').get('data', [])}

    def credential(placeholder, name, header, value, type_='httpHeaderAuth', data=None):
        if name in deja:
            c = deja[name]
            print(f'= credential « {name} » existe déjà ({c["id"]})')
        elif value:
            c = call('POST', '/credentials', {'name': name, 'type': type_,
                                               'data': data or {'name': header, 'value': value}})
            print(f'+ credential « {name} » ({c["id"]})')
        else:
            print(f'! credential « {name} » à créer à la main (voir doc)')
            return
        creds[placeholder] = (c['id'], c['name'])

    env = dict(l.split('=', 1) for l in Path('/etc/vocabag-media.env').read_text().split() if '=' in l)
    credential('VbMediaToken0001', 'VocaBag media (X-Media-Token)', 'X-Media-Token', env['MEDIA_TOKEN'])
    vb = {}
    for l in Path(os.environ.get('VOCABAG_ENV', '/var/www/vocabag-staging/.env')).read_text().splitlines():
        if '=' in l and not l.lstrip().startswith('#'):
            k, v = l.split('=', 1)
            vb[k.strip()] = v.strip().strip('"\'')
    credential('VbSmtpGmail00001', 'Gmail - contact.vocabag (SMTP)', '', vb.get('GMAIL_SMTP_PASS'), 'smtp',
               {'user': vb.get('GMAIL_FROM', ''), 'password': vb.get('GMAIL_SMTP_PASS', ''), 'host': 'smtp.gmail.com',
                'port': 465, 'secure': True, 'hostName': ''})   # disableStartTls interdit quand secure=true

    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from build_workflows import ANCIENS
    for wid in ANCIENS:
        try:
            call('POST', f'/workflows/{wid}/deactivate')
        except SystemExit:
            pass                                  # déjà inactif ou absent
        try:
            call('DELETE', f'/workflows/{wid}')
            print(f'- workflow {wid} supprimé')
        except SystemExit as e:
            if '404' in str(e):
                print(f'= workflow {wid} déjà absent')
            else:
                raise

    out = ROOT / 'workflows' / 'import'
    out.mkdir(exist_ok=True)
    for old in out.glob('*.json'):
        old.unlink()
    for f in sorted((ROOT / 'workflows').glob('*.json')):
        wf = json.loads(f.read_text())
        for n in wf['nodes']:
            for typ, ref in (n.get('credentials') or {}).items():
                if ref['id'] in creds:
                    ref['id'], ref['name'] = creds[ref['id']]
        (out / f.name).write_text(json.dumps(wf, ensure_ascii=False, indent=2))
    print(f'→ workflows prêts pour l’import : {out}')


if __name__ == '__main__':
    sys.exit(main())
