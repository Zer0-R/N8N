#!/usr/bin/env python3
"""
Mise à jour des Data Tables du 2026-09-28 (idempotent, relançable sans risque) :
  1. vb_textes  : retire « Swipe 👉 » (et variantes) des textes existants ;
  2. vb_textes  : ajoute les descriptions en anglais (en) manquantes des 10 langues apprises ;
  3. vb_hashtags: ajoute les hashtags en anglais (en) manquants des 10 langues apprises.
Une ligne (langue_description, langue_apprise) déjà présente n'est ni dupliquée ni modifiée.

Clé API n8n : variable N8N_API_KEY, sinon fichier /root/.n8n_api_key (chmod 600).
Usage : python3 tables_20260928.py [--dry-run]
"""
import os
import re
import sys
from pathlib import Path

import setup_n8n as s

EN_TEXTES = {
    'darija': "Want to speak Darija like a local in Morocco? 🇲🇦 Here are a few everyday words, with transliteration so you can pronounce them right.",
    'anglais': "Level up your English vocabulary 🇬🇧 with useful everyday words, reviewed at the right time so they stick.",
    'allemand': "German looks intimidating? 🇩🇪 Start with a few everyday words, one at a time.",
    'espagnol': "Learning Spanish? 🇪🇸 Here are a few words you'll need to get by every day.",
    'portugais': "Want to speak Brazilian Portuguese? 🇧🇷 Here are a few everyday words to get you started.",
    'italien': "Italian is the language that sings 🇮🇹 Here are a few useful words to start speaking it.",
    'néerlandais': "Getting started with Dutch? 🇳🇱 Here are a few everyday words to begin with.",
    'russe': "Russian is written in Cyrillic 🇷🇺 Take it step by step with a few useful words.",
    'turc': "Want to learn Turkish? 🇹🇷 Here are a few everyday words to get you going.",
    'coréen': "Korean is written in Hangul 🇰🇷 Here are a few words for your first steps.",
}
EN_HASHTAGS = {
    'darija': "#vocabag #darija #moroccanarabic #learndarija #morocco #languagelearning",
    'anglais': "#vocabag #learnenglish #englishvocabulary #english #esl #languagelearning",
    'allemand': "#vocabag #learngerman #german #deutsch #germanvocabulary #languagelearning",
    'espagnol': "#vocabag #learnspanish #spanish #español #spanishvocabulary #languagelearning",
    'portugais': "#vocabag #learnportuguese #brazilianportuguese #portuguese #brasil #languagelearning",
    'italien': "#vocabag #learnitalian #italian #italiano #italianvocabulary #languagelearning",
    'néerlandais': "#vocabag #learndutch #dutch #nederlands #dutchvocabulary #languagelearning",
    'russe': "#vocabag #learnrussian #russian #русский #cyrillic #languagelearning",
    'turc': "#vocabag #learnturkish #turkish #türkçe #turkishvocabulary #languagelearning",
    'coréen': "#vocabag #learnkorean #korean #한국어 #hangul #languagelearning",
}

# Même règle que sansSwipe() du nœud « Tirer · description » (build_workflows.py).
_SWIPE = re.compile(r'[ \t]*\b(swipe|glisse|fais défiler)\b[^.!?\n]*[.!?]?[ \t]*(👉)?', re.I)


def sans_swipe(t: str) -> str:
    lignes = [l.rstrip() for l in _SWIPE.sub('', t).split('\n')]
    garde = [l for i, l in enumerate(lignes) if l or (i > 0 and lignes[i - 1])]
    return '\n'.join(garde).strip()


def lignes(tid):
    return s.call('GET', f'/data-tables/{tid}/rows?limit=250').get('data', [])


def main():
    dry = '--dry-run' in sys.argv
    key = os.environ.get('N8N_API_KEY') or (Path('/root/.n8n_api_key').read_text().strip()
                                            if Path('/root/.n8n_api_key').exists() else '')
    if not key:
        raise SystemExit('Clé API absente : N8N_API_KEY ou /root/.n8n_api_key')
    s.KEY = key
    tables = {t['name']: t['id'] for t in s.call('GET', '/data-tables?limit=250').get('data', [])}

    # 1. Swipe
    textes = lignes(tables['vb_textes'])
    for r in textes:
        net = sans_swipe(str(r.get('texte') or ''))
        if net and net != r.get('texte'):
            print(f"~ vb_textes #{r['id']} : {net[:70]}…")
            if not dry:
                s.call('PATCH', f"/data-tables/{tables['vb_textes']}/rows/update", {
                    'filter': {'type': 'and', 'filters': [{'columnName': 'id', 'condition': 'eq', 'value': r['id']}]},
                    'data': {'texte': net}})

    # 2-3. Lignes en
    for table, champ, contenu in (('vb_textes', 'texte', EN_TEXTES), ('vb_hashtags', 'hashtags', EN_HASHTAGS)):
        existe = {(str(r.get('langue_description', '')).strip(), str(r.get('langue_apprise', '')).strip())
                  for r in (textes if table == 'vb_textes' else lignes(tables[table]))}
        nouvelles = [{'langue_description': 'en', 'langue_apprise': a, champ: t, 'derniere_utilisation': ''}
                     for a, t in contenu.items() if ('en', a) not in existe]
        print(f"+ {table} : {len(nouvelles)} ligne(s) en à ajouter"
              + (f" ({', '.join(n['langue_apprise'] for n in nouvelles)})" if nouvelles else ''))
        if nouvelles and not dry:
            s.call('POST', f'/data-tables/{tables[table]}/rows', {'data': nouvelles, 'returnType': 'count'})
    print('(simulation, rien écrit)' if dry else 'OK')


if __name__ == '__main__':
    main()
