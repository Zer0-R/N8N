#!/usr/bin/env python3
"""Génère le workflow n8n « Muz Rappel - Stories » → ../workflows/06_muz_stories.json.

Chaque jour (heure de Paris) :
  09h  story « Reel » : extrait < 60 s (coupé entre deux phrases) du Reel publié à 07:00 (Muzrappel Video) ;
  13h  story « question » : extrait exact d'un hadith déjà publié en vidéo + question à 3 choix
       (quel Compagnon l'a rapporté ? / dans quel recueil ?) ;
  20h  story « réponse » : bonne réponse + référence complète + titre du hadith.
Publiée sur Instagram (compte muz.rappel) et sur la page Facebook Muz Rappel.

Aucune information inventée : extrait, rapporteur, recueil et référence sont lus tels quels dans
favima_bdd.muzrappel (description_full) ; les mauvaises réponses sont d'autres Compagnons / recueils réels,
absents du texte du hadith. Le quiz du jour est tiré avec la date comme graine : la réponse de 20h retrouve
la question de 13h sans rien mémoriser. Rendu des images : service média VocaBag (/render, modèles muz_*).

Test manuel : bouton « Execute workflow » → action = Config.test_action ; en CLI (n8n execute, mode « production »),
renseigner Config.forcer_action le temps du test. ⚠️ $execution.mode ne vaut jamais 'trigger'.
"""
import json
import re
import uuid
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE.parent / 'workflows' / '06_muz_stories.json'
WF_NAME = 'Muz Rappel - Stories'
ERREURS_WF = 'eUErVpA15sgk6j1m'      # « Muzrappel - Erreurs » : alerte Telegram @muzrappelbot en cas de plantage

CRED_DB = {'mySql': {'id': 'tif3ZW4DtUwXJyLA', 'name': 'MySQL account'}}                       # favima_bdd
CRED_MEDIA = {'httpHeaderAuth': {'id': 'L2zYP3cEvAgZVffN', 'name': 'VocaBag media (X-Media-Token)'}}
CRED_IG = {'instagramApi': {'id': '15ZtH32OCXt9f2v3', 'name': 'Instagram account 2'}}           # muz.rappel
CRED_FB = {'facebookGraphApi': {'id': 'SZI9tiIqTC821bCa', 'name': 'Facebook Graph account 2'}}  # page Muz Rappel

CONFIG_JS = r"""
// CONFIGURATION — modifier ici. Les secrets restent dans les credentials n8n.
return [{ json: {
  creneaux: { '09': 'reel', '13': 'question', '20': 'reponse' },   // heure de Paris ('HH') → story publiée
  // 'reel' : extrait < 60 s du Reel publié à 07:00 (service média /muz/reel-story, coupé entre deux phrases)
  test_action: 'question',                           // action du déclencheur « Test manuel »
  forcer_action: '',                                 // test CLI : 'question' | 'reponse' | 'reel' (ignore l'heure). Remettre ''.
  ig_video_attente_s: 15, ig_video_essais: 20,      // traitement de la vidéo par Instagram : 20 x 15 s max
  media_service: 'http://host.docker.internal:8791',
  ig_api: 'https://graph.facebook.com/v23.0',        // Instagram via connexion Facebook, jeton de page (2026-10-04)
  ig_user: '17841472522032723',                      // id Instagram professionnel @muz.rappel lié à la page
  ig_attente_s: 15,                                  // délai avant publication du conteneur Instagram
  fb_page: 'https://graph.facebook.com/v23.0/501465773057138',   // id Graph de la page Muz Rappel
} }];
"""

CRENEAU_JS = r"""
const cfg = $('Config').first().json;
const paris = $now.setZone('Europe/Paris');
// $execution.mode vaut 'test' (bouton « Execute workflow ») ou 'production' (planifié, CLI).
// Test : test_action ; forcer_action (tests CLI) passe avant tout — le remettre à '' ensuite.
const test = $execution.mode === 'test';
const action = cfg.forcer_action || (test ? cfg.test_action : cfg.creneaux[paris.toFormat('HH')]);
if (!action) return [];
return [{ json: { action, date: paris.toFormat('yyyy-MM-dd'), test } }];
"""

