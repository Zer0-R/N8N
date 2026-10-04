#!/usr/bin/env python3
"""Branche « Vocabag Video » et « Muzrappel Video » sur les sous-workflows « Meta - Publier Reel » (2026-10-04).

Usage : patch_video_publication.py <export_api.json> <vocabag|muz> <sortie.json>
(export = GET /api/v1/workflows/{id}). Idempotent : un workflow déjà patché est renvoyé tel quel.

Remplace les nœuds « Publish » (nœud communautaire Instagram) et « Publish Facebook » par :
  Préparer publication (Code) ─┬─► Publier Reel (IG + FB)  [Execute Workflow → sous-workflow du compte]
                               │       ├─► Instagram publié ? ($json.instagram_id) → Marquer … Instagram
                               │       └─► Facebook publié ?  ($json.facebook_id)  → Marquer … Facebook
                               └─► Fiche publication → Fiche en fichier → Écrire fiche
La fiche du jour (_publications/AAAA-MM-JJ.json : légende, titres, chemin de la vidéo, dossier, id en base) sert
au rattrapage automatique des workflows « … - Vérification ».
"""
import json
import sys
import uuid

SOUS_WF = {'vocabag': 'WFKPD7GzMgbEuM5F', 'muz': '7YuYOdKwY7tZQceq'}

PREP_JS = {
    'vocabag': r"""
// Données de publication (Instagram + Facebook) — la légende vient de la branche Instagram, titre/description de YouTube.
const leg = $('Construire legende Instagram');
if (!leg.isExecuted) throw new Error('« Construire legende Instagram » pas encore exécuté : ordre des branches modifié ?');
const meta = $('Preparer metadata YouTube').first().json;
const folder = String($('Construire requete mots').first().json.folder);
return [{ json: {
  video_url: $('Poll video soundtrack').last().json.download_url,
  caption: leg.first().json.caption,
  fb_title: meta.title,
  fb_description: meta.description,
  share_to_feed: false,                       // Reels uniquement (2026-09-27)
  contexte: `Vocabag Video — ${folder}`,
  date: $now.setZone('Europe/Paris').toISODate(),
  folder,
  video_path: `/files/vocabag/${folder}_final_sound.mp4`,
} }];
""",
    'muz': r"""
// Données de publication (Instagram + Facebook) — mêmes textes qu'avant le passage au sous-workflow.
const sql = $('Execute had sql').first().json;
const phrase = String($('Code in JavaScript1').first().json.phrase || '');
return [{ json: {
  video_url: $('Poll video with overlay').last().json.download_url,
  caption: `${sql.title}\n\n${phrase}`,
  fb_title: sql.title,
  fb_description: `${sql.title}\n\n${phrase.replace('lien dans la bio', 'lien dans la section « À propos » de la page')}`,
  share_to_feed: true,
  contexte: `Muzrappel Video — ${sql.title}`,
  date: $now.setZone('Europe/Paris').toISODate(),
  folder: sql.folder,
  db_id: sql.id,
  video_path: `/files/muzrappel/${sql.folder}/render_with_soundtrack.mp4`,
} }];
""",
}
FICHE_JS = r"""
// Fiche du jour pour le rattrapage (sans l'URL RVM, qui expire au bout de 2 h)
const p = { ...$('Préparer publication').first().json };
delete p.video_url;
return [{ json: p }];
"""
SOURCE = {'vocabag': 'Preparer metadata YouTube', 'muz': 'Code in JavaScript1'}
DOSSIER = {'vocabag': '/files/vocabag/_publications', 'muz': '/files/muzrappel/_publications'}
MARQUER_IG = {'vocabag': 'Marquer Instagram (suivi)', 'muz': 'Marquer posted Instagram'}
MARQUER_FB = {'vocabag': 'Marquer Facebook (suivi)', 'muz': 'Marquer posted Facebook'}


