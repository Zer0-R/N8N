# VocaBag Social — Instagram (carrousel Telegram, stories), blog, newsletter + Pinterest (préparé)

> **Point de reprise à jour : §20 (2026-09-28).** Workflows actifs : Vocabag Video, Carrousel, Stories, Blog,
> Newsletter hebdo (§19), Erreurs (§18).
>
> **Mise à jour 2026-09-27 : les 11 workflows ont été fusionnés en 3** (+ Vocabag Video inchangé) — voir §12.
> Les sections 1 à 9 décrivent la découpe d'origine ; la logique est la même, seuls les « sous-workflows »
> sont devenus des blocs de nœuds intégrés.

Créé le 2026-09-27. Fichiers : `/var/www/muz-video-template/social/`
(pas de dépôt git : ce dossier n'a ni historique ni sauvegarde).

```
social/
├── media-service/      service local vocabag-media (Python) : conversion, rendu HTML→image, hébergement
│   ├── server.py
│   ├── vocabag-media.service
│   └── assets/         logo VocaBag + police Inter (copiés de vocabag-staging)
├── public/             fichiers servis sur https://staging.vocabag.com/social-media/ (purge 14 j)
├── setup/
│   ├── build_workflows.py   génère workflows/*.json (MODIFIER ICI, pas dans les JSON)
│   ├── setup_n8n.py         Data Tables + lignes d'exemple + credentials + JSON prêts à importer
│   └── install.sh           media | apache | n8n | all
└── workflows/          8 workflows JSON importables (+ import/ : ids de credentials réels)
```

Le workflow Reel existant (**Vocabag Video**, `ixlsBGrzOeP8BmKk`, 19h00) n'est **pas modifié**.

## 1. Architecture

| Workflow (id) | Rôle | Déclencheur |
|---|---|---|
| **Config** (`VbSocialConfig01`) | seul nœud de configuration : chat_id, horaires des stories, exclusions X, URLs/UTM, limites, langues | appelé par tous |
| **Tirer description** (`VbSocialDescr001`) | texte + CTA + hashtags tirés séparément, anti-répétition, met à jour `derniere_utilisation` | sous-workflow |
| **Publier Instagram** (`VbSocialPubIG001`) | format commun → conteneurs → attente `FINISHED` → `media_publish` → permalien → journal | sous-workflow |
| **Publier Pinterest** (`VbSocialPubPin01`) | une épingle par image, lien UTM `utm_source=pinterest` ; **ne fait rien** tant que `pinterest.actif=false` | sous-workflow |
| **Carrousel Telegram** (`VbSocialCarrous1`) | album Telegram → carrousel (ou photo seule → post) | Telegram Trigger (@vocabagbot) |
| **Stories** (`VbSocialStories1`) | question 09h, réponse + visuel final 13h, Reel du jour en story 20h | Schedule horaire + `story_creneaux` |
| **Token Instagram** (`VbSocialTokenIG1`) | renouvelle le token longue durée, met à jour le credential, alerte si expiration < 15 j | lundi 04h |
| **Erreurs** (`VbSocialErreurs1`) | toute erreur non gérée → Telegram | Error workflow des 7 autres |

**Format commun** passé aux sous-workflows « Publier » :
`{ type: reel|carrousel|story|post, images[], video, texte, langue_description, langue_apprise, source, source_ref, desc_ids }`
(`source_ref` sert d'anti-doublon : `tg-album-<media_group_id>`, `tg-msg-<id>`, `story-question-<jour>`…).
Retour : `{ ok, post_id, permalink }` ou `{ ok:false, erreur }`.

**Gestion d'erreurs** : 3 essais espacés de 5 s sur chaque appel API (Instagram, Telegram, média, MySQL),
attente du conteneur limitée (`poll_max` × `poll_attente_s` = 5 min), erreurs Instagram renvoyées en clair
sur Telegram, journal `statut=echec` avec le message, Error workflow pour le reste.

## 2. Choix techniques (proposés, à valider)

- **Tables → Data Tables n8n** (plutôt que Google Sheets, MySQL ou JSON). Elles sont modifiables comme un
  tableur dans n8n (menu *Data tables*), sans migration de la base prod, sans droit MySQL supplémentaire
  (l'utilisateur `vocabag` n'a que SELECT) et sans OAuth Google. Un fichier JSON ne supporte pas les
  écritures concurrentes (`derniere_utilisation`).
- **Mots des stories → directement la base VocaBag** (`vocabulary` + `vocabulary_translations`, environ 12 600 mots validés
  avec translittération), en lecture seule. La table `vb_story_mots` garde l'historique : mot, langue,
  traduction, translittération, `derniere_utilisation`. Elle sert à l'anti-répétition (60 derniers mots exclus)
  et à retrouver la réponse. Catégorie « religion » exclue, mots de 18 caractères max. **Aucun texte n'est généré par IA** : les
  seuls textes libres sont les lignes des tables, écrites à l'avance.
- **Hébergement public → service local `vocabag-media` + Apache** (plutôt que Cloudinary ou S3). Pas de compte
  tiers ni de coût. Noms de fichiers aléatoires, purge après 14 jours, `noindex`. L'URL Telegram (qui contient le token du bot)
  ne sort jamais : n8n télécharge le fichier, le service le ré-héberge.
- **Rendu HTML→image** : Chromium (Playwright, déjà installé) + polices Noto (arabe, CJK) installées le 2026-09-27.
  `lang`/`dir="rtl"` corrects, logo VocaBag en bas, police Inter partout, fond `#0f9f8e`.

## 3. Tables (Data Tables n8n) — structure et exemples

`id` = identifiant système de n8n. `langue_apprise` accepte le code ou un nom (`ary`/`darija`, `zh`/`chinois`,
`ar`/`arabe`…, voir `Config → langues`). **Vide = ligne générique**, utilisée en repli.

**vb_textes** — `langue_description, langue_apprise, texte, derniere_utilisation`

| langue_description | langue_apprise | texte |
|---|---|---|
| fr | *(vide)* | Apprendre une langue, ce n'est pas tout retenir d'un coup : c'est revoir le bon mot au bon moment 🧠 Swipe pour découvrir les mots du jour 👉 |
| fr | darija | Tu veux parler darija comme au Maroc ? 🇲🇦 Voici quelques mots du quotidien, avec leur translittération… Swipe 👉 |
| fr | chinois | Le chinois te paraît impossible ? Commence par quelques caractères utiles 🇨🇳 … Swipe 👉 |
| en | *(vide)* | Learning a language isn't about memorizing everything at once — it's about reviewing the right word at the right time 🧠 … |
| en | arabe | Starting Arabic? 🇸🇦 Here are a few essential words, with transliteration… Swipe 👉 |
| en | chinois | Chinese looks hard? Start with a few useful characters 🇨🇳 … Swipe 👉 |

**vb_ctas** — `langue_description, texte, derniere_utilisation`

| langue_description | texte |
|---|---|
| fr | 📲 Apprends ces mots avec la répétition espacée sur VocaBag — lien en bio. |
| fr | 🎯 Quiz, révisions intelligentes et 12 langues : essaie VocaBag gratuitement (lien en bio). |
| fr | 💾 Enregistre ce post pour le réviser, puis continue sur VocaBag — lien en bio. |
| en | 📲 Learn these words with spaced repetition on VocaBag — link in bio. |
| en | 🎯 Quizzes, smart reviews and 12 languages: try VocaBag for free (link in bio). |
| en | 💾 Save this post to review it later, then keep going on VocaBag — link in bio. |

**vb_hashtags** — `langue_description, langue_apprise, hashtags, derniere_utilisation` (30 max, tronqué sinon)

| langue_description | langue_apprise | hashtags |
|---|---|---|
| fr | *(vide)* | #vocabag #apprendreunelangue #vocabulaire #langues #polyglotte #apprendre |
| fr | darija | #vocabag #darija #darijamarocaine #maroc #apprendreledarija #vocabulaire |
| fr | chinois | #vocabag #chinois #apprendrelechinois #mandarin #hanzi #vocabulaire |
| en | *(vide)* | #vocabag #languagelearning #vocabulary #polyglot #learnalanguage #studygram |
| en | arabe | #vocabag #learnarabic #arabic #arabiclanguage #arabicvocabulary #languagelearning |
| en | chinois | #vocabag #learnchinese #mandarin #chinesecharacters #hanzi #languagelearning |

**vb_story_mots** — `vocabulary_id, mot, langue_apprise, traduction, translitteration, derniere_utilisation, statut, jour`
(rempli automatiquement ; `statut` = `question_publiee` puis `reponse_publiee`). Exemple illustratif (seule
la 1re ligne correspond à un vrai mot de la base ; les ids des deux autres sont fictifs) :

| vocabulary_id | mot | langue_apprise | traduction | translitteration | statut | jour |
|---|---|---|---|---|---|---|
| 1166 | الصيد | ary | Pêche | Ssyd | reponse_publiee | 2026-09-28 |
| 317 | 钓鱼 | zh | Pêche | diàoyú | question_publiee | 2026-09-29 |
| 68 | Angeln | de | Pêche | | reponse_publiee | 2026-09-30 |

**vb_journal** — `plateforme, type, statut, post_id, permalink, langue_description, langue_apprise, texte_id, cta_id,
hashtags_id, source, source_ref, erreur, date_publication` (une ligne par tentative, `ok` ou `echec`).

**vb_tampon_album** — `media_group_id, message_id, file_id, kind, caption, recu_le` (tampon technique des
albums Telegram, vidé après traitement).

**Règles de tirage** : lignes de la `langue_description` → parmi elles, celles de la `langue_apprise` si elle
est renseignée, sinon (ou s'il n'y en a aucune) les lignes génériques → on exclut les X lignes utilisées le
plus récemment (`Config.exclusions` : textes 5, CTA 3, hashtags 3 ; on garde toujours au moins 1 candidate) →
tirage aléatoire → `derniere_utilisation = maintenant`. Les CTA n'ont pas de langue apprise. S'il n'existe
aucune ligne pour la langue de description, rien n'est publié et Telegram l'indique.

## 4. Credentials et permissions

| Credential n8n | État | Usage |
|---|---|---|
| **Instagram account** (`yWMtvSRb69T9GKW2`, `instagramApi`, jeton `IG…` de `vocabag_com`) | existant | publication (même credential que le Reel), refresh du token |
| **Telegram - vocabagbot** (`TgVocabagBot0001`) | existant | Telegram Trigger du carrousel, réponses, alertes |
| **Vocabag DB** (`qZ2NnMkubbTE5fNX`, MySQL, SELECT seul) | existant | mots des stories, Reel du jour (`vocabag_videos`) |
| **VocaBag media (X-Media-Token)** (Header Auth) | créé par `setup_n8n.py` | appels au service local |
| **n8n API (credential:update)** (Header Auth `X-N8N-API-KEY`) | **à créer** : clé API n8n limitée à `credential:update` (+ `credential:list`), passée via `N8N_REFRESH_KEY` | le workflow Token met à jour le credential Instagram |
| **Pinterest OAuth2** | plus tard | scopes `boards:read`, `pins:write` ; renseigner `pinterest.board_id` puis `actif: true` |

**Côté Meta (application Instagram)** — API Instagram avec connexion Instagram (`graph.instagram.com`) :
- permissions `instagram_business_basic` + `instagram_business_content_publish` (déjà utilisées par le Reel) ;
- compte professionnel (Business ou Creator). La Page Facebook n'est pas nécessaire avec ce type de jeton ;
- l'application doit être **en mode Live** (ou le compte déclaré testeur), sinon les publications échouent ;
- quota : 100 publications par l'API par 24 h glissantes (un carrousel compte pour une).

**Limites de l'API** (vérifiées dans la doc Meta à la date de rédaction, à revérifier en cas d'erreur) :
- carrousel : 10 médias maximum (réglable dans `Config.max_carrousel`) ;
- ratio des images du fil : 4:5 à 1.91:1. Le 3:4 est **hors plage** pour l'API, même si l'application mobile le propose.
  Avec `ratio_policy: 'pad'`, une image hors plage est complétée de blanc jusqu'en 4:5 et Telegram le signale.
  Passer à `'none'` pour tester si Instagram accepte le 3:4 ;
- stories : pas de légende, pas de stickers (quiz, sondage, lien) : **à ajouter à la main**, le workflow ne les simule pas ;
  vidéo de 60 s maximum.

## 5. Fonctionnement

**Carrousel** : envoyer à @vocabagbot un album de 2 à 10 photos (ou une seule photo pour un post simple).
Mieux vaut les envoyer « en fichier » : Telegram compresse les photos à 1280 px. Légende du **1er** message :
```
fr darija
desc: Texte personnalisé (optionnel, peut faire plusieurs lignes)
```
Chaque photo déclenche une exécution. Toutes passent par le tampon `vb_tampon_album`, attendent
`album_attente_s` (10 s), et seule l'exécution de la **dernière** photo traite l'album, dans l'ordre d'envoi.
Si l'album contient plus de 10 photos, rien n'est publié et Telegram prévient. Le retour Telegram contient le lien
du post et la description utilisée, ou l'erreur précise. Le même contenu est ensuite transmis au sous-workflow Pinterest.

**Stories** (`Config.story_creneaux`, heure de Paris) :
- 09h, `question` : mot tiré au hasard (langues pondérées) → image « Comment dit-on « X » en [langue] ? » ;
- 13h, `reponse` : image de la réponse (écriture native, translittération), puis visuel final
  « Apprends ces mots sur VocaBag / vocabag.com » ;
- 20h, `reel` : le Reel publié par Vocabag Video (19h) est republié en story vidéo.
  Instagram ne permet pas de repartager un Reel via l'API : la vidéo est donc envoyée une seconde fois.

Une story déjà publiée le même jour n'est jamais republiée (`vb_journal.source_ref`).

## 6. Installation

```bash
cd /var/www/muz-video-template/social/setup
bash install.sh media      # service vocabag-media + test depuis le conteneur n8n
bash install.sh apache     # alias /social-media/ sur le vhost staging.vocabag.com (sauvegarde /root/*.bak-*)
N8N_API_KEY=<clé> N8N_REFRESH_KEY=<clé limitée credential:update> bash install.sh n8n
```
`install.sh n8n` refuse de continuer si une exécution n8n est en cours (redémarrage final). Il publie Config,
Tirer description, Publier Instagram, Publier Pinterest, Erreurs et **Carrousel Telegram**, ce qui active le
webhook du bot. **Stories et Token restent non publiés** jusqu'aux tests.

## 7. Tests (dans cet ordre)

⚠️ Pas de mode « dry-run » : un test = une vraie publication sur `vocabag_com` (supprimable ensuite dans l'app).

1. **Service média** : `bash install.sh media` et `bash install.sh apache` affichent `{"ok": true}` et `test`.
2. **Carrousel, cas d'erreur (aucune publication)** :
   - envoyer un texte → message d'aide ;
   - un album de 11 photos → refus « 10 maximum » ;
   - légende `es` → « aucune ligne « es » dans : textes, ctas, hashtags » ;
   - depuis un autre compte Telegram → aucune réponse.
3. **Carrousel réel** : album de 3 images 4:5 avec la légende `fr darija` → vérifier le lien reçu, l'ordre des images,
   la description (texte darija + CTA + hashtags darija), `vb_journal` (ligne `ok`), `derniere_utilisation`
   mise à jour et `vb_tampon_album` vidé.
4. **Variantes** : `en chinois` + `desc: …` (description imposée, CTA et hashtags EN) ; une photo seule (post) ;
   une image 9:16 (complétée en 4:5 + avertissement).
5. **Stories** : dans Config, `story_forcer_action: 'question'`, puis exécuter Stories à la main dans l'interface.
   Vérifier la story et la ligne dans `vb_story_mots`. Même chose avec `'reponse'` (réponse + visuel final),
   puis `'reel'` (après 19h). Remettre `''` et **publier** Stories.
6. **Token** : exécuter Token Instagram à la main → pas d'alerte, credential mis à jour. Publier ensuite
   (lundi 04h), puis vérifier que le Reel de 19h publie toujours.
7. **Erreurs** : chaque échec doit arriver sur Telegram (🚨 / ❌).

## 8. Points non vérifiés / limites

- Rien n'a encore tourné dans n8n : JSON générés et nœuds Code testés hors ligne (logique de tirage, légende,
  album, contrôles), rendu HTML→image testé en local. L'import et les tests réels restent à faire (section 7).
- n8n 2.x : il n'est pas confirmé qu'un sous-workflow doive être *publié* pour être appelé. `install.sh`
  les publie par sécurité.
- Un redémarrage de n8n pendant les 10 s d'attente d'un album perd cet album : il suffit de le renvoyer.
- Le token Instagram doit avoir plus de 24 h et ne pas être expiré pour être renouvelé. Le refresh peut renvoyer un
  nouveau jeton : il est écrit dans le credential partagé avec le Reel, qui en profite aussi.

## 9. Blog : un article par carrousel (ajouté le 2026-09-27)

Chaque **carrousel** publié sur Instagram (pas une photo seule) donne un article de blog en français,
hébergé sur vocabag.com avec ses images. Rédaction par **Claude Code en mode headless (`claude -p`) sur
l'abonnement** : pas de clé API, pas de facturation au token, mais cela consomme le quota de l'abonnement.

```
Carrousel Telegram ─(publié OK)─► vocabag-media POST /blog/enqueue   images copiées dans social/blog/carrousels/<id>/
Blog Revue (21h)   ─────────────► POST /blog/rediger  → redacteur.py en arrière-plan → claude -p (par carrousel)
redacteur.py       ─────────────► webhook n8n « Blog Prêt » (X-Media-Token)
Blog Prêt          ─► e-mail brouillon complet (Gmail SMTP) + fichier .md sur Telegram + message [✅ Publier][🔁 Réécrire][❌ Rejeter]
clic bouton        ─► Telegram Trigger du Carrousel (callback_query) → sous-workflow « Blog Décision » → /blog/publier|rejeter|reecrire
```

| Workflow (id) | Rôle |
|---|---|
| **Blog Revue** (`VbSocialBlogRev1`) | chaque soir 21h (cron dans le déclencheur), lance la rédaction ; silencieux sauf erreur |
| **Blog Prêt** (`VbSocialBlogPret`) | webhook `POST /webhook/vb-blog-pret` (en-tête X-Media-Token) → e-mail + Telegram |
| **Blog Décision** (`VbSocialBlogDec1`) | appelé par le Carrousel sur un clic ; remplace le message (plus de boutons) en cas de succès |

Config : bloc `blog` du workflow Config (`actif`, `email`, `max_par_soir`, `modele`, `webhook_pret`).
Credential ajouté : **Gmail - contact.vocabag (SMTP)** (identifiants du `.env` VocaBag, créé par `setup_n8n.py`).

**Fichiers** (`social/blog/`) : `blogfile.py` (file, publication, aperçu HTML), `redacteur.py` (appel de Claude,
contrôles, rappel du webhook), `consigne.md` (consigne de rédaction, modifiable), `mots.py` (recherche en lecture
seule dans le vocabulaire, base **staging**), `carrousels/<id>/` (meta.json, images, brouillon.md, redaction.log),
`carrousels/redacteur.log`.

**Garde-fous du rédacteur** : Claude n'a que `Read` et `python3 mots.py …` (tout le reste est refusé, testé) ;
consigne : aucun mot, traduction ou exemple hors images/base, rien d'inventé (chiffres, études, témoignages).
Contrôles après coup : en-tête, slug, longueur ≥ 150 mots, `IMAGE_n` existantes, liens internes connus,
Markdown non pris en charge par le site → avertissements dans l'e-mail et sur Telegram. 2 essais puis `echec`.

**Publier** = article `blog/articles/<slug>.md` + images `assets/images/blog/<slug>/n.jpg` (1200 px) dans
`/var/www/vocabag-staging`, **commit local sur la branche `staging`** (auteur « VocaBag blog (n8n) », seuls ces
chemins, jamais le reste de l'index), **pas de push**. Visible tout de suite sur staging.vocabag.com, en prod au
prochain déploiement (staging → master → `deploy_prod.sh`). Refusé si le dépôt n'est pas sur `staging`.
Les images sont en chemins relatifs (`/assets/…`) : `blog/article.php` les accepte depuis le commit 82fbbae.

**Statuts** (`meta.json`) : `en_attente → redaction → pret → publie | rejete`, `echec`. Un rédacteur coupé
(redémarrage du service) laisse `redaction` : remis `en_attente` au lancement suivant.

**Test du 2026-09-27** : carrousel de 3 images rendues → brouillon de 700 mots en 44 s, tous les mots cités
vérifiés dans la base ; publication testée dans un clone du dépôt ; webhook → e-mail accepté par Gmail,
fichier et boutons envoyés sur Telegram ; clic ❌ Rejeter testé OK (Carrousel → Blog Décision → statut rejete, message remplacé).
Entrée de test : `carrousels/c20260927-0d92e8` (source_ref `test-blog-1`), rejetée.

**Limites** : la page n'est pas relue avant publication (c'est ton rôle) ; les nouveaux articles ne reçoivent
pas de lien entrant depuis les anciens (maillage à faire à la main si besoin) ; si la session Claude Code
de root expire, la rédaction échoue → alerte Telegram (relancer `claude` une fois en root pour se reconnecter).

## 10. Hébergement des médias sur staging.vocabag.com (2026-09-27)

Décision : les images lues par Instagram/Pinterest sont servies par **https://staging.vocabag.com/social-media/**
(et non plus par n8n.rapidvideomaker.com). Alias Apache vers `social/public/` (hors dépôt git) dans
`vocabag-staging-le-ssl.conf`, installé par `install.sh apache` ; `PUBLIC_BASE_URL` mis à jour dans
`/etc/vocabag-media.env`. Sauvegardes du vhost dans `/root/vocabag-staging-le-ssl.conf.bak-*`.
Seule exception au mot de passe du staging : GET/HEAD uniquement (POST → 403), pas de listing (403),
scripts refusés (.php, .py, .sh… → 403), en-tête `X-Robots-Tag: noindex`. Vérifié : image 200 sans mot de passe,
reste du staging 401, prod inchangée. Purge des fichiers après 14 jours (inchangé).

## 11. État au 2026-09-27 (soir) — point de reprise

**Fait et vérifié**
- Service `vocabag-media` : routes `/blog/*`, médias publics sur https://staging.vocabag.com/social-media/.
- n8n : 3 workflows (voir §12) ; publiés : Carrousel, Blog. **Non publié** : Stories.
- Blog, testé de bout en bout : rédaction par `claude -p`, e-mail, fichier .md et boutons Telegram, clic ❌ Rejeter.
  La publication a été testée dans un clone du dépôt, pas dans le vrai `vocabag-staging`.
- Dépôt `vocabag-staging` (branche staging) : commit local 82fbbae (`blog/article.php`, images `/assets/…`), **non poussé**.

**Pas encore fait / à tester**
1. Premier vrai carrousel via @vocabagbot → vérifier la publication Instagram (jamais faite : les médias n'étaient
   pas accessibles avant ce soir), puis le brouillon de 21h et un premier clic ✅ Publier réel (commit dans vocabag-staging).
2. ~~Test Stories~~ fait et publié le 2026-09-27 (§13).
3. Pousser la branche staging et déployer en prod (82fbbae + articles publiés) : uniquement sur demande explicite.
4. Plus tard : maillage interne (liens entrants vers les nouveaux articles), Pinterest (`pinterest.actif`).
5. Ancien plan abandonné : pas d'alias `/social-media/` sur le vhost n8n.rapidvideomaker.com.

## 12. Fusion en 4 workflows (2026-09-27)

Demande : uniquement Video (existant), Carrousel, Stories, Blog ; pas de renouvellement de token (il est bon) ;
pas de remontée d'erreurs.

| Workflow (id) | Déclencheurs | Contenu |
|---|---|---|
| **Vocabag Video** (`ixlsBGrzOeP8BmKk`) | 19h | inchangé |
| **Carrousel Telegram** (`VbSocialCarrous1`, 79 nœuds) | Telegram (messages + clics de boutons) | albums → Instagram ; blocs intégrés « · description », « · IG », « · Pinterest » ; mise en file blog ; clic → appelle Blog |
| **Stories** (`VbSocialStories1`, 85 nœuds) | chaque heure | question/réponse/reel → un bloc « · IG story » ; visuel final → bloc « · IG visuel final » ; **non publié** |
| **Blog** (`VbSocialBlog0001`, 23 nœuds) | 21h, webhook `vb-blog-pret`, appel du Carrousel | un Config, aiguillage par `$('…').isExecuted` |

- Chaque workflow a son propre nœud **Config** avec ses seuls réglages ; un réglage commun (chat Telegram,
  API Instagram, service média, langues) est donc à changer dans chacun si on le modifie dans l'interface.
  Source unique : `CONFIG` dans `build_workflows.py`. `blog_actif` est dans le Config du Carrousel.
- Blocs intégrés : `integrer()` dans `build_workflows.py` copie l'ex-sous-workflow dans le workflow hôte ; le nœud
  d'origine (« Publier Instagram », « Tirer description »…) reste comme nœud de passage portant le résultat.
- Erreurs : plus de workflow Erreurs ni de `errorWorkflow`. Les réponses aux actions Telegram (album refusé,
  publication échouée, brouillon raté avec « Réessayer ») sont gardées ; Stories et lancement du soir : silencieux,
  les échecs de publication restent dans `vb_journal` (statut `echec`).
- Supprimés de n8n via l'API (`setup_n8n.py`, liste `ANCIENS`) : Config, Tirer description, Publier Instagram,
  Publier Pinterest, Token Instagram, Erreurs, Blog Revue, Blog Prêt, Blog Décision.
- Vérifié : références `$('…')` toutes résolues, aucun nœud isolé ; brouillon [TEST] rejoué dans Blog → e-mail,
  fichier et boutons OK ; clic ❌ Rejeter OK (Carrousel → Blog, 19:49). Reste à tester : vrai carrousel, Stories.
- Ancien générateur conservé : scratchpad de session uniquement (pas de git dans `social/`).

**2026-09-27 (soir) — photo seule** : une image seule envoyée à @vocabagbot est publiée en post Instagram **et**
donne aussi un article de blog (avant : carrousels uniquement). Consigne du rédacteur adaptée (1 image = couverture seule).

**2026-09-27 (soir) — bug de fusion corrigé** : 1er envoi réel (photo seule) arrêté au nœud « Tirer · description »
(« Referenced node doesn't exist ») : le code lisait ses tables via `$(variable)`, non renommé par `integrer()`.
Corrigé (références littérales) + contrôle dans `build_workflows.py` : toute référence `$(…)` non littérale ou
vers un nœud absent fait échouer la génération. Rien n'avait été publié. Sans workflow Erreurs, ce type de plantage
est silencieux côté Telegram (visible seulement dans les exécutions n8n).

**2026-09-27 (soir) — duel de deux langues** (comme le genre « duel » de Vocabag Video, ex. Arabe vs Darija) :
légende `ar vs darija`, `fr ar vs darija`, `ar/ary` ou `ar + ary` (« vs », « / » ou « + » obligatoire ; sans,
`ar darija` = description en arabe + darija, inchangé). Description : titre « Arabe littéraire vs Darija 🇸🇦🇲🇦 »
(drapeaux seuls si la description n'est pas en français), texte des lignes `vb_textes` avec `langue_apprise = duel`
(à créer dans la Data Table ; sinon texte générique), hashtags des deux langues réunis + `#comparaisondelangues`
(30 max). Journal : `langue_apprise = ar+ary`. Blog : article comparatif, mots vérifiés dans les deux langues,
catégorie = 1re langue. Testé hors ligne avec Node (9 légendes, 3 tirages). Aucun envoi réel encore.

**2026-09-27 (soir) — langue déduite des images** : si la légende ne donne aucune langue apprise (vide, ou `fr`
seul), le Carrousel appelle `POST /detect-langues` (vocabag-media → `social/blog/detection.py`) : Claude Code
headless, modèle `haiku`, outil Read seul, lit les 3 premières images et renvoie 1 langue ou 2 (duel).
~10 s par envoi. Testé : darija (y3ishek) → `ary`, chinois (你好) → `zh`, confiance haute. La légende reste
prioritaire. Config Carrousel : `detection_langues`, `detection_modele`. La réponse Telegram indique
« 🔎 Langue(s) déduite(s) des images : … (confiance, raison) » ; échec ou doute → description générique + avertissement.
Limite : l'arabe littéraire et le darija se distinguent mal sans indice visible (drapeau, nom, translittération).

**2026-09-27 (soir) — 1er post réel** : image seule sans légende → duel ary vs ar détecté (confiance haute) →
https://www.instagram.com/p/DdzbJQ4go8L/ , mis en file blog (`c20260927-35786f`). Défaut vu : texte générique
« Swipe pour découvrir… 👉 » sur une image seule → pour un post, les mentions swipe/glisse/fais défiler sont
maintenant retirées du texte tiré. Contenu à compléter dans les Data Tables : hashtags `fr` + `arabe`,
textes `duel`.

**2026-09-27 (soir) — 1er article publié via le bouton ✅** : `darija-vs-arabe-litteraire-10-phrases` (duel ary/ar,
870 mots, mots vérifiés dans les 2 langues via mots.py), commit **97caf3b** sur la branche staging (article + 1 image),
non poussé. Page rendue OK en local (titre, image, og:image absolue, catégorie Darija). En prod après déploiement.

**2026-09-27 (soir) — couverture et image entière** : la couverture (bandeau recadré en `object-fit: cover`,
qui coupait l'image Instagram) est désormais générée à la publication : `couverture.jpg` 1200x630 = haut du fond
de la langue (`channels/vocabag/images/languages/<code>.png`, duel `<a>_<b>.png` dans un sens ou l'autre) voilé à
18 % + image Instagram **entière** au centre (coins arrondis, ombre). L'image Instagram est aussi mise en entier dans
le corps (après l'introduction si Claude ne l'a pas placée : `image_dans_corps()`). Article
`darija-vs-arabe-litteraire-10-phrases` refait : commit **d4aa8eb** (staging, non poussé).
**Mise à jour** : sur demande, la couverture n'inclut plus l'image Instagram — `couverture.jpg` = haut du fond de
la langue seul ; l'image Instagram n'apparaît que dans le corps, en entier (CSS `.blog-content img` sans recadrage).

**2026-09-27 (soir) — article de test supprimé** de staging (commit **44842f3**, `git rm` de l'article et de ses
images) ; entrée `c20260927-35786f` passée en `rejete`. Le post Instagram DdzbJQ4go8L reste en ligne. Commits
d'infrastructure conservés : 82fbbae (images relatives), d7eca63 (images du corps en entier).

## 13. Stories testées et publiées (2026-09-27 soir)

- Déclencheur de test ajouté au workflow Stories : `POST http://localhost:5678/webhook/vb-stories-test`,
  en-tête `X-Media-Token` (jeton de /etc/vocabag-media.env), corps `{"action":"question"|"reponse"|"reel"}`.
  Contourne `n8n execute` (inutilisable avec les Data Tables). `install.sh` : `PUBLIER_STORIES=1` publie Stories.
- Tests réels sur vocabag_com : question (老板 / lǎobǎn, chinois), réponse + visuel final, Reel du jour en story
  (vidéo de 12 Mo hébergée puis publiée). Relance de « question » le même jour → bloquée par l'anti-doublon
  (arrêt à « Aiguiller »), rien publié.
- Gabarit « question » corrigé : guillemets insécables (plus de « » orphelin), taille adaptée à la longueur,
  « Réponds-moi en message 💬 » (on ne commente pas une story).
- **Stories est actif** : 09h question, 13h réponse + visuel final, 20h Reel en story (heure de Paris).

**2026-09-27 (soir) — tables complétées** (API n8n) : `vb_hashtags` + 1 ligne `fr / arabe`
(`#vocabag #arabe #apprendrelarabe #arabelitteraire #languearabe #vocabulaire`) ; `vb_textes` + 4 lignes `duel`
(3 `fr`, 1 `en`). Simulation avec les vraies tables : duel ary vs ar → texte duel + hashtags darija ET arabe ;
« Swipe » retiré en post simple, gardé en carrousel. Encore sans ligne `fr` dédiée : textes de 10 langues
(seuls darija et chinois en ont) et hashtags de 9 langues (darija, chinois, arabe en ont) → repli générique.
**Suite** : `fr` complété pour les 12 langues — `vb_textes` +10 (arabe, anglais, allemand, espagnol, portugais,
italien, néerlandais, russe, turc, coréen ; 20 lignes au total), `vb_hashtags` +9 (16 au total). Vérifié par
simulation avec les vraies tables : chaque langue tire sa propre ligne (plus de repli générique), pas de « Swipe »
en post simple. Les descriptions en anglais (`en`) n'ont toujours des lignes que pour arabe et chinois.

## 14. Stories alignées sur le Reel du jour (2026-09-27 soir)

- **Vocabag Video lancé à 15h** (au lieu de 19h ; génération ~10-13 min → Reel publié vers 15h15).
- **Créneaux Stories** : `16` reel en story, `18` question, `21` réponse + visuel final (Config de Stories).
- **Question tirée du Reel du jour** (`Mots du reel` : `vocabag_videos` → `JSON_TABLE(word_ids)`, même langue,
  mot vu dans le Reel). Duel (`word_ids` = A1,B1,A2,B2…) → une paire : « Comment dit-on « X » en darija et en
  arabe littéraire ? », 2 lignes dans `vb_story_mots`, réponse avec le gabarit `answer_duel` (les deux mots, drapeau
  + langue chacun). Sans Reel publié dans les 20 h → repli sur l'ancien tirage au hasard.
- `Marquer répondu` : filtre jour + statut (les 2 lignes en duel). Gabarits : « ? » insécable.
- Testé : logique hors ligne (solo, duel, duel incomplet, sans Reel, réponse 1 ou 2 mots), requête JSON_TABLE sur la
  base staging, rendus `question` duel et `answer_duel`. **Pas encore testé en réel** : 1re exécution le 2026-09-28
  (16h reel, 18h question, 21h réponse) — la question du 2026-09-27 est déjà publiée (anti-doublon).

Vocabag Video, scène 2 (titre) : le drapeau emoji s'affichait en deux carrés « T » « R » (drawtext sans police
emoji) → texte à l'écran sans emoji (`titleTextEcran`), drapeau conservé dans la légende. Sauvegarde :
`/root/vocabag-video-avant-15h-titre-20260927.json`.

**2026-09-27 (soir) — déployé en prod** : staging (44842f3) → master → `deploy_prod.sh -y`, après 907 tests PHPUnit OK.
Seul `blog/article.php` change (images `/assets/…`, images du corps en entier). Vérifié : article 200, nouvelle règle
CSS servie, ancienne absente, aucune erreur PHP récente, article de test absent.

## 15. Point de reprise — 2026-09-27, fin de soirée (remplacé par le §20)

**En production / actif**
- n8n : **Vocabag Video** (15h, Reels seuls, titre sans emoji), **Carrousel Telegram**, **Stories**
  (16h reel · 18h question tirée du Reel · 21h réponse + visuel final), **Blog** (21h + validation Telegram).
- Carrousel : photo seule ou album ; langue(s) en légende ou déduite(s) des images (Haiku) ; duel `ar vs darija` ;
  « Swipe » retiré en post simple. Tables `vb_textes` (20) / `vb_hashtags` (16) complètes en `fr` pour les 12 langues.
- Blog : couverture = fond de la langue, image Instagram entière dans le corps ; `blog/article.php` déployé (44842f3).
- Médias publics : https://staging.vocabag.com/social-media/ (seule exception au mot de passe du staging).

**À faire / à vérifier**
1. **Vérifier les Stories du 2026-09-28** (16h, 18h, 21h) + le Reel de 15h (titre sans carrés). Rappel programmé
   dans la session Claude du 27 (perdu si la session est fermée → le redemander).
2. ~~« Swipe 👉 »~~ : retiré partout le 2026-09-28 (§16).
3. ~~Lignes `en`, colonne `format`, maillage interne~~ : faits le 2026-09-28 (§17).
4. Pas de YouTube Stories (fonction supprimée, Posts non publiables par l'API).
- (2026-09-27, fin) Disque du VPS nettoyé : 31 → 22 Go (voir `docs/video-cleanup.md`). Rien d'autre à faire côté social.
- (2026-09-27, fin) `redacteur.py` : l'en-tête du `.md` d'aperçu (Telegram) pointe désormais vers la vraie couverture
  `/assets/images/blog/<slug>/couverture.jpg` (avant : l'image Instagram). Aucun redémarrage requis.

## 16. « Swipe 👉 » retiré partout (2026-09-28)

Décision : plus aucune invitation à faire défiler, ni en carrousel ni en image seule.
- Nœud `Tirer · description` (Carrousel) : `sansSwipe()` (swipe / glisse / fais défiler + 👉) s'applique maintenant à
  **tout** texte tiré de `vb_textes`, plus seulement aux posts (`req.type === 'post'`). Une description perso (légende
  `desc:`…) n'est pas touchée. Testé sur les 20 lignes : phrases intactes, aucune ligne vide ni ponctuation orpheline.
- Sources : `build_workflows.py` (même changement), `setup_n8n.py` (exemples sans Swipe), `workflows/` régénéré,
  `workflows/import/01_carrousel.json` patché.
- Appliqué en production (export → patch → import → publish → redémarrage), version active vérifiée. Sauvegarde :
  `/root/carrousel-avant-swipe-20260928.json`.
- Les 20 lignes de la Data Table `vb_textes` contiennent **encore** « Swipe 👉 » : c'est sans effet sur ce qui est
  publié, mais c'est à nettoyer si on veut (à la main dans l'interface, ou par l'API avec une clé).
- Piège vu : après `import:workflow`, le workflow reste **désactivé** tant que `publish:workflow` n'a pas été fait.
  Pour le Carrousel, ça coupe @vocabagbot et les boutons du Blog.

## 17. Lignes `en`, colonne `format`, maillage interne du blog (2026-09-28)

**Lignes `en`** : script `social/setup/tables_20260928.py` (idempotent, `--dry-run` pour simuler). Il ajoute 10 lignes
`vb_textes` et 10 lignes `vb_hashtags` en anglais (darija, anglais, allemand, espagnol, portugais, italien, néerlandais,
russe, turc, coréen ; arabe et chinois existaient déjà) et retire « Swipe 👉 » des textes existants (même règle que
`sansSwipe()`). Clé API : `N8N_API_KEY`, sinon fichier `/root/.n8n_api_key` (chmod 600).

**Colonne `format`** (`vb_textes`, facultative) : vide = tout format, `post` = image seule, `carrousel` = album.
`tirer()` (nœud `Tirer · description`) écarte les lignes d'un autre format avant le tirage ; s'il ne reste rien pour la
langue apprise, il retombe sur les lignes génériques comme avant. Sans la colonne, rien ne change. L'API publique
n8n ne sait pas ajouter une colonne → à créer dans l'interface (Data Tables → vb_textes → + colonne `format`, texte).
`setup_n8n.py` la crée pour une nouvelle installation. Testé hors ligne (Node, vraies tables, 4 cas).
Sauvegarde avant patch : `/root/carrousel-avant-format-20260928.json`.

**Maillage interne** (dépôt vocabag-staging, commit `38b1c10`, déployé en prod le 2026-09-28) : bloc « À lire aussi »
sous chaque article, 3 liens : même catégorie d'abord, puis Méthode, puis les autres, les plus récents en premier
(`blogRelatedArticles()` dans `app/Helpers/functions.php`, 4 tests unitaires, suite complète 911 OK). Un article
publié via le bouton ✅ est donc lié tout de suite depuis les pages de sa langue. En production au prochain déploiement.

**Appliqué le 2026-09-28** : `tables_20260928.py` lancé avec la clé de `/root/.n8n_api_key` → `vb_textes` 30 lignes
(14 en, 0 « Swipe »), `vb_hashtags` 26 lignes (13 en) ; 2e passage vide (idempotent). Carrousel importé, publié et actif
avec le filtre `format`. Colonne `format` créée par l’utilisateur le 2026-09-28 (vide sur les 30 lignes = tous formats).

## 18. Alertes d'erreur sur Telegram + permissions Claude (2026-09-28)

**Workflow « Erreurs - alerte Telegram »** (`VbErreursAlerte1`, 3 nœuds, généré par `build_workflows.py` →
`workflows/04_erreurs.json`) : Error Trigger → « Préparer alerte » → message @vocabagbot (chat 6980427615) avec
workflow, nœud, erreur, heure de Paris et lien vers l'exécution. Même erreur (workflow + nœud + 120 premiers
caractères) : une alerte par 6 h au plus (`$getWorkflowStaticData`). Remplace l'ancien choix « pas de remontée
d'erreurs » du 27/09 (demande utilisateur). L'ancien « Error workflow » WhatsApp (`wzbD0m8kMwi87iD3`, inactif,
jamais configuré) n'est pas utilisé.
- Branché (`settings.errorWorkflow`) sur : Vocabag Video, Muzrappel Video, Carrousel, Stories, Blog, Vocabag
  Commenter, Muzrappel Commenter. **Pas** sur Coran tiktok / coran tiktok v2 (en cours de travail par l'utilisateur).
  `build_workflows.py` l'ajoute d'office aux workflows qu'il génère. Sauvegardes : `/root/n8n-avant-erreurs-20260928/`.
- **Piège n8n 2.x** : le workflow d'erreur doit être **publié**, sinon « Workflow … is not active and cannot be
  executed » dans les logs et rien n'est envoyé. `install.sh` le publie maintenant.
- Ne se déclenche que si l'exécution **plante** (automatique, pas manuelle). Les échecs tolérés ne remontent pas :
  Instagram en `continueRegularOutput` (Vocabag Video, Muzrappel Video) → voir `posted_on_instagram` en base ;
  Stories/Carrousel → `vb_journal` statut `echec`.
- Testé de bout en bout le 2026-09-28 : workflow jetable qui plante → alerte reçue (exéc. 1743) ; 2e plantage
  identique → pas de 2e message (1745). Workflow de test supprimé.
- Piège vu : `n8n import:workflow --separate` ignore les fichiers d'export (ce sont des listes) → importer un par un
  avec `--input=fichier`.

**Permissions Claude Code** (`/root/.claude/settings.json`, sauvegarde `settings.json.bak-20260928`) : `docker exec`
(dont `-u root` et `-e …`), `docker cp` vers/depuis `n8n-n8n-1` et `docker restart n8n-n8n-1` autorisés → Claude
fait lui-même export → import → publish → redémarrage. Clé API n8n : `/root/.n8n_api_key` (chmod 600).

## 19. Newsletter hebdo (2026-09-28)

**Workflow « VocaBag - Newsletter hebdo »** (`VbNewsletterHeb1`, 19 nœuds, `build_workflows.py` → `05_newsletter.json`),
actif, **dimanche 10h** (Paris). Abonnés : table `newsletter_subscribers` de la base **prod** (formulaires du blog,
sources `blog_article` / `blog_sidebar`), désabonnés exclus. Réglages : section `newsletter` du Config.
- Contenu : nouveaux articles des 7 derniers jours (date du frontmatter ; route `POST /blog/recents` du service
  média, qui lit `/var/www/vocabag/blog/articles` en lecture seule, `BLOG_PROD_DIR`) + jusqu'à 7 vidéos YouTube de
  la période (`vocabag_videos`) avec leurs mots et traductions FR. Sujet : titre du 1er article, sinon « Vos N vidéos… ».
  Liens avec UTM `utm_source=newsletter&utm_campaign=hebdo-AAAA-Sxx`. Lien de désinscription personnel
  (`unsubscribe.php?token=`). Vouvoiement, comme l'e-mail de bienvenue du site.
- Ni article ni vidéo → aucun envoi + message Telegram. Un envoi par semaine ISO au plus (staticData).
- Envoi un par un via le credential « Gmail - contact.vocabag (SMTP) » (limite Gmail ≈ 500/jour : à revoir au-delà
  de quelques centaines d'abonnés). Bilan sur Telegram (envoyés / échecs). Plantage → alerte du workflow Erreurs.
- **Test** : `POST http://localhost:5678/webhook/vb-newsletter-test` + en-tête `X-Media-Token` → envoi au seul
  `email_test` (contact.secbec@gmail.com), sujet préfixé [TEST], rien n'est marqué. Testé le 2026-09-28 (exéc. 1746,
  1/1 envoyé, 0 article + 7 vidéos). Rendu vérifié en capture (Playwright) avec 4 articles + 7 vidéos.
- Au 2026-09-28 : **0 abonné** (staging et prod). Credentials du fichier généré : repères remplacés par les vrais
  ids (`workflows/import/05_newsletter.json`).

## 20. Point de reprise — 2026-09-28, fin de soirée (remplace le §15)

**Vérifié le 2026-09-28** : Reel Vocabag 15h (nl, IG + YT + commentaire) ; Stories 16h reel / 18h question « de rat »
(mot du Reel) / 21h réponse + visuel final → 4 × `ok` dans `vb_journal` ; Blog 21h (rien à rédiger).

**Fait le 2026-09-28**
- « Swipe 👉 » retiré partout (§16) ; lignes `en` des tables, colonne `format`, maillage « À lire aussi » déployé (§17).
- Alertes d'erreur Telegram `VbErreursAlerte1` sur 7 workflows (§18) ; permissions Claude + clé API n8n (§18).
- Newsletter hebdo `VbNewsletterHeb1`, dimanche 10h (§19).
- Attente des Reels Instagram portée à ~5 min dans le nœud communautaire + garde Instagram dans Muzrappel Video
  (`muzrappel-n8n-publication.md`).
- Hors n8n : PostHog sans cookie en prod (vocabag.com, commit 613617b), `privacy.php` corrigée ; ports MySQL 3306/33060
  fermés au public ; décision Google Analytics notée dans `vocabag-staging/ENDOVER.md`.

**Pinterest (en attente de l'utilisateur)** — n8n n'a pas de credential Pinterest : `build_workflows.py` utilise
maintenant un credential **OAuth2 générique** « Pinterest - vocabag » (`CRED_PIN`, id `A_REMPLACER_PIN` à reporter),
nœud « Créer épingle » plus désactivé ; tableau cible **« Vocabulaire VocaBag »** ; `pinterest.actif` encore `false`.
Réglages du credential : Authorization URL `https://www.pinterest.com/oauth/`, Access Token URL
`https://api.pinterest.com/v5/oauth/token`, scope `boards:read,pins:read,pins:write`, Authentication = Header,
redirect `https://n8n.rapidvideomaker.com/rest/oauth2-credential/callback`. Compte Pinterest professionnel + app sur
developers.pinterest.com (accès « Trial » au départ : visibilité des épingles à vérifier). Reste à faire par Claude une
fois connecté : id du credential dans `CRED_PIN`, board_id (GET /v5/boards via n8n), `actif: true`, import + test.
⚠️ Ne pas réimporter le Carrousel généré avant d'avoir reporté l'id réel de `CRED_PIN`.

**À vérifier**
1. 2026-09-29 07h : Muzrappel Video (garde Instagram + attente 5 min) ; alerte Telegram si plantage.
2. Premier vrai **album** sur @vocabagbot (carrousel jamais publié en réel ; sans Swipe ; textes `en`).
3. Dimanche 2026-10-04 10h : 1re newsletter réelle. Avec 0 abonné (état au 2026-09-28), attendu sur Telegram :
   bilan « 0/0 envoyée(s) » (ou « pas d'envoi » s'il n'y a ni article ni vidéo sur la semaine).
4. PostHog : visites de vocabag.com visibles dans Activity / Web analytics.

**Optionnel** : alertes d'erreur sur Coran tiktok / coran tiktok v2 ; titre du Reel sans carrés (vérif. visuelle) ;
Reel Muzrappel du 2026-09-28 non publié sur Instagram (relance manuelle possible avant ~07h le 29).


**Stories Facebook (2026-09-30)** — `VocaBag Social - Stories` publie aussi chaque story sur la **page Facebook VocaBag**
(fonction `stories_facebook()` de `build_workflows.py`, nœuds « … · FB story », 101 nœuds en ligne avec la note).
Chaque « Story question / réponse / reel / visuel final » a une 2e sortie vers `Entrée · FB story`, exécutée après
la branche Instagram (ordre v1) :
- image : `POST /{page}/photos` (`url`, `published=false`) → `POST /{page}/photo_stories` (`photo_id`) ;
- vidéo (Reel 16h) : `POST /{page}/video_stories` (`upload_phase=start`) → relecture du fichier (`Fichier du reel`)
  → envoi **binaire** sur l'`upload_url` rupload (en-têtes `offset: 0`, `file_size`) → `upload_phase=finish`.
  Pas de `file_url` : Facebook refuse de lire `staging.vocabag.com` (« 403 Restricted by robots.txt » : le robots.txt
  est derrière le mot de passe du staging). Les images, elles, passent par URL.
- Credential « Facebook Graph account » (`RL5TaCOZpmZmBEc8`) = token de page VocaBag ; page `1361049150428275`.
  L'auth `access_token` en query (credential n8n) est acceptée aussi par rupload.
- Erreurs ignorées (onError continue + neverError) ; **pas de ligne `vb_journal`** (le contrôle « Déjà publiée ? »
  ne filtre pas par plateforme : une ligne Facebook masquerait un échec Instagram).
- Tests réels OK le 2026-09-30 (story photo `1911922559788417`, story vidéo `1820579268954323`) ; workflow de test supprimé.
- `workflows/02_stories.json` régénéré ; `workflows/import/` non régénéré (install.sh).

**Carrousel → Facebook (2026-09-30)** — `VocaBag Social - Carrousel Telegram` publie aussi chaque carrousel (ou photo seule) sur la
**page Facebook VocaBag** : fonction `carrousel_facebook()` de `build_workflows.py`, 7 nœuds (89 au total).
`Répondre` → `Envoyer à Facebook` (seulement si Instagram a réussi, comme Pinterest : pas de doublon Facebook si
on renvoie un carrousel après un échec Instagram) → `Photo non publiée · FB` (une par image, `/photos` `published=false`,
par URL `staging.vocabag.com/social-media/…`) → `Photos FB` (toutes acceptées, sinon rien) → `Publier · FB`
(`POST /{page}/feed`, `message` = légende Instagram, `attached_media` = photos) → `Signaler · FB` (Telegram
« 📘 Facebook : publié » + lien, ou « ❌ Publication Facebook échouée »). Credential « Facebook Graph account ».
Pas de ligne `vb_journal`. Non testé en réel (déclencheur Telegram) : premier carrousel envoyé = premier test.

**Reel du jour des stories (2026-09-30)** — « Reel du jour » (story 16h) et « Mots du reel » (question 18h) retiennent la vidéo
publiée sur **au moins un** réseau : `(posted_on_youtube = 1 OR posted_on_instagram = 1 OR posted_on_facebook = 1) AND
created_at >= NOW() - INTERVAL 20 HOUR`. Avant : Instagram seul (`posted_instagram_at`) → un Reel Instagram en échec
supprimait aussi la story (Instagram et Facebook) et la question tombait sur un mot au hasard (cas du 30/09).

## Prompt carrousel (2026-10-04)

Workflow **« VocaBag Social - Prompt carrousel »** (`VbSocialPrompt01`, `wf_prompt()` dans `build_workflows.py`,
`workflows/07_prompt.json`), appelé par le Carrousel (seul Telegram Trigger de @vocabagbot).

- Message `prompt` (ou `/prompt`, réglage `mots_cles_prompt` du Config du Carrousel) → boutons **langue** :
  12 solos (ar, ary, de, en, es, it, ko, nl, pt, ru, tr, zh) + 5 duels (ary_ar, de_nl, es_it, es_pt, it_pt).
- Clic → boutons **catégorie** (les 21 catégories ; entre parenthèses le nombre de mots, ou de sens communs aux
  deux langues en duel ; ✖️ = moins de `nb_mots`, un clic affiche seulement une notification).
- Clic → **prompt ChatGPT** (bloc `<pre>`, copiable) : drapeau(x) + nom(s) de langue, titre de la liste
  (`prompt.titres` par slug), sous-titre, les 10 mots (10 paires en duel = 20 mots) avec prononciation et
  traduction FR, consigne d'ajouter un émoji par mot et de ne rien changer aux mots. Boutons « Autres mots »,
  « Autre catégorie », « Autre langue » (nouveaux messages).
- Mots : base VocaBag (`Vocabag DB`, SELECT), actifs + validés, `word`/`expression`, ≤ 30 caractères, une entrée
  par sens, tirage aléatoire. Duel = même traduction FR dans la même catégorie (comme le genre duel de Vocabag Video).
- `callback_data` : `cp[n]:l|c|b[:sel[:cat]]` (`n` = répondre par un nouveau message au lieu de modifier).
- **Claviers fixes** : n8n 2.41 ignore une expression posée sur tout le clavier Telegram (fixedCollection) et
  supprime un champ additionnel inconnu (`reply_markup`) ; seuls textes et `callback_data` des boutons acceptent
  des expressions. Liste des catégories figée dans `PROMPT_CATEGORIES` (à compléter si une catégorie est ajoutée).
- Test : `POST /webhook/vb-prompt-test` + en-tête `X-Media-Token`, corps `{"etape":"langue"|"categorie"|"prompt",
  "sel":"ary", "cat":19}` (envoie de vrais messages sur Telegram).
- Déploiement : `import:workflow` (id fixe) puis **désactiver + réactiver** par l'API ; sans cela, n8n continue
  d'exécuter l'ancienne version (et le 1er appel juste après peut encore l'utiliser). Carrousel modifié en prod par
  l'API (Config, Filtrer message, Aide + nœuds « Prompt ? » et « Prompt carrousel ») ; sauvegarde de la version
  précédente : `workflows/.carrousel_prod_avant_prompt_2026-10-04.json`.
- **2026-10-04 (retours sur le prompt)** : le template est UNE image avec une seule zone « Catégorie : » → prompt
  réécrit : « Remplis le template ci-joint… une seule image au même format », `Zone « Catégorie : » → 🇲🇦 Les animaux
  en darija` (duel : `🇲🇦 vs 🇸🇦 Les animaux`), une ligne courte par mot (`mot · (prononciation) · traduction`,
  duel : `🇲🇦 mot (pron) · 🇸🇦 mot (pron) · traduction`), règles sur une ligne. Traductions des `word` sans article
  (« Canard », pas « le canard »). Le message Telegram ne contient plus que le prompt (récapitulatif seulement dans
  le message des catégories). Données à corriger en base (non fait, décision utilisateur) : ح noté « h » au lieu de
  « 7 » dans 120 des 145 mots darija qui le contiennent ; الحوت (id 4146) traduit « la baleine » ; 1 664 traductions
  avec article.
- **2026-10-04** : en duel, les sens sont comparés **sans article ni casse** (`norm()` dans « Préparer » :
  la base dit « la tête » en néerlandais, « Tête » en allemand). `de_nl` : 3 → 16 catégories utilisables
  (« Corps & santé » 1 → 25 mots communs), `es_pt` : 7 → 16. Les mots eux-mêmes ne sont pas modifiés (ex.
  « Kopf » sans article, « het hoofd » avec).
- **2026-10-04 (2) — prompts refaits sur consigne utilisateur** :
  - **Émojis choisis par le workflow**, plus par ChatGPT : nœuds « Demande émojis » → « Choisir les émojis »
    (POST `vocabag-media /emojis`, module `social/blog/emojis.py` : Claude Code headless, haiku, sans outil ;
    réponse vérifiée — nombre, émojis valides, tous différents — avec un 2e essai). ~20-25 s : « Patienter »
    répond tout de suite au bouton (notification ⏳). Échec → message d'erreur avec les boutons « Autres mots… ».
    Le serveur vocabag-media est mono-thread : pendant ce temps, ses autres requêtes attendent.
  - **Versus** : structure imposée — bannière gauche (turquoise) / droite (bleue) = drapeau + langue, zone
    « Catégorie : » (en bas) = titre, lignes `N. émoji Mot1 | Mot2`, sans traduction ; règles fixes (numéros
    centraux et « VS » inchangés).
  - **1 langue** : lignes `N. émoji Mot · (Prononciation) · Traduction` (traduction sans article).
  - Majuscule initiale partout ; pas de drapeau devant les mots ; message Telegram = prompt seul.
  - Les mots viennent de la base VocaBag, aucun LLM n'écrit de texte : les consignes « 3/7, poisson/baleine,
    Salida » sont des corrections de DONNÉES (poisson = الحوت id 74 et baleine = البالينة id 4146 : OK ;
    espagnol « départ » = Partida id 4319 en base, pas Salida → à corriger en base si validé).
- **2026-10-04 (3) — suite /code-review** : `_est_emoji` accepte les plages d'émojis même inconnues de Python 3.11
  (Unicode 14 : 🪿 🫏 🪼 🩷) et les touches chiffrées (1️⃣, #️⃣, jusqu'à 3 accolées : 2️⃣0️⃣) ; Claude appelé
  **sans réflexion** (`MAX_THINKING_TOKENS=0`, `--tools ''`, `--strict-mcp-config`) : 3-5 s au lieu de 18-80 s ;
  60 s max par essai, un dépassement déclenche le 2e essai (120 s max < 180 s du nœud n8n). Versus `ary_ar` :
  règle « Pour l'arabe : recopie caractère par caractère… » ajoutée (demande utilisateur).
