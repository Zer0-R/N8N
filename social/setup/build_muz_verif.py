#!/usr/bin/env python3
"""Génère le workflow n8n « Muzrappel - Vérification » → ../workflows/08_muz_verif.json.

Contrôle ce qui est RÉELLEMENT publié (les workflows Muz passent en « success » même quand un Publish échoue,
cf. tokens Meta invalidés le 2026-10-03) et alerte sur Telegram (@muzrappelbot, conversation privée)
uniquement s'il y a un problème. Heure de Paris :
  08h15  Reel du jour (Muzrappel Video, 07:00) présent sur YouTube, Instagram et la page Facebook ;
  21h45  idem + stories du jour (09h Reel, 13h question, 20h réponse) sur Instagram et Facebook.
À chaque passage : erreurs d'API (code 190 = token Meta invalide, 401 = token YouTube) et stock de scripts
(favima_bdd.muzrappel script_create=1, video_create=0).

Test : bouton « Execute workflow » → envoie toujours le bilan (même si tout va bien). Config.forcer_moment
('matin' | 'soir') impose le type de contrôle.
"""
import json
import re
import uuid
from pathlib import Path

import verif_rattrapage

HERE = Path(__file__).resolve().parent
OUT = HERE.parent / 'workflows' / '08_muz_verif.json'
WF_NAME = 'Muzrappel - Vérification'
ERREURS_WF = 'eUErVpA15sgk6j1m'      # « Muzrappel - Erreurs » → @muzrappelbot

CRED_DB = {'mySql': {'id': 'tif3ZW4DtUwXJyLA', 'name': 'MySQL account'}}                       # favima_bdd
CRED_FB = {'facebookGraphApi': {'id': 'SZI9tiIqTC821bCa', 'name': 'Facebook Graph account 2'}}  # page Muz Rappel (sert aussi pour IG)
CRED_YT = {'youTubeOAuth2Api': {'id': 'cwYHFUad2DZdTq0k', 'name': 'YouTube account'}}           # chaîne Muz Rappel
CRED_TG = {'telegramApi': {'id': 'TnA0UuhJFPlr5QZu', 'name': 'Telegram - muzrappelbot'}}

CONFIG_JS = r"""
// CONFIGURATION — modifier ici. Les secrets restent dans les credentials n8n.
return [{ json: {
  graph: 'https://graph.facebook.com/v23.0',
  ig_user: '17841472522032723',        // @muz.rappel (lié à la page)
  fb_page: '501465773057138',          // page Muz Rappel
  stories_attendues: 3,                // 09h Reel + 13h question + 20h réponse (contrôle du soir)
  seuil_stock: 7,                      // alerte si moins de N scripts prêts à rendre
  chat_id: '6980427615',               // conversation privée avec @muzrappelbot
  forcer_moment: '',                   // test : 'matin' | 'soir' (sinon d'après l'heure). Remettre ''.
} }];
"""

