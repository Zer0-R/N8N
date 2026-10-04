#!/usr/bin/env python3
"""Génère les workflows n8n « VocaBag Social » (JSON importables) dans ../workflows/.

Pourquoi un générateur : 8 workflows, ~120 nœuds, connexions nombreuses ; les écrire à la main en
JSON est source d'erreurs. Modifier ce fichier puis relancer :  python3 build_workflows.py
Les identifiants de workflow sont fixes (les sous-workflows s'appellent par id).
"""
import json
import re
import uuid
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / 'workflows'

# ------------------------------------------------------------------ identifiants
WF = {
    'carrousel': 'VbSocialCarrous1',
    'stories':   'VbSocialStories1',
    'blog':      'VbSocialBlog0001',
    'erreurs':   'VbErreursAlerte1',
    'newsletter': 'VbNewsletterHeb1',  # newsletter hebdo (2026-09-28)   # alerte Telegram (2026-09-28) ; ≠ VbSocialErreurs1 (ancien, supprimé)
    'prompt':    'VbSocialPrompt01',  # prompt ChatGPT de carrousel, piloté par boutons Telegram (2026-10-04)
    # blocs intégrés (plus des workflows) : ids servant seulement à nommer les nœuds générés
    'descr':     'VbSocialDescr001',
    'ig':        'VbSocialPubIG001',
    'pin':       'VbSocialPubPin01',
}
# Anciens workflows remplacés par la fusion du 2026-09-27 (supprimés de n8n par install.sh).
ANCIENS = ['VbSocialConfig01', 'VbSocialDescr001', 'VbSocialPubIG001', 'VbSocialPubPin01', 'VbSocialTokenIG1',
           'VbSocialErreurs1', 'VbSocialBlogRev1', 'VbSocialBlogPret', 'VbSocialBlogDec1']

# Credentials existants (n8n) — ceux marqués « à créer » sont décrits dans la doc.
CRED_IG = {'instagramApi': {'id': 'yWMtvSRb69T9GKW2', 'name': 'Instagram account'}}   # vocabag_com
CRED_TG = {'telegramApi': {'id': 'TgVocabagBot0001', 'name': 'Telegram - vocabagbot'}}
CRED_DB = {'mySql': {'id': 'qZ2NnMkubbTE5fNX', 'name': 'Vocabag DB'}}                   # SELECT seul
CRED_MEDIA = {'httpHeaderAuth': {'id': 'VbMediaToken0001', 'name': 'VocaBag media (X-Media-Token)'}}   # à créer
# Pinterest : n8n n'a pas de credential Pinterest → OAuth2 générique (voir doc §19). Id à reporter après création.
CRED_PIN = {'oAuth2Api': {'id': 'A_REMPLACER_PIN', 'name': 'Pinterest - vocabag'}}
CRED_SMTP = {'smtp': {'id': 'VbSmtpGmail00001', 'name': 'Gmail - contact.vocabag (SMTP)'}}
# Token de PAGE Facebook VocaBag (Graph API Explorer → me/accounts), créé à la main dans n8n le 2026-09-30.
CRED_FB = {'facebookGraphApi': {'id': 'RL5TaCOZpmZmBEc8', 'name': 'Facebook Graph account'}}
FB_PAGE = 'https://graph.facebook.com/v23.0/1361049150428275'   # id Graph de la page VocaBag (≠ id de l'URL)              # setup_n8n.py


class W:
    """Petit constructeur de workflow."""

    def __init__(self, key, name):
        self.id = WF[key]
        self.name = name
        self.nodes = []
        self.conn = {}
        self.x = 0

    def add(self, name, type_, version, params, pos=None, **extra):
        if pos is None:
            pos = [self.x, 0]
            self.x += 240
        node = {'parameters': params, 'id': str(uuid.uuid5(uuid.NAMESPACE_URL, self.id + name)),
                'name': name, 'type': type_, 'typeVersion': version, 'position': pos}
        node.update(extra)
        self.nodes.append(node)
        return name

    def link(self, a, b, out=0, inp=0):
        outs = self.conn.setdefault(a, {'main': []})['main']
        while len(outs) <= out:
            outs.append([])
        outs[out].append({'node': b, 'type': 'main', 'index': inp})

    def chain(self, *names):
        for a, b in zip(names, names[1:]):
            self.link(a, b)

    def dump(self, active=False, settings_extra=None):
        # Un plantage (exécution en erreur) déclenche le workflow « Erreurs » → alerte Telegram (2026-09-28).
        settings = {'executionOrder': 'v1', 'timezone': 'Europe/Paris', 'callerPolicy': 'workflowsFromSameOwner'}
        if self.id != WF['erreurs']:
            settings['errorWorkflow'] = WF['erreurs']
        settings.update(settings_extra or {})
        return {'id': self.id, 'name': self.name, 'active': active, 'nodes': self.nodes,
                'connections': self.conn, 'settings': settings, 'pinData': {}, 'tags': []}


# ------------------------------------------------------------------ blocs intégrés
def integrer(w, nom, builder, tag, dy=700):
    """Remplace le nœud d'appel « nom » (placeholder) par les nœuds du bloc builder() intégrés au workflow.

    Le bloc (ex-sous-workflow) garde sa logique : son déclencheur « Entrée » devient un nœud de passage
    « Entrée · tag » qui reçoit les liens entrants du placeholder ; son « Config » est celui du workflow ;
    ses nœuds finaux (sans sortie) aboutissent au nœud « nom », devenu un simple passage, dont les liens
    sortants sont conservés : les références $('nom') du workflow continuent de lire le résultat.
    """
    sub = builder()
    ph = next(n for n in w.nodes if n['name'] == nom)
    x0, y0 = ph['position']
    renomme = {n['name']: f"{n['name']} · {tag}" for n in sub['nodes'] if n['name'] not in ('Config',)}

    def remplacer(v):
        if isinstance(v, str):
            for a, b in renomme.items():
                v = v.replace(f"$('{a}')", f"$('{b}')").replace(f'$("{a}")', f'$("{b}")')
            return v
        if isinstance(v, list):
            return [remplacer(x) for x in v]
        if isinstance(v, dict):
            return {k: remplacer(x) for k, x in v.items()}
        return v

    sx = min(n['position'][0] for n in sub['nodes'])
    for n in sub['nodes']:
        if n['name'] == 'Config':
            continue
        nn = remplacer(dict(n))
        nn['name'] = renomme[n['name']]
        nn['id'] = str(uuid.uuid5(uuid.NAMESPACE_URL, w.id + nn['name']))
        nn['position'] = [x0 + n['position'][0] - sx, y0 + dy + n['position'][1]]
        if 'webhookId' in nn:
            nn['webhookId'] = str(uuid.uuid5(uuid.NAMESPACE_URL, w.id + nn['name'] + 'wh'))
        if n['name'] == 'Entrée':
            nn.update(type='n8n-nodes-base.noOp', typeVersion=1, parameters={})
        w.nodes.append(nn)
    # liens internes (Config → X devient Entrée → X)
    for src, c in sub['connections'].items():
        a = renomme['Entrée'] if src == 'Config' else renomme[src]
        for i, outs in enumerate(c['main']):
            for t in outs:
                if t['node'] == 'Config':
                    continue
                w.link(a, renomme[t['node']], i, t['index'])
    # liens entrants du placeholder → entrée du bloc
    for src, c in w.conn.items():
        for outs in c['main']:
            for t in outs:
                if t['node'] == nom:
                    t['node'] = renomme['Entrée']
    # nœuds finaux → placeholder (passage)
    sources = {s_ for s_ in sub['connections'] if s_ != 'Config'} | {'Config'}
    for n in sub['nodes']:
        if n['name'] not in sources and n['name'] not in ('Entrée',) and not n.get('disabled'):
            w.link(renomme[n['name']], nom)
    ph.update(type='n8n-nodes-base.noOp', typeVersion=1, parameters={})
    for k in ('retryOnFail', 'maxTries', 'waitBetweenTries', 'onError'):
        ph.pop(k, None)


# ------------------------------------------------------------------ fabriques de nœuds
def code(js):
    return 'n8n-nodes-base.code', 2, {'jsCode': js.strip() + '\n'}


def code_each(js):
    return 'n8n-nodes-base.code', 2, {'mode': 'runOnceForEachItem', 'jsCode': js.strip() + '\n'}


def call(wf_key):
    return 'n8n-nodes-base.executeWorkflow', 1.1, {
        'source': 'database',
        'workflowId': {'__rl': True, 'value': WF[wf_key], 'mode': 'id'},
        'mode': 'once',
        'options': {'waitForSubWorkflow': True},
    }


def if_true(expr):
    return 'n8n-nodes-base.if', 2, {
        'conditions': {
            'options': {'caseSensitive': True, 'leftValue': '', 'typeValidation': 'loose', 'version': 1},
            'conditions': [{'id': str(uuid.uuid4()), 'leftValue': '={{ ' + expr + ' }}', 'rightValue': '',
                            'operator': {'type': 'boolean', 'operation': 'true', 'singleValue': True}}],
            'combinator': 'and'},
        'options': {}}


def dt(table, operation, **p):
    params = {'resource': 'row', 'operation': operation,
              'dataTableId': {'__rl': True, 'mode': 'name', 'value': table}}
    params.update(p)
    return 'n8n-nodes-base.dataTable', 1.1, params


def dt_filter(*conds):
    return {'matchType': 'allConditions',
            'filters': {'conditions': [{'keyName': k, 'condition': 'eq', 'keyValue': v} for k, v in conds]}}


def dt_columns(mapping):
    return {'columns': {'mappingMode': 'defineBelow', 'value': mapping, 'matchingColumns': [],
                        'schema': [{'id': k, 'displayName': k, 'required': False, 'defaultMatch': False,
                                    'display': True, 'type': 'string', 'canBeUsedToMatch': True}
                                   for k in mapping]}}


def http(method, url, auth=None, query_json=None, body_json=None, binary=False, headers=None):
    p = {'method': method, 'url': url, 'options': {}}
    if auth == 'ig':
        p.update({'authentication': 'predefinedCredentialType', 'nodeCredentialType': 'instagramApi'})
    elif auth == 'pin':
        p.update({'authentication': 'genericCredentialType', 'genericAuthType': 'oAuth2Api'})
    elif auth == 'media':
        p.update({'authentication': 'genericCredentialType', 'genericAuthType': 'httpHeaderAuth'})
    elif auth == 'fb':
        p.update({'authentication': 'predefinedCredentialType', 'nodeCredentialType': 'facebookGraphApi'})
    if query_json:
        p.update({'sendQuery': True, 'specifyQuery': 'json', 'jsonQuery': query_json})
    if body_json:
        p.update({'sendBody': True, 'specifyBody': 'json', 'jsonBody': body_json})
    if binary:
        p.update({'sendBody': True, 'contentType': 'binaryData', 'inputDataFieldName': 'data'})
    return 'n8n-nodes-base.httpRequest', 4.2, p


RETRY = {'retryOnFail': True, 'maxTries': 3, 'waitBetweenTries': 5000}
SOFT = {'onError': 'continueRegularOutput'}


def telegram(text_expr, chat_expr="={{ $('Config').first().json.telegram_chat_id }}"):
    return 'n8n-nodes-base.telegram', 1.2, {
        'chatId': chat_expr, 'text': text_expr,
        'additionalFields': {'appendAttribution': False, 'parse_mode': 'HTML',
                             'disable_web_page_preview': True}}


def cred(kind):
    return {'ig': CRED_IG, 'tg': CRED_TG, 'db': CRED_DB, 'media': CRED_MEDIA,
            'pin': CRED_PIN, 'smtp': CRED_SMTP, 'fb': CRED_FB}[kind]


CONFIG_CHAT_ID = '6980427615'   # = telegram_chat_id du CONFIG (workflow Erreurs, sans nœud Config)

# Échappement HTML pour Telegram (parse_mode HTML) — réutilisé dans plusieurs Code.
JS_ESC = "const e = s => String(s ?? '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');"


# ================================================================== 1. CONFIG (un nœud « Config » par workflow)
# Plus de sous-workflow Config : chaque workflow porte son propre nœud « Config » (Code), avec seulement
# les réglages qui le concernent. Source unique : les blocs ci-dessous (un réglage commun à plusieurs
# workflows est donc à modifier dans chacun d'eux si on le change dans l'interface n8n).
CONFIG = {
    'telegram': r"""
  // --- Telegram : seul ce chat peut piloter le bot et reçoit les messages
  telegram_chat_id: '6980427615',
""",
    'instagram': r"""
  // --- Instagram via connexion Facebook : jeton de PAGE VocaBag (n'expire pas), graph.facebook.com (2026-10-04)
  ig_api: 'https://graph.facebook.com/v23.0',
  ig_user: '17841449858344452',   // id Instagram professionnel @vocabag lié à la page VocaBag
  max_carrousel: 10,          // limite actuelle de l'API (documentation Content Publishing)
  min_carrousel: 2,
  poll_max: 60,               // vérifications du statut du conteneur (x poll_attente_s)
  poll_attente_s: 5,
""",
    'media': r"""
  // --- Service média local (conversion, rendu HTML→image, hébergement public, blog)
  media_service: 'http://host.docker.internal:8791',
""",
    'carrousel': r"""
  // --- Carrousel Telegram
  ratio_policy: 'pad',        // 'pad' = image hors 4:5…1.91:1 complétée de blanc ; 'none' = envoyée telle quelle
  album_attente_s: 10,        // silence après la dernière photo d'un album avant traitement
  langue_description_defaut: 'fr',
  langues_description: ['fr', 'en', 'ar', 'es', 'de', 'it', 'pt', 'nl'],
  exclusions: { textes: 5, ctas: 3, hashtags: 3 },   // tirage : on exclut les X dernières lignes utilisées
  blog_actif: true,           // false = les carrousels ne sont plus mis en file pour le blog
  detection_langues: true,    // légende sans langue → Claude lit les images et en déduit 1 langue (ou 2 = duel)
  detection_modele: 'haiku',  // modèle Claude Code de la détection (léger : ~10 s, peu de quota)
  lien_pinterest: 'https://vocabag.com/?utm_source=pinterest&utm_medium=pin',
  pinterest: { actif: false, board_id: '', api: 'https://api.pinterest.com/v5' },   // prêt, désactivé
  mots_cles_prompt: ['prompt', '/prompt'],   // message texte → workflow « Prompt carrousel » (langue → catégorie → prompt)
""",
    'prompt': r"""
  // --- Prompt carrousel : boutons Telegram langue → catégorie → prompt ChatGPT (mots tirés de la base VocaBag)
  prompt: {
    solos: __SOLOS__,
    duels: __DUELS__,     // = images languages/<a>_<b>.png
    categories: __CATEGORIES__,   // boutons fixes (PROMPT_CATEGORIES du générateur)
    nb_mots: 10,                // par langue (duel : 10 paires = 20 mots)
    // Nom affiché sur le carrousel (avec le drapeau de Config.langues)
    noms: { ary: 'Darija marocaine', ar: 'Arabe littéraire', zh: 'Chinois (mandarin)', en: 'Anglais', de: 'Allemand',
            es: 'Espagnol', pt: 'Portugais (Brésil)', it: 'Italien', nl: 'Néerlandais', ru: 'Russe', tr: 'Turc',
            ko: 'Coréen' },
    // Fin de la zone « Catégorie : » (solo) : « 🇲🇦 Les animaux en darija »
    en: { ary: 'en darija', ar: 'en arabe littéraire', zh: 'en chinois', en: 'en anglais', de: 'en allemand',
          es: 'en espagnol', pt: 'en portugais', it: 'en italien', nl: 'en néerlandais', ru: 'en russe', tr: 'en turc',
          ko: 'en coréen' },
    // Appellation de la liste par catégorie (slug) ; sinon le nom de la catégorie sur le site
    titres: {
      greetings: 'Les salutations indispensables', basics: 'Les expressions de base', travel: 'Les mots du voyage',
      food: 'À table ! Les mots de la cuisine', daily_life: 'Les mots du quotidien', family: 'La famille & les proches',
      numbers_time: 'Chiffres & temps', colors_desc: 'Couleurs & descriptions', health_body: 'Le corps & la santé',
      market_shopping: 'Au marché', work_studies: 'Travail & études', emotions: 'Exprimer ses émotions',
      religion_culture: 'Religion & culture', transport: 'Se déplacer', technology: 'Technologie & Internet',
      home_interior: 'À la maison', clothing: 'Les vêtements', weather_nature: 'Météo & nature',
      animals: 'Les animaux', sports_leisure: 'Sports & loisirs', money_banking: 'Argent & banque',
    },
  },
""",
    'stories': r"""
  // --- Stories : heure (Europe/Paris, 'HH') → action. Le Reel sort vers 15h15 (Vocabag Video, lancé à 15h) :
  //     les stories suivent, dans la/les langue(s) du Reel, avec un mot (ou une paire, en duel) tiré du Reel.
  story_creneaux: { '16': 'reel', '18': 'question', '21': 'reponse' },
  story_forcer_action: '',    // test : 'question' | 'reponse' | 'reel' (ignore l'heure). Remettre '' après.
  exclusions: { story_mots: 60 },   // les 60 derniers mots ne reviennent pas
  story_langues: [            // langues des questions en story, tirées au sort (poids)
    { code: 'ary', poids: 25 }, { code: 'ar', poids: 15 }, { code: 'zh', poids: 10 },
    { code: 'en', poids: 8 }, { code: 'es', poids: 8 }, { code: 'de', poids: 7 }, { code: 'ko', poids: 7 },
    { code: 'it', poids: 5 }, { code: 'pt', poids: 5 }, { code: 'tr', poids: 4 }, { code: 'ru', poids: 3 },
    { code: 'nl', poids: 3 },
  ],
""",
    'newsletter': r"""
  // --- Newsletter hebdo (abonnés : table newsletter_subscribers de vocabag.com). Jour et heure : déclencheur
  //     « Chaque dimanche ». Rien n'est envoyé s'il n'y a ni nouvel article ni vidéo sur la période.
  newsletter: {
    expediteur: 'VocaBag <contact.vocabag@gmail.com>',
    email_test: 'contact.secbec@gmail.com',   // seul destinataire du déclencheur « Test »
    jours: 7,                   // période couverte (articles et vidéos)
    max_videos: 7,
    site: 'https://vocabag.com',
    desinscription: 'https://vocabag.com/unsubscribe.php?token=',
  },
""",
    'blog': r"""
  // --- Blog : un article par carrousel publié, rédigé chaque soir par Claude Code (abonnement, sans API)
  //     puis validé sur Telegram. L'heure de la revue est dans le déclencheur « Chaque soir ».
  blog: {
    email: 'contact.secbec@gmail.com',   // reçoit le brouillon complet
    email_expediteur: 'VocaBag Blog <contact.vocabag@gmail.com>',
    max_par_soir: 5,
    modele: '',                   // '' = modèle par défaut de Claude Code ; ex. 'sonnet' pour économiser le quota
    webhook_pret: 'http://localhost:5678/webhook/vb-blog-pret',   // appelé par le rédacteur (hôte)
  },
""",
    'langues': r"""
  // --- Langues apprises : code VocaBag ⇄ noms acceptés dans la légende Telegram / les tables
  langues: {
    ary: { nom: 'darija',            drapeau: '🇲🇦', alias: ['ary', 'darija', 'marocain', 'moroccan'] },
    ar:  { nom: 'arabe littéraire',  drapeau: '🇸🇦', alias: ['ar', 'arabe', 'arabic', 'msa', 'fusha'] },
    zh:  { nom: 'chinois',           drapeau: '🇨🇳', alias: ['zh', 'chinois', 'chinese', 'mandarin'] },
    en:  { nom: 'anglais',           drapeau: '🇬🇧', alias: ['en', 'anglais', 'english'] },
    de:  { nom: 'allemand',          drapeau: '🇩🇪', alias: ['de', 'allemand', 'german'] },
    es:  { nom: 'espagnol',          drapeau: '🇪🇸', alias: ['es', 'espagnol', 'spanish'] },
    pt:  { nom: 'portugais',         drapeau: '🇧🇷', alias: ['pt', 'portugais', 'portuguese'] },
    it:  { nom: 'italien',           drapeau: '🇮🇹', alias: ['it', 'italien', 'italian'] },
    nl:  { nom: 'néerlandais',       drapeau: '🇳🇱', alias: ['nl', 'neerlandais', 'néerlandais', 'dutch'] },
    ru:  { nom: 'russe',             drapeau: '🇷🇺', alias: ['ru', 'russe', 'russian'] },
    tr:  { nom: 'turc',              drapeau: '🇹🇷', alias: ['tr', 'turc', 'turkish'] },
    ko:  { nom: 'coréen',            drapeau: '🇰🇷', alias: ['ko', 'coreen', 'coréen', 'korean'] },
  },
""",
}


