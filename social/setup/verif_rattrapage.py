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
// Anti-doublon : publication du jour encore en cours (< 1 h), ou plateforme dont l'ID de la fiche existe toujours
// (lu directement : GET /{id}). On ne republie que si l'objet est introuvable ou en erreur.
const minutes = t => t ? (Date.now() - Date.parse(t)) / 60000 : Infinity;
const ageMin = minutes(fiche.ecrit_a);
const objIG = lire('R · IG objet'), objFB = lire('R · FB objet');
const enLigneIG = !!(fiche.instagram_id && objIG.id && !objIG.error);
const enLigneFB = !!(fiche.facebook_id && objFB.id && !objFB.error && objFB.status?.video_status !== 'error');
const instagram = ev.rat.instagram >= 0 && !enLigneIG;
const facebook = ev.rat.facebook >= 0 && !enLigneFB;
let raison = '';
if (!fiche || !fiche.video_path) raison = 'fiche du jour introuvable (_publications/' + $now.setZone('Europe/Paris').toISODate() + '.json)';
else if (fiche.statut === 'en_cours' && ageMin < 60) raison = `publication du jour encore en cours (lancée il y a ${Math.round(ageMin)} min) — pas de rattrapage pour éviter un doublon`;
else if (!instagram && !facebook) raison = `déjà en ligne d'après l'API (Instagram ${fiche.instagram_id || '—'}, Facebook ${fiche.facebook_id || '—'}), non retrouvé par la recherche du jour`;
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

FICHE_MAJ_JS = r"""
// Rattrapage réussi : la fiche du jour reçoit les nouveaux ID → la vérification suivante ne republie pas
const prep = $('R · Préparer').first().json;
const r = $input.first().json;
if (!r.instagram_id && !r.facebook_id) return [];
const f = prep.fiche || {};
return [{ json: { ...f, statut: 'termine', rattrape_a: new Date().toISOString(),
                  instagram_id: r.instagram_id || f.instagram_id || '', facebook_id: r.facebook_id || f.facebook_id || '' } }];
"""

BILAN_JS = r"""
// Réécrit le bilan de « Évaluer » avec le résultat du rattrapage.
const e = s => String(s ?? '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
const ev = $('Évaluer').first().json;
const lire = n => { try { return $(n).first().json; } catch (x) { return null; } };
const prep = lire('R · Préparer') || { raison: 'rattrapage non lancé' };
const res = lire('R · Publier') || {};
const pb = [...ev.pb];
const fiche = prep.fiche || {};
const maj = (idx, nom, cle) => {
  if (idx < 0) return;
  const idFiche = fiche[cle + '_id'];
  if (idFiche && prep[cle] === false && !/encore en cours/.test(prep.raison || ''))
    pb[idx] = `ℹ️ ${nom} : publié (${e(idFiche)}) et toujours en ligne d'après l'API, mais non retrouvé par la recherche du jour — pas de republication`;
  else if (res[cle + '_id']) pb[idx] = `🔁 ${nom} : Reel manquant, republié automatiquement (${e(res[cle + '_id'])})`;
  else pb[idx] += ` — rattrapage échoué : ${e(prep.raison || res[cle + '_erreur'] || res.error?.message || 'erreur inconnue')}`;
};
maj(ev.rat.instagram, 'Instagram', 'instagram');
maj(ev.rat.facebook, 'Facebook', 'facebook');
const vrais = pb.filter(x => !x.startsWith('🔁') && !x.startsWith('ℹ️'));
const titre = vrais.length ? `🚨 <b>${ev.label} — ${vrais.length} problème(s)</b>`
  : pb.some(x => x.startsWith('🔁')) ? `🔁 <b>${ev.label} — Reel rattrapé</b>` : `ℹ️ <b>${ev.label} — rien à rattraper</b>`;
const texte = `${titre} (${ev.entete})\n\n` + [...pb, ...(ev.test ? ev.ok.map(x => '✔️ ' + x) : [])].join('\n');
return [{ json: { envoyer: true, problemes: vrais.length, texte: texte.slice(0, 4000), chat_id: ev.chat_id } }];
"""