EVAL_JS = r"""
const e = s => String(s ?? '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
const cfg = $('Config').first().json;
const now = DateTime.now().setZone('Europe/Paris');
const today = now.toISODate();
const moment = cfg.forcer_moment || (now.hour < 14 ? 'matin' : 'soir');
const test = $execution.mode === 'test';
const pb = [], ok = [];
const rat = { instagram: -1, facebook: -1 };   // index dans pb du Reel manquant → rattrapage automatique
const parisDate = v => {
  if (v == null || v === '') return null;
  const d = /^\d+$/.test(String(v)) ? DateTime.fromSeconds(Number(v)) : DateTime.fromISO(String(v));
  return d.isValid ? d.setZone('Europe/Paris').toISODate() : null;
};
// Erreur d'API → message lisible (et null si la réponse est valide)
const apiErr = (j, quoi) => {
  const er = j && j.error;
  if (!er) return null;
  const code = er.code ?? er.status ?? '';
  const msg = er.message || JSON.stringify(er).slice(0, 200);
  if (String(code) === '190') return `🔑 ${quoi} : token Meta invalide (code 190) — régénérer le token de page Muz Rappel. <i>${e(msg)}</i>`;
  if (String(code) === '401' || /invalid_grant|unauthorized/i.test(msg)) return `🔑 ${quoi} : token YouTube invalide — reconnecter la credential « YouTube account ». <i>${e(msg)}</i>`;
  return `⚠️ ${quoi} : erreur API ${e(code)} — <i>${e(msg)}</i>`;
};
const get = n => { try { return $(n).first().json; } catch (x) { return { error: { message: 'nœud non exécuté' } }; } };

// --- Reel du jour : Instagram
const ig = get('IG · Publications');
let er = apiErr(ig, 'Instagram');
if (er) pb.push(er);
else {
  const r = (ig.data || []).find(m => m.media_product_type === 'REELS' && parisDate(m.timestamp) === today);
  r ? ok.push(`Instagram : Reel du jour (${e(r.permalink)})`) : (rat.instagram = pb.length, pb.push('❌ Instagram : aucun Reel publié aujourd\'hui sur @muz.rappel'));
}
// --- Reel du jour : Facebook (les vidéos de story n'ont pas de permalien /reel/)
const fb = get('FB · Vidéos');
er = apiErr(fb, 'Facebook');
if (er) pb.push(er);
else {
  const v = (fb.data || []).find(x => parisDate(x.created_time) === today && /\/reel\//.test(x.permalink_url || ''));
  v ? ok.push(`Facebook : Reel du jour (${e(v.title || v.id)})`) : (rat.facebook = pb.length, pb.push('❌ Facebook : aucun Reel publié aujourd\'hui sur la page Muz Rappel'));
}
// --- Reel du jour : YouTube
const ytc = get('YT · Chaîne');
const yt = get('YT · Dernières vidéos');
er = apiErr(ytc, 'YouTube') || apiErr(yt, 'YouTube');
if (er) pb.push(er);
else {
  const v = (yt.items || []).find(i => parisDate(i.contentDetails?.videoPublishedAt || i.snippet?.publishedAt) === today);
  v ? ok.push(`YouTube : ${e(v.snippet?.title)}`) : pb.push('❌ YouTube : aucune vidéo publiée aujourd\'hui sur la chaîne Muz Rappel');
}
// --- Stories du jour (contrôle du soir)
if (moment === 'soir') {
  const n = cfg.stories_attendues;
  const igs = get('IG · Stories');
  er = apiErr(igs, 'Instagram stories');
  if (er) pb.push(er);
  else {
    const c = (igs.data || []).filter(s => parisDate(s.timestamp) === today).length;
    c >= n ? ok.push(`Instagram : ${c} stories aujourd'hui`) : pb.push(`❌ Instagram : ${c}/${n} stories aujourd'hui (09h Reel, 13h question, 20h réponse)`);
  }
  const fbs = get('FB · Stories');
  er = apiErr(fbs, 'Facebook stories');
  if (er) pb.push(er);
  else {
    const c = (fbs.data || []).filter(s => parisDate(s.creation_time ?? s.created_time) === today).length;
    c >= n ? ok.push(`Facebook : ${c} stories aujourd'hui`) : pb.push(`❌ Facebook : ${c}/${n} stories aujourd'hui (09h Reel, 13h question, 20h réponse)`);
  }
}
// --- Stock de scripts
const db = get('BD · Stock');
if (db.restant == null) pb.push('⚠️ Base favima_bdd : lecture du stock impossible');
else if (Number(db.restant) < cfg.seuil_stock) pb.push(`⚠️ Stock : plus que ${db.restant} script(s) prêt(s) à rendre (script_create=1, video_create=0)`);
else ok.push(`Stock : ${db.restant} scripts prêts`);

const titre = pb.length ? `🚨 <b>Muzrappel — ${pb.length} problème(s)</b>` : '✅ <b>Muzrappel — tout est OK</b>';
const texte = `${titre} (${moment}, ${now.toFormat('dd/MM HH:mm')})\n\n` + [...pb, ...(pb.length && !test ? [] : ok.map(x => '✔️ ' + x))].join('\n');
return [{ json: { envoyer: pb.length > 0 || test, problemes: pb.length, texte: texte.slice(0, 4000), chat_id: cfg.chat_id,
  pb, ok, rat, test, label: 'Muzrappel', entete: `${moment}, ${now.toFormat('dd/MM HH:mm')}` } }];
"""


