# Muzrappel — publication n8n (YouTube + Instagram)

> État relevé le 2026-09-20. Aucune valeur de secret dans ce document.

## Quel workflow publie ?

> 2026-09-26 : renommé « Muzrappel Video » (même id), voir « Voix + karaoké » plus bas.

Dans le n8n Docker (`n8n-n8n-1`, `/root/n8n/docker-compose.yml`), le workflow **actif** pour Muzrappel est
**« test Muzrappel »** (id `y3L85t9otCm68hS5`, 70 nœuds : génération de la vidéo via l'API RVM, soundtrack, overlay ebook, puis
YouTube + Instagram + suivi en base). Les workflows **« Muzrappel creator »** (`rk1LpyKNMaCbOyHq`) et **« Muzrappel postor »**
(`0VTikRMMYBOPOZkk`) sont **inactifs** ; leur ancienne logique (YouTube seul) n'est plus celle en production.
Ne pas se fier au nom : c'est « test Muzrappel » qui tourne.

## Où sont construites la description YouTube et la légende Instagram

Un seul point : le nœud Code **`Code in JavaScript1`** produit le champ `phrase`
(`PHRASES[catégorie]` — ebook gratuit + accroche par catégorie — puis `\n\n` + hashtags), lu par :
- `Upload a video` (YouTube) : `description` = `phrase` (avec `lien dans la bio` remplacé par « lien dans la section À propos de la chaîne ») ;
- `Publish` (Instagram Reels) : `caption` = titre + `phrase`.
(`Create audio` lit un autre `phrase`, celui de la boucle des scènes : sans lien.)

## Message de contact en fin de description (2026-09-20)

`phrase` se termine désormais par (français, après les hashtags, formulé comme une recommandation pour un service tiers) :

> 🎬 Envie d’apprendre à générer gratuitement des vidéos similaires avec l’IA ? Contacte RapidVideoMaker : contact.rapidvideomaker@gmail.com

Ajouté via la constante `CONTACT_MSG` dans `Code in JavaScript1` : `phrase: \`${basePhrase}\\n\\n${tagsString}\\n\\n${CONTACT_MSG}\``.
Seul ce nœud a été modifié ; connexions identiques ; workflow actif après redémarrage. **Non prouvé en réel** : la prochaine
publication planifiée. Pour retirer le message : supprimer `CONTACT_MSG` et sa concaténation dans ce nœud.

## Procédure pour modifier un workflow actif

Export (`n8n export:workflow --id=… --output=…`) → patch du JSON → `n8n import:workflow` (désactive le workflow) →
`n8n publish:workflow --id=…` → `docker restart n8n-n8n-1`. Vérifier avant qu'aucune exécution n'est en cours
(`execution_entity.status` dans `/var/lib/docker/volumes/n8n_n8n_data/_data/database.sqlite`, en lecture seule). Les exports
contiennent des jetons en clair : ne pas les afficher, les supprimer après usage (aussi dans le conteneur, en `-u root`).
Autres workflows non couverts par ce message : Muzreminder, rvm-actu.

## Voix + karaoké générés par RapidVideoMaker (2026-09-26)

Le workflow s'appelle désormais **« Muzrappel Video »** (même id `y3L85t9otCm68hS5`). Chaque scène était auparavant
produite en deux temps : `text_to_mp3` (nœuds `Create audio` → `Poll audio` → `If ready1` / `Wait 10s4` → `Download mp3` →
`Save mp3` → `Read/Write Files from Disk1` → `Merge image / audio`), puis `image_to_video` avec image + MP3 et texte fixe.
**Ces 8 nœuds sont supprimés** : `Save background` va directement dans `Loop over scenes`, et `Create video` n'envoie plus
que l'image (champ `data`) + les options. RapidVideoMaker génère la voix à partir du texte de la scène dans le même job et
colore chaque mot au moment où il est prononcé.

Options de `Define video setting` (en plus du cadrage existant) :

