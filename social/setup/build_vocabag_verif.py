#!/usr/bin/env python3
"""Génère le workflow n8n « VocaBag - Vérification » → ../workflows/09_vocabag_verif.json.

Même principe que « Muzrappel - Vérification » (build_muz_verif.py) : contrôle ce qui est RÉELLEMENT publié et alerte
sur Telegram (@vocabagbot) uniquement s'il y a un problème. Heure de Paris :
  15h50  Reel du jour (Vocabag Video, lancé à 15:00) : ligne du jour dans vocabag.vocabag_videos + présence sur YouTube,
         Instagram (@vocabag) et la page Facebook VocaBag ;
  21h50  idem + stories du jour (16h Reel, 18h question, 21h réponse + visuel final) sur Instagram et Facebook.
À chaque passage : erreurs d'API (code 190 = token Meta invalide, 401 = token YouTube) et suivi incohérent
(publié sur une plateforme mais posted_on_* = 0 dans vocabag_videos).

Test : bouton « Execute workflow » → envoie toujours le bilan. Config.forcer_moment ('apres_reel' | 'soir').
"""
import json
import re
import uuid
from pathlib import Path

import verif_rattrapage

from build_muz_verif import http as _http, node as _node

HERE = Path(__file__).resolve().parent
OUT = HERE.parent / 'workflows' / '09_vocabag_verif.json'
WF_NAME = 'VocaBag - Vérification'
ERREURS_WF = 'VbErreursAlerte1'
NS = 'vocabag-verif/'

CRED_DB = {'mySql': {'id': 'qZ2NnMkubbTE5fNX', 'name': 'Vocabag DB'}}                          # base vocabag (SELECT)
CRED_FB = {'facebookGraphApi': {'id': 'RL5TaCOZpmZmBEc8', 'name': 'Facebook Graph account'}}    # page VocaBag (sert aussi pour IG)
CRED_YT = {'youTubeOAuth2Api': {'id': '1KMbY9e6VCrfiKfu', 'name': 'YouTube account 3'}}         # chaîne VocaBag
CRED_TG = {'telegramApi': {'id': 'TgVocabagBot0001', 'name': 'Telegram - vocabagbot'}}

CONFIG_JS = r"""
// CONFIGURATION — modifier ici. Les secrets restent dans les credentials n8n.
return [{ json: {
  graph: 'https://graph.facebook.com/v23.0',
  ig_user: '17841449858344452',        // @vocabag (lié à la page)
  fb_page: '1361049150428275',         // page VocaBag
  stories_attendues: 3,                // 16h Reel + 18h question + 21h réponse (+ visuel final) — contrôle du soir
  chat_id: '6980427615',               // conversation privée avec @vocabagbot
  forcer_moment: '',                   // test : 'apres_reel' | 'soir' (sinon d'après l'heure). Remettre ''.
} }];
"""