QUIZ_NODE_JS = r"""
__QUIZ__

const c = $('Créneau').first().json;
const rows = $input.all().map(i => i.json);
const quiz = construireQuiz(rows, c.date);
if (!quiz) throw new Error(`Aucun quiz possible pour le ${c.date} (${rows.length} hadiths lus)`);
return [{ json: { ...quiz, action: c.action,
                  rendu: { template: c.action === 'reponse' ? 'muz_answer' : 'muz_question', data: quiz } } }];
"""

_n = 0


def node(name, type_, version, params, pos, **extra):
    d = {'parameters': params, 'id': str(uuid.uuid5(uuid.NAMESPACE_URL, 'muz-stories-quiz/' + name)),
         'name': name, 'type': type_, 'typeVersion': version, 'position': pos}
    d.update(extra)
    return d


def http(name, pos, method, url, cred, query=None, json_body=None, headers=None, binary=False, file=False,
         timeout=None, **extra):
    p = {'method': method, 'url': url, 'options': {'response': {'response': {'neverError': True}}}}
    if file:
        p['options'] = {'response': {'response': {'responseFormat': 'file', 'outputPropertyName': 'data'}}}
    kind = next(iter(cred)) if cred else None
    if kind is None:
        pass
    elif kind == 'httpHeaderAuth':
        p.update({'authentication': 'genericCredentialType', 'genericAuthType': 'httpHeaderAuth', 'options': {}})
    else:
        p.update({'authentication': 'predefinedCredentialType', 'nodeCredentialType': kind})
    if query:
        p.update({'sendQuery': True, 'queryParameters': {'parameters': [{'name': a, 'value': b} for a, b in query.items()]}})
    if headers:
        p.update({'sendHeaders': True, 'headerParameters': {'parameters': [{'name': a, 'value': b} for a, b in headers.items()]}})
    if json_body:
        p.update({'sendBody': True, 'specifyBody': 'json', 'jsonBody': json_body})
    if binary:
        p.update({'sendBody': True, 'contentType': 'binaryData', 'inputDataFieldName': 'data'})
    if timeout:
        p['options']['timeout'] = timeout
    if cred:
        extra['credentials'] = cred
    return node(name, 'n8n-nodes-base.httpRequest', 4.2, p, pos, **extra)


def IF_TRUE(expr):
    return 'n8n-nodes-base.if', 2, {
        'conditions': {
            'options': {'caseSensitive': True, 'leftValue': '', 'typeValidation': 'loose', 'version': 1},
            'conditions': [{'id': str(uuid.uuid5(uuid.NAMESPACE_URL, 'muz-if/' + expr)), 'leftValue': '={{ ' + expr + ' }}',
                            'rightValue': '', 'operator': {'type': 'boolean', 'operation': 'true', 'singleValue': True}}],
            'combinator': 'and'},
        'options': {}}


def code(name, js, pos):
    return node(name, 'n8n-nodes-base.code', 2, {'jsCode': js.strip() + '\n'}, pos)