def config_node(w, pos, *sections):
    """Nœud « Config » du workflow : réglages des sections demandées (voir CONFIG)."""
    corps = ''.join(CONFIG[k] for k in sections)
    if 'prompt' in sections:   # listes fixes des boutons (constantes PROMPT_* plus bas)
        slugs = dict(PROMPT_SLUGS)
        corps = (corps.replace('__SOLOS__', json.dumps([c for c, _ in PROMPT_SOLOS]))
                 .replace('__DUELS__', json.dumps([c for c, _ in PROMPT_DUELS]))
                 .replace('__CATEGORIES__', json.dumps([{'id': i, 'icon': ic, 'nom': n, 'slug': slugs[i]}
                                                        for i, ic, n in PROMPT_CATEGORIES], ensure_ascii=False)))
    js = ("// CONFIGURATION de ce workflow — modifier ici. Les secrets restent dans les credentials n8n.\n"
          "return [{ json: {" + corps + "} }];")
    return w.add('Config', *code(js), pos)


# Normalisation « darija » → « ary » (utilisée dans plusieurs Code).
JS_NORM = r"""
const normLangue = (cfg, v) => {
  const s = String(v ?? '').trim().toLowerCase();
  if (!s) return '';
  for (const [code, l] of Object.entries(cfg.langues)) if (code === s || l.alias.includes(s)) return code;
  return null; // inconnue
};"""


# ================================================================== 2. TIRER DESCRIPTION
def wf_descr():
    w = W('descr', 'VocaBag Social - Tirer description')
    w.add('Entrée', 'n8n-nodes-base.executeWorkflowTrigger', 1, {}, [0, 0])
    w.add('Config', 'n8n-nodes-base.noOp', 1, {}, [220, 0])   # remplacé par le Config du workflow hôte
    lire = dict(returnAll=True, options={})
    w.add('Lire textes', *dt('vb_textes', 'get', **lire), [440, 0], executeOnce=True, alwaysOutputData=True)
    w.add('Lire CTA', *dt('vb_ctas', 'get', **lire), [660, 0], executeOnce=True, alwaysOutputData=True)
    w.add('Lire hashtags', *dt('vb_hashtags', 'get', **lire), [880, 0], executeOnce=True, alwaysOutputData=True)
    w.add('Tirer', *code(JS_NORM + r"""
// Tirage aléatoire anti-répétition (règles de la spec) :
//  - lignes de la langue de description ; parmi elles celles de la langue apprise si renseignée,
//    sinon repli sur les lignes génériques (langue_apprise vide) ;
//  - on exclut les X lignes utilisées le plus récemment (en gardant au moins 1 candidate).
const req = $('Entrée').first().json;
const cfg = $('Config').first().json;
const lang = String(req.langue_description || cfg.langue_description_defaut).toLowerCase();
// Duel (2 langues, comme « Arabe vs Darija » dans Vocabag Video) : titre « A vs B », texte des lignes
// langue_apprise = « duel » (sinon génériques), hashtags des DEUX langues réunis + #comparaisondelangues.
const apprs = [...new Set((req.langues_apprises?.length ? req.langues_apprises : [req.langue_apprise])
  .map(v => normLangue(cfg, v)).filter(Boolean))].slice(0, 2);
const duel = apprs.length === 2;
const appr = apprs[0] || '';
const rows = noeud => noeud.all().map(i => i.json).filter(r => r && r.id !== undefined);

// Colonne facultative « format » (vb_textes) : vide = tout format, sinon « post » (image seule) ou « carrousel ».
const typePub = String(req.type || '').trim().toLowerCase();
const bonFormat = r => { const f = String(r.format ?? '').trim().toLowerCase(); return !f || f === typePub; };

function tirer(lignes, X, avecLangueApprise, cible = appr) {
  const L = lignes.filter(r => String(r.langue_description || '').trim().toLowerCase() === lang && bonFormat(r));
  let c = [];
  if (avecLangueApprise && cible === 'duel') c = L.filter(r => String(r.langue_apprise || '').trim().toLowerCase() === 'duel');
  else if (avecLangueApprise && cible) c = L.filter(r => normLangue(cfg, r.langue_apprise) === cible);
  if (!c.length) c = avecLangueApprise ? L.filter(r => !String(r.langue_apprise || '').trim()) : L;
  if (!c.length) return null;
  const recents = [...c].filter(r => r.derniere_utilisation)
    .sort((a, b) => String(b.derniere_utilisation).localeCompare(String(a.derniere_utilisation)))
    .slice(0, Math.min(X, c.length - 1)).map(r => r.id);
  const pool = c.filter(r => !recents.includes(r.id));
  return pool[Math.floor(Math.random() * pool.length)];
}

const perso = String(req.desc_perso || '').trim();
const texte = perso ? null : tirer(rows($('Lire textes')), cfg.exclusions.textes, true, duel ? 'duel' : appr);
const cta = tirer(rows($('Lire CTA')), cfg.exclusions.ctas, false);
const tags = tirer(rows($('Lire hashtags')), cfg.exclusions.hashtags, true);
const tagsB = duel ? tirer(rows($('Lire hashtags')), cfg.exclusions.hashtags, true, apprs[1]) : null;

const manque = [];
if (!perso && !texte) manque.push('textes');
if (!cta) manque.push('ctas');
if (!tags) manque.push('hashtags');
if (manque.length) {
  return [{ json: { ok: false, erreur: `aucune ligne « ${lang} »${appr ? ' / ' + appr : ''} dans : ${manque.join(', ')}`,
                    texte_id: -1, cta_id: -1, hashtags_id: -1 } }];
}
// Instagram : 30 hashtags max, on tronque proprement.
const brutTags = [tags, tagsB].filter(Boolean).map(t => String(t.hashtags)).join(' ') + (duel ? ' #comparaisondelangues' : '');
const hashtags = [...new Set(brutTags.match(/#[^\s#]+/g) || [])].slice(0, 30).join(' ');
let titre = '';
if (duel && !perso) {
  const [a, b] = apprs.map(c => cfg.langues[c]);
  const nom = l => l.nom.charAt(0).toUpperCase() + l.nom.slice(1);
  titre = lang === 'fr' ? `${nom(a)} vs ${nom(b)} ${a.drapeau}${b.drapeau}` : `${a.drapeau} vs ${b.drapeau}`;
}
// Aucune invitation à faire défiler (« Swipe 👉 ») : retirée des textes tirés, carrousel comme image seule (2026-09-28).
const sansSwipe = t => t.replace(/[ \t]*\b(swipe|glisse|fais défiler)\b[^.!?\n]*[.!?]?[ \t]*(👉)?/gi, '')
  .split('\n').map(l => l.trimEnd()).filter((l, i, arr) => l || (i > 0 && arr[i - 1])).join('\n').trim();
let corps = perso || String(texte.texte).trim();
if (!perso) corps = sansSwipe(corps) || corps;
const caption = [titre, corps, String(cta.texte).trim(), hashtags].filter(Boolean).join('\n\n');
return [{ json: {
  ok: true, caption,
  texte_id: texte ? texte.id : -1, cta_id: cta.id, hashtags_id: tags.id,
  desc_perso: !!perso, langue_description: lang, langue_apprise: apprs.join('+'), duel,
  maintenant: new Date().toISOString(),
} }];
"""), [1100, 0])
    maj = lambda champ: dict(**dt_filter(('id', "={{ $('Tirer').first().json." + champ + " }}")),
                              **dt_columns({'derniere_utilisation': "={{ $('Tirer').first().json.maintenant }}"}),
                              options={})
    w.add('Tirage OK ?', *if_true("$json.ok"), [1320, 0])
    w.add('Marquer texte', *dt('vb_textes', 'update', **maj('texte_id')), [1540, -100], executeOnce=True, alwaysOutputData=True)
    w.add('Marquer CTA', *dt('vb_ctas', 'update', **maj('cta_id')), [1760, -100], executeOnce=True, alwaysOutputData=True)
    w.add('Marquer hashtags', *dt('vb_hashtags', 'update', **maj('hashtags_id')), [1980, -100], executeOnce=True, alwaysOutputData=True)
    w.add('Retour', *code("return [{ json: $('Tirer').first().json }];"), [2200, 0])
    w.chain('Entrée', 'Config', 'Lire textes', 'Lire CTA', 'Lire hashtags', 'Tirer', 'Tirage OK ?')
    w.link('Tirage OK ?', 'Marquer texte', 0)
    w.chain('Marquer texte', 'Marquer CTA', 'Marquer hashtags', 'Retour')
    w.link('Tirage OK ?', 'Retour', 1)
    return w.dump()


# ================================================================== 3. PUBLIER INSTAGRAM
JOURNAL_COLS = ['plateforme', 'type', 'statut', 'post_id', 'permalink', 'langue_description', 'langue_apprise',
                'texte_id', 'cta_id', 'hashtags_id', 'source', 'source_ref', 'erreur', 'date_publication']


def journal_row_js(plateforme, statut, post_id_expr, permalink_expr, erreur_expr):
    return f"""
const req = $('Entrée').first().json;
const d = req.desc_ids || {{}};
const s = v => (v === undefined || v === null) ? '' : String(v);
return [{{ json: {{
  plateforme: '{plateforme}', type: s(req.type), statut: '{statut}',
  post_id: s({post_id_expr}), permalink: s({permalink_expr}),
  langue_description: s(req.langue_description), langue_apprise: s(req.langue_apprise),
  texte_id: s(d.texte_id), cta_id: s(d.cta_id), hashtags_id: s(d.hashtags_id),
  source: s(req.source), source_ref: s(req.source_ref), erreur: s({erreur_expr}).slice(0, 900),
  date_publication: new Date().toISOString(),
}} }}];"""


def journal_insert():
    return dt('vb_journal', 'insert', **dt_columns({c: '={{ $json.' + c + ' }}' for c in JOURNAL_COLS}), options={})


def wf_ig():
    w = W('ig', 'VocaBag Social - Publier Instagram')
    w.add('Entrée', 'n8n-nodes-base.executeWorkflowTrigger', 1, {}, [0, 0])
    w.add('Config', 'n8n-nodes-base.noOp', 1, {}, [220, 0])   # remplacé par le Config du workflow hôte
    w.add('Préparer conteneurs', *code(r"""
// Format commun : { type: reel|carrousel|story|post, images[], video, texte, langue_description,
//                   langue_apprise, source, source_ref, desc_ids }  →  un conteneur par média.
const cfg = $('Config').first().json;
const req = $('Entrée').first().json;
const type = String(req.type || '').toLowerCase();
const images = (req.images || []).filter(Boolean);
const caption = String(req.texte || '');
const fail = m => [{ json: { _ok: false, erreur: m } }];
let items = [];
if (type === 'carrousel') {
  if (images.length < cfg.min_carrousel) return fail(`carrousel : ${images.length} image(s), minimum ${cfg.min_carrousel}`);
  if (images.length > cfg.max_carrousel) return fail(`carrousel : ${images.length} images, maximum de l'API ${cfg.max_carrousel}`);
  items = images.map(u => ({ image_url: u, is_carousel_item: true }));
} else if (type === 'post') {
  if (images.length !== 1) return fail('post : exactement 1 image attendue');
  items = [{ image_url: images[0], caption }];
} else if (type === 'story') {
  if (req.video) items = [{ media_type: 'STORIES', video_url: req.video }];
  else if (images.length === 1) items = [{ media_type: 'STORIES', image_url: images[0] }];
  else return fail('story : 1 image ou 1 vidéo attendue');
} else if (type === 'reel') {
  if (!req.video) return fail('reel : vidéo manquante');
  items = [{ media_type: 'REELS', video_url: req.video, caption }];
} else return fail(`type inconnu : « ${type} »`);
if (caption.length > 2200) return fail(`légende trop longue (${caption.length}/2200 caractères)`);
const nTags = (caption.match(/#[^\s#]+/g) || []).length;
if (nTags > 30) return fail(`${nTags} hashtags (Instagram : 30 max)`);
return items.map(params => ({ json: { _ok: true, params } }));
"""), [440, 0])
    w.add('Entrée valide ?', *if_true('$json._ok'), [660, 0])
    ig = "={{ $('Config').first().json.ig_api }}"
    w.add('Créer conteneur', *http('POST', ig + "/{{ $('Config').first().json.ig_user }}/media", auth='ig',
                                   query_json='={{ JSON.stringify($json.params) }}'),
          [880, -100], credentials=cred('ig'), **RETRY, **SOFT)
    w.add('Collecter conteneurs', *code(r"""
const req = $('Entrée').first().json;
const ids = [], errs = [];
for (const it of $input.all()) {
  if (it.json.id) ids.push(String(it.json.id));
  else errs.push([it.json.error?.message, it.json.error?.description].filter(Boolean).join(' — ') || JSON.stringify(it.json).slice(0, 300));
}
if (errs.length) return [{ json: { _ok: false, erreur: 'création du conteneur : ' + errs.join(' | ') } }];
return [{ json: { _ok: true, ids, carrousel: String(req.type).toLowerCase() === 'carrousel' } }];
"""), [1100, -100])
    w.add('Conteneurs OK ?', *if_true('$json._ok'), [1320, -100])
    w.add('Carrousel ?', *if_true('$json.carrousel'), [1540, -200])
    w.add('Créer carrousel', *http('POST', ig + "/{{ $('Config').first().json.ig_user }}/media", auth='ig', query_json=(
        "={{ JSON.stringify({ media_type: 'CAROUSEL', children: $json.ids.join(','), "
        "caption: String($('Entrée').first().json.texte || '') }) }}")),
          [1760, -300], credentials=cred('ig'), **RETRY, **SOFT)
    w.add('Cible', *code(r"""
// Conteneur à publier : le carrousel parent, ou le conteneur unique (post / story / reel).
const j = $json;
if (j.ids) return [{ json: { _ok: true, creation_id: j.ids[0] } }];
if (j.id) return [{ json: { _ok: true, creation_id: String(j.id) } }];
return [{ json: { _ok: false, erreur: 'création du carrousel : ' + ([j.error?.message, j.error?.description].filter(Boolean).join(' — ') || JSON.stringify(j).slice(0, 300)) } }];
"""), [1980, -200])
    w.add('Cible OK ?', *if_true('$json._ok'), [2200, -200])
    w.add('Statut conteneur', *http('GET', ig + "/{{ $('Cible').first().json.creation_id }}", auth='ig',
                                    query_json="={{ JSON.stringify({ fields: 'status_code,status' }) }}"),
          [2420, -300], credentials=cred('ig'), **RETRY, **SOFT)
    w.add('Évaluer statut', *code(r"""
// FINISHED → publier ; ERROR/EXPIRED → échec ; sinon on réessaie (garde : poll_max vérifications).
const cfg = $('Config').first().json;
const s = $json.status_code;
if (s === 'FINISHED') return [{ json: { etat: 'pret' } }];
if (s === 'ERROR' || s === 'EXPIRED') return [{ json: { etat: 'echec', erreur: `conteneur ${s} : ${$json.status || ''}` } }];
if ($runIndex + 1 >= cfg.poll_max) return [{ json: { etat: 'echec', erreur: `conteneur toujours « ${s || $json.error?.message || '?'} » après ${$runIndex + 1} vérifications` } }];
return [{ json: { etat: 'attente' } }];
"""), [2640, -300])
    w.add('Prêt ?', *if_true("$json.etat === 'pret'"), [2860, -300])
    w.add('En attente ?', *if_true("$json.etat === 'attente'"), [3080, -200])
    w.add('Attendre', 'n8n-nodes-base.wait', 1.1,
          {'amount': "={{ $('Config').first().json.poll_attente_s }}", 'unit': 'seconds'}, [3300, -100],
          webhookId=str(uuid.uuid5(uuid.NAMESPACE_URL, 'vb-ig-wait')))
    w.add('Publier', *http('POST', ig + "/{{ $('Config').first().json.ig_user }}/media_publish", auth='ig',
                           query_json="={{ JSON.stringify({ creation_id: $('Cible').first().json.creation_id }) }}"),
          [3080, -400], credentials=cred('ig'), **RETRY, **SOFT)
    w.add('Publié ?', *if_true('!!$json.id'), [3300, -400])
    w.add('Permalien', *http('GET', ig + '/{{ $json.id }}', auth='ig',
                             query_json="={{ JSON.stringify({ fields: 'permalink,media_type' }) }}"),
          [3520, -500], credentials=cred('ig'), **RETRY, **SOFT)
    w.add('Ligne journal (succès)', *code(journal_row_js(
        'instagram', 'ok', "$('Publier').first().json.id", '$json.permalink', "''")), [3740, -500])
    w.add('Journal succès', *journal_insert(), [3960, -500], **SOFT)
    w.add('Retour succès', *code(r"""
const pub = $('Publier').first().json;
return [{ json: { ok: true, plateforme: 'instagram', post_id: String(pub.id),
                  permalink: String($('Permalien').first().json.permalink || '') } }];
"""), [4180, -500])
    w.add('Échec', *code(r"""
// Toutes les branches d'erreur arrivent ici.
const j = $json;
const erreur = j.erreur || [j.error?.message, j.error?.description].filter(Boolean).join(' — ') || JSON.stringify(j).slice(0, 400);
return [{ json: { erreur } }];
"""), [3300, 200])
    w.add('Ligne journal (échec)', *code(journal_row_js('instagram', 'echec', "''", "''", '$json.erreur')), [3520, 200])
    w.add('Journal échec', *journal_insert(), [3740, 200], **SOFT)
    w.add('Retour échec', *code(
        "return [{ json: { ok: false, plateforme: 'instagram', erreur: $('Échec').first().json.erreur } }];"),
          [3960, 200])

    w.chain('Entrée', 'Config', 'Préparer conteneurs', 'Entrée valide ?')
    w.link('Entrée valide ?', 'Créer conteneur', 0)
    w.link('Entrée valide ?', 'Échec', 1)
    w.chain('Créer conteneur', 'Collecter conteneurs', 'Conteneurs OK ?')
    w.link('Conteneurs OK ?', 'Carrousel ?', 0)
    w.link('Conteneurs OK ?', 'Échec', 1)
    w.link('Carrousel ?', 'Créer carrousel', 0)
    w.link('Carrousel ?', 'Cible', 1)
    w.link('Créer carrousel', 'Cible')
    w.link('Cible', 'Cible OK ?')
    w.link('Cible OK ?', 'Statut conteneur', 0)
    w.link('Cible OK ?', 'Échec', 1)
    w.chain('Statut conteneur', 'Évaluer statut', 'Prêt ?')
    w.link('Prêt ?', 'Publier', 0)
    w.link('Prêt ?', 'En attente ?', 1)
    w.link('En attente ?', 'Attendre', 0)
    w.link('En attente ?', 'Échec', 1)
    w.link('Attendre', 'Statut conteneur')
    w.link('Publier', 'Publié ?')
    w.link('Publié ?', 'Permalien', 0)
    w.link('Publié ?', 'Échec', 1)
    w.chain('Permalien', 'Ligne journal (succès)', 'Journal succès', 'Retour succès')
    w.chain('Échec', 'Ligne journal (échec)', 'Journal échec', 'Retour échec')
    return w.dump()