EVAL_JS = r"""
const e = s => String(s ?? '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
const cfg = $('Config').first().json;
const now = DateTime.now().setZone('Europe/Paris');
const today = now.toISODate();
const moment = cfg.forcer_moment || (now.hour < 19 ? 'apres_reel' : 'soir');
const test = $execution.mode === 'test';
const pb = [], ok = [];
const rat = { instagram: -1, facebook: -1 };   // index dans pb du Reel manquant → rattrapage automatique
const parisDate = v => {
  if (v == null || v === '') return null;
  const d = /^\d+$/.test(String(v)) ? DateTime.fromSeconds(Number(v)) : DateTime.fromISO(String(v));
  return d.isValid ? d.setZone('Europe/Paris').toISODate() : null;
};
const apiErr = (j, quoi) => {
  const er = j && j.error;
  if (!er) return null;
  const code = er.code ?? er.status ?? '';
  const msg = er.message || JSON.stringify(er).slice(0, 200);
  if (String(code) === '190') return `🔑 ${quoi} : token Meta invalide (code 190) — régénérer le token de page VocaBag. <i>${e(msg)}</i>`;
  if (String(code) === '401' || /invalid_grant|unauthorized/i.test(msg)) return `🔑 ${quoi} : token YouTube invalide — reconnecter la credential « YouTube account 3 ». <i>${e(msg)}</i>`;
  return `⚠️ ${quoi} : erreur API ${e(code)} — <i>${e(msg)}</i>`;
};
const get = n => { try { return $(n).first().json; } catch (x) { return { error: { message: 'nœud non exécuté' } }; } };

// --- Vidéo du jour dans vocabag_videos (dossier préfixé par la date)
const row = get('BD · Vidéo du jour');
const dbOk = row && row.folder;
if (row && row.error) pb.push(`⚠️ Base vocabag : lecture impossible — <i>${e(row.error.message || row.error)}</i>`);
else if (!dbOk) pb.push('❌ Vocabag Video : aucune vidéo générée aujourd\'hui (pas de ligne du jour dans vocabag_videos)');
else ok.push(`Vidéo du jour : ${e(row.folder)}`);
const suivi = (champ, plateforme) => {
  if (dbOk && Number(row[champ]) !== 1) pb.push(`⚠️ Suivi : publié sur ${plateforme} mais ${champ} = 0 pour ${e(row.folder)}`);
};

// --- Reel du jour : Instagram
const ig = get('IG · Publications');
let er = apiErr(ig, 'Instagram');
if (er) pb.push(er);
else {
  const r = (ig.data || []).find(m => m.media_product_type === 'REELS' && parisDate(m.timestamp) === today);
  if (r) { ok.push(`Instagram : Reel du jour (${e(r.permalink)})`); suivi('posted_on_instagram', 'Instagram'); }
  else (rat.instagram = pb.length, pb.push('❌ Instagram : aucun Reel publié aujourd\'hui sur @vocabag'));
}
// --- Reel du jour : Facebook (les vidéos de story n'ont pas de permalien /reel/)
const fb = get('FB · Vidéos');
er = apiErr(fb, 'Facebook');
if (er) pb.push(er);
else {
  const v = (fb.data || []).find(x => parisDate(x.created_time) === today && /\/reel\//.test(x.permalink_url || ''));
  if (v) { ok.push(`Facebook : Reel du jour (${e(v.title || v.id)})`); suivi('posted_on_facebook', 'Facebook'); }
  else (rat.facebook = pb.length, pb.push('❌ Facebook : aucun Reel publié aujourd\'hui sur la page VocaBag'));
}
// --- Reel du jour : YouTube
const ytc = get('YT · Chaîne');
const yt = get('YT · Dernières vidéos');
er = apiErr(ytc, 'YouTube') || apiErr(yt, 'YouTube');
if (er) pb.push(er);
else {
  const v = (yt.items || []).find(i => parisDate(i.contentDetails?.videoPublishedAt || i.snippet?.publishedAt) === today);
  if (v) { ok.push(`YouTube : ${e(v.snippet?.title)}`); suivi('posted_on_youtube', 'YouTube'); }
  else pb.push('❌ YouTube : aucune vidéo publiée aujourd\'hui sur la chaîne VocaBag');
}
// --- Stories du jour (contrôle du soir)
if (moment === 'soir') {
  const n = cfg.stories_attendues;
  const igs = get('IG · Stories');
  er = apiErr(igs, 'Instagram stories');
  if (er) pb.push(er);
  else {
    const c = (igs.data || []).filter(s => parisDate(s.timestamp) === today).length;
    c >= n ? ok.push(`Instagram : ${c} stories aujourd'hui`) : pb.push(`❌ Instagram : ${c}/${n} stories aujourd'hui (16h Reel, 18h question, 21h réponse)`);
  }
  const fbs = get('FB · Stories');
  er = apiErr(fbs, 'Facebook stories');
  if (er) pb.push(er);
  else {
    const c = (fbs.data || []).filter(s => parisDate(s.creation_time ?? s.created_time) === today).length;
    c >= n ? ok.push(`Facebook : ${c} stories aujourd'hui`) : pb.push(`❌ Facebook : ${c}/${n} stories aujourd'hui (16h Reel, 18h question, 21h réponse)`);
  }
}

const titre = pb.length ? `🚨 <b>VocaBag — ${pb.length} problème(s)</b>` : '✅ <b>VocaBag — tout est OK</b>';
const texte = `${titre} (${moment === 'soir' ? 'soir' : 'après le Reel'}, ${now.toFormat('dd/MM HH:mm')})\n\n`
  + [...pb, ...(pb.length && !test ? [] : ok.map(x => '✔️ ' + x))].join('\n');
return [{ json: { envoyer: pb.length > 0 || test, problemes: pb.length, texte: texte.slice(0, 4000), chat_id: cfg.chat_id,
  pb, ok, rat, test, label: 'VocaBag', entete: `${moment === 'soir' ? 'soir' : 'après le Reel'}, ${now.toFormat('dd/MM HH:mm')}` } }];
"""


