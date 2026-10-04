#!/usr/bin/env python3
"""Génère le workflow n8n « Recyclage Reels en story » → ../workflows/15_recyclage.json.

Chaque samedi (Paris) — Muz Rappel 11h, VocaBag 17h (hors créneaux des stories quotidiennes) : choisit le Reel
Instagram publié il y a 14 à 120 jours avec le meilleur engagement (likes + 2 × commentaires ; vues dès que
instagram_manage_insights sera accordée n'est pas nécessaire ici), jamais recyclé (liste en staticData), en fait un
extrait < 60 s via le service média (POST /recycle : coupé entre deux phrases, bandeau « vidéo complète » pour Muz)
et le publie en story Instagram puis Facebook (même méthode que « Muz Rappel - Stories »). Résumé Telegram du compte.
Config.simulation = true : choisit et prépare l'extrait, ne publie rien.
"""
import json
import re
import uuid
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE.parent / 'workflows' / '15_recyclage.json'
WF_NAME = 'Recyclage Reels en story'
NS = 'recyclage/'
G = 'https://graph.facebook.com/v23.0'
MEDIA = 'http://host.docker.internal:8791'
CRED_MEDIA = {'httpHeaderAuth': {'id': 'L2zYP3cEvAgZVffN', 'name': 'VocaBag media (X-Media-Token)'}}

COMPTES = [
    {'cle': 'MZ', 'label': 'Muz Rappel', 'ig': '17841472522032723', 'page': '501465773057138', 'bandeau': 'muz',
     'heure': 11, 'fb': {'facebookGraphApi': {'id': 'SZI9tiIqTC821bCa', 'name': 'Facebook Graph account 2'}},
     'tg': {'telegramApi': {'id': 'TnA0UuhJFPlr5QZu', 'name': 'Telegram - muzrappelbot'}}},
    {'cle': 'VB', 'label': 'VocaBag', 'ig': '17841449858344452', 'page': '1361049150428275', 'bandeau': '',
     'heure': 17, 'fb': {'facebookGraphApi': {'id': 'RL5TaCOZpmZmBEc8', 'name': 'Facebook Graph account'}},
     'tg': {'telegramApi': {'id': 'TgVocabagBot0001', 'name': 'Telegram - vocabagbot'}}},
]

CONFIG_JS = r"""
return [{ json: {
  cle: '__A__', label: '__LABEL__', ig_user: '__IG__', fb_page: '__PAGE__', bandeau: '__BANDEAU__',
  jours_min: 14, jours_max: 120,     // âge du Reel recyclé
  ig_essais: 20,                     // statut du conteneur story : 20 x 20 s max
  chat_id: '6980427615',
  simulation: false,                 // true : choisit et prépare l'extrait, ne publie rien
} }];
"""

CHOISIR_JS = r"""
// Meilleur Reel de 14 à 120 jours jamais recyclé (likes + 2 × commentaires)
const cfg = $('__A__ · Config').first().json;
const memo = $getWorkflowStaticData('global');
const deja = new Set(memo['recycles_' + cfg.cle] || []);
const now = DateTime.now();
const l = ($input.first().json.data || []).filter(m => {
  const age = now.diff(DateTime.fromISO(m.timestamp), 'days').days;
  return m.media_product_type === 'REELS' && m.media_url && age >= cfg.jours_min && age <= cfg.jours_max && !deja.has(m.id);
}).map(m => ({ ...m, score: Number(m.like_count || 0) + 2 * Number(m.comments_count || 0) }))
  .sort((a, b) => b.score - a.score);
if (!l.length) return [];
const m = l[0];
return [{ json: { media_id: m.id, media_url: m.media_url, permalink: m.permalink, score: m.score,
                  likes: m.like_count, coms: m.comments_count, date: m.timestamp,
                  titre: String(m.caption || '').split('\n')[0].slice(0, 90) } }];
"""

