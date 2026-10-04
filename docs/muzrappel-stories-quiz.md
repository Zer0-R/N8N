# Muz Rappel — stories (Reel, quiz) Instagram + Facebook

Workflow n8n **« Muz Rappel - Stories »** (ex-« Stories quiz », renommé le 2026-09-30) (id `FFiqDzWiMSQWifNL`, actif depuis le 2026-09-30).
Généré par `social/setup/build_muz_stories.py` (+ logique `social/setup/muz_quiz.js`) → `social/workflows/06_muz_stories.json`.
**Modifier le générateur**, puis `python3 build_muz_stories.py` et `PUT /api/v1/workflows/FFiqDzWiMSQWifNL` (+ `/activate`).

## Fonctionnement
- Déclencheur horaire ; `Config.creneaux` (heure de Paris) : `13` → story **question**, `20` → story **réponse**.
  Exécution manuelle (interface ou `n8n execute`) = test : publie `Config.test_action` (défaut `question`).
- `Hadiths publiés` : `SELECT … FROM muzrappel WHERE video_create = 1` (credential « MySQL account », favima_bdd).
- `Construire quiz` : quiz tiré avec la **date comme graine** → même quiz à 13h et à 20h, sans état mémorisé.
  Types (alternés un jour sur deux) : « Quel Compagnon a rapporté ce hadith ? », « Dans quel recueil ce hadith est-il rapporté ? ».
- `Rendre image` : service média VocaBag `/render`, modèles `muz_question` / `muz_answer` (`media-service/server.py`,
  logo `assets/muz-logo.png`) → JPEG public `staging.vocabag.com/social-media/…`.
- Instagram (1re branche) : `graph.instagram.com/v23.0/me/media` (`media_type=STORIES`, `image_url`) → attente 15 s → `media_publish`,
  credential **« Instagram account 2 »** (muz.rappel).
- Facebook : `/{page}/photos` (`published=false`) → `/{page}/photo_stories`, credential **« Facebook Graph account 2 »**
  (page Muz Rappel `501465773057138`).
- Nœuds de publication en onError continue + neverError : un échec Instagram n'empêche pas Facebook (et inversement).
  Plantage (ex. aucun quiz possible) → workflow « Erreurs - alerte Telegram ».

## Fidélité aux sources (règle Muzrappel)
Aucune IA, rien d'inventé : l'extrait, le rapporteur, le recueil et la référence sont lus tels quels dans `description_full`.
- Extrait = texte entre « D'après … » et « (Rapporté par … ) » (citation « … » si présente, sinon narration) — jamais l'explication.
- Rapporteur : nom avant « (qu'Allah l'agrée / les agrée) », normalisé sur une liste de 17 Compagnons ; écarté si le nom
  figure dans l'extrait. Recueil : retenu seulement si **un seul** recueil connu est cité dans tout le texte.
- Mauvaises réponses : autres Compagnons / grands recueils réels **absents du texte** du hadith. Jamais de faux texte de hadith.
- Validation 2026-09-30 : 120 jours simulés → 120 quiz, 101 hadiths distincts, 60/60 par type.

## Tests (2026-09-30)
- Exécution 1822 : rendu OK, **story Facebook publiée** (`1634306581811983`, hadith 3822, réponse C « Abou Houreira » vérifiée en base).
- Instagram : **token invalidé** (« session has been invalidated… », code 190) — les deux credentials Instagram (Muz et VocaBag)
  sont touchées ; à renouveler dans n8n.

## Piège (2026-09-30)
`$execution.mode` dans une expression/Code n8n vaut `test` ou `production` — jamais `trigger` (valeur de la colonne
`execution_entity.mode`). Une première version testait `!== 'trigger'` : chaque run horaire se croyait en test et republiait
la question (runs de 16h et 17h Paris, tous deux en échec de token : aucun doublon). Corrigé : test = `=== 'test'` + `forcer_action`.
Tokens Instagram renouvelés le 2026-09-30 ; tokens de page Facebook expirés le même jour (tokens courte durée) → à remplacer
par des tokens de page permanents.

## Story Reel (ajoutée le 2026-09-30)
Créneau `09` → `reel` : extrait du Reel publié à 07:00 par « Muzrappel Video ».
- Service média `POST /muz/reel-story {date}` : dernier `channels/muzrappel/videos/*/render_with_soundtrack.mp4` modifié ce jour-là
  (Paris) ; les stories vidéo sont limitées à 60 s (vidéos Muz ≈ 95 s) → coupe à la dernière pause de voix avant 59 s
  (`silencedetect` sur `render.mp4`, sans musique) = entre deux phrases, fondu 0,6 s, ré-encodage (~1 min). Absent → rien.
- Bandeau de fin (depuis le 2026-09-30) : « La vidéo complète / est sur notre compte » (PNG généré par PIL, Noto Sans Bold,
  cache `media-service/tmp/muz_bandeau_v1.png` — changer le nom `_v1` pour le régénérer) en fondu sur les 4,5 dernières s,
  en haut (y = 250) : les sous-titres karaoké sont au centre et la pub ebook en bas.
- Instagram : `me/media` (`media_type=STORIES`, `video_url`) → boucle `IG · Attendre vidéo` / `IG · Statut vidéo`
  (`status_code`, 15 s × 20 max) → `media_publish`.
- Facebook : `video_stories` start → téléchargement de l'extrait (fichier) → envoi binaire sur `upload_url` (en-têtes
  `offset`, `file_size`) → finish. (Facebook refuse de lire `staging.vocabag.com` : robots.txt derrière mot de passe.)
- Test réel 2026-09-30 (exéc. 1837, 2 min 15) : extrait 55,4 s ; story IG `18428343064149473` ; story FB `1414005980873678`.
- Test CLI : `Config.forcer_action = 'reel'` le temps du test (workflow désactivé pendant), puis version normale redéployée.
