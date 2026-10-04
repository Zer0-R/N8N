"""Rattrapage automatique des Reels manqués — partagé par build_muz_verif.py et build_vocabag_verif.py (2026-10-04).

Quand « Évaluer » signale le Reel du jour absent d'Instagram et/ou de Facebook (champ `rat` = index du message dans
`pb`, -1 sinon), la vérification :
  1. relit la fiche du jour écrite par le workflow vidéo (_publications/AAAA-MM-JJ.json : légende, titres, chemin) ;
  2. lit la vidéo sur le disque et la rend publique via le service média (POST /stage) ;
  3. la publie avec le sous-workflow « Meta - Publier Reel » du compte (alerter=false : le bilan est fait ici) ;
  4. met à jour le suivi en base (SQL construit par `sql_js`) ;
  5. réécrit le message : « 🔁 … rattrapé » ou la raison de l'échec.
Le YouTube manquant n'est pas rattrapé (simple alerte).
"""
import uuid

CRED_MEDIA = {'httpHeaderAuth': {'id': 'L2zYP3cEvAgZVffN', 'name': 'VocaBag media (X-Media-Token)'}}
MEDIA_URL = 'http://host.docker.internal:8791'

PREPARER_JS = r"""
// Fiche du jour + URL publique de la vidéo → données pour le sous-workflow « Meta - Publier Reel »
const ev = $('Évaluer').first().json;
const lire = n => { try { return $(n).first().json; } catch (x) { return {}; } };
let fiche = lire('R · Fiche');
fiche = fiche.data ?? fiche;
if (Array.isArray(fiche)) fiche = fiche[0] || {};
const media = lire('R · Héberger');
// Anti-doublon : publication du jour encore en cours (< 1 h), ou plateforme déjà publiée d'après la fiche
const ageMin = fiche.ecrit_a ? (Date.now() - Date.parse(fiche.ecrit_a)) / 60000 : Infinity;
const instagram = ev.rat.instagram >= 0 && !fiche.instagram_id;
const facebook = ev.rat.facebook >= 0 && !fiche.facebook_id;
let raison = '';
if (!fiche || !fiche.video_path) raison = 'fiche du jour introuvable (_publications/' + $now.setZone('Europe/Paris').toISODate() + '.json)';
else if (fiche.statut === 'en_cours' && ageMin < 60) raison = `publication du jour encore en cours (lancée il y a ${Math.round(ageMin)} min) — pas de rattrapage pour éviter un doublon`;
else if (!instagram && !facebook) raison = `déjà publié d'après la fiche (Instagram ${fiche.instagram_id || '—'}, Facebook ${fiche.facebook_id || '—'}) : pas encore visible dans l'API ?`;
else if (!media.url) raison = 'vidéo non hébergée : ' + String(media.error || media.message || 'fichier ' + fiche.video_path + ' illisible').slice(0, 200);
return [{ json: {
  publier: !raison, raison,
  fiche,
  video_url: media.url || '',
  caption: fiche.caption, fb_title: fiche.fb_title, fb_description: fiche.fb_description,
  share_to_feed: fiche.share_to_feed,
  instagram, facebook,
  alerter: false,
  contexte: 'Rattrapage automatique — ' + (fiche.folder || ''),
} }];
"""

BILAN_JS = r"""
// Réécrit le bilan de « Évaluer » avec le résultat du rattrapage.
const e = s => String(s ?? '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
const ev = $('Évaluer').first().json;
const lire = n => { try { return $(n).first().json; } catch (x) { return null; } };
const prep = lire('R · Préparer') || { raison: 'rattrapage non lancé' };
const res = lire('R · Publier') || {};
const pb = [...ev.pb];
const maj = (idx, nom, id, err) => {
  if (idx < 0) return;
  if (id) pb[idx] = `🔁 ${nom} : Reel manquant, republié automatiquement (${e(id)})`;
  else pb[idx] += ` — rattrapage échoué : ${e(prep.raison || err || res.error?.message || 'erreur inconnue')}`;
};
maj(ev.rat.instagram, 'Instagram', res.instagram_id, res.instagram_erreur);
maj(ev.rat.facebook, 'Facebook', res.facebook_id, res.facebook_erreur);
const vrais = pb.filter(x => !x.startsWith('🔁'));
const titre = vrais.length ? `🚨 <b>${ev.label} — ${vrais.length} problème(s)</b>` : `🔁 <b>${ev.label} — Reel rattrapé</b>`;
const texte = `${titre} (${ev.entete})\n\n` + [...pb, ...(ev.test ? ev.ok.map(x => '✔️ ' + x) : [])].join('\n');
return [{ json: { envoyer: true, problemes: vrais.length, texte: texte.slice(0, 4000), chat_id: ev.chat_id } }];
"""


