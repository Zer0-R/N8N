#!/usr/bin/env python3
"""Génère le workflow n8n « Stats hebdo » → ../workflows/14_stats_hebdo.json.

Chaque lundi 9h (Paris), un bilan par compte sur Telegram (VocaBag → @vocabagbot, Muz Rappel → @muzrappelbot) :
Reels des 7 derniers jours sur YouTube (vues, likes, commentaires), Instagram (likes, commentaires) et Facebook
(vues, likes, commentaires), top 3, abonnés et leur évolution depuis le bilan précédent (mémorisés dans
staticData du workflow, exécutions planifiées uniquement), et pour VocaBag les vues YouTube par langue.
Lecture seule. Vues/portée Instagram : nécessitent la permission instagram_manage_insights (absente au 2026-10-04) ;
le nœud « IG · Vues » les ajoute automatiquement dès qu'elle est accordée.
"""
import json
import re
import uuid
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE.parent / 'workflows' / '14_stats_hebdo.json'
WF_NAME = 'Stats hebdo (VocaBag + Muz Rappel)'
NS = 'stats-hebdo/'

COMPTES = [
    {'cle': 'VB', 'label': 'VocaBag', 'ig': '17841449858344452', 'page': '1361049150428275', 'par_langue': True,
     'fb': {'facebookGraphApi': {'id': 'RL5TaCOZpmZmBEc8', 'name': 'Facebook Graph account'}},
     'yt': {'youTubeOAuth2Api': {'id': '1KMbY9e6VCrfiKfu', 'name': 'YouTube account 3'}},
     'tg': {'telegramApi': {'id': 'TgVocabagBot0001', 'name': 'Telegram - vocabagbot'}}, 'erreurs': 'VbErreursAlerte1'},
    {'cle': 'MZ', 'label': 'Muz Rappel', 'ig': '17841472522032723', 'page': '501465773057138', 'par_langue': False,
     'fb': {'facebookGraphApi': {'id': 'SZI9tiIqTC821bCa', 'name': 'Facebook Graph account 2'}},
     'yt': {'youTubeOAuth2Api': {'id': 'cwYHFUad2DZdTq0k', 'name': 'YouTube account'}},
     'tg': {'telegramApi': {'id': 'TnA0UuhJFPlr5QZu', 'name': 'Telegram - muzrappelbot'}}, 'erreurs': 'eUErVpA15sgk6j1m'},
]
CHAT_ID = '6980427615'
G = 'https://graph.facebook.com/v23.0'

