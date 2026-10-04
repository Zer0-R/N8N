#!/usr/bin/env python3
"""À lancer APRÈS sql/001_muzrappel_posted_at.sql : remplit posted_*_at dans les workflows Muz (2026-10-04).

1. « Muzrappel Video » (y3L85t9otCm68hS5) : les 3 UPDATE posted_on_* = 1 ajoutent posted_*_at = NOW().
2. Rattrapage de « Muzrappel - Vérification » : SQL_JS de build_muz_verif.py idem → régénérer 08_muz_verif.json
   puis redéployer (PUT + deactivate/activate).
Usage : python3 apply_muz_posted_at.py <export_muzrappel_video.json> <sortie.json>   (étape 1, hors ligne)
L'étape 2 est faite en modifiant build_muz_verif.py (sed) — voir docs/muzrappel-n8n-publication.md.
"""
import json
import sys

REMPLACEMENTS = [
    ('SET posted_on_youtube = 1 WHERE', 'SET posted_on_youtube = 1, posted_youtube_at = NOW() WHERE'),
    ('SET posted_on_instagram = 1 WHERE', 'SET posted_on_instagram = 1, posted_instagram_at = NOW() WHERE'),
    ('SET posted_on_facebook = 1 WHERE', 'SET posted_on_facebook = 1, posted_facebook_at = NOW() WHERE'),
]

if __name__ == '__main__':
    src, out = sys.argv[1:3]
    w = json.load(open(src))
    n = 0
    for node in w['nodes']:
        q = node['parameters'].get('query')
        if isinstance(q, str):
            for a, b in REMPLACEMENTS:
                if a in q:
                    node['parameters']['query'] = q = q.replace(a, b)
                    n += 1
    assert n == 3, f'{n} requête(s) modifiée(s) au lieu de 3'
    json.dump(w, open(out, 'w'), ensure_ascii=False)
    print(out, 'ok,', n, 'requêtes')