# ================================================================== 4. PUBLIER PINTEREST (désactivé)
def wf_pin():
    w = W('pin', 'VocaBag Social - Publier Pinterest')
    w.add('Entrée', 'n8n-nodes-base.executeWorkflowTrigger', 1, {}, [0, 0])
    w.add('Config', 'n8n-nodes-base.noOp', 1, {}, [220, 0])   # remplacé par le Config du workflow hôte
    w.add('Préparer épingles', *code(r"""
// Adaptation Pinterest du format commun : une épingle par image (carrousel/post),
// lien vers vocabag.com avec UTM Pinterest. Stories et Reels : pas publiés ici.
const cfg = $('Config').first().json;
const req = $('Entrée').first().json;
if (!cfg.pinterest.actif) return [{ json: { _ok: false, ignore: true, raison: 'Pinterest désactivé (Config → pinterest.actif)' } }];
const type = String(req.type || '').toLowerCase();
if (!['carrousel', 'post'].includes(type)) return [{ json: { _ok: false, ignore: true, raison: `type « ${type} » non publié sur Pinterest` } }];
if (!cfg.pinterest.board_id) return [{ json: { _ok: false, erreur: 'pinterest.board_id manquant dans Config' } }];
const texte = String(req.texte || '');
const titre = texte.split('\n')[0].replace(/#[^\s#]+/g, '').trim().slice(0, 100) || 'VocaBag';
const lien = cfg.lien_pinterest + '&utm_campaign=' + encodeURIComponent(req.source_ref || type);
return (req.images || []).map((url, i) => ({ json: { _ok: true, body: {
  board_id: cfg.pinterest.board_id, title: titre, description: texte.slice(0, 500), link: lien,
  alt_text: titre, media_source: { source_type: 'image_url', url },
} } }));
"""), [440, 0])
    w.add('Épingle à publier ?', *if_true('$json._ok'), [660, 0])
    w.add('Créer épingle', *http('POST', "={{ $('Config').first().json.pinterest.api }}/pins", auth='pin',
                                 body_json='={{ JSON.stringify($json.body) }}'),
          [880, -100], **RETRY, **SOFT, credentials=cred('pin'))
    w.add('Retour', *code(r"""
const r = $input.all().map(i => i.json);
const first = $('Préparer épingles').first().json;
if (first.ignore) return [{ json: { ok: false, ignore: true, raison: first.raison } }];
const ok = r.filter(j => j.id).map(j => String(j.id));
return [{ json: { ok: ok.length > 0, plateforme: 'pinterest', pins: ok,
                  erreur: ok.length ? '' : (first.erreur || 'aucune épingle créée') } }];
"""), [1100, 0])
    w.chain('Entrée', 'Config', 'Préparer épingles', 'Épingle à publier ?')
    w.link('Épingle à publier ?', 'Créer épingle', 0)
    w.link('Épingle à publier ?', 'Retour', 1)
    w.link('Créer épingle', 'Retour')
    # Nœud « Créer épingle » : credential OAuth2 générique « Pinterest - vocabag » (scopes boards:read,
    # pins:read, pins:write). Un seul tableau : pinterest.board_id (« Vocabulaire VocaBag »).
    return w.dump()