BILAN_JS = r"""
const e = s => String(s ?? '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
const n = v => Number(v || 0);
const fmt = v => n(v).toLocaleString('fr-FR');
const A = '__A__', LABEL = '__LABEL__', PAR_LANGUE = __PAR_LANGUE__;
const get = x => { try { return $(x).first().json; } catch (err) { return {}; } };
const debut = DateTime.now().setZone('Europe/Paris').minus({ days: 7 });
const recent = t => t && DateTime.fromISO(String(t)) >= debut;
const erreurs = [];
const err = (j, quoi) => { if (j && j.error) erreurs.push(`${quoi} : ${e(j.error.message || JSON.stringify(j.error)).slice(0, 120)}`); };

// --- YouTube
const ytc = get(`${A} · YT chaîne`), yts = get(`${A} · YT stats`);
err(ytc, 'YouTube'); err(yts, 'YouTube stats');
const yt = (yts.items || []).filter(v => recent(v.snippet?.publishedAt)).map(v => ({
  titre: v.snippet.title, vues: n(v.statistics?.viewCount), likes: n(v.statistics?.likeCount), coms: n(v.statistics?.commentCount) }));
// --- Instagram (vues seulement si instagram_manage_insights est accordée)
const igm = get(`${A} · IG médias`), igc = get(`${A} · IG compte`);
err(igm, 'Instagram'); err(igc, 'Instagram compte');
const vuesIG = {};
try { for (const it of $(`${A} · IG vues`).all()) { const d = it.json.data; if (Array.isArray(d)) for (const m of d) if (m.name === 'views') vuesIG[String(m.id).split('/')[0]] = n(m.values?.[0]?.value); } } catch (x) {}
const ig = (igm.data || []).filter(m => m.media_product_type === 'REELS' && recent(m.timestamp)).map(m => ({
  titre: String(m.caption || '').split('\n')[0].slice(0, 70), likes: n(m.like_count), coms: n(m.comments_count), vues: vuesIG[m.id] }));
// --- Facebook (vidéos de Reel : permalien /reel/)
const fbv = get(`${A} · FB vidéos`), fbp = get(`${A} · FB page`);
err(fbv, 'Facebook'); err(fbp, 'Facebook page');
const fb = (fbv.data || []).filter(v => /\/reel\//.test(v.permalink_url || '') && recent(v.created_time)).map(v => ({
  titre: v.title || '', vues: n(v.views), likes: n(v.likes?.summary?.total_count), coms: n(v.comments?.summary?.total_count) }));

// --- Abonnés + évolution (staticData : exécutions planifiées uniquement)
const abo = { youtube: n(ytc.items?.[0]?.statistics?.subscriberCount), instagram: n(igc.followers_count), facebook: n(fbp.followers_count) };
const memo = $getWorkflowStaticData('global');
const avant = memo[A] || null;
memo[A] = abo;
const delta = k => avant ? ` (${abo[k] - avant[k] >= 0 ? '+' : ''}${abo[k] - avant[k]})` : '';

const somme = (l, k) => l.reduce((s, x) => s + n(x[k]), 0);
const lignes = [];
lignes.push(`📊 <b>${LABEL} — semaine du ${debut.toFormat('dd/MM')} au ${DateTime.now().setZone('Europe/Paris').minus({ days: 1 }).toFormat('dd/MM')}</b>`);
lignes.push('');
lignes.push(`▶️ <b>YouTube</b> : ${yt.length} vidéo(s) · ${fmt(somme(yt, 'vues'))} vues · ${fmt(somme(yt, 'likes'))} likes · ${fmt(somme(yt, 'coms'))} com.`);
const vIG = ig.some(x => x.vues != null) ? ` · ${fmt(somme(ig, 'vues'))} vues` : '';
lignes.push(`📸 <b>Instagram</b> : ${ig.length} Reel(s)${vIG} · ${fmt(somme(ig, 'likes'))} likes · ${fmt(somme(ig, 'coms'))} com.`);
lignes.push(`📘 <b>Facebook</b> : ${fb.length} Reel(s) · ${fmt(somme(fb, 'vues'))} vues · ${fmt(somme(fb, 'likes'))} likes · ${fmt(somme(fb, 'coms'))} com.`);
lignes.push('');
lignes.push(`👥 <b>Abonnés</b> : YouTube ${fmt(abo.youtube)}${delta('youtube')} · Instagram ${fmt(abo.instagram)}${delta('instagram')} · Facebook ${fmt(abo.facebook)}${delta('facebook')}`);
const top = [...yt].sort((a, b) => b.vues - a.vues).slice(0, 3);
if (top.length) {
  lignes.push('', '🏆 <b>Top YouTube</b>');
  top.forEach((v, i) => lignes.push(`${i + 1}. ${e(v.titre)} — ${fmt(v.vues)} vues, ${fmt(v.likes)} likes`));
}
const topIG = [...ig].sort((a, b) => (b.vues ?? b.likes) - (a.vues ?? a.likes)).slice(0, 3);
if (topIG.length) {
  lignes.push('', '🏆 <b>Top Instagram</b>');
  topIG.forEach((v, i) => lignes.push(`${i + 1}. ${e(v.titre)} — ${v.vues != null ? fmt(v.vues) + ' vues, ' : ''}${fmt(v.likes)} likes`));
}
if (PAR_LANGUE && yt.length) {
  const parL = {};
  for (const v of yt) {
    const t = String(v.titre);
    const duel = t.match(/([A-ZÉÈ][\p{L}-]+)\s+(?:vs|VS|contre)\.?\s+([A-ZÉÈ][\p{L}-]+)/u);
    const m = t.match(/\ben ([A-ZÉÈ][\p{L}-]+)/u);
    const l = duel ? `${duel[1]} vs ${duel[2]}` : m ? m[1] : 'autre';
    parL[l] = parL[l] || { vues: 0, nb: 0 }; parL[l].vues += v.vues; parL[l].nb += 1;
  }
  lignes.push('', '🌍 <b>Vues YouTube par langue</b> (moyenne par vidéo)');
  Object.entries(parL).sort((a, b) => b[1].vues / b[1].nb - a[1].vues / a[1].nb)
    .forEach(([l, x]) => lignes.push(`• ${e(l)} : ${fmt(Math.round(x.vues / x.nb))} (${x.nb} vidéo${x.nb > 1 ? 's' : ''})`));
}
if (!ig.some(x => x.vues != null)) lignes.push('', '<i>Vues Instagram indisponibles : permission instagram_manage_insights à ajouter au token.</i>');
if (erreurs.length) lignes.push('', '⚠️ ' + erreurs.join('\n⚠️ '));
return [{ json: { texte: lignes.join('\n').slice(0, 4000), chat_id: '__CHAT__' } }];
"""


def node(name, type_, version, params, pos, **extra):
    d = {'parameters': params, 'id': str(uuid.uuid5(uuid.NAMESPACE_URL, NS + name)), 'name': name,
         'type': type_, 'typeVersion': version, 'position': pos}
    d.update(extra)
    return d