SQL_JS = r"""
// Suivi favima_bdd.muzrappel après rattrapage (id de la ligne lu dans la fiche du jour)
const f = $('R · Préparer').first().json.fiche || {};
const r = $input.first().json;
const id = parseInt(f.db_id, 10);
const sets = [];
if (r.instagram_id) sets.push('posted_on_instagram = 1');
if (r.facebook_id) sets.push('posted_on_facebook = 1');
return [{ json: { ...r, sql: sets.length && id > 0 ? `UPDATE muzrappel SET ${sets.join(', ')} WHERE id = ${id}` : '' } }];
"""


def node(name, type_, version, params, pos, **extra):
    d = {'parameters': params, 'id': str(uuid.uuid5(uuid.NAMESPACE_URL, 'muz-verif/' + name)),
         'name': name, 'type': type_, 'typeVersion': version, 'position': pos}
    d.update(extra)
    return d


def http(name, pos, url, cred, query):
    p = {'method': 'GET', 'url': url, 'authentication': 'predefinedCredentialType', 'nodeCredentialType': next(iter(cred)),
         'sendQuery': True, 'queryParameters': {'parameters': [{'name': a, 'value': b} for a, b in query.items()]},
         'options': {'response': {'response': {'neverError': True}}, 'timeout': 30000}}
    # neverError : une réponse 4xx (token invalide…) passe à « Évaluer » au lieu de planter
    return node(name, 'n8n-nodes-base.httpRequest', 4.2, p, pos, credentials=cred, onError='continueRegularOutput',
                alwaysOutputData=True)