# ================================================================== 5. CARROUSEL TELEGRAM
def wf_carrousel():
    w = W('carrousel', 'VocaBag Social - Carrousel Telegram')
    w.add('Telegram', 'n8n-nodes-base.telegramTrigger', 1.2,
          {'updates': ['message', 'callback_query'], 'additionalFields': {}}, [0, 0], credentials=cred('tg'),
          webhookId=str(uuid.uuid5(uuid.NAMESPACE_URL, 'vb-carrousel-tg')))
    config_node(w, [220, 0], 'telegram', 'instagram', 'media', 'carrousel', 'langues')
    w.add('Filtrer message', *code(r"""
// Seul le chat configuré est accepté ; tout autre expéditeur est ignoré sans réponse.
const cfg = $('Config').first().json;
// Boutons des brouillons de blog (« blog:pub|rej|redo:<id> ») → sous-workflow « Blog Décision ».
const cq = $('Telegram').first().json.callback_query;
if (cq) {
  if (String(cq.message?.chat?.id) !== String(cfg.telegram_chat_id)) return [];
  // Boutons du prompt carrousel : « cp[n]:l|c|b[:sel[:cat]] » (n = répondre par un nouveau message).
  const p = /^cp(n?):([lcb])(?::([a-z]{2,3}(?:_[a-z]{2,3})?))?(?::(\d{1,3}))?$/.exec(cq.data || '');
  if (p) return [{ json: { action: 'prompt', etape: { l: 'categorie', c: 'prompt', b: 'langue' }[p[2]],
                           sel: p[3] || '', cat: Number(p[4] || 0), nouveau: p[1] === 'n', callback_query_id: cq.id,
                           message_id: cq.message.message_id } }];
  const b =/^blog:(pub|rej|redo):(c\d{8}-[0-9a-f]{6})$/.exec(cq.data || '');
  if (!b) return [];
  return [{ json: { action: 'blog', decision: b[1], id: b[2], callback_query_id: cq.id,
                    chat_id: String(cq.message.chat.id), message_id: cq.message.message_id } }];
}
const m = $('Telegram').first().json.message || {};
if (String(m.chat?.id) !== String(cfg.telegram_chat_id)) return [];
if (cfg.mots_cles_prompt.includes(String(m.text || '').trim().toLowerCase()))
  return [{ json: { action: 'prompt', etape: 'langue', sel: '', cat: 0, nouveau: true, callback_query_id: '', message_id: 0 } }];
let file_id = null, kind = null;
if (m.photo?.length) {            // la plus grande résolution proposée par Telegram
  file_id = [...m.photo].sort((a, b) => b.width * b.height - a.width * a.height)[0].file_id; kind = 'photo';
} else if (m.document && /^image\//.test(m.document.mime_type || '')) {   // envoyé « en fichier » : qualité d'origine
  file_id = m.document.file_id; kind = 'document';
}
if (!file_id) return [{ json: { action: 'aide' } }];
return [{ json: {
  action: 'image', message_id: m.message_id, media_group_id: m.media_group_id ? String(m.media_group_id) : '',
  file_id, kind, caption: m.caption || '', recu_le: new Date().toISOString(),
} }];
"""), [440, 0])
    w.add('Bouton blog ?', *if_true("$json.action === 'blog'"), [550, 0])
    w.add('Décision blog', *call('blog'), [770, -350], **SOFT)
    w.add('Prompt ?', *if_true("$json.action === 'prompt'"), [605, 200])
    w.add('Prompt carrousel', *call('prompt'), [770, 350], **SOFT)
    w.add('Image ?', *if_true("$json.action === 'image'"), [660, 0])
    w.add('Aide', *telegram(
        "=📸 Envoie 1 photo (post) ou un album de 2 à {{ $('Config').first().json.max_carrousel }} photos (carrousel).\n"
        "Légende du 1er message :\n<code>fr darija</code> (langue de la description + langue apprise, défaut : fr)\n"
        "<code>ar vs darija</code> ou <code>fr ar vs darija</code> : duel de deux langues\n"
        "Sans langue apprise : je la déduis des images.\n"
        "<code>desc: ton texte</code> pour imposer la description (CTA et hashtags restent tirés).\n"
        "Astuce : envoie les images « en fichier » pour garder la qualité d'origine.\n\n"
        "✍️ <code>prompt</code> : prompt ChatGPT pour créer un carrousel (langue → catégorie → 10 mots)."),
          [880, 150], credentials=cred('tg'))
    w.add('Album ?', *if_true("$json.media_group_id !== ''"), [880, -100])
    # --- album : tampon + attente du silence
    tampon_cols = {'media_group_id': '={{ $json.media_group_id }}', 'message_id': '={{ $json.message_id }}',
                   'file_id': '={{ $json.file_id }}', 'kind': '={{ $json.kind }}',
                   'caption': '={{ $json.caption }}', 'recu_le': '={{ $json.recu_le }}'}
    w.add('Mettre en tampon', *dt('vb_tampon_album', 'insert', **dt_columns(tampon_cols), options={}), [1100, -200])
    w.add("Attendre fin d'album", 'n8n-nodes-base.wait', 1.1,
          {'amount': "={{ $('Config').first().json.album_attente_s }}", 'unit': 'seconds'}, [1320, -200],
          webhookId=str(uuid.uuid5(uuid.NAMESPACE_URL, 'vb-album-wait')))
    w.add('Lire album', *dt('vb_tampon_album', 'get', returnAll=True,
                            **dt_filter(('media_group_id', "={{ $('Filtrer message').first().json.media_group_id }}")),
                            options={}), [1540, -200], executeOnce=True, alwaysOutputData=True)
    w.add('Dernière photo ?', *code(r"""
// Chaque photo de l'album a déclenché sa propre exécution. Seule celle de la DERNIÈRE photo reçue
// traite l'album (les autres s'arrêtent) ; comme elle a attendu album_attente_s après son arrivée,
// l'album est complet.
const moi = $('Filtrer message').first().json;
const rows = $input.all().map(i => i.json).filter(r => r.file_id)
  .sort((a, b) => Number(a.message_id) - Number(b.message_id));
if (!rows.length) return [];
if (Number(rows[rows.length - 1].message_id) !== Number(moi.message_id)) return [];
const vus = new Set();
const images = rows.filter(r => !vus.has(r.file_id) && vus.add(r.file_id))
  .map(r => ({ file_id: r.file_id, kind: r.kind, message_id: Number(r.message_id) }));
return [{ json: { images, caption: (rows.find(r => String(r.caption || '').trim()) || {}).caption || '',
                  media_group_id: moi.media_group_id, source_ref: 'tg-album-' + moi.media_group_id } }];
"""), [1760, -200])
    w.add('Photo seule', *code(r"""
const m = $('Filtrer message').first().json;
return [{ json: { images: [{ file_id: m.file_id, kind: m.kind, message_id: m.message_id }], caption: m.caption,
                  media_group_id: '', source_ref: 'tg-msg-' + m.message_id } }];
"""), [1320, 0])
    w.add('Analyser légende', *code(JS_NORM + r"""
// 1re ligne non vide : « langue_description langue_apprise » (ex. « fr darija », « en chinois »),
// ou un DUEL de deux langues avec « vs » (ou / ou +) : « ar vs darija », « fr ar vs darija »,
// comme le genre « duel » de Vocabag Video. Sans « vs », « ar darija » = description en arabe + darija.
// Une ligne « desc: … » (et tout ce qui suit) remplace le texte tiré de la table.
const cfg = $('Config').first().json;
const d = $json;
const lignes = String(d.caption || '').split(/\r?\n/);
const iDesc = lignes.findIndex(l => /^\s*desc\s*:/i.test(l));
const desc_perso = iDesc >= 0 ? [lignes[iDesc].replace(/^\s*desc\s*:/i, ''), ...lignes.slice(iDesc + 1)].join('\n').trim() : '';
const params = (iDesc >= 0 ? lignes.slice(0, iDesc) : lignes).map(l => l.trim()).find(Boolean) || '';
const mots = params.toLowerCase().replace(/\s*[\/+]\s*/g, ' vs ').split(/\s+/).filter(Boolean);
const avert = [];
let langue_description = cfg.langue_description_defaut;
const bruts = [];
const iVs = mots.findIndex(m => m === 'vs' || m === 'versus');
if (iVs >= 0) {
  const gauche = mots.slice(0, iVs), droite = mots.slice(iVs + 1);
  if (gauche.length >= 2 && cfg.langues_description.includes(gauche[0])) langue_description = gauche.shift();
  bruts.push(gauche.join(' '), droite.join(' '));
} else {
  if (mots.length >= 2 && cfg.langues_description.includes(mots[0])) langue_description = mots.shift();
  // « fr » seul : langue de description (pas une langue apprise) → langue apprise à déduire des images
  else if (mots.length === 1 && cfg.langues_description.includes(mots[0]) && !normLangue(cfg, mots[0])) langue_description = mots.shift();
  if (mots.length) bruts.push(mots.join(' '));
}
const langues_apprises = [];
for (const brut of bruts) {
  const code = brut ? normLangue(cfg, brut) : null;
  if (code && !langues_apprises.includes(code)) langues_apprises.push(code);
  else if (!code) avert.push(`langue apprise « ${brut || '(vide)'} » inconnue → ignorée`);
}
if (bruts.length === 2 && langues_apprises.length < 2) avert.push('duel incomplet → description pour une seule langue');
const langue_apprise = langues_apprises[0] || '';
const n = d.images.length;
const type = n === 1 ? 'post' : 'carrousel';
const refus = n > cfg.max_carrousel ? `${n} images reçues : l'API Instagram accepte ${cfg.max_carrousel} images maximum par carrousel. Rien n'a été publié.` : '';
return [{ json: { ...d, type, langue_description, langue_apprise, langues_apprises, desc_perso, avertissements: avert, refus } }];
"""), [1980, 0])
    w.add('Nombre OK ?', *if_true("!$json.refus"), [2200, 0])
    w.add('Refus', *telegram("=⚠️ {{ $json.refus }}"), [2420, 200], credentials=cred('tg'))
    w.add('Déjà publié ?', *dt('vb_journal', 'get', returnAll=True,
                               **dt_filter(('source_ref', '={{ $json.source_ref }}'), ('statut', 'ok')),
                               options={}), [2420, -100], executeOnce=True, alwaysOutputData=True)
    w.add('Une ligne par image', *code(r"""
// Anti-doublon : un album / message déjà publié n'est jamais republié.
if ($input.all().some(i => i.json.post_id)) return [];
const a = $('Analyser légende').first().json;
return a.images.map((img, i) => ({ json: { ...img, idx: i } }));
"""), [2640, -100])
    w.add('Télécharger image', 'n8n-nodes-base.telegram', 1.2,
          {'resource': 'file', 'operation': 'get', 'fileId': '={{ $json.file_id }}', 'download': True, 'additionalFields': {}},
          [2860, -100], credentials=cred('tg'), **RETRY)
    w.add('Héberger image', *http('POST', "={{ $('Config').first().json.media_service }}/ingest?ratio_policy={{ $('Config').first().json.ratio_policy }}",
                                  auth='media', binary=True),
          [3080, -100], credentials=cred('media'), **RETRY, **SOFT)
    w.add('Collecter images', *code(r"""
// Ordre d'envoi conservé (idx). L'URL Telegram (qui contient le token du bot) n'est jamais transmise :
// seule l'URL de notre hébergement public part vers Instagram.
const a = $('Analyser légende').first().json;
const res = $input.all().map((it, i) => ({ ...it.json, idx: i }));
const errs = res.filter(r => !r.url).map(r => `image ${r.idx + 1} : ${r.error?.message || r.error || 'échec hébergement'}`);
const avert = [...a.avertissements];
res.forEach(r => (r.warnings || []).forEach(w => avert.push(`image ${r.idx + 1} : ${w}`)));
res.filter(r => r.converted).forEach(r => avert.push(`image ${r.idx + 1} convertie de ${r.source_format} en JPEG`));
const ratios = [...new Set(res.filter(r => r.ratio).map(r => r.ratio.toFixed(2)))];
if (ratios.length > 1) avert.push(`ratios différents (${ratios.join(', ')}) : Instagram recadre tout le carrousel sur le ratio de la 1re image`);
return [{ json: { ...a, images: res.map(r => r.url).filter(Boolean), avertissements: avert,
                  erreur: errs.join(' | ') } }];
"""), [3300, -100])
    w.add('Images OK ?', *if_true('!$json.erreur'), [3520, -100])
    # Langue(s) : celles de la légende si données, sinon détectées sur les images (Claude, service média).
    w.add('Détecter langue ?', *if_true("!$json.langues_apprises.length && $('Config').first().json.detection_langues"),
          [3630, -450])
    w.add('Détecter langues', *http('POST', "={{ $('Config').first().json.media_service }}/detect-langues", auth='media',
                                    body_json="={{ JSON.stringify({ images: $json.images, "
                                              "modele: $('Config').first().json.detection_modele }) }}"),
          [3740, -600], credentials=cred('media'), **SOFT)
    w.add('Langues', *code(r"""
// Résultat unique lu par la suite du workflow ($('Langues')) : images + légende + langue(s) finales.
const a = $('Collecter images').first().json;
if (!$('Détecter langues').isExecuted) return [{ json: { ...a, note_langues: '' } }];
const d = $('Détecter langues').first().json;
const langues = d.ok ? (d.langues || []) : [];
const avert = [...a.avertissements];
let note = '';
if (!d.ok) avert.push(`détection de la langue impossible (${d.error?.message || d.error || '?'}) → description générique`);
else if (!langues.length) avert.push('langue non reconnue sur les images → description générique (précise-la en légende)');
else note = `🔎 Langue${langues.length > 1 ? 's' : ''} déduite${langues.length > 1 ? 's' : ''} des images : ${langues.join(' vs ')} ` +
            `(confiance ${d.confiance || '?'}${d.raison ? ' — ' + d.raison : ''})`;
return [{ json: { ...a, langue_apprise: langues[0] || '', langues_apprises: langues, avertissements: avert, note_langues: note } }];
"""), [3960, -450])
    w.add('Demande description', *code(r"""
const a = $json;
return [{ json: { langue_description: a.langue_description, langue_apprise: a.langue_apprise,
                  langues_apprises: a.langues_apprises, desc_perso: a.desc_perso, type: a.type } }];
"""), [3740, -200])
    w.add('Tirer description', *call('descr'), [3960, -200], **SOFT)
    w.add('Description OK ?', *if_true('$json.ok === true'), [4180, -200])
    w.add('Demande publication', *code(r"""
// Format commun des sous-workflows « Publier ».
const a = $('Langues').first().json;
const d = $json;
return [{ json: {
  type: a.type, images: a.images, video: '', texte: d.caption,
  langue_description: a.langue_description, langue_apprise: a.langues_apprises.join('+'),   // journal : « ar+ary »
  source: 'telegram', source_ref: a.source_ref,
  desc_ids: { texte_id: d.desc_perso ? '' : d.texte_id, cta_id: d.cta_id, hashtags_id: d.hashtags_id },
} }];
"""), [4400, -300])
    w.add('Publier Instagram', *call('ig'), [4620, -300], **SOFT)
    w.add('Message retour', *code(JS_ESC + r"""
const r = $json;
const a = $('Langues').first().json;
const demande = $('Demande publication').first().json;
const av = (a.note_langues ? '\n\n' + e(a.note_langues) : '')
  + (a.avertissements.length ? '\n\n⚠️ ' + a.avertissements.map(e).join('\n⚠️ ') : '');
if (r.ok) {
  return [{ json: { texte: `✅ ${a.type === 'post' ? 'Post' : 'Carrousel de ' + a.images.length + ' images'} publié\n${e(r.permalink || r.post_id)}\n\n<b>Description utilisée :</b>\n${e(demande.texte)}${av}` } }];
}
return [{ json: { texte: `❌ Publication Instagram échouée :\n${e(r.erreur || r.error?.message || JSON.stringify(r))}${av}` } }];
"""), [4840, -300])
    w.add('Répondre', *telegram('={{ $json.texte }}'), [5060, -300], credentials=cred('tg'))
    w.add('Envoyer à Pinterest', *code(r"""
// Même contenu vers le sous-workflow Pinterest (qui ne fait rien tant que pinterest.actif = false).
if (!$('Publier Instagram').first().json.ok) return [];
return [{ json: $('Demande publication').first().json }];
"""), [5280, -300])
    w.add('Publier Pinterest', *call('pin'), [5500, -300], **SOFT)
    w.add('Erreur avant publication', *code(JS_ESC + r"""
const j = $json;
const msg = j.erreur || j.error?.message || JSON.stringify(j).slice(0, 400);
return [{ json: { texte: `❌ Rien n'a été publié :\n${e(msg)}` } }];
"""), [4400, 100])
    w.add('Signaler erreur', *telegram('={{ $json.texte }}'), [4620, 100], credentials=cred('tg'))
    w.add('Pour le blog ?', *code(r"""
// Un article de blog par publication Instagram (carrousel OU photo seule) ; rédigé le soir par le workflow Blog.
const cfg = $('Config').first().json;
const r = $('Publier Instagram').first().json;
const a = $('Langues').first().json;
if (!cfg.blog_actif || !r.ok) return [];
const d = $('Demande publication').first().json;
return [{ json: { source_ref: a.source_ref, images: a.images, langue_apprise: a.langue_apprise,
                  langues_apprises: a.langues_apprises,
                  langue_description: a.langue_description, caption: a.caption, texte: d.texte,
                  permalink: r.permalink || '' } }];
"""), [5280, -500])
    w.add('Mettre en file blog', *http('POST', "={{ $('Config').first().json.media_service }}/blog/enqueue", auth='media',
                                       body_json='={{ JSON.stringify($json) }}'),
          [5500, -500], credentials=cred('media'), **RETRY, **SOFT)
    w.add('File blog OK ?', *code(JS_ESC + r"""
const j = $json;
if (j.ok) return [];
return [{ json: { texte: `⚠️ Carrousel publié, mais pas mis en file pour le blog :\n${e(j.error?.message || j.error || JSON.stringify(j).slice(0, 300))}` } }];
"""), [5720, -500])
    w.add('Signaler file blog', *telegram('={{ $json.texte }}'), [5940, -500], credentials=cred('tg'))
    w.add('Vider tampon ?', *code(r"""
const g = $('Analyser légende').first().json.media_group_id;
return g ? [{ json: { media_group_id: g } }] : [];
"""), [5720, 0])
    w.add('Vider tampon', *dt('vb_tampon_album', 'deleteRows',
                              **dt_filter(('media_group_id', '={{ $json.media_group_id }}')), options={}),
          [5940, 0], **SOFT)

    w.chain('Telegram', 'Config', 'Filtrer message', 'Bouton blog ?')
    w.link('Bouton blog ?', 'Décision blog', 0)
    w.link('Bouton blog ?', 'Prompt ?', 1)
    w.link('Prompt ?', 'Prompt carrousel', 0)
    w.link('Prompt ?', 'Image ?', 1)
    w.link('Image ?', 'Album ?', 0)
    w.link('Image ?', 'Aide', 1)
    w.link('Album ?', 'Mettre en tampon', 0)
    w.link('Album ?', 'Photo seule', 1)
    w.chain('Mettre en tampon', "Attendre fin d'album", 'Lire album', 'Dernière photo ?', 'Analyser légende')
    w.link('Photo seule', 'Analyser légende')
    w.link('Analyser légende', 'Nombre OK ?')
    w.link('Nombre OK ?', 'Déjà publié ?', 0)
    w.link('Nombre OK ?', 'Refus', 1)
    w.link('Refus', 'Vider tampon ?')
    w.chain('Déjà publié ?', 'Une ligne par image', 'Télécharger image', 'Héberger image', 'Collecter images', 'Images OK ?')
    w.link('Images OK ?', 'Détecter langue ?', 0)
    w.link('Détecter langue ?', 'Détecter langues', 0)
    w.link('Détecter langue ?', 'Langues', 1)
    w.link('Détecter langues', 'Langues')
    w.link('Langues', 'Demande description')
    w.link('Images OK ?', 'Erreur avant publication', 1)
    w.chain('Demande description', 'Tirer description', 'Description OK ?')
    w.link('Description OK ?', 'Demande publication', 0)
    w.link('Description OK ?', 'Erreur avant publication', 1)
    w.chain('Demande publication', 'Publier Instagram', 'Message retour', 'Répondre', 'Envoyer à Pinterest',
            'Publier Pinterest')
    w.chain('Répondre', 'Vider tampon ?', 'Vider tampon')
    w.chain('Répondre', 'Pour le blog ?', 'Mettre en file blog', 'File blog OK ?', 'Signaler file blog')
    w.chain('Erreur avant publication', 'Signaler erreur', 'Vider tampon ?')
    integrer(w, 'Tirer description', wf_descr, 'description')
    integrer(w, 'Publier Instagram', wf_ig, 'IG')
    integrer(w, 'Publier Pinterest', wf_pin, 'Pinterest')
    carrousel_facebook(w)
    return w.dump()


def carrousel_facebook(w):
    """Carrousel → publication multi-photos sur la page Facebook VocaBag (2026-09-30).

    Comme Pinterest : seulement si Instagram a réussi (un carrousel renvoyé après un échec Instagram ne part donc
    pas deux fois sur Facebook). Photos envoyées non publiées (/photos, published=false) puis une seule publication
    /feed (message = légende Instagram, attached_media = les photos). Résultat signalé sur Telegram.
    """
    y = min(n['position'][1] for n in w.nodes) - 400
    x0 = next(n for n in w.nodes if n['name'] == 'Répondre')['position'][0] + 240
    X = lambda i: x0 + i * 240
    fb = dict(credentials=cred('fb'), **SOFT)

    def req(method, url, query=None, body_json=None):
        t, v, p = http(method, url, auth='fb', body_json=body_json)
        p['options'] = {'response': {'response': {'neverError': True}}}
        if query:
            p.update({'sendQuery': True, 'queryParameters': {'parameters': [{'name': a, 'value': b} for a, b in query.items()]}})
        return t, v, p

    w.add('Envoyer à Facebook', *code(r"""
// Une ligne par image (même contenu qu'Instagram), seulement si Instagram a réussi.
if (!$('Publier Instagram').first().json.ok) return [];
const d = $('Demande publication').first().json;
return (d.images || []).map(url => ({ json: { url } }));
"""), [X(0), y])
    w.add('Photo non publiée · FB', *req('POST', FB_PAGE + '/photos',
          {'url': '={{ $json.url }}', 'published': 'false'}), [X(1), y], **fb)
    w.add('Photos FB', *code(r"""
// Toutes les photos doivent être acceptées, sinon on ne publie pas un carrousel incomplet.
const r = $input.all().map(i => i.json);
const ids = r.map(x => x.id).filter(Boolean);
if (ids.length !== r.length) {
  const err = r.find(x => !x.id);
  return [{ json: { ok: false, erreur: err?.error?.message || JSON.stringify(err) } }];
}
return [{ json: { ok: true, corps: { message: $('Demande publication').first().json.texte,
                                     attached_media: ids.map(id => ({ media_fbid: id })) } } }];
"""), [X(2), y])
    w.add('Photos FB OK ?', *if_true('$json.ok === true'), [X(3), y])
    w.add('Publier · FB', *req('POST', FB_PAGE + '/feed', body_json='={{ JSON.stringify($json.corps) }}'),
          [X(4), y - 100], **fb)
    w.add('Message · FB', *code(r"""
const e = s => String(s ?? '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
const r = $json;
if (r.id) return [{ json: { texte: `📘 Facebook : publié\nhttps://www.facebook.com/${e(r.id)}` } }];
return [{ json: { texte: `❌ Publication Facebook échouée :\n${e(r.erreur || r.error?.message || JSON.stringify(r))}` } }];
"""), [X(5), y])
    w.add('Signaler · FB', *telegram('={{ $json.texte }}'), [X(6), y], credentials=cred('tg'))
    w.link('Répondre', 'Envoyer à Facebook')
    w.chain('Envoyer à Facebook', 'Photo non publiée · FB', 'Photos FB', 'Photos FB OK ?')
    w.link('Photos FB OK ?', 'Publier · FB', 0)
    w.link('Photos FB OK ?', 'Message · FB', 1)
    w.chain('Publier · FB', 'Message · FB', 'Signaler · FB')


# ================================================================== BLOG (articles tirés des carrousels)
# Carrousel publié → /blog/enqueue (workflow Carrousel) ; chaque soir « Blog Revue » lance le rédacteur
# (Claude Code sur l'hôte, via vocabag-media) ; il rappelle « Blog Prêt » (webhook) → e-mail + Telegram
# avec boutons ; le clic arrive dans le Telegram Trigger du Carrousel → « Blog Décision ».
def boutons(*btns):
    return {'rows': [{'row': {'buttons': [{'text': t, 'additionalFields': {'callback_data': d}} for t, d in btns]}}]}


