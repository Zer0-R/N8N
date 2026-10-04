#!/usr/bin/env python3
"""Génère le workflow n8n « VocaBag - Réponses commentaires » → ../workflows/13_vocabag_reponses.json.

Toutes les 3 h : pour les Reels VocaBag des 7 derniers jours (vocabag.vocabag_videos : instagram_media_id,
youtube_video_id), lit les commentaires Instagram (@vocabag) et YouTube (chaîne VocaBag) et répond à ceux qui ont
écrit la phrase (ou un mot) du Reel — phrases attendues lues dans channels/vocabag/videos/<folder>_words.json
(gardé 7 jours) :
  ≥ 85 % des mots de la phrase       → « Bravo 👏 C’est exactement ça ! (traduction) 🎉 »
  40-85 % (phrase de 3 mots ou plus) → « Presque 💪 La phrase exacte : « … » (translittération) »
  mot du Reel écrit seul             → « Bravo 👏 C’est bien ça : « mot » = traduction 🎉 »
  autre commentaire                  → pas de réponse.
Logique de comparaison : vocabag_correcteur.js (testable avec node). Une seule réponse par commentaire
(Instagram : pas déjà répondu par @vocabag ; YouTube : aucune réponse existante). Résumé Telegram (@vocabagbot)
quand des réponses partent. Config.simulation = true → calcule et résume sans rien publier.
"""
import json
import re
import uuid
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE.parent / 'workflows' / '13_vocabag_reponses.json'
WF_NAME = 'VocaBag - Réponses commentaires'
NS = 'vocabag-reponses/'
ERREURS_WF = 'VbErreursAlerte1'

CRED_DB = {'mySql': {'id': 'qZ2NnMkubbTE5fNX', 'name': 'Vocabag DB'}}
CRED_FB = {'facebookGraphApi': {'id': 'RL5TaCOZpmZmBEc8', 'name': 'Facebook Graph account'}}   # page VocaBag → @vocabag
CRED_YT = {'youTubeOAuth2Api': {'id': '1KMbY9e6VCrfiKfu', 'name': 'YouTube account 3'}}
CRED_TG = {'telegramApi': {'id': 'TgVocabagBot0001', 'name': 'Telegram - vocabagbot'}}

CONFIG_JS = r"""
return [{ json: {
  graph: 'https://graph.facebook.com/v23.0',
  compte_ig: 'vocabag',          // nom d'utilisateur Instagram : ses commentaires / réponses sont ignorés
  jours: 7,                      // Reels pris en compte (les <folder>_words.json sont purgés à 7 jours)
  chat_id: '6980427615',
  simulation: false,             // true : calcule et résume sur Telegram, ne publie rien
} }];
"""

CORRECTEUR = re.sub(r"\nif \(typeof module.*", '', (HERE / 'vocabag_correcteur.js').read_text(encoding='utf-8')).strip()

CIBLES_JS = r"""
// Reels récents → phrases attendues (words.json) ; une sortie par Reel publié sur la plateforme __PLAT__
const phrases = {};
for (const it of $('Phrases').all()) {
  let d = it.json.data ?? it.json;
  if (Array.isArray(d)) d = d[0];
  if (d && d.folder && Array.isArray(d.reveals)) phrases[d.folder] = d.reveals;
}
const champ = '__CHAMP__';
return $('BD · Reels récents').all()
  .map(r => r.json)
  .filter(r => r[champ] && phrases[r.folder])
  .map(r => ({ json: { id: String(r[champ]), folder: r.folder, reveals: phrases[r.folder] } }));
"""

REPONSES_IG_JS = CORRECTEUR + r"""

// Commentaires Instagram (une réponse HTTP par Reel, même ordre que « Cibles IG »)
const cfg = $('Config').first().json;
const cibles = $('Cibles IG').all();
const sortie = [];
$input.all().forEach((it, i) => {
  const cible = cibles[i]?.json;
  if (!cible) return;
  const cands = candidats(cible.reveals);
  for (const c of (it.json.data || [])) {
    if (c.username === cfg.compte_ig) continue;
    if ((c.replies?.data || []).some(r => r.username === cfg.compte_ig)) continue;
    const ev = evaluer(c.text, cands);
    if (ev) sortie.push({ json: { plateforme: 'Instagram', comment_id: c.id, auteur: c.username, texte: c.text,
                                  type: ev.type, replyText: reponse(ev), folder: cible.folder } });
  }
});
return sortie;
"""