BILAN_JS = r"""
const e = s => String(s ?? '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
const A = '__A__';
const cfg = $(`${A} · Config`).first().json;
const choix = $(`${A} · Choisir`).first().json;
const extrait = $(`${A} · Extrait`).first().json;
const lire = n => { try { return $(n).first().json; } catch (x) { return null; } };
const ig = lire(`${A} · IG publier`), fb = lire(`${A} · FB publier`), igst = lire(`${A} · IG statut`);
const okIG = !!ig?.id, okFB = !!(fb?.success || fb?.post_id);
if ((okIG || okFB) && !cfg.simulation) {
  const memo = $getWorkflowStaticData('global');
  memo['recycles_' + A] = [...(memo['recycles_' + A] || []), choix.media_id].slice(-200);
}
const etat = (ok, r, quoi) => cfg.simulation ? `${quoi} : simulation` :
  ok ? `✔️ ${quoi} publiée` : `❌ ${quoi} : ${e(JSON.stringify(r?.error || r || 'non publiée').slice(0, 150))}`;
const texte = [
  `♻️ <b>${e(cfg.label)} — Reel recyclé en story</b>${cfg.simulation ? ' (simulation)' : ''}`,
  `« ${e(choix.titre)} »`,
  `Publié le ${DateTime.fromISO(choix.date).setZone('Europe/Paris').toFormat('dd/MM/yyyy')} · ${choix.likes} likes · ${choix.coms} com.`,
  extrait.url ? `Extrait : ${extrait.duree} s (sur ${extrait.duree_source} s)` : `❌ Extrait impossible : ${e(JSON.stringify(extrait).slice(0, 150))}`,
  etat(okIG, ig || igst, 'Story Instagram'),
  etat(okFB, fb, 'Story Facebook'),
].join('\n');
return [{ json: { texte, chat_id: cfg.chat_id } }];
"""


def node(name, type_, version, params, pos, **extra):
    d = {'parameters': params, 'id': str(uuid.uuid5(uuid.NAMESPACE_URL, NS + name)), 'name': name,
         'type': type_, 'typeVersion': version, 'position': pos}
    d.update(extra)
    return d


def http(name, pos, method, url, cred=None, query=None, **kw):
    p = {'method': method, 'url': url, 'options': {'response': {'response': {'neverError': True}}, 'timeout': 120000}}
    if cred and 'httpHeaderAuth' in cred:
        p.update({'authentication': 'genericCredentialType', 'genericAuthType': 'httpHeaderAuth'})
    elif cred:
        p.update({'authentication': 'predefinedCredentialType', 'nodeCredentialType': next(iter(cred))})
    if query:
        p.update({'sendQuery': True, 'queryParameters': {'parameters': [{'name': a, 'value': b} for a, b in query.items()]}})
    p.update(kw.pop('params', {}))
    extra = {'onError': 'continueRegularOutput'}
    if cred:
        extra['credentials'] = cred
    extra.update(kw)
    return node(name, 'n8n-nodes-base.httpRequest', 4.2, p, pos, **extra)


def iff(name, expr, pos):
    return node(name, 'n8n-nodes-base.if', 2, {
        'conditions': {'options': {'caseSensitive': True, 'leftValue': '', 'typeValidation': 'loose', 'version': 1},
                       'conditions': [{'id': str(uuid.uuid5(uuid.NAMESPACE_URL, NS + 'if/' + name)),
                                       'leftValue': '={{ ' + expr + ' }}', 'rightValue': '',
                                       'operator': {'type': 'boolean', 'operation': 'true', 'singleValue': True}}],
                       'combinator': 'and'}, 'options': {}}, pos)


