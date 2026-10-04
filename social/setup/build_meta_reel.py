#!/usr/bin/env python3
"""Génère les sous-workflows n8n « Meta - Publier Reel (VocaBag) » et « Meta - Publier Reel (Muz Rappel) »
→ ../workflows/11_meta_reel_vocabag.json et 12_meta_reel_muz.json.

Publication d'un Reel sur Instagram (compte pro lié à la page) puis sur la page Facebook, en nœuds HTTP standard
(graph.facebook.com + token de page, credential facebookGraphApi) — remplace le nœud communautaire
@mookielianhd/n8n-nodes-instagram, dont les patchs locaux sautaient à chaque mise à jour (2026-10-04).

Appel : nœud « Execute Workflow » (mode once, waitForSubWorkflow) avec UN item :
  video_url       URL publique de la vidéo (download_url RVM, ou /stage du service média)
  caption         légende Instagram
  fb_title, fb_description   titre / description Facebook
  share_to_feed   false = Reel seul (VocaBag), true par défaut
  instagram, facebook        false pour sauter une plateforme (défaut : true)
  alerter         false = pas d'alerte Telegram (la vérification fait son propre bilan)
  contexte        texte libre repris dans l'alerte (ex. dossier de la vidéo)
Retour (dernier nœud « Retour ») : { compte, instagram_id, instagram_erreur, facebook_id, facebook_erreur }.

Fiabilité : jusqu'à `essais` tentatives par plateforme, `pause_s` secondes d'écart (attentes < 65 s : restent en
mémoire, pas de reprise depuis la base), aucune nouvelle tentative si le token est invalide (code 190).
Échec définitif → alerte Telegram immédiate (bot du compte).
"""
import json
import uuid
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT_DIR = HERE.parent / 'workflows'

COMPTES = {
    'vocabag': {
        'fichier': '11_meta_reel_vocabag.json', 'nom': 'Meta - Publier Reel (VocaBag)', 'label': 'VocaBag',
        'ig_user': '17841449858344452', 'fb_page': '1361049150428275',
        'cred_fb': {'facebookGraphApi': {'id': 'RL5TaCOZpmZmBEc8', 'name': 'Facebook Graph account'}},
        'cred_tg': {'telegramApi': {'id': 'TgVocabagBot0001', 'name': 'Telegram - vocabagbot'}},
        'erreurs_wf': 'VbErreursAlerte1',
    },
    'muz': {
        'fichier': '12_meta_reel_muz.json', 'nom': 'Meta - Publier Reel (Muz Rappel)', 'label': 'Muz Rappel',
        'ig_user': '17841472522032723', 'fb_page': '501465773057138',
        'cred_fb': {'facebookGraphApi': {'id': 'SZI9tiIqTC821bCa', 'name': 'Facebook Graph account 2'}},
        'cred_tg': {'telegramApi': {'id': 'TnA0UuhJFPlr5QZu', 'name': 'Telegram - muzrappelbot'}},
        'erreurs_wf': 'eUErVpA15sgk6j1m',
    },
}
CHAT_ID = '6980427615'

CONFIG_JS = r"""
// Paramètres du compte + valeurs reçues du workflow appelant.
const entree = $input.first().json;
return [{ json: {
  graph: 'https://graph.facebook.com/v23.0',
  graph_video: 'https://graph-video.facebook.com/v23.0',
  ig_user: '__IG_USER__',
  fb_page: '__FB_PAGE__',
  compte: '__LABEL__',
  chat_id: '__CHAT_ID__',
  essais: 3,             // tentatives par plateforme
  pause_s: 60,           // entre deux tentatives (< 65 s : l'exécution reste en mémoire)
  poll_s: 15,            // entre deux lectures du statut du conteneur Instagram
  poll_max_s: 600,       // traitement Instagram au-delà → tentative en échec
  instagram: true, facebook: true, alerter: true, share_to_feed: true, contexte: '',
  ...entree,
} }];
"""

# Message d'erreur lisible + token invalide ? (partagé par les nœuds « Échec »)
ERR_JS = r"""
const msgErreur = j => {
  if (!j) return 'réponse vide';
  if (j.erreur) return String(j.erreur);
  const e = j.error;
  if (e) return [e.error_user_title, e.error_user_msg || e.message, e.code != null ? `(code ${e.code}${e.error_subcode ? '/' + e.error_subcode : ''})` : '']
    .filter(Boolean).join(' ');
  return JSON.stringify(j).slice(0, 300);
};
const tokenInvalide = m => /\(code 190\b|access token|session has been invalidated/i.test(m);
"""