REPONSES_YT_JS = CORRECTEUR + r"""

// Fils de commentaires YouTube (une réponse HTTP par vidéo, même ordre que « Cibles YT »)
const cibles = $('Cibles YT').all();
const sortie = [];
$input.all().forEach((it, i) => {
  const cible = cibles[i]?.json;
  if (!cible) return;
  const cands = candidats(cible.reveals);
  for (const t of (it.json.items || [])) {
    const s = t.snippet || {};
    const top = s.topLevelComment?.snippet || {};
    if (s.totalReplyCount > 0) continue;                               // déjà une réponse
    if (top.authorChannelId?.value && top.authorChannelId.value === s.channelId) continue;   // notre chaîne
    const ev = evaluer(top.textOriginal || top.textDisplay, cands);
    if (ev) sortie.push({ json: { plateforme: 'YouTube', comment_id: s.topLevelComment.id, auteur: top.authorDisplayName,
                                  texte: top.textOriginal || top.textDisplay, type: ev.type, replyText: reponse(ev),
                                  folder: cible.folder } });
  }
});
return sortie;
"""

RESUME_JS = r"""
// Résumé Telegram des réponses de la plateforme (publiées ou simulées)
const e = s => String(s ?? '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
const cfg = $('Config').first().json;
const faites = $('__SRC__').all().map(x => x.json);
const res = cfg.simulation ? [] : $input.all().map(x => x.json);
const lignes = faites.map((r, i) => {
  const err = res[i] && (res[i].error || (!res[i].id && !cfg.simulation)) ? ' ❌ ' + e(JSON.stringify(res[i].error || res[i]).slice(0, 120)) : '';
  return `• <b>${e(r.auteur)}</b> : « ${e(String(r.texte).slice(0, 80))} »\n   → ${e(r.replyText)}${err}`;
});
const titre = `💬 <b>VocaBag — ${faites.length} réponse(s) ${faites[0].plateforme}</b>${cfg.simulation ? ' (simulation, rien publié)' : ''}`;
return [{ json: { texte: (titre + '\n\n' + lignes.join('\n')).slice(0, 4000), chat_id: cfg.chat_id } }];
"""


def node(name, type_, version, params, pos, **extra):
    d = {'parameters': params, 'id': str(uuid.uuid5(uuid.NAMESPACE_URL, NS + name)), 'name': name,
         'type': type_, 'typeVersion': version, 'position': pos}
    d.update(extra)
    return d


def code(name, js, pos):
    return node(name, 'n8n-nodes-base.code', 2, {'jsCode': js.strip() + '\n'}, pos)


def http(name, pos, method, url, cred, query=None, body=None):
    p = {'method': method, 'url': url, 'authentication': 'predefinedCredentialType', 'nodeCredentialType': next(iter(cred)),
         'options': {'response': {'response': {'neverError': True}}, 'timeout': 60000}}
    if query:
        p.update({'sendQuery': True, 'queryParameters': {'parameters': [{'name': a, 'value': b} for a, b in query.items()]}})
    if body:
        p.update({'sendBody': True, 'bodyParameters': {'parameters': [{'name': a, 'value': b} for a, b in body.items()]}})
    return node(name, 'n8n-nodes-base.httpRequest', 4.2, p, pos, credentials=cred, onError='continueRegularOutput',
                alwaysOutputData=False)


def iff(name, expr, pos):
    return node(name, 'n8n-nodes-base.if', 2, {
        'conditions': {'options': {'caseSensitive': True, 'leftValue': '', 'typeValidation': 'loose', 'version': 1},
                       'conditions': [{'id': str(uuid.uuid5(uuid.NAMESPACE_URL, NS + 'if/' + name)),
                                       'leftValue': '={{ ' + expr + ' }}', 'rightValue': '',
                                       'operator': {'type': 'boolean', 'operation': 'true', 'singleValue': True}}],
                       'combinator': 'and'}, 'options': {}}, pos)


def telegram(name, pos):
    return node(name, 'n8n-nodes-base.telegram', 1.2,
                {'chatId': '={{ $json.chat_id }}', 'text': '={{ $json.texte }}',
                 'additionalFields': {'appendAttribution': False, 'parse_mode': 'HTML', 'disable_web_page_preview': True}},
                pos, credentials=CRED_TG, onError='continueRegularOutput')