def ajouter(nodes, link, ns, node_fn, http_fn, sous_wf, dossier, cred_db, sql_js, x0, y0=350, cred_fb=None):
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

    def http_id(name, pos, champ, fields):
        # lecture directe de l'objet publié dont l'ID est dans la fiche ('aucun' → erreur → considéré absent)
        d = http_fn(name, pos, "={{ $('Config').first().json.graph }}/{{ ($('R · Fiche').first().json.data ?? "
                    f"$('R · Fiche').first().json).{champ} || 'aucun' }}}}", cred_fb, {'fields': fields})
        d['id'] = str(uuid.uuid5(uuid.NAMESPACE_URL, ns + 'rattrapage/' + name))
        return d
    x, y = x0, y0
    nodes += [
        iff('Rattraper ?', '$json.rat.instagram >= 0 || $json.rat.facebook >= 0', [x, 100]),
        nd('R · Lire fiche', 'n8n-nodes-base.readWriteFile', 1.1,
           {'fileSelector': f"={dossier}/{{{{ $now.setZone('Europe/Paris').toISODate() }}}}.json",
            'options': {'dataPropertyName': 'data'}}, [x + 220, y], **cont),
        nd('R · Fiche', 'n8n-nodes-base.extractFromFile', 1.1, {'operation': 'fromJson', 'options': {}}, [x + 440, y], **cont),
        http_id('R · IG objet', [x + 440, y + 200], 'instagram_id', 'id,media_product_type,permalink'),
        http_id('R · FB objet', [x + 660, y + 200], 'facebook_id', 'id,permalink_url,status'),
        nd('R · Lire vidéo', 'n8n-nodes-base.readWriteFile', 1.1,
           {'fileSelector': "={{ ($('R · Fiche').first().json.data ?? $('R · Fiche').first().json).video_path || '/introuvable.mp4' }}",
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
        nd('R · Fiche à jour', 'n8n-nodes-base.code', 2, {'jsCode': FICHE_MAJ_JS.strip() + '\n'}, [x + 1760, y - 300],
           onError='continueRegularOutput'),
        nd('R · Fiche en fichier', 'n8n-nodes-base.convertToFile', 1.1,
           {'operation': 'toJson', 'mode': 'each', 'binaryPropertyName': 'data_json', 'options': {}}, [x + 1980, y - 300],
           onError='continueRegularOutput'),
        nd('R · Écrire fiche', 'n8n-nodes-base.readWriteFile', 1.1,
           {'operation': 'write', 'fileName': f"={dossier}/{{{{ $now.setZone('Europe/Paris').toISODate() }}}}.json",
            'dataPropertyName': 'data_json', 'options': {}}, [x + 2200, y - 300], onError='continueRegularOutput'),
    ]
    for a, b, o in [
        ('Rattraper ?', 'R · Lire fiche', 0), ('Rattraper ?', 'Envoyer ?', 1),
        ('R · Lire fiche', 'R · Fiche', 0), ('R · Fiche', 'R · IG objet', 0), ('R · IG objet', 'R · FB objet', 0),
        ('R · FB objet', 'R · Lire vidéo', 0), ('R · Lire vidéo', 'R · Héberger', 0),
        ('R · Héberger', 'R · Préparer', 0), ('R · Préparer', 'R · Publier ?', 0),
        ('R · Publier ?', 'R · Publier', 0), ('R · Publier ?', 'R · Bilan', 1),
        ('R · Publier', 'R · Fiche à jour', 0), ('R · Fiche à jour', 'R · Fiche en fichier', 0),
        ('R · Fiche en fichier', 'R · Écrire fiche', 0),
        ('R · Publier', 'R · Suivi SQL', 0), ('R · Suivi SQL', 'R · SQL ?', 0),
        ('R · SQL ?', 'R · Marquer', 0), ('R · SQL ?', 'R · Bilan', 1), ('R · Marquer', 'R · Bilan', 0),
        ('R · Bilan', 'Envoyer ?', 0),
    ]:
        link(a, b, o)