def ajouter(nodes, link, ns, node_fn, http_fn, sous_wf, dossier, cred_db, sql_js, x0, y0=350):
    """Ajoute la branche de rattrapage entre « Évaluer » et « Envoyer ? »."""
    def nd(name, type_, version, params, pos, **extra):
        d = node_fn(name, type_, version, params, pos, **extra)
        d['id'] = str(uuid.uuid5(uuid.NAMESPACE_URL, ns + 'rattrapage/' + name))
        return d

    def iff(name, expr, pos):
        return nd(name, 'n8n-nodes-base.if', 2, {
            'conditions': {'options': {'caseSensitive': True, 'leftValue': '', 'typeValidation': 'loose', 'version': 1},
                           'conditions': [{'id': str(uuid.uuid5(uuid.NAMESPACE_URL, ns + 'if/' + name)),
                                           'leftValue': '={{ ' + expr + ' }}', 'rightValue': '',
                                           'operator': {'type': 'boolean', 'operation': 'true', 'singleValue': True}}],
                           'combinator': 'and'}, 'options': {}}, pos)

    cont = {'onError': 'continueRegularOutput', 'alwaysOutputData': True}
    x, y = x0, y0
    nodes += [
        iff('Rattraper ?', '$json.rat.instagram >= 0 || $json.rat.facebook >= 0', [x, 100]),
        nd('R · Lire fiche', 'n8n-nodes-base.readWriteFile', 1.1,
           {'fileSelector': f"={dossier}/{{{{ $now.setZone('Europe/Paris').toISODate() }}}}.json",
            'options': {'dataPropertyName': 'data'}}, [x + 220, y], **cont),
        nd('R · Fiche', 'n8n-nodes-base.extractFromFile', 1.1, {'operation': 'fromJson', 'options': {}}, [x + 440, y], **cont),
        nd('R · Lire vidéo', 'n8n-nodes-base.readWriteFile', 1.1,
           {'fileSelector': "={{ ($json.data ?? $json).video_path || '/introuvable.mp4' }}",
            'options': {'dataPropertyName': 'data'}}, [x + 660, y], **cont),
        nd('R · Héberger', 'n8n-nodes-base.httpRequest', 4.2,
           {'method': 'POST', 'url': f'{MEDIA_URL}/stage', 'authentication': 'genericCredentialType',
            'genericAuthType': 'httpHeaderAuth', 'sendQuery': True,
            'queryParameters': {'parameters': [{'name': 'ext', 'value': 'mp4'}]},
            'sendBody': True, 'contentType': 'binaryData', 'inputDataFieldName': 'data',
            'options': {'response': {'response': {'neverError': True}}, 'timeout': 300000}},
           [x + 880, y], credentials=CRED_MEDIA, **cont),
        nd('R · Préparer', 'n8n-nodes-base.code', 2, {'jsCode': PREPARER_JS.strip() + '\n'}, [x + 1100, y]),
        iff('R · Publier ?', '$json.publier', [x + 1320, y]),
        nd('R · Publier', 'n8n-nodes-base.executeWorkflow', 1.1,
           {'source': 'database', 'workflowId': {'__rl': True, 'value': sous_wf, 'mode': 'id'},
            'mode': 'once', 'options': {'waitForSubWorkflow': True}}, [x + 1540, y - 100], onError='continueRegularOutput'),
        nd('R · Suivi SQL', 'n8n-nodes-base.code', 2, {'jsCode': sql_js.strip() + '\n'}, [x + 1760, y - 100]),
        iff('R · SQL ?', '!!$json.sql', [x + 1980, y - 100]),
        nd('R · Marquer', 'n8n-nodes-base.mySql', 2.4,
           {'operation': 'executeQuery', 'query': '={{ $json.sql }}', 'options': {}}, [x + 2200, y - 200],
           credentials=cred_db, **cont),
        nd('R · Bilan', 'n8n-nodes-base.code', 2, {'jsCode': BILAN_JS.strip() + '\n'}, [x + 2420, y]),
    ]
    for a, b, o in [
        ('Rattraper ?', 'R · Lire fiche', 0), ('Rattraper ?', 'Envoyer ?', 1),
        ('R · Lire fiche', 'R · Fiche', 0), ('R · Fiche', 'R · Lire vidéo', 0), ('R · Lire vidéo', 'R · Héberger', 0),
        ('R · Héberger', 'R · Préparer', 0), ('R · Préparer', 'R · Publier ?', 0),
        ('R · Publier ?', 'R · Publier', 0), ('R · Publier ?', 'R · Bilan', 1),
        ('R · Publier', 'R · Suivi SQL', 0), ('R · Suivi SQL', 'R · SQL ?', 0),
        ('R · SQL ?', 'R · Marquer', 0), ('R · SQL ?', 'R · Bilan', 1), ('R · Marquer', 'R · Bilan', 0),
        ('R · Bilan', 'Envoyer ?', 0),
    ]:
        link(a, b, o)