SQL_JS = r"""
// Suivi vocabag.vocabag_videos après rattrapage (dossier lu dans la fiche du jour)
const f = $('R · Préparer').first().json.fiche || {};
const r = $input.first().json;
const folder = String(f.folder || '').replace(/[^A-Za-z0-9_]/g, '');
const num = v => String(v).replace(/[^0-9]/g, '');
const sets = [];
if (r.instagram_id) sets.push(`posted_on_instagram = 1, instagram_media_id = '${num(r.instagram_id)}', posted_instagram_at = NOW()`);
if (r.facebook_id) sets.push(`posted_on_facebook = 1, facebook_video_id = '${num(r.facebook_id)}', posted_facebook_at = NOW()`);
return [{ json: { ...r, sql: sets.length && folder ? `UPDATE vocabag_videos SET ${sets.join(', ')} WHERE folder = '${folder}'` : '' } }];
"""


def node(name, *a, **k):
    d = _node(name, *a, **k)
    d['id'] = str(uuid.uuid5(uuid.NAMESPACE_URL, NS + name))
    return d


def http(name, *a, **k):
    d = _http(name, *a, **k)
    d['id'] = str(uuid.uuid5(uuid.NAMESPACE_URL, NS + name))
    return d


def build():
    cfg = "$('Config').first().json"
    nodes = [
        node('Planifié', 'n8n-nodes-base.scheduleTrigger', 1.2,
             {'rule': {'interval': [{'triggerAtHour': 15, 'triggerAtMinute': 50},
                                    {'triggerAtHour': 21, 'triggerAtMinute': 50}]}}, [0, 0]),
        node('Test manuel', 'n8n-nodes-base.manualTrigger', 1, {}, [0, 200]),
        node('Config', 'n8n-nodes-base.code', 2, {'jsCode': CONFIG_JS.strip() + '\n'}, [220, 100]),
        node('BD · Vidéo du jour', 'n8n-nodes-base.mySql', 2.4,
             {'operation': 'executeQuery',
              'query': "=SELECT folder, posted_on_youtube, posted_on_instagram, posted_on_facebook FROM vocabag_videos "
                       "WHERE folder LIKE '{{ $now.setZone('Europe/Paris').toFormat('yyyyMMdd') }}_%' ORDER BY folder DESC LIMIT 1",
              'options': {}}, [440, 100], credentials=CRED_DB, onError='continueRegularOutput', alwaysOutputData=True),
        http('IG · Publications', [660, 100], f"={{{{ {cfg}.graph }}}}/{{{{ {cfg}.ig_user }}}}/media", CRED_FB,
             {'fields': 'timestamp,media_product_type,permalink', 'limit': '10'}),
        http('IG · Stories', [880, 100], f"={{{{ {cfg}.graph }}}}/{{{{ {cfg}.ig_user }}}}/stories", CRED_FB,
             {'fields': 'timestamp,media_type'}),
        http('FB · Vidéos', [1100, 100], f"={{{{ {cfg}.graph }}}}/{{{{ {cfg}.fb_page }}}}/videos", CRED_FB,
             {'fields': 'created_time,title,permalink_url', 'limit': '15'}),
        http('FB · Stories', [1320, 100], f"={{{{ {cfg}.graph }}}}/{{{{ {cfg}.fb_page }}}}/stories", CRED_FB, {'limit': '25'}),
        http('YT · Chaîne', [1540, 100], 'https://www.googleapis.com/youtube/v3/channels', CRED_YT,
             {'part': 'contentDetails', 'mine': 'true'}),
        http('YT · Dernières vidéos', [1760, 100], 'https://www.googleapis.com/youtube/v3/playlistItems', CRED_YT,
             {'part': 'snippet,contentDetails', 'maxResults': '5',
              'playlistId': "={{ $json.items?.[0]?.contentDetails?.relatedPlaylists?.uploads || 'introuvable' }}"}),
        node('Évaluer', 'n8n-nodes-base.code', 2, {'jsCode': EVAL_JS.strip() + '\n'}, [1980, 100]),
        node('Envoyer ?', 'n8n-nodes-base.if', 2, {
            'conditions': {
                'options': {'caseSensitive': True, 'leftValue': '', 'typeValidation': 'loose', 'version': 1},
                'conditions': [{'id': str(uuid.uuid5(uuid.NAMESPACE_URL, NS + 'envoyer')),
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
    chain = ['Config', 'BD · Vidéo du jour', 'IG · Publications', 'IG · Stories', 'FB · Vidéos', 'FB · Stories',
             'YT · Chaîne', 'YT · Dernières vidéos', 'Évaluer']
    for a, b in zip(chain, chain[1:]):
        link(a, b)
    link('Envoyer ?', 'Alerte Telegram', 0)
    link('Évaluer', 'Rattraper ?')
    verif_rattrapage.ajouter(nodes, link, NS, node, http, 'WFKPD7GzMgbEuM5F', '/files/vocabag/_publications', CRED_DB, SQL_JS, 2200, cred_fb=CRED_FB)
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