def build():
    cfg = "$('Config').first().json"
    nodes = [
        node('Planifié', 'n8n-nodes-base.scheduleTrigger', 1.2,
             {'rule': {'interval': [{'field': 'hours', 'hoursInterval': 3, 'triggerAtMinute': 20}]}}, [0, 0]),
        node('Test manuel', 'n8n-nodes-base.manualTrigger', 1, {}, [0, 200]),
        code('Config', CONFIG_JS, [220, 100]),
        node('BD · Reels récents', 'n8n-nodes-base.mySql', 2.4,
             {'operation': 'executeQuery',
              'query': "=SELECT folder, instagram_media_id, youtube_video_id FROM vocabag_videos "
                       "WHERE folder >= '{{ $now.setZone('Europe/Paris').minus({ days: $('Config').first().json.jours }).toFormat('yyyyMMdd') }}' "
                       "ORDER BY folder DESC",
              'options': {}}, [440, 100], credentials=CRED_DB),
        node('Lire phrases', 'n8n-nodes-base.readWriteFile', 1.1,
             {'fileSelector': '=/files/vocabag/{{ $json.folder }}_words.json', 'options': {'dataPropertyName': 'data'}},
             [660, 100], onError='continueRegularOutput'),
        node('Phrases', 'n8n-nodes-base.extractFromFile', 1.1, {'operation': 'fromJson', 'options': {}}, [880, 100],
             onError='continueRegularOutput'),
        # --- Instagram
        code('Cibles IG', CIBLES_JS.replace('__PLAT__', 'Instagram').replace('__CHAMP__', 'instagram_media_id'), [1100, 0]),
        http('IG · Commentaires', [1320, 0], 'GET', f"={{{{ {cfg}.graph }}}}/{{{{ $json.id }}}}/comments", CRED_FB,
             {'fields': 'id,text,username,timestamp,replies{username}', 'limit': '50'}),
        code('Réponses IG', REPONSES_IG_JS, [1540, 0]),
        iff('Publier IG ?', f'!{cfg}.simulation', [1760, 0]),
        http('IG · Répondre', [1980, -100], 'POST', f"={{{{ {cfg}.graph }}}}/{{{{ $json.comment_id }}}}/replies", CRED_FB,
             {'message': '={{ $json.replyText }}'}),
        code('Résumé IG', RESUME_JS.replace('__SRC__', 'Réponses IG'), [2200, 0]),
        telegram('Telegram IG', [2420, 0]),
        # --- YouTube
        code('Cibles YT', CIBLES_JS.replace('__PLAT__', 'YouTube').replace('__CHAMP__', 'youtube_video_id'), [1100, 300]),
        http('YT · Commentaires', [1320, 300], 'GET', 'https://www.googleapis.com/youtube/v3/commentThreads', CRED_YT,
             {'part': 'snippet', 'videoId': '={{ $json.id }}', 'maxResults': '50', 'textFormat': 'plainText'}),
        code('Réponses YT', REPONSES_YT_JS, [1540, 300]),
        iff('Publier YT ?', f'!{cfg}.simulation', [1760, 300]),
        http('YT · Répondre', [1980, 200], 'POST', 'https://www.googleapis.com/youtube/v3/comments', CRED_YT,
             {'part': 'snippet'}, {'snippet.parentId': '={{ $json.comment_id }}', 'snippet.textOriginal': '={{ $json.replyText }}'}),
        code('Résumé YT', RESUME_JS.replace('__SRC__', 'Réponses YT'), [2200, 300]),
        telegram('Telegram YT', [2420, 300]),
    ]
    conn = {}

    def link(a, b, out=0):
        conn.setdefault(a, {'main': []})
        while len(conn[a]['main']) <= out:
            conn[a]['main'].append([])
        conn[a]['main'][out].append({'node': b, 'type': 'main', 'index': 0})

    for a, b, o in [
        ('Planifié', 'Config', 0), ('Test manuel', 'Config', 0), ('Config', 'BD · Reels récents', 0),
        ('BD · Reels récents', 'Lire phrases', 0), ('Lire phrases', 'Phrases', 0),
        ('Phrases', 'Cibles IG', 0), ('Phrases', 'Cibles YT', 0),
        ('Cibles IG', 'IG · Commentaires', 0), ('IG · Commentaires', 'Réponses IG', 0), ('Réponses IG', 'Publier IG ?', 0),
        ('Publier IG ?', 'IG · Répondre', 0), ('Publier IG ?', 'Résumé IG', 1), ('IG · Répondre', 'Résumé IG', 0),
        ('Résumé IG', 'Telegram IG', 0),
        ('Cibles YT', 'YT · Commentaires', 0), ('YT · Commentaires', 'Réponses YT', 0), ('Réponses YT', 'Publier YT ?', 0),
        ('Publier YT ?', 'YT · Répondre', 0), ('Publier YT ?', 'Résumé YT', 1), ('YT · Répondre', 'Résumé YT', 0),
        ('Résumé YT', 'Telegram YT', 0),
    ]:
        link(a, b, o)
    return {'name': WF_NAME, 'nodes': nodes, 'connections': conn,
            'settings': {'executionOrder': 'v1', 'timezone': 'Europe/Paris', 'errorWorkflow': ERREURS_WF,
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