def build():
    cfg = "$('Config').first().json"
    nodes = [
        node('Planifié', 'n8n-nodes-base.scheduleTrigger', 1.2,
             {'rule': {'interval': [{'triggerAtHour': 8, 'triggerAtMinute': 15},
                                    {'triggerAtHour': 21, 'triggerAtMinute': 45}]}}, [0, 0]),
        node('Test manuel', 'n8n-nodes-base.manualTrigger', 1, {}, [0, 200]),
        node('Config', 'n8n-nodes-base.code', 2, {'jsCode': CONFIG_JS.strip() + '\n'}, [220, 100]),
        http('IG · Publications', [440, 100], f"={{{{ {cfg}.graph }}}}/{{{{ {cfg}.ig_user }}}}/media", CRED_FB,
             {'fields': 'timestamp,media_product_type,permalink', 'limit': '10'}),
        http('IG · Stories', [660, 100], f"={{{{ {cfg}.graph }}}}/{{{{ {cfg}.ig_user }}}}/stories", CRED_FB,
             {'fields': 'timestamp,media_type'}),
        http('FB · Vidéos', [880, 100], f"={{{{ {cfg}.graph }}}}/{{{{ {cfg}.fb_page }}}}/videos", CRED_FB,
             {'fields': 'created_time,title,permalink_url', 'limit': '15'}),
        http('FB · Stories', [1100, 100], f"={{{{ {cfg}.graph }}}}/{{{{ {cfg}.fb_page }}}}/stories", CRED_FB, {'limit': '25'}),
        http('YT · Chaîne', [1320, 100], 'https://www.googleapis.com/youtube/v3/channels', CRED_YT,
             {'part': 'contentDetails', 'mine': 'true'}),
        http('YT · Dernières vidéos', [1540, 100], 'https://www.googleapis.com/youtube/v3/playlistItems', CRED_YT,
             {'part': 'snippet,contentDetails', 'maxResults': '5',
              'playlistId': "={{ $json.items?.[0]?.contentDetails?.relatedPlaylists?.uploads || 'introuvable' }}"}),
        node('BD · Stock', 'n8n-nodes-base.mySql', 2.4,
             {'operation': 'executeQuery',
              'query': 'SELECT COUNT(*) AS restant FROM muzrappel WHERE script_create = 1 AND video_create = 0',
              'options': {}}, [1760, 100], credentials=CRED_DB, onError='continueRegularOutput', alwaysOutputData=True),
        node('Évaluer', 'n8n-nodes-base.code', 2, {'jsCode': EVAL_JS.strip() + '\n'}, [1980, 100]),
        node('Envoyer ?', 'n8n-nodes-base.if', 2, {
            'conditions': {
                'options': {'caseSensitive': True, 'leftValue': '', 'typeValidation': 'loose', 'version': 1},
                'conditions': [{'id': str(uuid.uuid5(uuid.NAMESPACE_URL, 'muz-verif/envoyer')),
                                'leftValue': '={{ $json.envoyer }}', 'rightValue': '',
                                'operator': {'type': 'boolean', 'operation': 'true', 'singleValue': True}}],
                'combinator': 'and'},
            'options': {}}, [2200, 100]),
        node('Alerte Telegram', 'n8n-nodes-base.telegram', 1.2,
             {'chatId': '={{ $json.chat_id }}', 'text': '={{ $json.texte }}',
              'additionalFields': {'appendAttribution': False, 'parse_mode': 'HTML', 'disable_web_page_preview': True}},
             [2420, 0], credentials=CRED_TG),
    ]
    conn = {}

    def link(a, b, out=0):
        conn.setdefault(a, {'main': []})
        while len(conn[a]['main']) <= out:
            conn[a]['main'].append([])
        conn[a]['main'][out].append({'node': b, 'type': 'main', 'index': 0})

    link('Planifié', 'Config')
    link('Test manuel', 'Config')
    chain = ['Config', 'IG · Publications', 'IG · Stories', 'FB · Vidéos', 'FB · Stories', 'YT · Chaîne',
             'YT · Dernières vidéos', 'BD · Stock', 'Évaluer']
    for a, b in zip(chain, chain[1:]):
        link(a, b)
    link('Envoyer ?', 'Alerte Telegram', 0)
    link('Évaluer', 'Rattraper ?')
    verif_rattrapage.ajouter(nodes, link, 'muz-verif/', node, http, '7YuYOdKwY7tZQceq', '/files/muzrappel/_publications', CRED_DB, SQL_JS, 2200)
    for n in nodes:   # « Envoyer ? » / Telegram après la branche de rattrapage
        if n['name'] == 'Envoyer ?':
            n['position'] = [4840, 100]
        if n['name'] == 'Alerte Telegram':
            n['position'] = [5060, 0]
    return {'name': WF_NAME, 'nodes': nodes, 'connections': conn,
            'settings': {'executionOrder': 'v1', 'timezone': 'Europe/Paris', 'errorWorkflow': ERREURS_WF,
                         'callerPolicy': 'workflowsFromSameOwner'}}


if __name__ == '__main__':
    data = build()
    names = {n['name'] for n in data['nodes']}
    texte = json.dumps([n['parameters'] for n in data['nodes']], ensure_ascii=False)
    for ref in re.findall(r"\$\('([^']+)'\)", texte):
        assert ref in names, ('nœud inexistant', ref)
    for ref in re.findall(r"get\('([^']+)'\)", EVAL_JS):
        assert ref in names, ('nœud inexistant', ref)
    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=2))
    print(f'{OUT.name}  {len(data["nodes"])} nœuds')