IG_DEPART_JS = r"""
const r = $input.first().json;
if (r.id) return [{ json: { ok: true, creation_id: r.id, debut: Date.now() } }];
return [{ json: { ok: false, erreur: msgErreur(r) } }];
"""

IG_EVALUER_JS = r"""
const cfg = $('Config').first().json;
const r = $input.first().json;
const depart = $('IG · Départ').last().json;
if (r.error) return [{ json: { etat: 'echec', erreur: msgErreur(r) } }];
const s = r.status_code;
if (s === 'FINISHED') return [{ json: { etat: 'pret' } }];
if (s === 'ERROR' || s === 'EXPIRED') return [{ json: { etat: 'echec', erreur: `conteneur ${s} : ${r.status || ''}` } }];
if (Date.now() - depart.debut > cfg.poll_max_s * 1000)
  return [{ json: { etat: 'echec', erreur: `traitement Instagram trop long (${s || '?'} après ${cfg.poll_max_s} s)` } }];
return [{ json: { etat: 'attente' } }];
"""

ECHEC_JS = r"""
// Une exécution de ce nœud = une tentative ratée ($runIndex compte les passages).
const cfg = $('Config').first().json;
const erreur = msgErreur($input.first().json);
const tentative = $runIndex + 1;
return [{ json: { erreur, tentative, retenter: !tokenInvalide(erreur) && tentative < cfg.essais } }];
"""

IG_FIN_JS = r"""
const cfg = $('Config').first().json;
const j = $input.first().json;
if (cfg.instagram === false) return [{ json: { instagram: 'ignoré' } }];
if (j.id && j.erreur == null) return [{ json: { instagram_id: String(j.id) } }];
return [{ json: { instagram_erreur: `${j.erreur} — ${j.tentative} tentative(s)` } }];
"""

FB_EVALUER_JS = r"""
const r = $input.first().json;
if (r.id) return [{ json: { id: String(r.id) } }];
return [{ json: { erreur: msgErreur(r) } }];
"""

FB_FIN_JS = r"""
const cfg = $('Config').first().json;
const j = $input.first().json;
if (cfg.facebook === false) return [{ json: { facebook: 'ignoré' } }];
if (j.id && j.erreur == null) return [{ json: { facebook_id: String(j.id) } }];
return [{ json: { facebook_erreur: `${j.erreur} — ${j.tentative} tentative(s)` } }];
"""

RESULTAT_JS = r"""
const e = s => String(s ?? '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
const cfg = $('Config').first().json;
const ig = $('IG · Fin').first().json, fb = $('FB · Fin').first().json;
const res = { compte: cfg.compte, instagram_id: ig.instagram_id || '', instagram_erreur: ig.instagram_erreur || '',
              facebook_id: fb.facebook_id || '', facebook_erreur: fb.facebook_erreur || '' };
const lignes = [];
if (res.instagram_erreur) lignes.push(`❌ Instagram : ${e(res.instagram_erreur)}`);
if (res.facebook_erreur) lignes.push(`❌ Facebook : ${e(res.facebook_erreur)}`);
if (res.instagram_id) lignes.push(`✔️ Instagram publié (${res.instagram_id})`);
if (res.facebook_id) lignes.push(`✔️ Facebook publié (${res.facebook_id})`);
const echec = !!(res.instagram_erreur || res.facebook_erreur);
res.alerte = echec && cfg.alerter !== false
  ? `🚨 <b>${e(cfg.compte)} — publication du Reel en échec</b>${cfg.contexte ? '\n' + e(cfg.contexte) : ''}\n\n${lignes.join('\n')}`
    + (/code 190/.test(lignes.join(' ')) ? '\n\n🔑 Token Meta invalide : régénérer le token de page.' : '')
    + '\n\nLa vérification du jour tentera un rattrapage automatique.'
  : '';
return [{ json: res }];
"""

RETOUR_JS = r"""
const r = { ...$('Résultat').first().json };
delete r.alerte;
return [{ json: r }];
"""