def wf_blog():
    """Blog : 3 déclencheurs, un seul Config, puis aiguillage selon le déclencheur qui a démarré l'exécution.
      - Chaque soir (21h)  → lance le rédacteur (Claude Code sur l'hôte, via vocabag-media) ;
      - Webhook vb-blog-pret (appelé par le rédacteur) → e-mail + Telegram avec boutons ;
      - Entrée (appelée par le Carrousel, qui reçoit les clics de boutons du bot) → publier / rejeter / réécrire.
    """
    w = W('blog', 'VocaBag Social - Blog')
    w.add('Chaque soir', 'n8n-nodes-base.scheduleTrigger', 1.2,
          {'rule': {'interval': [{'field': 'cronExpression', 'expression': '0 21 * * *'}]}}, [0, 0])
    w.add('Lancer la rédaction', *http('POST', "={{ $('Config').first().json.media_service }}/blog/rediger", auth='media',
                                       body_json="={{ JSON.stringify({ webhook: $('Config').first().json.blog.webhook_pret, "
                                                 "max: $('Config').first().json.blog.max_par_soir, "
                                                 "modele: $('Config').first().json.blog.modele }) }}"),
          [660, 0], credentials=cred('media'), **RETRY, **SOFT)
    # Échec du lancement : rien (le rédacteur reprendra les carrousels en attente le soir suivant).
    w.add('Webhook', 'n8n-nodes-base.webhook', 2,
          {'httpMethod': 'POST', 'path': 'vb-blog-pret', 'authentication': 'headerAuth',
           'responseMode': 'onReceived', 'options': {}}, [0, 500], credentials={'httpHeaderAuth': CRED_MEDIA['httpHeaderAuth']},
          webhookId=str(uuid.uuid5(uuid.NAMESPACE_URL, 'vb-blog-pret')))
    w.add('Brouillon', *code(r"""
const b = $('Webhook').first().json.body || {};
if (!/^c\d{8}-[0-9a-f]{6}$/.test(b.id || '')) return [];
return [{ json: b }];
"""), [440, 500])
    w.add('Rédigé ?', *if_true('$json.ok === true'), [660, 500])
    w.add('Composer e-mail', *code(JS_ESC + r"""
const cfg = $('Config').first().json;
const b = $json;
const av = (b.avertissements || []).length
  ? `<div style="background:#fff7ed;border:1px solid #fdba74;border-radius:8px;padding:10px 14px;margin:12px 0">⚠️ ${b.avertissements.map(e).join('<br>⚠️ ')}</div>` : '';
const html = `<div style="font-family:Inter,Arial,sans-serif;max-width:680px;margin:auto;color:#0f172a;line-height:1.7">
<p style="color:#64748b;font-size:13px">Brouillon rédigé à partir du ${b.permalink ? `<a href="${e(b.permalink)}">carrousel Instagram</a>` : 'carrousel Instagram'}.
Pour le publier : bouton ✅ <b>Publier</b> sur Telegram (@vocabagbot). Il sera commité sur la branche staging
et arrivera sur vocabag.com au prochain déploiement.</p>
<p style="font-size:13px"><b>Catégorie :</b> ${e(b.categorie)} · <b>Adresse :</b> /blog/${e(b.slug)} · ${b.mots} mots<br>
<b>Description Google :</b> ${e(b.description)}</p>${av}
<hr style="border:none;border-top:1px solid #e2e8f0"><h1 style="font-size:26px;line-height:1.3">${e(b.titre)}</h1>
${b.html}</div>`;
return [{ json: { ...b, email_html: html, email_sujet: `📝 Brouillon blog : ${b.titre}` } }];
"""), [880, 400])
    w.add('E-mail brouillon', 'n8n-nodes-base.emailSend', 2.1,
          {'fromEmail': "={{ $('Config').first().json.blog.email_expediteur }}",
           'toEmail': "={{ $('Config').first().json.blog.email }}",
           'subject': '={{ $json.email_sujet }}', 'emailFormat': 'html', 'html': '={{ $json.email_html }}',
           'options': {}}, [1100, 400], credentials=cred('smtp'), **RETRY, **SOFT)
    w.add('Fichier .md', *code(r"""
// Le brouillon complet part aussi en fichier sur Telegram (lisible sans ouvrir l'e-mail).
const b = $('Composer e-mail').first().json;
const r = $json;
return [{ json: { ...b, email_erreur: r.error ? (r.error.message || String(r.error)) : '' },
          binary: { data: { data: Buffer.from(b.markdown, 'utf8').toString('base64'),
                            mimeType: 'text/markdown', fileName: `${b.slug}.md`, fileExtension: 'md' } } }];
"""), [1320, 400])
    w.add('Envoyer le fichier', 'n8n-nodes-base.telegram', 1.2,
          {'operation': 'sendDocument', 'chatId': "={{ $('Config').first().json.telegram_chat_id }}",
           'binaryData': True, 'binaryPropertyName': 'data',
           'additionalFields': {'caption': '=📝 {{ $json.titre }}'}}, [1540, 400], credentials=cred('tg'), **RETRY, **SOFT)
    w.add('Texte à valider', *code(JS_ESC + r"""
const cfg = $('Config').first().json;
const b = $('Fichier .md').first().json;
const av = (b.avertissements || []).length ? '\n\n⚠️ ' + b.avertissements.map(e).join('\n⚠️ ') : '';
const mail = b.email_erreur ? `⚠️ E-mail non envoyé : ${e(b.email_erreur)}` : `📧 Brouillon complet envoyé à ${e(cfg.blog.email)}`;
return [{ json: { id: b.id, texte:
  `📝 <b>Nouveau brouillon de blog</b>\n\n<b>${e(b.titre)}</b>\n${e(b.description)}\n\n` +
  `${e(b.categorie)} · ${b.mots} mots · /blog/${e(b.slug)}${av}\n\n${mail}\n\n` +
  `✅ Publier = commit sur la branche staging ; en ligne sur vocabag.com au prochain déploiement.` } }];
"""), [1760, 400])
    w.add('Demander validation', 'n8n-nodes-base.telegram', 1.2,
          {'chatId': "={{ $('Config').first().json.telegram_chat_id }}", 'text': '={{ $json.texte }}',
           'replyMarkup': 'inlineKeyboard',
           'inlineKeyboard': boutons(('✅ Publier', '=blog:pub:{{ $json.id }}'), ('🔁 Réécrire', '=blog:redo:{{ $json.id }}'),
                                     ('❌ Rejeter', '=blog:rej:{{ $json.id }}')),
           'additionalFields': {'appendAttribution': False, 'parse_mode': 'HTML', 'disable_web_page_preview': True}},
          [1980, 400], credentials=cred('tg'), **RETRY)
    w.add('Message échec', *code(JS_ESC + r"""
const b = $json;
const suite = b.definitif ? 'Abandonné après plusieurs essais.' : 'Nouvel essai au prochain passage (21h).';
return [{ json: { id: b.id, texte: `❌ <b>Rédaction du blog échouée</b> (${e(b.id)})\n${e(b.erreur)}\n\n${suite}` +
  (b.permalink ? `\nCarrousel : ${e(b.permalink)}` : '') } }];
"""), [880, 650])
    w.add('Signaler échec', 'n8n-nodes-base.telegram', 1.2,
          {'chatId': "={{ $('Config').first().json.telegram_chat_id }}", 'text': '={{ $json.texte }}',
           'replyMarkup': 'inlineKeyboard',
           'inlineKeyboard': boutons(('🔁 Réessayer maintenant', '=blog:redo:{{ $json.id }}'),
                                     ('❌ Abandonner', '=blog:rej:{{ $json.id }}')),
           'additionalFields': {'appendAttribution': False, 'parse_mode': 'HTML', 'disable_web_page_preview': True}},
          [1100, 650], credentials=cred('tg'), **RETRY)
    w.chain('Brouillon', 'Rédigé ?')
    w.link('Rédigé ?', 'Composer e-mail', 0)
    w.link('Rédigé ?', 'Message échec', 1)
    w.chain('Composer e-mail', 'E-mail brouillon', 'Fichier .md', 'Envoyer le fichier', 'Texte à valider', 'Demander validation')
    w.chain('Message échec', 'Signaler échec')
    w.add('Entrée', 'n8n-nodes-base.executeWorkflowTrigger', 1, {}, [0, 1200])
    w.add('Appeler le service', *http('POST', "={{ $('Config').first().json.media_service }}/blog/"
                                              "{{ ({ pub: 'publier', rej: 'rejeter', redo: 'reecrire' })[$('Entrée').first().json.decision] }}",
                                      auth='media', body_json="={{ JSON.stringify({ id: $('Entrée').first().json.id }) }}"),
          [440, 1200], credentials=cred('media'), **SOFT)
    w.add('Réponse', *code(JS_ESC + r"""
const d = $('Entrée').first().json;
const r = $json;
let texte, court;
if (!r.ok) {
  const err = r.error?.message || r.error || JSON.stringify(r).slice(0, 300);
  return [{ json: { ...d, ok: false, court: 'Échec', texte: `❌ Action « ${d.decision} » impossible sur ${e(d.id)} :\n${e(err)}` } }];
}
if (d.decision === 'pub') {
  court = 'Publié sur staging';
  texte = r.deja ? `✅ Déjà publié : ${e(r.url_staging)}`
    : `✅ <b>Publié sur staging</b> — ${e(r.titre)}\n${e(r.url_staging)}\n\nCommit ${e(r.commit)} sur la branche staging (non poussé).\n` +
      `En ligne sur vocabag.com au prochain déploiement :\n${e(r.url_prod)}`;
} else if (d.decision === 'rej') {
  court = 'Rejeté';
  texte = `❌ Brouillon rejeté${r.titre ? ' — ' + e(r.titre) : ''}`;
} else {
  court = 'Réécriture lancée';
  texte = r.lance ? '🔁 Réécriture lancée : nouveau brouillon dans quelques minutes.'
                  : '🔁 Réécriture programmée (une rédaction est déjà en cours, ou au prochain passage de 21h).';
}
return [{ json: { ...d, ok: true, court, texte } }];
"""), [660, 1200])
    w.add('Accuser réception', 'n8n-nodes-base.telegram', 1.2,
          {'resource': 'callback', 'operation': 'answerQuery', 'queryId': '={{ $json.callback_query_id }}',
           'additionalFields': {'text': '={{ $json.court }}'}}, [880, 1200], credentials=cred('tg'), **SOFT)
    w.add('Réussi ?', *if_true("$('Réponse').first().json.ok === true"), [1100, 1200])
    # Succès : le message du brouillon est remplacé (ses boutons disparaissent, pas de double clic).
    w.add('Remplacer le message', 'n8n-nodes-base.telegram', 1.2,
          {'operation': 'editMessageText', 'messageType': 'message',
           'chatId': "={{ $('Réponse').first().json.chat_id }}", 'messageId': "={{ $('Réponse').first().json.message_id }}",
           'text': "={{ $('Réponse').first().json.texte }}", 'replyMarkup': 'none',
           'additionalFields': {'parse_mode': 'HTML', 'disable_web_page_preview': True}},
          [1320, 1100], credentials=cred('tg'), **SOFT)
    # Échec : les boutons restent sur le brouillon pour réessayer.
    w.add('Signaler', *telegram("={{ $('Réponse').first().json.texte }}"), [1320, 1300], credentials=cred('tg'))
    w.chain('Appeler le service', 'Réponse', 'Accuser réception', 'Réussi ?')
    w.link('Réussi ?', 'Remplacer le message', 0)
    w.link('Réussi ?', 'Signaler', 1)
    config_node(w, [150, 750], 'telegram', 'media', 'blog')
    w.add('Revue du soir ?', *if_true("$('Chaque soir').isExecuted"), [300, 250])
    w.add('Brouillon reçu ?', *if_true("$('Webhook').isExecuted"), [300, 900])
    for t in ('Chaque soir', 'Webhook', 'Entrée'):
        w.link(t, 'Config')
    w.link('Config', 'Revue du soir ?')
    w.link('Revue du soir ?', 'Lancer la rédaction', 0)
    w.link('Revue du soir ?', 'Brouillon reçu ?', 1)
    w.link('Brouillon reçu ?', 'Brouillon', 0)
    w.link('Brouillon reçu ?', 'Appeler le service', 1)
    return w.dump()


# ================================================================== PROMPT CARROUSEL (2026-10-04)
# Message « prompt » au bot → boutons langue (12 solos + 5 duels) → boutons catégorie → prompt ChatGPT avec les
# 10 mots (10 paires en duel) tirés de la base VocaBag, à coller avec les templates du carrousel.
# Appelé par le Carrousel (seul Telegram Trigger du bot). Test : POST /webhook/vb-prompt-test
# {"etape": "langue"|"categorie"|"prompt", "sel": "ary"|"es_it", "cat": 1} + en-tête X-Media-Token
# (sans message_id, tout part en nouveaux messages).
# Claviers FIXES : n8n ignore une expression posée sur tout le clavier (fixedCollection) ou sur un champ inconnu
# (reply_markup) ; seuls les textes / callback_data des boutons peuvent être des expressions. D'où : les 21
# catégories sont toujours affichées, celles qui n'ont pas assez de mots marquées ✖️ (clic = simple notification).
CRED_MEDIA_PROD = {'httpHeaderAuth': {'id': 'L2zYP3cEvAgZVffN', 'name': 'VocaBag media (X-Media-Token)'}}   # id réel en prod
PROMPT_SOLOS = [('ar', '🇸🇦 Arabe'), ('ary', '🇲🇦 Darija'), ('de', '🇩🇪 Allemand'), ('en', '🇬🇧 Anglais'),
                ('es', '🇪🇸 Espagnol'), ('it', '🇮🇹 Italien'), ('ko', '🇰🇷 Coréen'), ('nl', '🇳🇱 Néerlandais'),
                ('pt', '🇧🇷 Portugais'), ('ru', '🇷🇺 Russe'), ('tr', '🇹🇷 Turc'), ('zh', '🇨🇳 Chinois')]
PROMPT_DUELS = [('ary_ar', '🇲🇦 vs 🇸🇦 Darija / Arabe'), ('de_nl', '🇩🇪 vs 🇳🇱 Allemand / Néerl.'),
                ('es_it', '🇪🇸 vs 🇮🇹 Espagnol / Italien'), ('es_pt', '🇪🇸 vs 🇧🇷 Espagnol / Portugais'),
                ('it_pt', '🇮🇹 vs 🇧🇷 Italien / Portugais')]
# Catégories actives du site (categories + category_translations fr, 2026-10-04). Une nouvelle catégorie en base
# n'apparaît dans les boutons qu'après l'avoir ajoutée ici et régénéré le workflow.
PROMPT_CATEGORIES = [
    (1, '👋', 'Salutations'), (2, '💬', 'Expressions de base'), (3, '✈️', 'Voyage'), (4, '🍽️', 'Nourriture'),
    (5, '🏠', 'Activités quotidiennes'), (6, '👨‍👩‍👧', 'Famille & relations'), (7, '🔢', 'Chiffres & temps'),
    (8, '🎨', 'Couleurs & descriptions'), (9, '🏥', 'Corps & santé'), (10, '🛒', 'Marché & shopping'),
    (11, '💼', 'Travail & études'), (12, '😊', 'Émotions & états'), (13, '🕌', 'Religion & culture'),
    (14, '🚌', 'Transport & directions'), (15, '📱', 'Technologie & Internet'), (16, '🏠', 'Maison & intérieur'),
    (17, '👕', 'Vêtements'), (18, '⛅', 'Météo & nature'), (19, '🐱', 'Animaux'), (20, '⚽', 'Sports & loisirs'),
    (21, '💰', 'Argent & banque'),
]
PROMPT_SLUGS = list(enumerate(['greetings', 'basics', 'travel', 'food', 'daily_life', 'family', 'numbers_time',
                               'colors_desc', 'health_body', 'market_shopping', 'work_studies', 'emotions',
                               'religion_culture', 'transport', 'technology', 'home_interior', 'clothing',
                               'weather_nature', 'animals', 'sports_leisure', 'money_banking'], start=1))


def clavier_fixe(lignes):
    """Paramètre inlineKeyboard du nœud Telegram : lignes de (texte, callback_data), expressions permises."""
    return {'rows': [{'row': {'buttons': [{'text': t, 'additionalFields': {'callback_data': d}} for t, d in l]}}
                     for l in lignes]}


def par(seq, n):
    return [seq[i:i + n] for i in range(0, len(seq), n)]