| Option | Valeur | Pourquoi |
|---|---|---|
| `text_mode` | `karaoke` | texte synchronisé mot à mot sur la voix |
| `voice` | `fr-FR-HenriNeural` | même voix qu'avant (`text_to_mp3`) |
| `karaoke_style` | `fill` | les mots prononcés restent en vert (lecture facile) |
| `highlight_color` | `#2BD49A` | vert émeraude du logo (`#169666`) éclairci pour rester lisible sur fond sombre |
| `box_color` | `#111c1e@0.60` | fond sombre de l'icône Muz Rappel (l'ancien `green@0.40` rendait le vert illisible) |
| `karaoke_lines` | `4` | une phrase entière par page ; un titre d'intro long se découpe en pages |

`text_effect`/`text_effect_intensity` retirés (ignorés en karaoké). Chaque scène dure la voix + 0,6 s (petite pause entre
les phrases, ≈ +10 s sur une vidéo de 17 scènes). Couleurs choisies sur rendus d'essai (fond sombre vs ardoise `#5f797c` de
l'ebook, vert exact vs éclairci). Une scène sans texte arrête le workflow avec un message clair (la voix exige un texte).
Sauvegarde du workflow d'avant : export du 2026-09-26 (scratchpad de session, contient des jetons — non conservé ici).

### Mode test (2026-09-26) — terminé, workflow en production