def build(cle):
    c = COMPTES[cle]
    ns = f'meta-reel-{cle}/'

    def node(name, type_, version, params, pos, **extra):
        d = {'parameters': params, 'id': str(uuid.uuid5(uuid.NAMESPACE_URL, ns + name)), 'name': name,
             'type': type_, 'typeVersion': version, 'position': pos}
        d.update(extra)
        return d

    def code(name, js, pos, err=False):
        return node(name, 'n8n-nodes-base.code', 2, {'jsCode': ((ERR_JS.strip() + '\n') if err else '') + js.strip() + '\n'}, pos)

    def http(name, pos, method, url, query, timeout=60000):
        p = {'method': method, 'url': url, 'authentication': 'predefinedCredentialType',
             'nodeCredentialType': 'facebookGraphApi', 'sendQuery': True,
             'queryParameters': {'parameters': [{'name': a, 'value': b} for a, b in query.items()]},
             'options': {'response': {'response': {'neverError': True}}, 'timeout': timeout}}
        # neverError + continueRegularOutput : toute réponse (même 4xx) arrive au nœud suivant, qui décide
        return node(name, 'n8n-nodes-base.httpRequest', 4.2, p, pos, credentials=c['cred_fb'],
                    onError='continueRegularOutput', alwaysOutputData=True)

    def wait(name, expr, pos):
        return node(name, 'n8n-nodes-base.wait', 1.1, {'amount': expr, 'unit': 'seconds'}, pos,
                    webhookId=str(uuid.uuid5(uuid.NAMESPACE_URL, ns + 'webhook/' + name)))

    def iff(name, expr, pos):
        return node(name, 'n8n-nodes-base.if', 2, {
            'conditions': {'options': {'caseSensitive': True, 'leftValue': '', 'typeValidation': 'loose', 'version': 1},
                           'conditions': [{'id': str(uuid.uuid5(uuid.NAMESPACE_URL, ns + 'if/' + name)),
                                           'leftValue': '={{ ' + expr + ' }}', 'rightValue': '',
                                           'operator': {'type': 'boolean', 'operation': 'true', 'singleValue': True}}],
                           'combinator': 'and'}, 'options': {}}, pos)

    cfg = "$('Config').first().json"
    config_js = (CONFIG_JS.replace('__IG_USER__', c['ig_user']).replace('__FB_PAGE__', c['fb_page'])
                 .replace('__LABEL__', c['label']).replace('__CHAT_ID__', CHAT_ID))
    nodes = [
        node('Entrée', 'n8n-nodes-base.executeWorkflowTrigger', 1, {}, [0, 300]),
        code('Config', config_js, [200, 300]),
        # --- Instagram
        iff('Instagram ?', f'{cfg}.instagram !== false', [400, 300]),
        http('IG · Créer conteneur', [600, 200], 'POST', f"={{{{ {cfg}.graph }}}}/{{{{ {cfg}.ig_user }}}}/media",
             {'media_type': 'REELS', 'video_url': f'={{{{ {cfg}.video_url }}}}', 'caption': f'={{{{ {cfg}.caption }}}}',
              'share_to_feed': f'={{{{ {cfg}.share_to_feed === false ? "false" : "true" }}}}'}),
        code('IG · Départ', IG_DEPART_JS, [800, 200], err=True),
        iff('IG · Conteneur créé ?', '$json.ok', [1000, 200]),
        wait('IG · Attente', f'={{{{ {cfg}.poll_s }}}}', [1200, 100]),
        http('IG · Statut', [1400, 100], 'GET', f"={{{{ {cfg}.graph }}}}/{{{{ $('IG · Départ').last().json.creation_id }}}}",
             {'fields': 'status_code,status'}),
        code('IG · Évaluer', IG_EVALUER_JS, [1600, 100], err=True),
        iff('IG · Prêt ?', "$json.etat === 'pret'", [1800, 100]),
        iff('IG · En cours ?', "$json.etat === 'attente'", [2000, 200]),
        http('IG · Publier', [2000, 0], 'POST', f"={{{{ {cfg}.graph }}}}/{{{{ {cfg}.ig_user }}}}/media_publish",
             {'creation_id': "={{ $('IG · Départ').last().json.creation_id }}"}),
        iff('IG · Publié ?', '!!$json.id', [2200, 0]),
        code('IG · Échec', ECHEC_JS, [2200, 400], err=True),
        iff('IG · Réessayer ?', '$json.retenter', [2400, 400]),
        wait('IG · Pause', f'={{{{ {cfg}.pause_s }}}}', [2600, 500]),
        code('IG · Fin', IG_FIN_JS, [2600, 300]),
        # --- Facebook (après Instagram, quel que soit son résultat)
        iff('Facebook ?', f'{cfg}.facebook !== false', [2800, 300]),
        http('FB · Publier', [3000, 200], 'POST', f"={{{{ {cfg}.graph_video }}}}/{{{{ {cfg}.fb_page }}}}/videos",
             {'file_url': f'={{{{ {cfg}.video_url }}}}', 'title': f'={{{{ {cfg}.fb_title }}}}',
              'description': f'={{{{ {cfg}.fb_description }}}}'}, timeout=300000),
        code('FB · Évaluer', FB_EVALUER_JS, [3200, 200], err=True),
        iff('FB · Publié ?', '!!$json.id', [3400, 200]),
        code('FB · Échec', ECHEC_JS, [3600, 400], err=True),
        iff('FB · Réessayer ?', '$json.retenter', [3800, 400]),
        wait('FB · Pause', f'={{{{ {cfg}.pause_s }}}}', [4000, 500]),
        code('FB · Fin', FB_FIN_JS, [4000, 300]),
        # --- Bilan
        code('Résultat', RESULTAT_JS, [4200, 300]),
        iff('Alerter ?', '!!$json.alerte', [4400, 300]),
        node('Alerte Telegram', 'n8n-nodes-base.telegram', 1.2,
             {'chatId': f'={{{{ {cfg}.chat_id }}}}', 'text': '={{ $json.alerte }}',
              'additionalFields': {'appendAttribution': False, 'parse_mode': 'HTML', 'disable_web_page_preview': True}},
             [4600, 200], credentials=c['cred_tg'], onError='continueRegularOutput'),
        code('Retour', RETOUR_JS, [4800, 300]),
    ]
    conn = {}

    def link(a, b, out=0):
        conn.setdefault(a, {'main': []})
        while len(conn[a]['main']) <= out:
            conn[a]['main'].append([])
        conn[a]['main'][out].append({'node': b, 'type': 'main', 'index': 0})

    for a, b, o in [
        ('Entrée', 'Config', 0), ('Config', 'Instagram ?', 0),
        ('Instagram ?', 'IG · Créer conteneur', 0), ('Instagram ?', 'IG · Fin', 1),
        ('IG · Créer conteneur', 'IG · Départ', 0), ('IG · Départ', 'IG · Conteneur créé ?', 0),
        ('IG · Conteneur créé ?', 'IG · Attente', 0), ('IG · Conteneur créé ?', 'IG · Échec', 1),
        ('IG · Attente', 'IG · Statut', 0), ('IG · Statut', 'IG · Évaluer', 0), ('IG · Évaluer', 'IG · Prêt ?', 0),
        ('IG · Prêt ?', 'IG · Publier', 0), ('IG · Prêt ?', 'IG · En cours ?', 1),
        ('IG · En cours ?', 'IG · Attente', 0), ('IG · En cours ?', 'IG · Échec', 1),
        ('IG · Publier', 'IG · Publié ?', 0), ('IG · Publié ?', 'IG · Fin', 0), ('IG · Publié ?', 'IG · Échec', 1),
        ('IG · Échec', 'IG · Réessayer ?', 0), ('IG · Réessayer ?', 'IG · Pause', 0), ('IG · Réessayer ?', 'IG · Fin', 1),
        ('IG · Pause', 'IG · Créer conteneur', 0),
        ('IG · Fin', 'Facebook ?', 0),
        ('Facebook ?', 'FB · Publier', 0), ('Facebook ?', 'FB · Fin', 1),
        ('FB · Publier', 'FB · Évaluer', 0), ('FB · Évaluer', 'FB · Publié ?', 0),
        ('FB · Publié ?', 'FB · Fin', 0), ('FB · Publié ?', 'FB · Échec', 1),
        ('FB · Échec', 'FB · Réessayer ?', 0), ('FB · Réessayer ?', 'FB · Pause', 0), ('FB · Réessayer ?', 'FB · Fin', 1),
        ('FB · Pause', 'FB · Publier', 0),
        ('FB · Fin', 'Résultat', 0), ('Résultat', 'Alerter ?', 0),
        ('Alerter ?', 'Alerte Telegram', 0), ('Alerter ?', 'Retour', 1), ('Alerte Telegram', 'Retour', 0),
    ]:
        link(a, b, o)
    return {'name': c['nom'], 'nodes': nodes, 'connections': conn,
            'settings': {'executionOrder': 'v1', 'timezone': 'Europe/Paris', 'errorWorkflow': c['erreurs_wf'],
                         'callerPolicy': 'workflowsFromSameOwner'}}


if __name__ == '__main__':
    import re
    for cle, c in COMPTES.items():
        data = build(cle)
        names = {n['name'] for n in data['nodes']}
        texte = json.dumps([n['parameters'] for n in data['nodes']], ensure_ascii=False)
        for ref in re.findall(r"\$\('([^']+)'\)", texte):
            assert ref in names, ('nœud inexistant', ref)
        for a, v in data['connections'].items():
            assert a in names, a
            for outs in v['main']:
                for o in outs:
                    assert o['node'] in names, o
        (OUT_DIR / c['fichier']).write_text(json.dumps(data, ensure_ascii=False, indent=2))
        print(f"{c['fichier']}  {len(data['nodes'])} nœuds")
