#!/usr/bin/env python3
"""Recherche en LECTURE SEULE dans le vocabulaire VocaBag — seul outil de données autorisé au rédacteur.

Usage : python3 mots.py <code_langue> <terme> [<terme> …]
  code_langue : ary ar en de es pt it nl ru tr zh ko
  terme       : mot natif, translittération ou traduction française (recherche exacte puis partielle)
Sortie : une ligne JSON par mot trouvé (10 max par terme) :
  {"terme", "mot", "translitteration", "traduction_fr", "exemple", "exemple_fr", "categorie"}

Base : celle de VOCABAG_ENV (défaut : .env de staging, même vocabulaire que la prod) ; requêtes SELECT uniquement.
Les termes sont passés en hexadécimal (aucune injection SQL possible).
"""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ENV = Path(os.environ.get('VOCABAG_ENV', '/var/www/vocabag-staging/.env'))
LANGUES = {'ary', 'ar', 'en', 'de', 'es', 'pt', 'it', 'nl', 'ru', 'tr', 'zh', 'ko'}


def env():
    out = {}
    for line in ENV.read_text().splitlines():
        if '=' in line and not line.lstrip().startswith('#'):
            k, v = line.split('=', 1)
            out[k.strip()] = v.strip().strip('"\'')
    return out


def hexa(s):
    return "(CONVERT(0x%s USING utf8mb4) COLLATE utf8mb4_unicode_ci)" % s.encode().hex()


def requete(code, terme):
    t, like = hexa(terme), hexa('%' + terme + '%')
    return f"""
SELECT JSON_OBJECT('terme', {t}, 'mot', v.word, 'translitteration', v.transliteration,
                   'traduction_fr', vt.translation, 'exemple', vt.example_sentence,
                   'exemple_fr', vt.example_translation, 'categorie', c.slug)
FROM vocabulary v
JOIN languages l ON l.id = v.language_id AND l.code = {hexa(code)}
JOIN vocabulary_translations vt ON vt.vocabulary_id = v.id AND vt.target_locale = 'fr'
JOIN categories c ON c.id = v.category_id
WHERE v.active = 1 AND c.slug <> 'religion'
  AND (v.word = {t} OR v.transliteration = {t} OR vt.translation = {t}
       OR v.word LIKE {like} OR v.transliteration LIKE {like} OR vt.translation LIKE {like})
ORDER BY (v.word = {t} OR v.transliteration = {t} OR vt.translation = {t}) DESC, CHAR_LENGTH(v.word)
LIMIT 10;"""


def main():
    if len(sys.argv) < 3 or sys.argv[1] not in LANGUES:
        raise SystemExit(__doc__)
    code, termes = sys.argv[1], [t for t in sys.argv[2:] if t.strip()][:20]
    e = env()
    with tempfile.NamedTemporaryFile('w', suffix='.cnf') as cnf:
        os.chmod(cnf.name, 0o600)
        cnf.write(f"[client]\nuser={e['DB_USER']}\npassword={e['DB_PASS']}\nhost={e.get('DB_HOST', 'localhost')}\n")
        cnf.flush()
        sql = ''.join(requete(code, t.strip()[:200]) for t in termes)
        r = subprocess.run(['mysql', f'--defaults-extra-file={cnf.name}', '-B', '-N', '--raw', e['DB_NAME'], '-e', sql],
                           capture_output=True, text=True, timeout=30)
    if r.returncode:
        raise SystemExit('erreur base : ' + r.stderr.strip()[:300])
    trouves = {json.loads(l)['terme'] for l in r.stdout.splitlines() if l.strip()}
    print(r.stdout.strip())
    for t in termes:
        if t.strip() not in trouves:
            print(json.dumps({'terme': t.strip(), 'introuvable': True}, ensure_ascii=False))


if __name__ == '__main__':
    main()