Test réel réussi le 2026-09-26 (exécution 1632, ~24 min, hadith « Lorsqu'un homme rentre dans sa maison et mentionne le nom
d'Allah ») : 17 scènes karaoké, intro, soundtrack, overlay ebook, vidéo de 93,5 s. Fichiers générés supprimés ensuite
(`script.json` conservé ; la ligne n'a pas été marquée `video_create=1`, elle reste éligible). Liaison
`Save video concatened with soundtrack` → `Get had upd req sql` **rétablie**, note « MODE TEST » retirée, workflow publié et
actif (Schedule 07:00, `GENERIC_TIMEZONE=Europe/Paris`) le soir même.

## Garde-fou des boucles d'attente (2026-09-26) — Muzrappel Video + Vocabag Video

Incident : le 2026-09-26 à 17:03 UTC, un job `text_to_mp3` de Vocabag a échoué (edge-tts « No audio was received », raté
ponctuel de Microsoft : la même phrase passe ensuite). Les boucles `Poll → IF status == ready → Wait → Poll` ne testaient que
`ready` : un job en `error` faisait tourner la boucle **sans fin** (exécution 1630 : 2 962 appels à `jobs.php` en 4 h, vidéo
du jour non publiée). Correctif : un nœud Code **`Garde <nom du IF>`** sur la branche « pas prêt » de chaque boucle, avant
le Wait (16 dans Vocabag Video, 4 dans Muzrappel Video) :
- statut `error` → l'exécution s'arrête en erreur avec le message de RapidVideoMaker (`jobs.php` renvoie `error`) ;
- un même job encore en cours après 1 h → arrêt en erreur (horodatage gardé dans `$getWorkflowStaticData('node')`, clé
  `exécution:job_id`, une seule entrée par nœud).
La branche « prêt » est inchangée. Statuts possibles de `jobs.php` : `uploaded`, `queued`, `processing`, `ready`, `error`
(annulé → `error` ; job expiré/inconnu → HTTP 410/404, déjà une erreur du nœud HTTP).
Arrêter une exécution bloquée : pas de commande CLI ; `docker restart n8n-n8n-1` la coupe (elle reste affichée
« running » dans `execution_entity`, sans plus rien exécuter).

### Vocabag Video — un échec Instagram ne bloque plus YouTube (2026-09-26)

Relance manuelle du soir (exécution 1633) : le nœud Instagram `Publish` a expiré (« Timed out waiting for container to
become ready after 40 attempts », Reel resté `IN_PROGRESS` côté Instagram). Les deux branches partent de
`Enregistrer video (suivi)` et Instagram passe en premier : son erreur arrêtait l'exécution **avant YouTube**. `Publish` est
en `onError: continueRegularOutput`, suivi d'un IF **`Instagram publié ?`** (`$json.id` non vide) avant
`Marquer Instagram (suivi)`. **Piège** : ce nœud communautaire n'a qu'une sortie ; quand l'erreur est tolérée, il la renvoie
comme un résultat normal sur cette sortie (un premier essai en `continueErrorOutput` a donc marqué à tort
`posted_on_instagram = 1` avec un `instagram_media_id` vide — ligne 8, dossier `20260927_060247_phrase_ar_technology`,
2026-09-27). Désormais un échec Instagram laisse `posted_on_instagram = 0` et l'exécution continue vers YouTube (elle finit
en « success » : repérer les échecs Instagram par la base, pas par le statut de l'exécution). Délai du nœud pour un Reel :
40 × 2 s = 80 s d'attente du traitement Instagram (`resources/reels/index.js`) — 2 échecs de suite le 2026-09-26/27.
**Muzrappel Video** a la même
structure (Instagram `Publish` et YouTube en parallèle après `Code in JavaScript1`) : corrigé le 2026-09-28 (section suivante).

### Muzrappel Video — même garde Instagram + attente des Reels portée à 5 min (2026-09-28)

Exécution 1694 (07h, 2026-09-28) : même timeout (« after 40 attempts », Reel de 31 Mo `IN_PROGRESS`). YouTube était déjà
en ligne (sa branche passe avant), mais l'exécution s'est arrêtée en erreur et le Reel Instagram n'a pas été publié.
- **Workflow** : `Publish` en `onError: continueRegularOutput` → IF **`Instagram publié ?`** (`$json.id` non vide) →
  `Marquer posted Instagram` (`muzrappel.posted_on_instagram`). Un échec Instagram laisse la ligne à 0, et l'exécution
  finit en « success ». Sauvegarde avant modification : `/root/muzrappel-video-avant-garde-ig-20260928.json`.
- **Nœud communautaire** (vaut pour tous les workflows, dont Vocabag Video) : `resources/reels/index.js`
  `maxPollAttempts` 40 → **150** (× 2 s ≈ 5 min) ; `Instagram.node.js` : `maxTotalTimeMs = 90000` fixe →
  `Math.max(90000, maxPollAttempts * pollIntervalMs + 30000)` (sinon la limite de 90 s coupait quand même).
  Originaux : `*.orig_before_timeout` à côté des fichiers. **Perdu à chaque mise à jour du nœud**, comme le patch
  `graph.instagram.com`. Pour vérifier la syntaxe, utiliser `node --check`, pas `require()` : hors de n8n, le module
  `n8n-workflow` est introuvable.
- Le redémarrage de 22h16 (Paris) a coupé une exécution manuelle de « Coran tiktok » (1737), restée « running » en base.

### Bilan et rattrapage du Reel du 28 (2026-09-29)

- Exécutions planifiées karaoké : 1636 (27/09, ligne 2216) et 1755 (29/09, ligne 2776) OK YouTube + Instagram
  (`Publish` ~75 s) ; 1694 (28/09, ligne 3675) YouTube OK, Instagram en timeout (avant le patch ci-dessus).
- **Reel 3675 rattrapé** via un workflow manuel temporaire (`Lancer le test` → `Publish` reels), **supprimé ensuite** :
  - l'envoi binaire (`binaryPropertyName` = fichier local lu sur `/files/muzrappel/…`) échoue toujours en
    « Bad request » (token `IG…` : `video_url` public obligatoire) ;
  - OK avec `Video URL` = `download_url` du job overlay staging de l'exécution d'origine (toujours servi, même taille
    que le fichier local) + légende de cette exécution (`Execute had sql.title` + `Code in JavaScript1.phrase`) :
    publié en 66 s (media id 17956426221017972), puis `muzrappel.posted_on_instagram = 1` pour la ligne 3675
    (utilisateur MySQL `dashboard` en lecture seule ; `z3r0`, config RVM staging, a les droits).
  - **Méthode à réutiliser** pour tout Reel manqué : même URL + légende, jamais la vidéo du jour déjà publiée
    (doublon public).
- Chaîne vérifiée : workflow actif (07:00 Paris), `Publish` en `continueRegularOutput` → IF `Instagram publié ?` →
  `Marquer posted Instagram` (aucun faux 1 en cas d'échec), patch 150 tentatives chargé (n8n redémarré après).
- **À surveiller** : la credential « Instagram account 2 » date du 2026-09-19 et n'a jamais été renouvelée — si c'est
  un jeton long Instagram (60 j), expiration vers le **2026-11-18** (non vérifié ; le renouvellement automatique par le
  nœud n'est pas confirmé). À renouveler avant, sinon seuls les Reels échoueront (YouTube continue).

### Alertes d'erreur (2026-09-28)

Muzrappel Video et Muzrappel Commenter ont `settings.errorWorkflow = VbErreursAlerte1` : un plantage envoie un message
sur @vocabagbot (workflow, nœud, erreur, lien vers l'exécution ; une alerte par 6 h pour une même erreur). Voir
`vocabag-social-instagram.md` §18. Non branché sur Coran tiktok / coran tiktok v2.


## Facebook (ajouté le 2026-09-30)

Branche parallèle à Instagram/YouTube depuis `Code in JavaScript1` :
`Publish Facebook` (Facebook Graph API, `POST graph-video.facebook.com/v23.0/501465773057138/videos`, onError continue)
→ `Facebook publié ?` (`$json.id` non vide) → `Marquer posted Facebook` (`UPDATE muzrappel SET posted_on_facebook = 1`).

- Credential **« Facebook Graph account 2 »** (`SZI9tiIqTC821bCa`, `facebookGraphApi` ; « Facebook Graph account » = token VocaBag) = **token de page** Muz Rappel (pas un token utilisateur :
  `GET me` doit renvoyer « Muz Rappel »). ID Graph de la page : `501465773057138` (≠ `61572267555268`, ID visible dans l'URL).
- `file_url` = `download_url` du job overlay staging (même que le Reel Instagram), `title` = titre DB,
  `description` = titre + `phrase` (même texte qu'Insta/YT, contact `contact.rapidvideomaker@gmail.com`),
  « lien dans la bio » → « lien dans la section « À propos » de la page ».
- Workflow de test manuel  : tests réels OK le 2026-09-30 (workflows de test supprimés ensuite ; pour revérifier un token, `GET me` doit renvoyer le nom de la page).

## Vérification quotidienne — « Muzrappel - Vérification » (2026-10-04)
Workflow `rJgojRa6KiXK49S5`, actif, généré par `social/setup/build_muz_verif.py` → `social/workflows/08_muz_verif.json`.
Pourquoi : les workflows Muz restent en « success » quand un Publish échoue (onError continue) ; le 2026-10-03/04 les tokens
Meta invalidés ont bloqué toutes les publications Instagram/Facebook sans aucune alerte.
- **08h15** (Paris) : le Reel du jour (Muzrappel Video, 07:00) est-il sur YouTube (playlist uploads), Instagram (@muz.rappel,
  `REELS` du jour) et la page Facebook (vidéo du jour avec permalien `/reel/`) ?
- **21h45** : idem + stories du jour ≥ 3 (09h Reel, 13h question, 20h réponse) sur Instagram et Facebook.
- Toujours : erreurs d'API (code 190 → token Meta à régénérer ; 401 → credential YouTube) et stock
  `script_create=1 AND video_create=0` (< 7 → alerte).
- Alerte Telegram via **@muzrappelbot** (conversation privée, chat `6980427615`, credential « Telegram - muzrappelbot » `TnA0UuhJFPlr5QZu`), **uniquement en cas de
  problème** ; le bouton « Execute workflow » (mode test) envoie toujours le bilan complet. `Config.forcer_moment` = 'matin' | 'soir'.
- Lecture Instagram via le token de page (« Facebook Graph account 2 ») sur graph.facebook.com.

## Alertes Telegram dédiées Muzrappel — @muzrappelbot (2026-10-04)
- Bot **@muzrappelbot**, credential n8n « Telegram - muzrappelbot » (`TnA0UuhJFPlr5QZu`), conversation privée (chat `6980427615`).
- Workflow d'erreurs **« Muzrappel - Erreurs »** (`eUErVpA15sgk6j1m`, copie de « Erreurs - alerte Telegram » avec ce bot,
  anti-répétition 6 h ; JSON `social/workflows/10_muz_erreurs.json`). `settings.errorWorkflow` = `eUErVpA15sgk6j1m` pour
  Muzrappel Video, Muz Rappel - Stories, Muzrappel Commenter et Muzrappel - Vérification (générateurs mis à jour).
- Les workflows VocaBag restent sur « Erreurs - alerte Telegram » (@vocabagbot).

## Muzrappel Commenter — réponses Instagram (2026-10-04)
Workflow `eSABPiZmB8tjkT39` (21h Paris). Branche YouTube inchangée. Branche Instagram ajoutée sur le même Schedule Trigger :
`IG · Médias récents` (30 derniers médias @muz.rappel) → `IG · Médias commentés` (≥ 1 commentaire, 60 derniers jours) →
`IG · Commentaires` (`/{media}/comments`, champs `replies{username}`) → `IG · Réponses à faire` → `IG · Répondre`
(`POST /{comment}/replies?message=`). Credential « Facebook Graph account 2 » (token de page, permission `instagram_manage_comments`).
- Détection et textes **copiés du nœud YouTube** « Code in JavaScript » (`detectAminLanguage`, `extractEmojis`, réponses ar/fr +
  emojis du commentaire). Si on change les réponses YouTube, changer aussi `IG · Réponses à faire`.
- Ignorés : commentaires de muz.rappel, commentaires auxquels muz.rappel a déjà répondu (anti-doublon, sans état).
- Nœuds HTTP en `onError: continueRegularOutput` : une erreur Instagram ne bloque pas YouTube.
- Sauvegarde avant modif : `/root/n8n-backup-ig-via-fb-20261004/eSABPiZmB8tjkT39_avant_insta.json`.

## Publication Meta fiable + rattrapage automatique (2026-10-04)
- **Sous-workflows « Meta - Publier Reel (VocaBag) »** `WFKPD7GzMgbEuM5F` et **« (Muz Rappel) »** `7YuYOdKwY7tZQceq`
  (`social/setup/build_meta_reel.py`) : Reel Instagram (conteneur → statut FINISHED → `media_publish`) puis vidéo de page
  Facebook, en nœuds HTTP standard (graph.facebook.com, token de page). **Le nœud communautaire
  `@mookielianhd/n8n-nodes-instagram` n'est plus utilisé** (ses patchs locaux sautaient à chaque mise à jour).
  3 tentatives par plateforme, 60 s d'écart, pas de nouvelle tentative si token invalide (code 190) ; échec définitif →
  **alerte Telegram immédiate** (@vocabagbot / @muzrappelbot). Retour : `{instagram_id, instagram_erreur, facebook_id, facebook_erreur}`.
- **Vocabag Video / Muzrappel Video** (`social/setup/patch_video_publication.py`) : `Publish` + `Publish Facebook` remplacés par
  `Préparer publication` → `Publier Reel (IG + FB)` → `Instagram publié ?` / `Facebook publié ?` → `Marquer…`. Chaque jour, fiche
  `channels/<compte>/videos/_publications/AAAA-MM-JJ.json` (légende, titres, chemin de la vidéo, dossier, id en base ; purgée à 7 j).
- **Rattrapage automatique** dans « Muzrappel - Vérification » et « VocaBag - Vérification » (`social/setup/verif_rattrapage.py`) :
  Reel absent d'Instagram/Facebook (hors erreur de token) → fiche du jour → vidéo lue sur disque → `POST /stage` (service média,
  URL publique) → sous-workflow (alerter=false) → UPDATE du suivi → message « 🔁 … republié automatiquement » ou raison de l'échec.
  YouTube manquant : alerte seulement. Chaîne testée de bout en bout le 2026-10-04 (publication simulée).
- Sauvegardes avant modification : `/root/n8n-backup-ig-via-fb-20261004/*_avant_meta_reel.json`.
