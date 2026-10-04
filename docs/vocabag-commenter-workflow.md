# Workflow n8n « Vocabag commenter » — promotion par commentaires YouTube

État au 2026-09-20 (décision de l'utilisateur : **on reste comme ça pour l'instant**) : **piste 1 ACTIVE, publication DIRECTE (plus de validation), sans LLM (modèles préfabriqués), commentaires SANS lien, Telegram = notification seule** ; piste 4 déployée dans `Vocabag` (avec lien, non tranchée). Autres plateformes évaluées mais non lancées (voir « Autres plateformes »).

## Principe

Chaque jour à 12h30 (Europe/Paris), n8n cherche des vidéos YouTube récentes **en français** sur l'apprentissage des langues, choisit un commentaire
**préfabriqué** adapté à la langue de la vidéo (aucun LLM), le **poste directement** au nom de la chaîne VocaBag (3 max par jour, 2 min entre chaque),
puis envoie une **notification Telegram** (le chat_id de l'utilisateur est dans le nœud) (`@vocabagbot`) : titre, chaîne, vues, URL de la vidéo, modèle utilisé, texte du commentaire, lien direct vers le commentaire
(ou « ⚠️ Commentaire NON posté » + erreur). Décision de l'utilisateur (2026-09-20) : plus de validation manuelle.

## Workflow

- Nom : `Vocabag commenter` (id `VocaBagCommenter1`), **actif**, 12 nœuds. Schedule 12h30 Europe/Paris + Manual Trigger.
- Générateur : JSON produit par un script Python (scratchpad de session, non conservé) ; l'export n8n fait foi. Une copie de test (post désactivé, pause 1 s) a été utilisée puis supprimée.

Chaîne de nœuds :

1. **Choisir recherches** (Code) : 2 requêtes tirées au hasard (pondérées : darija/arabe prioritaires), **françaises uniquement pour l'instant**, fenêtre 7 jours.
2. **YouTube search** (HTTP, `search.list`, 100 unités de quota) : 8 résultats par requête, `safeSearch=strict`, `relevanceLanguage` = langue de la requête.
3. **Filtrer resultats** (Code) : dédoublonne, écarte les vidéos déjà vues (`staticData.seen`, 500 max) et les chaînes contenant « vocabag » ; garde la langue cible par vidéo.
4. **YouTube videos details** (HTTP, `videos.list`, 1 unité).
5. **Selectionner candidats** (Code), garde-fous puisqu'il n'y a plus de validation : commentaires ouverts, 300 à 300 000 vues, pas de live, **la langue visée doit figurer dans le TITRE ou le nom de chaîne (regex par langue) ET le titre/tags doivent signaler du contenu d'apprentissage** (regex `LEARN`),
   langue audio/défaut de la vidéo connue **et** différente de celle du commentaire → écartée ; tri **français d'abord** puis vues ; 3 vidéos maximum.
6. **Loop Over Items** (lot de 1) → **Preparer message** (Code) : modèle au hasard dans `T[langue_apprise + '_' + langue_du_commentaire]`, repli `_fr`.
7. **Poster commentaire** (HTTP `commentThreads.insert`, 50 unités, `onError: continueRegularOutput`) → **Notifier sur Telegram** → **Pause entre commentaires** (2 min) → vidéo suivante.

## Modèles de commentaires (préfabriqués)

Définis dans le nœud « Preparer message » (objet `T`). Chaque recherche est liée à une langue apprise (`target`) et à la langue du commentaire (`lang`) dans
« Choisir recherches ». Ton : compliment de la langue + difficulté classique (genres en allemand, ser/estar, racines arabes, alphabet…) + mention **sans lien** (« Retrouve VocaBag sur notre chaîne 📲 », 3 formulations FR / 2 EN en rotation). **Aucune URL** : voir « Incident 2026-09-20 (liens supprimés) ».
Règles : aucune affirmation invérifiable sur VocaBag (pas de fonctionnalité citée), **aucun témoignage personnel inventé** (« perso j'ai appris… » écarté volontairement),
faits linguistiques uniquement vrais et génériques. Pour ajouter une langue ou une variante : ajouter une entrée dans `T` et une requête dans le pool de « Choisir recherches ».
Sans validation manuelle, les garde-fous sont dans « Selectionner candidats » (mots-clés de la langue visée, langue de la vidéo) ; la notification Telegram permet de repérer un mauvais choix après coup et de supprimer le commentaire à la main.

## Credentials n8n utilisés

- `Telegram - vocabagbot` (id `TgVocabagBot0001`, type `telegramApi`) : bot `@vocabagbot`, token stocké chiffré dans n8n uniquement.
- `YouTube account 3` : même chaîne que l'upload du workflow `Vocabag` ; scope `youtube.force-ssl` présent (nécessaire aux commentaires).
- OpenAI n'est plus utilisé (crédit épuisé au 2026-09-20 → workflow réécrit avec des modèles préfabriqués).

## Limites et pièges

- **L'API YouTube ne permet pas d'épingler un commentaire** : l'épinglage reste manuel dans YouTube Studio.
- Instagram : l'API ne permet de commenter que ses propres posts, jamais ceux d'un tiers (pas de piste Instagram pour la piste 1). Voir « Autres plateformes ».
- Un commentaire posté par erreur se supprime à la main dans YouTube (le lien direct est dans la notification Telegram).
- `staticData` (liste des vidéos vues) ne persiste pas pour les exécutions manuelles/CLI ; il persiste en exécution planifiée.
- Quota YouTube partagé avec les uploads (10 000 unités/jour) : ce workflow consomme au plus ≈ 350 unités/jour.
- Test en CLI : `docker exec -e N8N_RUNNERS_BROKER_PORT=5690 n8n-n8n-1 n8n execute --id=<id>` (le port 5679 est pris par l'instance en marche).
  Un nœud Wait > 65 s met l'exécution en statut `waiting` (reprise par le serveur n8n).
- Copie de fichier dans le conteneur : `docker cp` crée un fichier root illisible par l'utilisateur `node` → `docker exec -u root … chmod 644` avant l'import.
- Risque de plateforme : les commentaires promotionnels répétés peuvent être filtrés ou signalés par YouTube ; garder un volume faible (≤ 3/jour) ; les modèles sont peu nombreux (4 à 6 par langue depuis le 2026-09-20) → des textes identiques sur plusieurs vidéos augmentent le risque de filtrage anti-spam : ajouter des variantes dans `T`.

## Incident 2026-09-20 (premier run réel)

Run réel lancé à la main : 2 commentaires posté(s), dont un **hors sujet** (vidéo de voyage « train de nuit en Russie » : l'ancien filtre acceptait le mot « russe » dans les tags/la description ;
ce commentaire a ensuite disparu de lui-même, comme les autres commentaires avec lien : rien à supprimer). La notification Telegram de la 2e vidéo a échoué (`can't parse entities` : le nœud Telegram envoie en Markdown par défaut),
ce qui a interrompu l'exécution avant la 3e vidéo. Corrigé : filtre resserré (titre/chaîne + mots d'apprentissage) et Telegram en `parse_mode: HTML` avec échappement (`e()`).
Piège : tout texte libre (titre, commentaire) envoyé par le nœud Telegram doit être échappé, sinon l'envoi échoue.

## Incident 2026-09-20 (liens supprimés par YouTube)

Les commentaires **contenant `https://vocabag.com`** postés sous des vidéos tierces disparaissaient au bout de quelques minutes (5 sur 5 ; visibles 10 s après l'envoi, absents ~9 min plus tard, relus via `commentThreads.list` avec le credential de la chaîne) ;
un commentaire **sans URL** est resté visible. L'API renvoie pourtant un `id` à l'insertion : **un `id` renvoyé ne prouve pas que le commentaire est visible**. Cause exacte (filtre anti-spam YouTube ou modération des créateurs) non distinguée.
Décision : aucune URL dans les modèles de la piste 1 (le lien est dans le profil/la description de la chaîne) + le nœud « Preparer message » supprime toute URL restante avant l'envoi.
À revérifier : que les commentaires sans lien tiennent sur plusieurs jours. Vérification de visibilité : workflow temporaire `commentThreads.list` / `comments.list` (id) avec le credential `YouTube account 3`, supprimé ensuite (suppression = arrêt n8n + DELETE SQLite, pas de commande CLI).
Test complémentaire : deux commentaires posés le même soir sous des vidéos tierces (`M6HCMv6PNvo` sans lien, `-g3BJHqxDSU` avec lien) → seul celui **sans lien** a survécu à ~9 min. Échantillon petit (1 contre 5) ; à revérifier sur plusieurs jours.
La piste 4 (commentaire sous nos propres vidéos) contient encore l'URL : non tranchée. Un commentaire de test avec lien a été posté sous `gXDSdksTEDQ` (`Ugy-pQc7FHiImh2mSEZ4AaABAg`) et est visible via l'API en tant que propriétaire ; **visibilité publique (navigation privée) non confirmée**.

## Piste 4 — commentaire sous chaque nouvelle vidéo VocaBag (DÉPLOYÉE 2026-09-20)

Nœud HTTP `Commenter YouTube` ajouté dans `Vocabag` (id `ixlsBGrzOeP8BmKk`, 148 nœuds) après « Marquer YouTube (suivi) » : `commentThreads.insert`,
`videoId = $('Upload a video').item.json.uploadId`, credential `YouTube account 3`, `onError: continueRegularOutput` (un échec ne casse jamais la publication).
Texte fixe : lien `https://vocabag.com` + question d'engagement. **Non prouvé** : le premier run planifié qui le posera est celui de 19h du 2026-09-21 ; épinglage manuel dans YouTube Studio.
Sauvegarde de l'original : scratchpad de session (`vocabag_before_comment.json`, non conservée durablement).
Procédure d'édition : export CLI → patch JSON → `import:workflow` → `publish:workflow` → `docker restart n8n-n8n-1`
(CLI : `docker exec -e N8N_RUNNERS_BROKER_PORT=<port libre> n8n-n8n-1 n8n …`).

## Incident 2026-09-20 (n8n figé)

n8n figé (CPU 92 %, HTTP en timeout) : exécution manuelle du workflow inactif `Coran tiktok` bloquée sur le nœud « creer clip verset ». Résolu par `docker restart`.
Cause profonde non identifiée ; éviter de relancer ce workflow en boucle depuis l'éditeur avant d'avoir examiné ce nœud.

## Autres plateformes (évaluées le 2026-09-20, **non lancées** — « on reste comme ça pour l'instant »)

- **Instagram** (nœud communautaire `@mookielianhd/n8n-nodes-instagram`, token `IG…`) : l'API ne permet PAS de commenter/liker/suivre/écrire à des comptes tiers ; tout contournement (scraping, automatisation non officielle) = risque de bannissement de `vocabag_com`.
  Possible : publier ses propres contenus (déjà fait), répondre aux commentaires de ses propres posts et envoyer un message privé avec le lien (permission `instagram_business_manage_messages`, 1 DM par commentaire, 7 jours), répondre aux mentions, collaborateurs sur un Reel (acceptation manuelle), publicités payantes via l'API Marketing.
  Recherche par hashtag : nécessite une connexion via Page Facebook + revue d'application, probablement indisponible avec un token `IG…` (non testé). Rien de tout cela n'a été testé sur le compte.
- **Republier les vidéos existantes ailleurs** (idées classées, non démarrées) : Facebook Page (Reels + lien cliquable), Pinterest (épingles avec lien), canal Telegram (`@vocabagbot` existe), TikTok (déjà `TikTok Manual` ; application non auditée = publication privée/brouillon), X/Threads.
- **Acquisition** : pages SEO par mot/expression sur vocabag.com (probablement le levier le plus durable), système d'affiliation existant proposé à des créateurs, publicité payante (Meta/TikTok/Google Ads), forums/Reddit à la main.
- Règle commune constatée : les API officielles permettent de publier sur ses propres comptes ; les commentaires promotionnels chez des tiers sont filtrés partout (cf. YouTube ci-dessus).

## Alertes d'erreur (2026-09-28)

`settings.errorWorkflow = VbErreursAlerte1` : un plantage du workflow envoie un message sur @vocabagbot
(voir `vocabag-social-instagram.md` §18).