def build():
    quiz_js = (HERE / 'muz_quiz.js').read_text(encoding='utf-8')
    quiz_js = re.sub(r"\nif \(typeof module.*", '', quiz_js).strip()
    soft = {'onError': 'continueRegularOutput'}
    retry = {'retryOnFail': True, 'maxTries': 3, 'waitBetweenTries': 10000}
    nodes = [
        node('Chaque heure', 'n8n-nodes-base.scheduleTrigger', 1.2,
             {'rule': {'interval': [{'field': 'hours', 'hoursInterval': 1, 'triggerAtMinute': 0}]}}, [0, 0]),
        node('Test manuel', 'n8n-nodes-base.manualTrigger', 1, {}, [0, 200]),
        code('Config', CONFIG_JS, [220, 100]),
        code('Créneau', CRENEAU_JS, [440, 100]),
        node('Hadiths publiés', 'n8n-nodes-base.mySql', 2.4,
             {'operation': 'executeQuery',
              'query': 'SELECT id, title, category, description_full FROM muzrappel WHERE video_create = 1 ORDER BY id',
              'options': {}}, [660, 100], credentials=CRED_DB),
        code('Construire quiz', QUIZ_NODE_JS.replace('__QUIZ__', quiz_js), [880, 100]),
        http('Rendre image', [1100, 100], 'POST', "={{ $('Config').first().json.media_service }}/render", CRED_MEDIA,
             json_body='={{ JSON.stringify($json.rendu) }}', **retry),
        # Instagram (1re sortie : exécutée avant Facebook)
        http('IG · Créer conteneur', [1320, 0], 'POST', "={{ $('Config').first().json.ig_api }}/{{ $('Config').first().json.ig_user }}/media", CRED_IG,
             query={'media_type': 'STORIES', 'image_url': '={{ $json.url }}'}, **soft),
        node('IG · Attendre', 'n8n-nodes-base.wait', 1.1,
             {'amount': "={{ $('Config').first().json.ig_attente_s }}", 'unit': 'seconds'}, [1540, 0],
             webhookId=str(uuid.uuid5(uuid.NAMESPACE_URL, 'muz-stories-quiz/ig-wait'))),
        http('IG · Publier', [1760, 0], 'POST', "={{ $('Config').first().json.ig_api }}/{{ $('Config').first().json.ig_user }}/media_publish", CRED_IG,
             query={'creation_id': "={{ $('IG · Créer conteneur').first().json.id }}"}, **soft),
        # Facebook : photo non publiée → story
        http('FB · Photo non publiée', [1320, 220], 'POST', "={{ $('Config').first().json.fb_page }}/photos", CRED_FB,
             query={'url': "={{ $('Rendre image').first().json.url }}", 'published': 'false'}, **soft),
        http('FB · Publier story', [1540, 220], 'POST', "={{ $('Config').first().json.fb_page }}/photo_stories", CRED_FB,
             query={'photo_id': '={{ $json.id }}'}, **soft),
        # --- Story Reel (créneau 'reel')
        node('Reel ?', *IF_TRUE("$json.action === 'reel'"), [660, -260]),
        http('Extrait du Reel', [880, -360], 'POST', "={{ $('Config').first().json.media_service }}/muz/reel-story",
             CRED_MEDIA, json_body="={{ JSON.stringify({ date: $('Créneau').first().json.date }) }}",
             timeout=600000),
        node('Extrait trouvé ?', *IF_TRUE("!$json.absent && !!$json.url"), [1100, -360]),
        http('IG · Conteneur vidéo', [1320, -460], 'POST', "={{ $('Config').first().json.ig_api }}/{{ $('Config').first().json.ig_user }}/media", CRED_IG,
             query={'media_type': 'STORIES', 'video_url': "={{ $('Extrait du Reel').first().json.url }}"}, **soft),
        node('IG · Attendre vidéo', 'n8n-nodes-base.wait', 1.1,
             {'amount': "={{ $('Config').first().json.ig_video_attente_s }}", 'unit': 'seconds'}, [1540, -460],
             webhookId=str(uuid.uuid5(uuid.NAMESPACE_URL, 'muz-stories-quiz/ig-video-wait'))),
        http('IG · Statut vidéo', [1760, -460], 'GET',
             "={{ $('Config').first().json.ig_api }}/{{ $('IG · Conteneur vidéo').first().json.id }}", CRED_IG,
             query={'fields': 'status_code'}, **soft),
        node('IG · Vidéo prête ?', *IF_TRUE("$json.status_code === 'FINISHED'"), [1980, -460]),
        http('IG · Publier vidéo', [2200, -560], 'POST', "={{ $('Config').first().json.ig_api }}/{{ $('Config').first().json.ig_user }}/media_publish", CRED_IG,
             query={'creation_id': "={{ $('IG · Conteneur vidéo').first().json.id }}"}, **soft),
        node('IG · Encore en cours ?', *IF_TRUE(
             "$json.status_code === 'IN_PROGRESS' && $runIndex < $('Config').first().json.ig_video_essais"),
             [2200, -380]),
        # Facebook : envoi binaire (Facebook refuse de lire staging.vocabag.com, robots.txt derrière mot de passe)
        http('FB · Démarrer vidéo', [1320, -240], 'POST', "={{ $('Config').first().json.fb_page }}/video_stories",
             CRED_FB, query={'upload_phase': 'start'}, **soft),
        http('FB · Télécharger extrait', [1540, -240], 'GET', "={{ $('Extrait du Reel').first().json.url }}", None,
             file=True, **soft),
        code('FB · Taille vidéo', r"""
// Taille exacte du fichier : requise par rupload.facebook.com (en-tête file_size).
const buf = await this.helpers.getBinaryDataBuffer(0, 'data');
return [{ json: { file_size: buf.length }, binary: $input.first().binary }];
""", [1760, -240]),
        http('FB · Envoyer vidéo', [1980, -240], 'POST', "={{ $('FB · Démarrer vidéo').first().json.upload_url }}", CRED_FB,
             headers={'offset': '0', 'file_size': '={{ $json.file_size }}'}, binary=True, **soft),
        http('FB · Publier vidéo', [2200, -240], 'POST', "={{ $('Config').first().json.fb_page }}/video_stories", CRED_FB,
             query={'upload_phase': 'finish', 'video_id': "={{ $('FB · Démarrer vidéo').first().json.video_id }}"}, **soft),
        node('Note', 'n8n-nodes-base.stickyNote', 1,
             {'content': '## Stories Muz Rappel\n09h extrait du Reel du jour, 13h question, 20h réponse (Config.creneaux, heure de Paris).\n'
                         'Quiz tiré de la base (favima_bdd.muzrappel, video_create=1) avec la date comme graine : '
                         'rien d\'inventé, question et réponse identiques le même jour.\n'
                         'Généré par social/setup/build_muz_stories.py — modifier là, pas ici.',
              'height': 220, 'width': 520}, [0, 420]),
    ]
    chain = ['Config', 'Créneau', 'Reel ?']
    conn = {}

    def link(a, b, out=0):
        outs = conn.setdefault(a, {'main': []})['main']
        while len(outs) <= out:
            outs.append([])
        outs[out].append({'node': b, 'type': 'main', 'index': 0})

    link('Chaque heure', 'Config')
    link('Test manuel', 'Config')
    for a, b in zip(chain, chain[1:]):
        link(a, b)
    link('Reel ?', 'Extrait du Reel', 0)
    link('Reel ?', 'Hadiths publiés', 1)
    for a, b in [('Hadiths publiés', 'Construire quiz'), ('Construire quiz', 'Rendre image')]:
        link(a, b)
    link('Extrait du Reel', 'Extrait trouvé ?')
    link('Extrait trouvé ?', 'IG · Conteneur vidéo', 0)          # Instagram d'abord
    link('Extrait trouvé ?', 'FB · Démarrer vidéo', 0)
    link('IG · Conteneur vidéo', 'IG · Attendre vidéo')
    link('IG · Attendre vidéo', 'IG · Statut vidéo')
    link('IG · Statut vidéo', 'IG · Vidéo prête ?')
    link('IG · Vidéo prête ?', 'IG · Publier vidéo', 0)
    link('IG · Vidéo prête ?', 'IG · Encore en cours ?', 1)
    link('IG · Encore en cours ?', 'IG · Attendre vidéo', 0)
    for a, b in [('FB · Démarrer vidéo', 'FB · Télécharger extrait'), ('FB · Télécharger extrait', 'FB · Taille vidéo'),
                 ('FB · Taille vidéo', 'FB · Envoyer vidéo'), ('FB · Envoyer vidéo', 'FB · Publier vidéo')]:
        link(a, b)
    link('Rendre image', 'IG · Créer conteneur')
    link('Rendre image', 'FB · Photo non publiée')
    link('IG · Créer conteneur', 'IG · Attendre')
    link('IG · Attendre', 'IG · Publier')
    link('FB · Photo non publiée', 'FB · Publier story')
    return {'name': WF_NAME, 'nodes': nodes, 'connections': conn,
            'settings': {'executionOrder': 'v1', 'timezone': 'Europe/Paris', 'errorWorkflow': ERREURS_WF,
                         'callerPolicy': 'workflowsFromSameOwner'}}


if __name__ == '__main__':
    data = build()
    names = {n['name'] for n in data['nodes']}
    texte = json.dumps([n['parameters'] for n in data['nodes']], ensure_ascii=False)
    for ref in re.findall(r"\$\('([^']+)'\)", texte):
        assert ref in names, ('nœud inexistant', ref)
    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=2))
    print(f'{OUT.name}  {len(data["nodes"])} nœuds')