def patch(w, cle):
    nodes = w['nodes']
    noms = {n['name'] for n in nodes}
    if 'Publier Reel (IG + FB)' in noms:
        return w
    pub = next(n for n in nodes if n['name'] == 'Publish')
    pubfb = next(n for n in nodes if n['name'] == 'Publish Facebook')
    x, y = pub['position']
    ns = f'video-publication-{cle}/'

    def node(name, type_, version, params, pos, **extra):
        d = {'parameters': params, 'id': str(uuid.uuid5(uuid.NAMESPACE_URL, ns + name)), 'name': name,
             'type': type_, 'typeVersion': version, 'position': pos}
        d.update(extra)
        return d

    w['nodes'] = [n for n in nodes if n['name'] not in ('Publish', 'Publish Facebook')]
    w['nodes'] += [
        node('Préparer publication', 'n8n-nodes-base.code', 2, {'jsCode': PREP_JS[cle].strip() + '\n'}, [x - 220, y]),
        node('Publier Reel (IG + FB)', 'n8n-nodes-base.executeWorkflow', 1.1,
             {'source': 'database', 'workflowId': {'__rl': True, 'value': SOUS_WF[cle], 'mode': 'id'},
              'mode': 'once', 'options': {'waitForSubWorkflow': True}}, [x, y], onError='continueRegularOutput'),
        node('Fiche publication', 'n8n-nodes-base.code', 2, {'jsCode': FICHE_JS.strip() + '\n'}, [x, y - 200],
             onError='continueRegularOutput'),
        node('Fiche en fichier', 'n8n-nodes-base.convertToFile', 1.1,
             {'operation': 'toJson', 'mode': 'each', 'binaryPropertyName': 'data_json', 'options': {}}, [x + 220, y - 200],
             onError='continueRegularOutput'),
        node('Écrire fiche', 'n8n-nodes-base.readWriteFile', 1.1,
             {'operation': 'write', 'fileName': f"={DOSSIER[cle]}/{{{{ $('Préparer publication').first().json.date }}}}.json",
              'dataPropertyName': 'data_json', 'options': {}}, [x + 440, y - 200], onError='continueRegularOutput'),
    ]
    c = w['connections']
    for src in list(c):
        for outs in c[src].get('main', []):
            if outs:
                outs[:] = [o for o in outs if o['node'] not in ('Publish', 'Publish Facebook')]
    c.pop('Publish', None)
    c.pop('Publish Facebook', None)
    c[SOURCE[cle]]['main'][0].append({'node': 'Préparer publication', 'type': 'main', 'index': 0})
    # fiche d'abord (au-dessus) puis publication
    c['Préparer publication'] = {'main': [[{'node': 'Fiche publication', 'type': 'main', 'index': 0},
                                           {'node': 'Publier Reel (IG + FB)', 'type': 'main', 'index': 0}]]}
    c['Fiche publication'] = {'main': [[{'node': 'Fiche en fichier', 'type': 'main', 'index': 0}]]}
    c['Fiche en fichier'] = {'main': [[{'node': 'Écrire fiche', 'type': 'main', 'index': 0}]]}
    c['Publier Reel (IG + FB)'] = {'main': [[{'node': 'Instagram publié ?', 'type': 'main', 'index': 0},
                                             {'node': 'Facebook publié ?', 'type': 'main', 'index': 0}]]}
    for n in w['nodes']:
        if n['name'] == 'Instagram publié ?':
            n['parameters']['conditions']['conditions'][0]['leftValue'] = '={{ $json.instagram_id }}'
        if n['name'] == 'Facebook publié ?':
            n['parameters']['conditions']['conditions'][0]['leftValue'] = '={{ $json.facebook_id }}'
        if n['name'] == MARQUER_IG[cle]:
            n['parameters']['query'] = n['parameters']['query'].replace('String($json.id)', 'String($json.instagram_id)')
        if n['name'] == MARQUER_FB[cle]:
            n['parameters']['query'] = n['parameters']['query'].replace('String($json.id)', 'String($json.facebook_id)')
    # contrôles
    texte = json.dumps(w['nodes'], ensure_ascii=False)
    assert '"Publish"' not in json.dumps(w['connections']), 'connexion vers Publish restante'
    assert 'String($json.id)' not in texte, 'Marquer encore sur $json.id'
    noms = {n['name'] for n in w['nodes']}
    for src, v in w['connections'].items():
        assert src in noms, src
        for outs in v.get('main', []):
            for o in outs or []:
                assert o['node'] in noms, o
    return w


if __name__ == '__main__':
    src, cle, out = sys.argv[1:4]
    w = patch(json.load(open(src)), cle)
    json.dump(w, open(out, 'w'), ensure_ascii=False, indent=1)
    print(out, len(w['nodes']), 'nœuds')