def wf_prompt():
    w = W('prompt', 'VocaBag Social - Prompt carrousel')
    w.add('Entrée', 'n8n-nodes-base.executeWorkflowTrigger', 1, {}, [0, 0])
    w.add('Test', 'n8n-nodes-base.webhook', 2,
          {'httpMethod': 'POST', 'path': 'vb-prompt-test', 'authentication': 'headerAuth',
           'responseMode': 'onReceived', 'options': {}}, [0, 200], credentials=CRED_MEDIA_PROD,
          webhookId=str(uuid.uuid5(uuid.NAMESPACE_URL, 'vb-prompt-test')))
    config_node(w, [220, 100], 'telegram', 'media', 'langues', 'prompt')
    w.add('Préparer', *code(r"""
// Valide la demande (sel / cat viennent des boutons : rien d'autre n'entre dans le SQL) et prépare la requête.
const cfg = $('Config').first().json;
const P = cfg.prompt;
const d = $('Entrée').isExecuted ? $('Entrée').first().json : ($('Test').first().json.body || {});
const etape = ['langue', 'categorie', 'prompt'].includes(d.etape) ? d.etape : 'langue';
const sel = String(d.sel || '');
const ok = P.solos.includes(sel) || P.duels.includes(sel);
const cat = parseInt(d.cat, 10);
const base = { etape, sel, cat: Number.isInteger(cat) ? cat : 0, callback_query_id: d.callback_query_id || '',
               message_id: Number(d.message_id) || 0, nouveau: d.nouveau !== false || !d.message_id };
if (etape === 'langue') return [{ json: { ...base, sql: '' } }];
if (!ok) return [{ json: { ...base, etape: 'langue', nouveau: true, sql: '', erreur: `Langue inconnue : ${sel}` } }];
const [a, b] = sel.split('_');
const lid = c => `(SELECT id FROM languages WHERE code = '${c}')`;
// Mots retenus : actifs, validés, mots/expressions courts (lisibles sur une diapo) ; une seule entrée par sens.
// Duel : un « mot » = un sens (traduction FR) présent dans les deux langues, même catégorie (comme Vocabag Video).
const filtre = x => `${x}.active = 1 AND ${x}.needs_validation = 0 AND ${x}.type IN ('word','expression') AND CHAR_LENGTH(${x}.word) <= 30`;
// Sens comparé sans article ni casse : selon la langue, la base dit « la tête » ou « Tête » (de_nl : 1 → 25 mots
// communs en « Corps & santé »).
const norm = x => `LOWER(REGEXP_REPLACE(REGEXP_REPLACE(TRIM(${x}), '^(le|la|les|un|une|des) ', ''), '^l[''’] ?', ''))`;
const joins = `JOIN vocabulary_translations ta ON ta.vocabulary_id = va.id AND ta.target_locale = 'fr'` + (b ? `
  JOIN vocabulary vb ON vb.category_id = va.category_id AND vb.language_id = ${lid(b)} AND ${filtre('vb')}
  JOIN vocabulary_translations tb ON tb.vocabulary_id = vb.id AND tb.target_locale = 'fr' AND ${norm('tb.translation')} = ${norm('ta.translation')}` : '');
const where = `va.language_id = ${lid(a)} AND ${filtre('va')} AND CHAR_LENGTH(ta.translation) <= 40`;
let sql;
if (etape === 'categorie') {
  sql = `SELECT va.category_id AS id, COUNT(DISTINCT ${norm('ta.translation')}) AS n
FROM vocabulary va
  ${joins}
WHERE ${where}
GROUP BY va.category_id`;
} else {
  if (!Number.isInteger(cat) || cat < 1) return [{ json: { ...base, etape: 'categorie', sql: '', erreur: 'Catégorie invalide' } }];
  const cols = b ? 'va.word AS word_a, va.transliteration AS translit_a, vb.word AS word_b, vb.transliteration AS translit_b, va.type'
                 : 'va.word AS word_a, va.transliteration AS translit_a, va.type';
  sql = `SELECT t.* FROM (
  SELECT ${cols}, ta.translation,
         ROW_NUMBER() OVER (PARTITION BY ${norm('ta.translation')} ORDER BY RAND()) AS rn
  FROM vocabulary va
  ${joins}
  WHERE ${where} AND va.category_id = ${cat}
) t
WHERE t.rn = 1
ORDER BY RAND()
LIMIT ${P.nb_mots}`;
}
return [{ json: { ...base, sql } }];
"""), [440, 100])
    w.add('Base ?', *if_true("!!$json.sql"), [660, 100])
    w.add('Interroger la base', 'n8n-nodes-base.mySql', 2.4,
          {'operation': 'executeQuery', 'query': '={{ $json.sql }}', 'options': {}},
          [880, 0], credentials=cred('db'), alwaysOutputData=True, **RETRY)
    w.add('Composer', *code(JS_ESC + r"""
// Un item par message : { vue, texte, ... } ; vue = clavier à utiliser (sortie de « Aiguiller ») :
// 0 langue (nouveau) · 1 langue (modifier) · 2 catégorie (nouveau) · 3 catégorie (modifier) · 4 prompt · 5 récap · 6 texte
// · 7 rien à envoyer (notification seule)
// « toast » : notification affichée au clic (réponse au bouton).
const cfg = $('Config').first().json;
const P = cfg.prompt;
const d = $('Préparer').first().json;
const rows = $('Interroger la base').isExecuted ? $('Interroger la base').all().map(i => i.json).filter(r => r.n || r.word_a) : [];
const L = c => ({ code: c, drapeau: cfg.langues[c]?.drapeau || '', nom: P.noms[c] || c });
const langs = d.sel ? d.sel.split('_').map(L) : [];
const libelle = langs.map(l => `${l.drapeau} ${l.nom}`).join(' vs ');
const duel = langs.length > 1;
const edit = !d.nouveau;
const item = (vue, texte, extra) => ({ json: { vue, texte, message_id: d.message_id, sel: d.sel, cat: d.cat, toast: '', ...extra } });
const err = d.erreur ? `⚠️ ${e(d.erreur)}\n\n` : '';

if (d.etape === 'langue')
  return [item(edit ? 1 : 0, `${err}✍️ <b>Prompt carrousel</b>\n\n1/2 — Choisis la langue, ou un duel de deux langues :`)];

if (d.etape === 'categorie') {
  const dispo = Object.fromEntries(rows.map(r => [String(r.id), Number(r.n)]));
  const etiquettes = {};
  for (const c of P.categories) {
    const n = dispo[String(c.id)] || 0;
    etiquettes[c.id] = n >= P.nb_mots ? `${c.icon} ${c.nom} (${n})` : `✖️ ${c.nom}`;
  }
  const nbOk = P.categories.filter(c => (dispo[String(c.id)] || 0) >= P.nb_mots).length;
  return [item(edit ? 3 : 2,
    `${err}✍️ <b>Prompt carrousel</b> — ${e(libelle)}\n\n2/2 — Choisis la catégorie ` +
    `(${nbOk} disponible${nbOk > 1 ? 's' : ''} ; entre parenthèses : ${duel ? 'mots communs aux deux langues' : 'mots disponibles'} ; ` +
    `✖️ = moins de ${P.nb_mots}) :`, { etiquettes })];
}

// --- prompt
const c = P.categories.find(x => x.id === d.cat) || { icon: '', nom: '?', slug: '' };
if (rows.length < P.nb_mots)
  return [item(7, '', { toast: `${c.nom} : pas assez de mots ${duel ? 'communs aux deux langues' : ''} (${rows.length}/${P.nb_mots}).` })];
const titre = P.titres[c.slug] || c.nom;
const nb = rows.length;
// Émojis fixés par le workflow (Claude via vocabag-media, nœud « Choisir les émojis »), plus par ChatGPT.
const em = $('Choisir les émojis').isExecuted ? $('Choisir les émojis').first().json : {};
if (!em.ok || !Array.isArray(em.emojis) || em.emojis.length !== nb)
  return [item(4, `❌ Choix des émojis impossible : ${e(em.error?.message || em.error || 'réponse inattendue')}\n` +
                  `Réessaie avec 🔁 Autres mots (ou rechoisis la catégorie).`)];
// Casse homogène : majuscule initiale partout ; traductions des mots sans article (« Canard », pas « le canard »).
const cap = t => { const s = String(t ?? '').trim(); return s ? s.charAt(0).toLocaleUpperCase('fr') + s.slice(1) : s; };
const sansArticle = (t, type) => type !== 'word' ? cap(t)
  : String(t).split(/\s*\/\s*/).map((x, i) => {
      const y = x.trim().replace(/^(le|la|les|un|une|des)\s+/i, '').replace(/^l['’]\s*/i, '');
      return i === 0 ? cap(y) : y;
    }).join(' / ');
const translit = (w, t) => t && t.trim() && t.trim() !== String(w).trim() ? cap(t) : '';
let prompt;
if (duel) {
  // Template « versus » (2026-10-04) : bannières des deux langues, une catégorie, 10 lignes « mot | mot »,
  // sans traduction ni drapeau devant les mots.
  const [l1, l2] = langs;
  prompt = [
    'Remplis le template « versus » ci-joint. Ne modifie ni le décor, ni la mise en page, ni les couleurs, ni les polices. Génère une seule image au même format.',
    '',
    `Bannière haut gauche (turquoise) → ${l1.drapeau} ${l1.nom}`,
    `Bannière haut droite (bleue) → ${l2.drapeau} ${l2.nom}`,
    `Zone « Catégorie : » (en bas) → ${titre}`,
    '',
    `Lignes 1 à ${nb} : mot ${l1.nom.toLowerCase()} dans la colonne de gauche, mot ${l2.nom.toLowerCase()} dans la colonne de droite, même émoji dans les deux ronds de la ligne.`,
    ...rows.map((r, i) => `${i + 1}. ${em.emojis[i]} ${cap(r.word_a)} | ${cap(r.word_b)}`),
    '',
    // Duel avec l'arabe (ary_ar) : consigne d'écriture ajoutée à la structure imposée (demande utilisateur 2026-10-04).
    'Règles : n\'ajoute, ne retire ni ne modifie aucun mot. Garde les accents et caractères spéciaux.' +
      (langs.some(l => ['ar', 'ary'].includes(l.code))
        ? ' Pour l\'arabe : recopie caractère par caractère, dans le bon sens, lettres liées si applicable.' : '') +
      ' Texte lisible, centré verticalement dans chaque ligne, sans déborder. Les numéros centraux et le « VS » restent inchangés.',
  ].join('\n');
} else {
  // Template « 1 langue » : zone « Catégorie : » (drapeau + titre), une ligne courte par mot avec traduction.
  const l = langs[0];
  const avecTranslit = rows.some(r => translit(r.word_a, r.translit_a));
  const special = ['ar', 'ary', 'zh', 'ko', 'ru'].includes(l.code)
    ? ` Pour ${['ar', 'ary'].includes(l.code) ? 'l\'arabe' : 'l\'alphabet non latin'} : recopie caractère par caractère, dans le bon sens, lettres liées si applicable.` : '';
  prompt = [
    'Remplis le template ci-joint. Ne modifie ni le décor, ni la mise en page, ni les couleurs, ni les polices. Génère une seule image au même format.',
    '',
    `Zone « Catégorie : » → ${`${l.drapeau} ${titre} ${P.en[l.code] || ''}`.trim()}`,
    '',
    `Lignes 1 à ${nb}, une par mot, format : émoji · mot${avecTranslit ? ' · (prononciation)' : ''} · traduction`,
    ...rows.map((r, i) => {
      const t = translit(r.word_a, r.translit_a);
      return `${i + 1}. ${em.emojis[i]} ${cap(r.word_a)}${t ? ` · (${t})` : ''} · ${sansArticle(r.translation, r.type)}`;
    }),
    '',
    `Règles : n'ajoute, ne retire ni ne modifie aucun mot ni émoji. Garde les accents et caractères spéciaux.${special} Texte lisible, centré verticalement dans chaque ligne, sans déborder.`,
  ].join('\n');
}
const recap = `✍️ ${e(libelle)} · ${e(c.icon)} ${e(titre)} — ${nb} ${duel ? 'paires' : 'mots'}`;
const out = [];
if (edit) out.push(item(5, `${recap}\n\nPrompt ci-dessous 👇`));
// Message = le prompt seul (appui = copie), sans en-tête ni note autour.
out.push(item(4, `<pre>${e(prompt)}</pre>`));
return out;
"""), [1100, 100])
    w.add('Demande émojis', *code(r"""
// Étape « prompt » avec assez de mots : sens en français envoyés au choix des émojis (un par ligne).
const cfg = $('Config').first().json;
const d = $('Préparer').first().json;
if (d.etape !== 'prompt') return [{ json: { skip: true } }];
const rows = $('Interroger la base').all().map(i => i.json).filter(r => r.word_a);
if (rows.length < cfg.prompt.nb_mots) return [{ json: { skip: true } }];
const c = cfg.prompt.categories.find(x => x.id === d.cat) || {};
const mots = rows.map(r => String(r.translation).replace(/^(le|la|les|un|une|des)\s+/i, '').replace(/^l['’]\s*/i, ''));
return [{ json: { skip: false, corps: { mots, categorie: c.nom || '' } } }];
"""), [990, -100])
    w.add('Émojis ?', *if_true('$json.skip !== true'), [1100, -100])
    w.add('Attente ?', *code(r"""
// Le choix des émojis prend quelques secondes : on répond tout de suite au bouton avec une notification d'attente.
const d = $('Préparer').first().json;
return d.callback_query_id ? [{ json: { callback_query_id: d.callback_query_id } }] : [];
"""), [1210, -300])
    w.add('Patienter', 'n8n-nodes-base.telegram', 1.2,
          {'resource': 'callback', 'operation': 'answerQuery', 'queryId': '={{ $json.callback_query_id }}',
           'additionalFields': {'text': '⏳ Choix des émojis…'}}, [1430, -300], credentials=cred('tg'), **SOFT)
    t_, v_, p_ = http('POST', "={{ $('Config').first().json.media_service }}/emojis", auth='media',
                      body_json='={{ JSON.stringify($json.corps) }}')
    p_['options'] = {'timeout': 180000}
    w.add('Choisir les émojis', t_, v_, p_, [1210, -100], credentials=CRED_MEDIA_PROD, **SOFT)
    w.add('Clic ?', *code(r"""
// Réponse au bouton (obligatoire pour Telegram, sinon le bouton reste « en chargement »), avec la notification éventuelle.
// Déjà faite par « Patienter » quand les émojis ont été demandés.
const d = $('Préparer').first().json;
if (!d.callback_query_id || $('Choisir les émojis').isExecuted) return [];
return [{ json: { callback_query_id: d.callback_query_id, toast: $('Composer').first().json.toast || '' } }];
"""), [1320, -150])
    w.add('Accuser réception', 'n8n-nodes-base.telegram', 1.2,
          {'resource': 'callback', 'operation': 'answerQuery', 'queryId': '={{ $json.callback_query_id }}',
           'additionalFields': {'text': '={{ $json.toast }}', 'show_alert': '={{ !!$json.toast }}'}},
          [1540, -150], credentials=cred('tg'), **SOFT)
    w.add('Aiguiller', 'n8n-nodes-base.switch', 3.2,
          {'mode': 'expression', 'numberOutputs': 8, 'output': '={{ $json.vue }}', 'options': {}}, [1320, 150])

    chat = "={{ $('Config').first().json.telegram_chat_id }}"
    opts = {'parse_mode': 'HTML', 'disable_web_page_preview': True}
    langues = clavier_fixe(par([(t, f'cp:l:{c}') for c, t in PROMPT_SOLOS], 3) + par([(t, f'cp:l:{c}') for c, t in PROMPT_DUELS], 2))
    cats = clavier_fixe(par([(f"={{{{ $json.etiquettes['{i}'] }}}}", f'=cp:c:{{{{ $json.sel }}}}:{i}')
                             for i, _, _ in PROMPT_CATEGORIES], 2) + [[('⬅️ Langues', 'cp:b')]])
    suite = clavier_fixe([[('🔁 Autres mots', '=cpn:c:{{ $json.sel }}:{{ $json.cat }}'),
                           ('📚 Autre catégorie', '=cpn:l:{{ $json.sel }}')], [('🌍 Autre langue', 'cpn:b')]])

    def envoyer(nom, pos, clavier=None):
        p = {'chatId': chat, 'text': '={{ $json.texte }}', 'additionalFields': {'appendAttribution': False, **opts}}
        if clavier:
            p.update(replyMarkup='inlineKeyboard', inlineKeyboard=clavier)
        return w.add(nom, 'n8n-nodes-base.telegram', 1.2, p, pos, credentials=cred('tg'), **RETRY)

    def modifier(nom, pos, clavier=None):
        # Sans clavier, Telegram retire les boutons du message modifié (récapitulatif).
        p = {'operation': 'editMessageText', 'messageType': 'message', 'chatId': chat,
             'messageId': '={{ $json.message_id }}', 'text': '={{ $json.texte }}', 'additionalFields': dict(opts)}
        p.update(replyMarkup='inlineKeyboard', inlineKeyboard=clavier) if clavier else p.update(replyMarkup='none')
        return w.add(nom, 'n8n-nodes-base.telegram', 1.2, p, pos, credentials=cred('tg'), **SOFT)

    sorties = [envoyer('Langues (nouveau)', [1540, 0], langues), modifier('Langues (modifier)', [1540, 150], langues),
               envoyer('Catégories (nouveau)', [1540, 300], cats), modifier('Catégories (modifier)', [1540, 450], cats),
               envoyer('Prompt', [1540, 600], suite), modifier('Récapitulatif', [1540, 750]),
               envoyer('Texte', [1540, 900])]
    w.link('Entrée', 'Config')
    w.link('Test', 'Config')
    w.chain('Config', 'Préparer', 'Base ?')
    w.link('Base ?', 'Interroger la base', 0)
    w.link('Base ?', 'Composer', 1)
    w.chain('Interroger la base', 'Demande émojis', 'Émojis ?')
    w.link('Émojis ?', 'Attente ?', 0)          # en premier (plus haut) : notification avant l'appel à Claude
    w.link('Émojis ?', 'Choisir les émojis', 0)
    w.link('Émojis ?', 'Composer', 1)
    w.chain('Attente ?', 'Patienter')
    w.link('Choisir les émojis', 'Composer')
    w.chain('Composer', 'Clic ?', 'Accuser réception')
    w.link('Composer', 'Aiguiller')
    for i, nom in enumerate(sorties):
        w.link('Aiguiller', nom, i)
    return w.dump()