def http(name, pos, url, cred, query):
    p = {'method': 'GET', 'url': url, 'authentication': 'predefinedCredentialType', 'nodeCredentialType': next(iter(cred)),
         'sendQuery': True, 'queryParameters': {'parameters': [{'name': a, 'value': b} for a, b in query.items()]},
         'options': {'response': {'response': {'neverError': True}}, 'timeout': 60000}}
    return node(name, 'n8n-nodes-base.httpRequest', 4.2, p, pos, credentials=cred, onError='continueRegularOutput',
                alwaysOutputData=True)


def build():
    nodes = [
        node('Planifié', 'n8n-nodes-base.scheduleTrigger', 1.2,
             {'rule': {'interval': [{'field': 'weeks', 'weeksInterval': 1, 'triggerAtDay': [1], 'triggerAtHour': 9}]}}, [0, 0]),
        node('Test manuel', 'n8n-nodes-base.manualTrigger', 1, {}, [0, 200]),
    ]
    conn = {}

    def link(a, b):
        conn.setdefault(a, {'main': [[]]})['main'][0].append({'node': b, 'type': 'main', 'index': 0})

    precedent = None
    for k, c in enumerate(COMPTES):
        A, y = c['cle'], k * 300
        chain = [
            http(f'{A} · IG médias', [220, y], f"{G}/{c['ig']}/media", c['fb'],
                 {'fields': 'id,timestamp,caption,like_count,comments_count,media_product_type', 'limit': '30'}),
            node(f'{A} · IG cibles', 'n8n-nodes-base.code', 2, {'jsCode': (
                "const debut = DateTime.now().minus({ days: 8 });\n"
                "const l = ($input.first().json.data || []).filter(m => m.media_product_type === 'REELS' && DateTime.fromISO(m.timestamp) >= debut);\n"
                "return l.length ? l.map(m => ({ json: { id: m.id } })) : [{ json: { id: '' } }];\n")}, [440, y]),
            http(f'{A} · IG vues', [660, y], f"={G}/{{{{ $json.id || 'aucun' }}}}/insights", c['fb'], {'metric': 'views'}),
            http(f'{A} · IG compte', [880, y], f"{G}/{c['ig']}", c['fb'], {'fields': 'followers_count,media_count'}),
            http(f'{A} · FB vidéos', [1100, y], f"{G}/{c['page']}/videos", c['fb'],
                 {'fields': 'id,title,created_time,views,permalink_url,likes.summary(true).limit(0),comments.summary(true).limit(0)',
                  'limit': '30'}),
            http(f'{A} · FB page', [1320, y], f"{G}/{c['page']}", c['fb'], {'fields': 'followers_count'}),
            http(f'{A} · YT chaîne', [1540, y], 'https://www.googleapis.com/youtube/v3/channels', c['yt'],
                 {'part': 'statistics,contentDetails', 'mine': 'true'}),
            http(f'{A} · YT uploads', [1760, y], 'https://www.googleapis.com/youtube/v3/playlistItems', c['yt'],
                 {'part': 'contentDetails', 'maxResults': '20',
                  'playlistId': "={{ $json.items?.[0]?.contentDetails?.relatedPlaylists?.uploads || 'introuvable' }}"}),
            http(f'{A} · YT stats', [1980, y], 'https://www.googleapis.com/youtube/v3/videos', c['yt'],
                 {'part': 'snippet,statistics',
                  'id': "={{ ($json.items || []).map(i => i.contentDetails.videoId).join(',') || 'aucun' }}"}),
            node(f'{A} · Bilan', 'n8n-nodes-base.code', 2, {'jsCode': BILAN_JS.replace('__A__', A).replace('__LABEL__', c['label'])
                 .replace('__PAR_LANGUE__', 'true' if c['par_langue'] else 'false').replace('__CHAT__', CHAT_ID).strip() + '\n'},
                 [2200, y]),
            node(f'{A} · Telegram', 'n8n-nodes-base.telegram', 1.2,
                 {'chatId': '={{ $json.chat_id }}', 'text': '={{ $json.texte }}',
                  'additionalFields': {'appendAttribution': False, 'parse_mode': 'HTML', 'disable_web_page_preview': True}},
                 [2420, y], credentials=c['tg'], onError='continueRegularOutput'),
        ]
        # « IG vues » s'exécute une fois par Reel ; « IG compte » ne doit tourner qu'une fois
        chain[3]['executeOnce'] = True
        nodes += chain
        noms = [n['name'] for n in chain]
        for a, b in zip(noms, noms[1:]):
            link(a, b)
        if precedent is None:
            link('Planifié', noms[0])
            link('Test manuel', noms[0])
        else:
            link(precedent, noms[0])      # comptes l'un après l'autre
        precedent = noms[-1]
    # executeOnce aussi pour les nœuds après « IG compte »
    for n in nodes:
        if any(s in n['name'] for s in ('FB vidéos', 'FB page', 'YT chaîne', 'YT uploads', 'YT stats', 'Bilan', 'Telegram')):
            n['executeOnce'] = True
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