def build():
    nodes = [node('Test manuel', 'n8n-nodes-base.manualTrigger', 1, {}, [0, 300])]
    conn = {}

    def link(a, b, out=0):
        conn.setdefault(a, {'main': []})
        while len(conn[a]['main']) <= out:
            conn[a]['main'].append([])
        conn[a]['main'][out].append({'node': b, 'type': 'main', 'index': 0})

    for k, c in enumerate(COMPTES):
        A, y = c['cle'], k * 600
        cfg = f"$('{A} · Config').first().json"
        nodes += [
            node(f'{A} · Planifié', 'n8n-nodes-base.scheduleTrigger', 1.2,
                 {'rule': {'interval': [{'field': 'weeks', 'weeksInterval': 1, 'triggerAtDay': [6], 'triggerAtHour': c['heure']}]}},
                 [0, y]),
            node(f'{A} · Config', 'n8n-nodes-base.code', 2, {'jsCode': CONFIG_JS.replace('__A__', A).replace('__LABEL__', c['label'])
                 .replace('__IG__', c['ig']).replace('__PAGE__', c['page']).replace('__BANDEAU__', c['bandeau']).strip() + '\n'}, [220, y]),
            http(f'{A} · IG médias', [440, y], 'GET', f"{G}/{c['ig']}/media", c['fb'],
                 {'fields': 'id,timestamp,caption,like_count,comments_count,media_url,media_product_type,permalink', 'limit': '100'}),
            node(f'{A} · Choisir', 'n8n-nodes-base.code', 2, {'jsCode': CHOISIR_JS.replace('__A__', A).strip() + '\n'}, [660, y]),
            http(f'{A} · Extrait', [880, y], 'POST', f'{MEDIA}/recycle', CRED_MEDIA,
                 params={'sendBody': True, 'specifyBody': 'json',
                         'jsonBody': f"={{{{ JSON.stringify({{ url: $json.media_url, bandeau: {cfg}.bandeau }}) }}}}",
                         'options': {'response': {'response': {'neverError': True}}, 'timeout': 600000}}),
            iff(f'{A} · Publier ?', f"!!$json.url && !{cfg}.simulation", [1100, y]),
            # --- story Instagram
            http(f'{A} · IG conteneur', [1320, y - 100], 'POST', f"{G}/{c['ig']}/media", c['fb'],
                 {'media_type': 'STORIES', 'video_url': f"={{{{ $('{A} · Extrait').first().json.url }}}}"}),
            node(f'{A} · IG attente', 'n8n-nodes-base.wait', 1.1, {'amount': 20, 'unit': 'seconds'}, [1540, y - 100],
                 webhookId=str(uuid.uuid5(uuid.NAMESPACE_URL, NS + A + '/wait'))),
            http(f'{A} · IG statut', [1760, y - 100], 'GET', f"={G}/{{{{ $('{A} · IG conteneur').first().json.id }}}}", c['fb'],
                 {'fields': 'status_code,status'}),
            iff(f'{A} · IG prête ?', "$json.status_code === 'FINISHED'", [1980, y - 100]),
            iff(f'{A} · IG encore ?', f"$json.status_code === 'IN_PROGRESS' && $runIndex < {cfg}.ig_essais", [2200, y]),
            http(f'{A} · IG publier', [2200, y - 200], 'POST', f"{G}/{c['ig']}/media_publish", c['fb'],
                 {'creation_id': f"={{{{ $('{A} · IG conteneur').first().json.id }}}}"}),
            # --- story Facebook (upload en 3 temps, comme « Muz Rappel - Stories »)
            http(f'{A} · FB démarrer', [2420, y - 100], 'POST', f"{G}/{c['page']}/video_stories", c['fb'],
                 {'upload_phase': 'start'}, executeOnce=True),
            http(f'{A} · FB télécharger', [2640, y - 100], 'GET', f"={{{{ $('{A} · Extrait').first().json.url }}}}",
                 params={'options': {'response': {'response': {'responseFormat': 'file', 'outputPropertyName': 'data'}}, 'timeout': 300000}}),
            node(f'{A} · FB taille', 'n8n-nodes-base.code', 2, {'jsCode': (
                "// Taille exacte du fichier : requise par rupload.facebook.com (en-tête file_size).\n"
                "const buf = await this.helpers.getBinaryDataBuffer(0, 'data');\n"
                "return [{ json: { file_size: buf.length }, binary: $input.first().binary }];\n")}, [2860, y - 100]),
            http(f'{A} · FB envoyer', [3080, y - 100], 'POST', f"={{{{ $('{A} · FB démarrer').first().json.upload_url }}}}", c['fb'],
                 params={'sendHeaders': True, 'headerParameters': {'parameters': [{'name': 'offset', 'value': '0'},
                                                                                {'name': 'file_size', 'value': '={{ $json.file_size }}'}]},
                         'sendBody': True, 'contentType': 'binaryData', 'inputDataFieldName': 'data'}),
            http(f'{A} · FB publier', [3300, y - 100], 'POST', f"{G}/{c['page']}/video_stories", c['fb'],
                 {'upload_phase': 'finish', 'video_id': f"={{{{ $('{A} · FB démarrer').first().json.video_id }}}}"}),
            node(f'{A} · Bilan', 'n8n-nodes-base.code', 2, {'jsCode': BILAN_JS.replace('__A__', A).strip() + '\n'}, [3520, y]),
            node(f'{A} · Telegram', 'n8n-nodes-base.telegram', 1.2,
                 {'chatId': '={{ $json.chat_id }}', 'text': '={{ $json.texte }}',
                  'additionalFields': {'appendAttribution': False, 'parse_mode': 'HTML', 'disable_web_page_preview': True}},
                 [3740, y], credentials=c['tg'], onError='continueRegularOutput'),
        ]
        for a, b, o in [
            (f'{A} · Planifié', f'{A} · Config', 0), ('Test manuel', f'{A} · Config', 0),
            (f'{A} · Config', f'{A} · IG médias', 0), (f'{A} · IG médias', f'{A} · Choisir', 0),
            (f'{A} · Choisir', f'{A} · Extrait', 0), (f'{A} · Extrait', f'{A} · Publier ?', 0),
            (f'{A} · Publier ?', f'{A} · IG conteneur', 0), (f'{A} · Publier ?', f'{A} · Bilan', 1),
            (f'{A} · IG conteneur', f'{A} · IG attente', 0), (f'{A} · IG attente', f'{A} · IG statut', 0),
            (f'{A} · IG statut', f'{A} · IG prête ?', 0),
            (f'{A} · IG prête ?', f'{A} · IG publier', 0), (f'{A} · IG prête ?', f'{A} · IG encore ?', 1),
            (f'{A} · IG encore ?', f'{A} · IG attente', 0), (f'{A} · IG encore ?', f'{A} · FB démarrer', 1),
            (f'{A} · IG publier', f'{A} · FB démarrer', 0),
            (f'{A} · FB démarrer', f'{A} · FB télécharger', 0), (f'{A} · FB télécharger', f'{A} · FB taille', 0),
            (f'{A} · FB taille', f'{A} · FB envoyer', 0), (f'{A} · FB envoyer', f'{A} · FB publier', 0),
            (f'{A} · FB publier', f'{A} · Bilan', 0), (f'{A} · Bilan', f'{A} · Telegram', 0),
        ]:
            link(a, b, o)
    return {'name': WF_NAME, 'nodes': nodes, 'connections': conn,
            'settings': {'executionOrder': 'v1', 'timezone': 'Europe/Paris', 'errorWorkflow': 'VbErreursAlerte1',
                         'callerPolicy': 'workflowsFromSameOwner'}}


if __name__ == '__main__':
    data = build()
    names = {n['name'] for n in data['nodes']}
    texte = json.dumps([n['parameters'] for n in data['nodes']], ensure_ascii=False)
    for ref in re.findall(r"\$\('([^']+)'\)", texte):
        assert ref in names, ('nœud inexistant', ref)
    for a, v in data['connections'].items():
        assert a in names
        for outs in v['main']:
            for o in outs:
                assert o['node'] in names, o
    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=2))
    print(f'{OUT.name}  {len(data["nodes"])} nœuds')