# ================================================================== 6. STORIES
def wf_stories():
    w = W('stories', 'VocaBag Social - Stories')
    w.add('Chaque heure', 'n8n-nodes-base.scheduleTrigger', 1.2,
          {'rule': {'interval': [{'field': 'hours', 'hoursInterval': 1, 'triggerAtMinute': 0}]}}, [0, 0])
    # Test manuel : POST /webhook/vb-stories-test {"action": "question"|"reponse"|"reel"} + en-tête X-Media-Token.
    w.add('Test', 'n8n-nodes-base.webhook', 2,
          {'httpMethod': 'POST', 'path': 'vb-stories-test', 'authentication': 'headerAuth',
           'responseMode': 'onReceived', 'options': {}}, [0, 200], credentials={'httpHeaderAuth': CRED_MEDIA['httpHeaderAuth']},
          webhookId=str(uuid.uuid5(uuid.NAMESPACE_URL, 'vb-stories-test')))
    config_node(w, [220, 0], 'telegram', 'instagram', 'media', 'stories', 'langues')
    w.add('Créneau', *code(r"""
// Les horaires sont définis dans Config → story_creneaux (heure Paris → action).
// Déclencheur « Test » : l'action demandée dans le corps passe avant tout.
const cfg = $('Config').first().json;
const heure = $now.setZone('Europe/Paris').toFormat('HH');
const test = $('Test').isExecuted ? String($('Test').first().json.body?.action || '') : '';
if (test && !['question', 'reponse', 'reel'].includes(test)) return [];
const action = test || cfg.story_forcer_action || cfg.story_creneaux[heure];
if (!action) return [];
const jour = $now.setZone('Europe/Paris').toFormat('yyyy-MM-dd');
return [{ json: { action, jour, source_ref: `story-${action}-${jour}` } }];
"""), [440, 0])
    w.add('Déjà publiée ?', *dt('vb_journal', 'get', returnAll=True,
                                **dt_filter(('source_ref', '={{ $json.source_ref }}'), ('statut', 'ok')),
                                options={}), [660, 0], executeOnce=True, alwaysOutputData=True)
    w.add('Aiguiller', *code(r"""
if ($input.all().some(i => i.json.post_id)) return [];   // déjà faite aujourd'hui (relance, test…)
return [{ json: $('Créneau').first().json }];
"""), [880, 0])
    w.add('Question ?', *if_true("$json.action === 'question'"), [1100, 0])
    w.add('Réponse ?', *if_true("$json.action === 'reponse'"), [1320, 200])
    w.add('Reel ?', *if_true("$json.action === 'reel'"), [1540, 400])

    # ---------- question
    w.add('Mots récents', *dt('vb_story_mots', 'get', returnAll=True, options={}), [1320, -200],
          executeOnce=True, alwaysOutputData=True)
    w.add('Requête mot', *code(r"""
// Mot tiré directement de la base VocaBag (mots validés, traduction FR), hors mots récents.
// Aucun texte généré par IA : mot, traduction et translittération viennent de la base.
const cfg = $('Config').first().json;
const total = cfg.story_langues.reduce((s, l) => s + l.poids, 0);
let r = Math.random() * total, code = cfg.story_langues[0].code;
for (const l of cfg.story_langues) { if ((r -= l.poids) < 0) { code = l.code; break; } }
code = code.replace(/[^a-z]/g, '');
const recents = $input.all().map(i => i.json).filter(j => j.vocabulary_id)
  .sort((a, b) => String(b.derniere_utilisation).localeCompare(String(a.derniere_utilisation)))
  .slice(0, cfg.exclusions.story_mots).map(j => parseInt(j.vocabulary_id, 10)).filter(Number.isInteger);
const exclure = recents.length ? `AND v.id NOT IN (${recents.join(',')})` : '';
const sql = `SELECT v.id, v.word, v.transliteration, t.translation, l.code
FROM vocabulary v
JOIN languages l ON l.id = v.language_id
JOIN categories c ON c.id = v.category_id
JOIN vocabulary_translations t ON t.vocabulary_id = v.id AND t.target_locale = 'fr'
WHERE l.code = '${code}' AND v.active = 1 AND v.needs_validation = 0 AND v.type = 'word'
  AND c.slug NOT LIKE '%religion%'
  AND CHAR_LENGTH(v.word) <= 18 AND CHAR_LENGTH(t.translation) <= 26
  ${exclure}
ORDER BY RAND() LIMIT 1`;
return [{ json: { sql, code } }];
"""), [1540, -200])
    w.add('Tirer un mot', 'n8n-nodes-base.mySql', 2.4,
          {'operation': 'executeQuery', 'query': '={{ $json.sql }}', 'options': {}},
          [1760, -200], credentials=cred('db'), **RETRY)
    w.add('Mot au hasard', *code(r"""
// Repli (pas de Reel publié aujourd'hui) : mot tiré au hasard dans les langues pondérées.
const m = $json;
if (!m.id) throw new Error('aucun mot trouvé pour ' + $('Requête mot').first().json.code);
return [{ json: { source: 'hasard', mots: [{ id: m.id, word: m.word, transliteration: m.transliteration,
                                            translation: m.translation, code: m.code }] } }];
"""), [1980, -300])
    # Cohérence avec le Reel du jour : même langue (ou même paire de langues en duel), mot tiré du Reel.
    w.add('Mots du reel', 'n8n-nodes-base.mySql', 2.4, {'operation': 'executeQuery', 'options': {}, 'query': (
        "SELECT v.id, v.word, v.transliteration, t.translation, l.code, vv.genre, j.ord "
        "FROM vocabag_videos vv "
        "CROSS JOIN JSON_TABLE(vv.word_ids, '$[*]' COLUMNS (ord FOR ORDINALITY, wid INT PATH '$')) j "
        "JOIN vocabulary v ON v.id = j.wid "
        "JOIN languages l ON l.id = v.language_id "
        "JOIN vocabulary_translations t ON t.vocabulary_id = v.id AND t.target_locale = 'fr' "
        "WHERE vv.id = (SELECT MAX(id) FROM vocabag_videos "
        "WHERE (posted_on_youtube = 1 OR posted_on_instagram = 1 OR posted_on_facebook = 1) "
        "AND created_at >= NOW() - INTERVAL 20 HOUR) ORDER BY j.ord")},
          [1320, -450], credentials=cred('db'), alwaysOutputData=True, **RETRY)
    w.add('Choisir dans le reel', *code(r"""
// word_ids du Reel : solo = [id…] ; duel = [A1, B1, A2, B2…] (paires côte à côte). On tire un mot, ou une paire.
const rows = $input.all().map(i => i.json).filter(r => r && r.id);
if (!rows.length) return [{ json: { source: 'hasard', mots: [] } }];
const pick = a => a[Math.floor(Math.random() * a.length)];
const m = r => ({ id: r.id, word: r.word, transliteration: r.transliteration, translation: r.translation, code: r.code });
if (rows[0].genre === 'duel') {
  const paires = {};
  for (const r of rows) (paires[Math.floor((Number(r.ord) - 1) / 2)] ??= []).push(r);
  const ok = Object.values(paires).filter(p => p.length === 2 && p[0].code !== p[1].code);
  if (ok.length) return [{ json: { source: 'reel', genre: 'duel', mots: pick(ok).map(m) } }];
}
return [{ json: { source: 'reel', genre: rows[0].genre, mots: [m(pick(rows))] } }];
"""), [1540, -450])
    w.add('Mot du reel ?', *if_true('$json.mots.length > 0'), [1760, -450])
    w.add('Données question', *code(r"""
// 1 mot : « Comment dit-on « X » en turc ? » ; 2 mots (duel) : « … en darija et en arabe littéraire ? ».
const cfg = $('Config').first().json;
const d = $json;
const L = c => cfg.langues[c] || { nom: c, drapeau: '' };
const [a, b] = d.mots;
return [{ json: { mots: d.mots, source: d.source, rendu: { template: 'question', data: {
  traduction: a.translation,
  langue_nom: b ? `${L(a.code).nom} et en ${L(b.code).nom}` : L(a.code).nom,
  drapeau: b ? L(a.code).drapeau + L(b.code).drapeau : L(a.code).drapeau,
  langue_code: a.code } } } }];
"""), [1980, -200])
    media = "={{ $('Config').first().json.media_service }}"
    w.add('Rendre question', *http('POST', media + '/render', auth='media', body_json='={{ JSON.stringify($json.rendu) }}'),
          [2200, -200], credentials=cred('media'), **RETRY)
    w.add('Story question', *code(r"""
const c = $('Créneau').first().json, d = $('Données question').first().json;
return [{ json: { type: 'story', images: [$json.url], video: '', texte: '', langue_description: 'fr',
                  langue_apprise: d.mots.map(m => m.code).join('+'), source: 'stories', source_ref: c.source_ref, desc_ids: {} } }];
"""), [2420, -200])
    # Une seule publication par exécution (question, réponse ou reel) → un seul bloc « Publier story ».
    w.add('Publier story', *call('ig'), [3300, 900], **SOFT)
    w.add('Story publiée ?', *if_true('$json.ok === true'), [3520, 900])
    w.add('Après question ?', *if_true("$('Créneau').first().json.action === 'question'"), [3740, 800])
    w.add('Après réponse ?', *if_true("$('Créneau').first().json.action === 'reponse'"), [3960, 900])
    w.add('Lignes à mémoriser', *code(r"""
// Une ligne par mot (2 en duel) : la réponse de 21h les relit toutes.
const c = $('Créneau').first().json;
return $('Données question').first().json.mots.map(m => ({ json: {
  vocabulary_id: m.id, mot: m.word, langue_apprise: m.code, traduction: m.translation,
  translitteration: m.transliteration || '', jour: c.jour } }));
"""), [3960, 600])
    mot_cols = {
        'vocabulary_id': '={{ $json.vocabulary_id }}', 'mot': '={{ $json.mot }}',
        'langue_apprise': '={{ $json.langue_apprise }}', 'traduction': '={{ $json.traduction }}',
        'translitteration': '={{ $json.translitteration }}',
        'derniere_utilisation': '={{ new Date().toISOString() }}',
        'statut': 'question_publiee', 'jour': '={{ $json.jour }}',
    }
    w.add('Mémoriser mot', *dt('vb_story_mots', 'insert', **dt_columns(mot_cols), options={}), [4180, 600])

    # ---------- réponse (+ visuel final)
    w.add('Question du jour', *dt('vb_story_mots', 'get', returnAll=True,
                                  **dt_filter(('jour', '={{ $json.jour }}'), ('statut', 'question_publiee')),
                                  options={}), [1540, 100], executeOnce=True, alwaysOutputData=True)
    w.add('Données réponse', *code(r"""
const cfg = $('Config').first().json;
const qs = $input.all().map(i => i.json).filter(j => j.vocabulary_id).sort((a, b) => a.id - b.id);
if (!qs.length) return [];   // pas de question publiée aujourd'hui → rien à répondre
const L = c => cfg.langues[c] || { nom: c, drapeau: '' };
const q = qs[0];
if (qs.length >= 2) {        // duel : les deux mots, chacun avec sa langue
  return [{ json: { q, langues: qs.map(x => x.langue_apprise).join('+'), rendu: { template: 'answer_duel', data: {
    traduction: q.traduction,
    mots: qs.slice(0, 2).map(x => ({ mot: x.mot, translitteration: x.translitteration, langue_code: x.langue_apprise,
                                     langue_nom: L(x.langue_apprise).nom, drapeau: L(x.langue_apprise).drapeau })) } } } }];
}
const l = L(q.langue_apprise);
return [{ json: { q, langues: q.langue_apprise, rendu: { template: 'answer', data: {
  traduction: q.traduction, mot: q.mot, translitteration: q.translitteration,
  langue_nom: l.nom, drapeau: l.drapeau, langue_code: q.langue_apprise } } } }];
"""), [1760, 100])
    w.add('Rendre réponse', *http('POST', media + '/render', auth='media', body_json='={{ JSON.stringify($json.rendu) }}'),
          [1980, 100], credentials=cred('media'), **RETRY)
    w.add('Story réponse', *code(r"""
const c = $('Créneau').first().json, r = $('Données réponse').first().json;
return [{ json: { type: 'story', images: [$json.url], video: '', texte: '', langue_description: 'fr',
                  langue_apprise: r.langues, source: 'stories', source_ref: c.source_ref, desc_ids: {} } }];
"""), [2200, 100])
    w.add('Marquer répondu', *dt('vb_story_mots', 'update',
                                  **dt_filter(('jour', "={{ $('Créneau').first().json.jour }}"), ('statut', 'question_publiee')),
                                  **dt_columns({'statut': 'reponse_publiee'}), options={}), [4180, 1000])
    w.add('Derniers mots', *dt('vb_story_mots', 'get', returnAll=True, options={}), [4400, 1000],
          executeOnce=True, alwaysOutputData=True)
    w.add('Données visuel final', *code(r"""
// « Apprends ces mots sur VocaBag » : le mot du jour + jusqu'à 3 mots récents (écritures natives).
const rows = $input.all().map(i => i.json).filter(j => j.mot)
  .sort((a, b) => String(b.derniere_utilisation).localeCompare(String(a.derniere_utilisation))).slice(0, 4);
return [{ json: { rendu: { template: 'cta', data: {
  mots: rows.map(r => ({ mot: r.mot, traduction: r.traduction, langue_code: r.langue_apprise })) } } } }];
"""), [4620, 1000])
    w.add('Rendre visuel final', *http('POST', media + '/render', auth='media', body_json='={{ JSON.stringify($json.rendu) }}'),
          [4840, 1000], credentials=cred('media'), **RETRY)
    w.add('Story visuel final', *code(r"""
const c = $('Créneau').first().json;
return [{ json: { type: 'story', images: [$json.url], video: '', texte: '', langue_description: 'fr',
                  langue_apprise: '', source: 'stories', source_ref: `story-cta-${c.jour}`, desc_ids: {} } }];
"""), [5060, 1000])
    w.add('Publier visuel final', *call('ig'), [5280, 1000], **SOFT)

    # ---------- reel du jour en story
    w.add('Reel du jour', 'n8n-nodes-base.mySql', 2.4, {'operation': 'executeQuery', 'options': {}, 'query': (
        # Reel du jour = publié sur AU MOINS un réseau (2026-09-30) : un échec Instagram ne supprime plus la story.
        "SELECT folder FROM vocabag_videos "
        "WHERE (posted_on_youtube = 1 OR posted_on_instagram = 1 OR posted_on_facebook = 1) "
        "AND created_at >= NOW() - INTERVAL 20 HOUR ORDER BY id DESC LIMIT 1")},
          [1760, 400], credentials=cred('db'), alwaysOutputData=True, **RETRY)
    w.add('Fichier du reel', *code(r"""
const f = String($json.folder || '').replace(/[^A-Za-z0-9_]/g, '');
if (!f) return [{ json: { absent: true } }];
return [{ json: { absent: false, chemin: `/files/vocabag/${f}_final_sound.mp4`, folder: f } }];
"""), [1980, 400])
    w.add('Reel trouvé ?', *if_true('!$json.absent'), [2200, 400])
    w.add('Lire vidéo', 'n8n-nodes-base.readWriteFile', 1, {'fileSelector': '={{ $json.chemin }}', 'options': {}},
          [2420, 300])
    w.add('Héberger vidéo', *http('POST', media + '/stage?ext=mp4', auth='media', binary=True),
          [2640, 300], credentials=cred('media'), **RETRY)
    w.add('Story reel', *code(r"""
const c = $('Créneau').first().json;
return [{ json: { type: 'story', images: [], video: $json.url, texte: '', langue_description: 'fr',
                  langue_apprise: '', source: 'stories', source_ref: c.source_ref,
                  desc_ids: {} } }];
"""), [2860, 300])

    w.chain('Chaque heure', 'Config', 'Créneau', 'Déjà publiée ?', 'Aiguiller', 'Question ?')
    w.link('Test', 'Config')
    w.link('Question ?', 'Mots du reel', 0)
    w.chain('Mots du reel', 'Choisir dans le reel', 'Mot du reel ?')
    w.link('Mot du reel ?', 'Données question', 0)
    w.link('Mot du reel ?', 'Mots récents', 1)
    w.link('Question ?', 'Réponse ?', 1)
    w.link('Réponse ?', 'Question du jour', 0)
    w.link('Réponse ?', 'Reel ?', 1)
    w.link('Reel ?', 'Reel du jour', 0)
    # Échecs : pas d'alerte (demande utilisateur) ; chaque essai est tracé dans vb_journal par le bloc IG.
    w.chain('Mots récents', 'Requête mot', 'Tirer un mot', 'Mot au hasard', 'Données question')
    w.chain('Données question', 'Rendre question', 'Story question', 'Publier story')
    w.chain('Question du jour', 'Données réponse', 'Rendre réponse', 'Story réponse', 'Publier story')
    w.chain('Reel du jour', 'Fichier du reel', 'Reel trouvé ?')
    w.link('Reel trouvé ?', 'Lire vidéo', 0)
    w.chain('Lire vidéo', 'Héberger vidéo', 'Story reel', 'Publier story')
    w.chain('Publier story', 'Story publiée ?', 'Après question ?')
    w.link('Après question ?', 'Lignes à mémoriser', 0)
    w.link('Lignes à mémoriser', 'Mémoriser mot')
    w.link('Après question ?', 'Après réponse ?', 1)
    w.link('Après réponse ?', 'Marquer répondu', 0)
    w.chain('Marquer répondu', 'Derniers mots', 'Données visuel final', 'Rendre visuel final', 'Story visuel final',
            'Publier visuel final')
    integrer(w, 'Publier story', wf_ig, 'IG story')
    integrer(w, 'Publier visuel final', wf_ig, 'IG visuel final')
    stories_facebook(w)
    return w.dump()


def stories_facebook(w):
    """Stories Facebook (page VocaBag, 2026-09-30) : chaque « Story … » alimente aussi cette branche.

    Reliée en 2e sortie, elle s'exécute après la branche Instagram (ordre v1) et ne la modifie pas.
    Photo : /photos (published=false) → /photo_stories. Vidéo (Reel) : /video_stories start → envoi binaire
    sur rupload (Facebook refuse de lire staging.vocabag.com : robots.txt derrière le mot de passe) → finish.
    Erreurs ignorées ; pas de ligne vb_journal (« Déjà publiée ? » ne filtre pas par plateforme).
    """
    y = max(n['position'][1] for n in w.nodes) + 320
    x0 = min(n['position'][0] for n in w.nodes)
    X = lambda i: x0 + i * 220
    fb = dict(credentials=cred('fb'), **SOFT)

    def req(method, url, query=None, headers=None, binary=False):
        t, v, p = http(method, url, auth='fb', binary=binary)
        p['options'] = {'response': {'response': {'neverError': True}}}
        if query:
            p.update({'sendQuery': True, 'queryParameters': {'parameters': [{'name': a, 'value': b} for a, b in query.items()]}})
        if headers:
            p.update({'sendHeaders': True, 'headerParameters': {'parameters': [{'name': a, 'value': b} for a, b in headers.items()]}})
        return t, v, p

    w.add('Entrée · FB story', 'n8n-nodes-base.noOp', 1, {}, [X(0), y])
    w.add('Vidéo ? · FB story', *if_true("!!$json.video"), [X(1), y])
    w.add('Démarrer vidéo · FB story', *req('POST', FB_PAGE + '/video_stories', {'upload_phase': 'start'}),
          [X(2), y - 120], **fb)
    w.add('Lire vidéo · FB story', 'n8n-nodes-base.readWriteFile', 1,
          {'fileSelector': "={{ $('Fichier du reel').first().json.chemin }}", 'options': {}}, [X(3), y - 120], **SOFT)
    w.add('Taille vidéo · FB story', *code(r"""
// Taille exacte du fichier : requise par rupload.facebook.com (en-tête file_size).
const buf = await this.helpers.getBinaryDataBuffer(0, 'data');
return [{ json: { file_size: buf.length }, binary: $input.first().binary }];
"""), [X(4), y - 120], **SOFT)
    w.add('Envoyer vidéo · FB story', *req('POST', "={{ $('Démarrer vidéo · FB story').first().json.upload_url }}",
          headers={'offset': '0', 'file_size': '={{ $json.file_size }}'}, binary=True), [X(5), y - 120], **fb)
    w.add('Publier vidéo · FB story', *req('POST', FB_PAGE + '/video_stories',
          {'upload_phase': 'finish', 'video_id': "={{ $('Démarrer vidéo · FB story').first().json.video_id }}"}),
          [X(6), y - 120], **fb)
    w.add('Photo non publiée · FB story', *req('POST', FB_PAGE + '/photos',
          {'url': '={{ ($json.images || [])[0] }}', 'published': 'false'}), [X(2), y + 120], **fb)
    w.add('Publier photo · FB story', *req('POST', FB_PAGE + '/photo_stories', {'photo_id': '={{ $json.id }}'}),
          [X(3), y + 120], **fb)
    for src in ('Story question', 'Story réponse', 'Story reel', 'Story visuel final'):
        w.link(src, 'Entrée · FB story')
    w.link('Entrée · FB story', 'Vidéo ? · FB story')
    w.link('Vidéo ? · FB story', 'Démarrer vidéo · FB story', 0)
    w.link('Vidéo ? · FB story', 'Photo non publiée · FB story', 1)
    w.chain('Démarrer vidéo · FB story', 'Lire vidéo · FB story', 'Taille vidéo · FB story',
            'Envoyer vidéo · FB story', 'Publier vidéo · FB story')
    w.link('Photo non publiée · FB story', 'Publier photo · FB story')


# ================================================================== 6. NEWSLETTER HEBDO
# Chaque dimanche : nouveaux articles du blog (service média → dépôt de prod) + vidéos de la semaine avec leurs
# mots (vocabag_videos), envoyés un par un aux abonnés via le SMTP Gmail. Déclencheur « Test » : POST
# /webhook/vb-newsletter-test + en-tête X-Media-Token → envoi au seul email_test, sans rien marquer.
def wf_newsletter():
    w = W('newsletter', 'VocaBag - Newsletter hebdo')
    w.add('Chaque dimanche', 'n8n-nodes-base.scheduleTrigger', 1.2,
          {'rule': {'interval': [{'field': 'cronExpression', 'expression': '0 10 * * 0'}]}}, [0, 0])
    w.add('Test', 'n8n-nodes-base.webhook', 2,
          {'httpMethod': 'POST', 'path': 'vb-newsletter-test', 'authentication': 'headerAuth',
           'responseMode': 'onReceived', 'options': {}}, [0, 200], credentials={'httpHeaderAuth': CRED_MEDIA['httpHeaderAuth']},
          webhookId=str(uuid.uuid5(uuid.NAMESPACE_URL, 'vb-newsletter-test')))
    config_node(w, [220, 0], 'telegram', 'media', 'newsletter')
    w.add('Préparer', *code(r"""
// Une seule newsletter par semaine ISO en production (un 2e déclenchement la même semaine ne fait rien).
const cfg = $('Config').first().json;
const test = $('Test').isExecuted;
const d = new Date(new Date().toLocaleString('en-US', { timeZone: 'Europe/Paris' }));
const t = new Date(Date.UTC(d.getFullYear(), d.getMonth(), d.getDate()));
t.setUTCDate(t.getUTCDate() + 4 - (t.getUTCDay() || 7));
const sem = Math.ceil(((t - Date.UTC(t.getUTCFullYear(), 0, 1)) / 864e5 + 1) / 7);
const semaine = `${t.getUTCFullYear()}-S${String(sem).padStart(2, '0')}`;
if (!test && $getWorkflowStaticData('global').derniere_semaine === semaine) return [];
return [{ json: { test, semaine, jours: cfg.newsletter.jours, max_videos: cfg.newsletter.max_videos } }];
"""), [440, 0])
    w.add('Articles récents', *http('POST', "={{ $('Config').first().json.media_service }}/blog/recents", auth='media',
                                    body_json='={{ JSON.stringify({ jours: $json.jours }) }}'),
          [660, 0], credentials=cred('media'), **RETRY)
    w.add('Vidéos de la semaine', 'n8n-nodes-base.mySql', 2.4, {'operation': 'executeQuery', 'options': {}, 'query': (
        "=SELECT id, genre, language_id_a, language_id_b, word_ids, youtube_video_id "
        "FROM vocabag_videos WHERE posted_on_youtube = 1 AND youtube_video_id IS NOT NULL "
        "AND posted_youtube_at >= NOW() - INTERVAL {{ Number($('Préparer').first().json.jours) }} DAY "
        "ORDER BY posted_youtube_at DESC LIMIT {{ Number($('Préparer').first().json.max_videos) }}")},
          [880, 0], credentials=cred('db'), alwaysOutputData=True, **RETRY)
    w.add('Requête mots', *code(r"""
const ids = [...new Set($('Vidéos de la semaine').all().flatMap(i => {
  try { return JSON.parse(i.json.word_ids || '[]'); } catch { return []; }
}).map(Number).filter(n => Number.isInteger(n) && n > 0))];
const sql = ids.length
  ? `SELECT v.id, v.word, v.transliteration, t.translation FROM vocabulary v
     LEFT JOIN vocabulary_translations t ON t.vocabulary_id = v.id AND t.target_locale = 'fr'
     WHERE v.id IN (${ids.join(',')})`
  : 'SELECT NULL AS id FROM DUAL WHERE 1 = 0';
return [{ json: { sql } }];
"""), [1100, 0])
    w.add('Mots', 'n8n-nodes-base.mySql', 2.4, {'operation': 'executeQuery', 'query': '={{ $json.sql }}', 'options': {}},
          [1320, 0], credentials=cred('db'), alwaysOutputData=True, **RETRY)
    w.add('Composer', *code(JS_ESC + r"""
const cfg = $('Config').first().json.newsletter;
const p = $('Préparer').first().json;
const utm = `utm_source=newsletter&utm_medium=email&utm_campaign=hebdo-${p.semaine}`;
const lien = (url) => url + (url.includes('?') ? '&' : '?') + utm;
const articles = ($('Articles récents').first().json.articles || []);
const mots = Object.fromEntries($('Mots').all().map(i => i.json).filter(m => m.id).map(m => [Number(m.id), m]));
const L = { 1: ['darija', '🇲🇦'], 2: ['arabe littéraire', '🇸🇦'], 3: ['anglais', '🇬🇧'], 4: ['allemand', '🇩🇪'],
  5: ['espagnol', '🇪🇸'], 6: ['portugais', '🇧🇷'], 7: ['italien', '🇮🇹'], 8: ['néerlandais', '🇳🇱'], 9: ['russe', '🇷🇺'],
  10: ['turc', '🇹🇷'], 11: ['chinois', '🇨🇳'], 12: ['coréen', '🇰🇷'] };
const videos = $('Vidéos de la semaine').all().map(i => i.json).filter(v => v.youtube_video_id).map(v => {
  const a = L[v.language_id_a] || ['?', ''], b = L[v.language_id_b];
  const titre = v.genre === 'duel' && b ? `${a[0]} vs ${b[0]} ${a[1]}${b[1]}`
              : v.genre === 'phrase' ? `Mots et phrases en ${a[0]} ${a[1]}` : `3 mots en ${a[0]} ${a[1]}`;
  let ids = []; try { ids = JSON.parse(v.word_ids || '[]'); } catch {}
  return { titre: titre.charAt(0).toUpperCase() + titre.slice(1), url: `https://www.youtube.com/shorts/${v.youtube_video_id}`,
           mots: ids.map(id => mots[Number(id)]).filter(Boolean) };
});
if (!articles.length && !videos.length) return [{ json: { vide: true } }];

const h2 = t => `<h2 style="font-size:18px;color:#1a1a2e;margin:32px 0 12px">${t}</h2>`;
const blocArticles = articles.map(a => `
  <a href="${e(lien(cfg.site + '/blog/' + a.slug))}" style="display:block;text-decoration:none;border:1px solid #e5e7eb;border-radius:12px;padding:14px 16px;margin:0 0 10px">
    ${a.category ? `<div style="font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.5px;color:#0d9488">${e(a.category)}</div>` : ''}
    <div style="font-size:16px;font-weight:700;color:#1a1a2e;margin:2px 0 4px">${e(a.title)}</div>
    <div style="font-size:14px;color:#555;line-height:1.5">${e(a.description)}</div>
  </a>`).join('');
const blocVideos = videos.map(v => `
  <div style="border:1px solid #e5e7eb;border-radius:12px;padding:14px 16px;margin:0 0 10px">
    <div style="font-size:16px;font-weight:700;color:#1a1a2e;margin:0 0 6px">${e(v.titre)}</div>
    ${v.mots.map(m => `<div style="font-size:14px;color:#333;line-height:1.6"><b>${e(m.word)}</b>${m.transliteration ? ` <span style="color:#888">(${e(m.transliteration)})</span>` : ''}${m.translation ? ` — ${e(m.translation)}` : ''}</div>`).join('')}
    <a href="${e(v.url)}" style="display:inline-block;margin-top:8px;font-size:14px;color:#0d9488;font-weight:600">▶ Regarder la vidéo</a>
  </div>`).join('');
const intro = [articles.length ? `${articles.length} nouvel${articles.length > 1 ? 's' : ''} article${articles.length > 1 ? 's' : ''}` : '',
               videos.length ? `${videos.length} vidéo${videos.length > 1 ? 's' : ''} de vocabulaire` : ''].filter(Boolean).join(' et ');
const html = `<!DOCTYPE html><html lang="fr"><head><meta charset="UTF-8"></head>
<body style="font-family:system-ui,-apple-system,sans-serif;background:#f4f6f8;margin:0;padding:20px">
<div style="max-width:560px;margin:0 auto;background:#fff;border-radius:16px;padding:32px;box-shadow:0 2px 20px rgba(0,0,0,.07)">
  <div style="font-size:32px">🎒</div>
  <h1 style="color:#1a1a2e;font-size:22px;margin:8px 0 8px">Votre semaine de vocabulaire</h1>
  <p style="color:#555;line-height:1.6;margin:0">Au programme cette semaine : ${e(intro)}.</p>
  ${articles.length ? h2('📚 Nouveau sur le blog') + blocArticles : ''}
  ${videos.length ? h2('🎬 Les vidéos de la semaine') + blocVideos : ''}
  <div style="text-align:center;margin:32px 0 8px">
    <a href="${e(lien(cfg.site + '/'))}" style="display:inline-block;background:#2dd4bf;color:#fff;text-decoration:none;padding:14px 28px;border-radius:10px;font-weight:600;font-size:15px">Réviser ces mots sur VocaBag →</a>
  </div>
  <p style="margin-top:24px;font-size:12px;color:#999;line-height:1.5">
    Vous recevez cet e-mail suite à votre inscription à la newsletter sur vocabag.com.<br>
    <a href="%%DESINSCRIPTION%%" style="color:#999">Se désinscrire</a> · <a href="${e(cfg.site)}/confidentialite" style="color:#999">Confidentialité</a>
  </p>
</div></body></html>`;
const sujet = articles.length ? `🎒 ${articles[0].title}` : `🎒 Vos ${videos.length} vidéos de vocabulaire de la semaine`;
return [{ json: { vide: false, sujet, html, nb_articles: articles.length, nb_videos: videos.length } }];
"""), [1540, 0])
    w.add('Contenu ?', *if_true('$json.vide !== true'), [1760, 0])
    w.add('Mode test ?', *if_true("$('Préparer').first().json.test"), [1980, -100])
    w.add('Destinataire test', *code(r"""
return [{ json: { email: $('Config').first().json.newsletter.email_test, unsubscribe_token: 'test' } }];
"""), [2200, -200])
    w.add('Abonnés', 'n8n-nodes-base.mySql', 2.4, {'operation': 'executeQuery', 'options': {}, 'query': (
        'SELECT email, unsubscribe_token FROM newsletter_subscribers WHERE unsubscribed_at IS NULL ORDER BY id')},
          [2200, 0], credentials=cred('db'), alwaysOutputData=True, **RETRY)
    w.add('Personnaliser', *code(r"""
const c = $('Composer').first().json;
const cfg = $('Config').first().json.newsletter;
const test = $('Préparer').first().json.test;
const out = $input.all().map(i => i.json).filter(a => a.email && a.unsubscribe_token).map(a => ({ json: {
  email: a.email, sujet: (test ? '[TEST] ' : '') + c.sujet,
  html: c.html.replace('%%DESINSCRIPTION%%', cfg.desinscription + encodeURIComponent(a.unsubscribe_token)),
} }));
return out.length ? out : [{ json: { email: '' } }];
"""), [2420, -100])
    w.add('À envoyer ?', *if_true('!!$json.email'), [2640, -100])
    w.add('Envoyer', 'n8n-nodes-base.emailSend', 2.1,
          {'fromEmail': "={{ $('Config').first().json.newsletter.expediteur }}", 'toEmail': '={{ $json.email }}',
           'subject': '={{ $json.sujet }}', 'emailFormat': 'html', 'html': '={{ $json.html }}',
           'options': {'appendAttribution': False}}, [2860, -200], credentials=cred('smtp'), **SOFT)
    w.add('Bilan', *code(JS_ESC + r"""
const p = $('Préparer').first().json;
const c = $('Composer').first().json;
const dest = $('Personnaliser').all().filter(i => i.json.email).length;
const res = $('Envoyer').isExecuted ? $('Envoyer').all().map(i => i.json) : [];
const ko = res.filter(r => r.error).length;
if (!p.test) $getWorkflowStaticData('global').derniere_semaine = p.semaine;
const texte = `📧 Newsletter ${p.test ? '<b>[TEST]</b> ' : ''}${e(p.semaine)} : ${res.length - ko}/${dest} envoyée(s)`
  + (ko ? ` · ⚠️ ${ko} échec(s) : ${e(res.find(r => r.error).error.message || '')}` : '')
  + `\n${c.nb_articles} article(s), ${c.nb_videos} vidéo(s) · « ${e(c.sujet)} »`;
return [{ json: { texte } }];
"""), [3080, -100])
    w.add('Bilan Telegram', *telegram('={{ $json.texte }}'), [3300, -100], credentials=cred('tg'))
    w.add('Rien à envoyer', *telegram(
        "=📧 Newsletter {{ $('Préparer').first().json.semaine }} : ni article ni vidéo sur la période, pas d'envoi."),
          [1980, 200], credentials=cred('tg'))
    w.chain('Chaque dimanche', 'Config')
    w.link('Test', 'Config')
    w.chain('Config', 'Préparer', 'Articles récents', 'Vidéos de la semaine', 'Requête mots', 'Mots', 'Composer',
            'Contenu ?')
    w.link('Contenu ?', 'Mode test ?', 0)
    w.link('Contenu ?', 'Rien à envoyer', 1)
    w.link('Mode test ?', 'Destinataire test', 0)
    w.link('Mode test ?', 'Abonnés', 1)
    w.link('Destinataire test', 'Personnaliser')
    w.link('Abonnés', 'Personnaliser')
    w.link('Personnaliser', 'À envoyer ?')
    w.link('À envoyer ?', 'Envoyer', 0)
    w.link('À envoyer ?', 'Bilan', 1)
    w.link('Envoyer', 'Bilan')
    w.link('Bilan', 'Bilan Telegram')
    return w.dump()


# ================================================================== 5. ERREURS (alerte Telegram)
# Workflow d'erreur n8n (settings.errorWorkflow) des workflows de production : une exécution automatique
# qui plante envoie un message sur @vocabagbot. Même erreur (workflow + nœud + message) : une alerte par 6 h.
def wf_erreurs():
    w = W('erreurs', 'Erreurs - alerte Telegram')
    w.add('Erreur', 'n8n-nodes-base.errorTrigger', 1, {})
    w.add('Préparer alerte', *code(JS_ESC + r'''
const d = $input.first().json;
const wf = d.workflow || {};
const ex = d.execution || {};
const err = ex.error || d.trigger?.error || {};
const noeud = ex.lastNodeExecuted || err.node?.name || (d.trigger ? 'déclencheur' : '?');
const message = String(err.message || err.description || 'erreur inconnue').trim();
// Anti-répétition : même workflow + nœud + message → une alerte toutes les 6 h au plus.
const memo = $getWorkflowStaticData('global');
memo.vues = memo.vues || {};
const maintenant = Date.now(), fenetre = 6 * 3600 * 1000;
for (const [k, t] of Object.entries(memo.vues)) if (maintenant - t > fenetre) delete memo.vues[k];
const cle = [wf.id, noeud, message.slice(0, 120)].join('|');
if (memo.vues[cle]) return [];
memo.vues[cle] = maintenant;
const heure = new Date().toLocaleString('fr-FR', { timeZone: 'Europe/Paris' });
const texte = [
  `🚨 <b>${e(wf.name || wf.id || 'workflow ?')}</b> a planté`,
  `Nœud : <code>${e(noeud)}</code>`,
  `Erreur : ${e(message.slice(0, 600))}`,
  `${e(heure)}` + (ex.mode ? ` · mode ${e(ex.mode)}` : ''),
  ex.url ? `<a href="${e(ex.url)}">Voir l'exécution</a>` : '',
].filter(Boolean).join('\n');
return [{ json: { texte } }];
'''))
    w.add('Alerte Telegram', *telegram('={{ $json.texte }}', CONFIG_CHAT_ID), credentials=cred('tg'))
    w.chain('Erreur', 'Préparer alerte', 'Alerte Telegram')
    return w.dump()


if __name__ == '__main__':
    OUT.mkdir(exist_ok=True)
    for old in OUT.glob('*.json'):          # anciens fichiers (11 workflows avant la fusion)
        if old.name != '06_muz_stories.json':   # généré par build_muz_stories.py
            old.unlink()
    builders = [('01_carrousel', wf_carrousel), ('02_stories', wf_stories), ('03_blog', wf_blog),
                ('04_erreurs', wf_erreurs), ('05_newsletter', wf_newsletter), ('07_prompt', wf_prompt)]
    for fname, fn in builders:
        data = fn()
        names = {n['name'] for n in data['nodes']}
        # Références de nœuds : toujours $('Nom') littéral (renommées par integrer()), jamais $(variable).
        texte = json.dumps([n['parameters'] for n in data['nodes']], ensure_ascii=False)
        assert not re.search(r"\$\((?!['\"])", texte), (fname, 'référence de nœud dynamique $(…)')
        for ref in re.findall(r"\$\('([^']+)'\)", texte):
            assert ref in names, (fname, 'nœud inexistant', ref)
        for src, c in data['connections'].items():
            assert src in names, (fname, src)
            for outs in c['main']:
                for t in outs:
                    assert t['node'] in names, (fname, t['node'])
        (OUT / f'{fname}.json').write_text(json.dumps(data, ensure_ascii=False, indent=2))
        print(f"{fname}.json  {len(data['nodes'])} nœuds")
