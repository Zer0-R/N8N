# Channel vocabag — vidéos vocabulaire multilingues — Setup & spec n8n

> **Emplacement (2026-09-19)** : ce document vit dans le dépôt **Vocabag** (`docs/vocabag-channel-setup.md`). Il était
> auparavant dans le dépôt RapidVideoMaker (`rapidvideomaker/docs/`, où il n'y a plus qu'un renvoi ; l'historique
> git de cette époque y reste). Le channel est un produit Vocabag qui **appelle l'API RapidVideoMaker** — il n'ajoute
> aucun code à RVM.
>
> **Lecture des chemins** : `worker/…`, `api/v1/…`, `api/download.php`, `config/tts_voices.php`, `docs/api.md`,
> `inori.py` désignent des fichiers du **dépôt RapidVideoMaker** (`/var/www/rapidvideomaker-staging/`) ;
> `channels/vocabag/…` (vidéos, images, sons, scripts) est dans `/var/www/muz-video-template/` ;
> la config Docker de n8n (`/root/n8n/docker-compose.yml`) est documentée dans le `CLAUDE.md` de RapidVideoMaker
> (§ « Docker n8n »).

## Portée de ce document

Création vidéo (formats + genres) + posting **Instagram et YouTube** (nœuds natifs n8n — section 11).
Facebook reste hors périmètre.

> **État au 2026-09-19 (section 11)** : le workflow est **actif** (Schedule Trigger **19h00**, heure de
> Paris), publie en production sur Instagram + YouTube, mixe un **soundtrack** (`sounds/01.mp3`, volume
> 0.2), suit les vidéos dans la table **`vocabag_videos`** (créée/postée + anti-répétition), tire la
> langue/catégorie via un **calendrier aléatoire pondéré** (section 2 obsolète) et utilise des requêtes
> **Pexels visuelles anglaises** avec filtre. Les sections 2 (calendrier), 9 (posting Instagram HTTP) et le
> paragraphe « pas de table SQL » ci-dessous sont **historiques** — voir section 11.

## Architecture

Contrairement à `muzrappel`/`muzreminder` (pipeline Python maison `worker/inori.py` + MoviePy), ce
channel **n'ajoute aucun code RVM** — tout se fait dans un workflow **n8n** qui appelle l'**API
publique RapidVideoMaker** (`api/v1/render.php`, Bearer token) exactement comme un intégrateur
externe. Dogfooding direct du produit.

```
n8n (cron)
  → choisit un genre du jour (rotation par jour de semaine — section 3)
  → choisit une langue + catégorie ("actualité" — calendrier mensuel, section 2)
  → prépare un texte d'intro + un texte d'outro (genre-aware, voix FR) — section 4bis
  → construit une requête SQL adaptée au genre, sélectionne 3 "reveals" (mot / phrase /
    concept multilingue selon le genre — section 3), anti-répétition via la table
    `vocabag_videos` (section 11 ; ancienne mémoire n8n `usedWords` supprimée)
  → pour chacun des 3 reveals (boucle) :
      1. Cherche une image Pexels avec des mots-clés pertinents (catégorie + mot), en
         portrait — GET /v1/search puis {{ $json.photos[0].src.portrait }}
      2. Écran QUESTION (voix FR) : "Comment dit-on {mot} en {langue} ?"
      3. Écran RÉPONSE (voix langue cible) : révèle le mot/la phrase cible à l'écran
         + rappel FR
  → fusionne 8 clips (1 intro + 3 reveals × 2 écrans + 1 outro) en une seule vidéo
  → mixe le soundtrack (`mix_audio`, `mp3_volume` 0.2) → `{folder}_final_sound.mp4` (section 11)
  → enregistre la vidéo dans `vocabag_videos`, dépose words.json dans channels/vocabag/videos/
  → publie sur Instagram + YouTube (nœuds natifs, section 11), puis marque `posted_on_*`
```

~~**Pas de table SQL de file d'attente**~~ — **obsolète depuis le 2026-09-19** : la table
`vocabag_videos` (migration `046`, base `vocabag`) remplace la mémoire du workflow n8n
(`$getWorkflowStaticData`, `usedWords`), perdue à chaque réimport du workflow. `words.json` reste
écrit par vidéo (sortie de contenu, non lu par la sélection).

## 1. Sources de données

### Base `vocabag` (contenu)

- `vocabulary` (id, language_id, category_id, word, transliteration, image_url, audio_path…) —
  **12 langues, ~1050 mots actifs chacune**, couverture strictement symétrique.
- `vocabulary_translations` (vocabulary_id, target_locale, translation, example_sentence,
  example_transliteration, example_translation) — `target_locale='fr'` uniquement pour l'instant.
- `categories` (21 : greetings, basics, travel, food, daily_life, family, numbers_time,
  colors_desc, health_body, market_shopping, work_studies, emotions, religion_culture, transport,
  technology, home_interior, clothing, weather_nature, animals, sports_leisure, money_banking).
- `languages` (id, code, name, native_name, direction).

| `id` | `code` | Langue | Voix edge-tts RVM (`config/tts_voices.php`) |
|---|---|---|---|
| 1 | `ary` | Darija marocain | `ar-MA-MounaNeural` / `ar-MA-JamalNeural` — pas de voix Darija dédiée, best-effort |
| 2 | `ar` | Arabe littéraire | `ar-SA-ZariyahNeural` / `ar-SA-HamedNeural` |
| 3 | `en` | Anglais | `en-US-AvaNeural` / `en-US-AndrewNeural` |
| 4 | `de` | Allemand | `de-DE-KatjaNeural` / `de-DE-ConradNeural` |
| 5 | `es` | Espagnol | `es-ES-ElviraNeural` / `es-ES-AlvaroNeural` |
| 6 | `pt` | Portugais (Brésil) | `pt-BR-FranciscaNeural` / `pt-BR-AntonioNeural` |
| 7 | `it` | Italien | `it-IT-ElsaNeural` / `it-IT-DiegoNeural` |
| 8 | `nl` | Néerlandais | `nl-NL-ColetteNeural` / `nl-NL-MaartenNeural` |
| 9 | `ru` | Russe | `ru-RU-SvetlanaNeural` / `ru-RU-DmitryNeural` |
| 10 | `tr` | Turc | `tr-TR-EmelNeural` / `tr-TR-AhmetNeural` |
| 11 | `zh` | Chinois | `zh-CN-XiaoxiaoNeural` / `zh-CN-YunxiNeural` — **⚠️ code RVM `zh-CN`, pas `zh`** |
| 12 | `ko` | Coréen | `ko-KR-SunHiNeural` / `ko-KR-InJoonNeural` |

**Credentials** (hors git) : `host.docker.internal` (pas `localhost`), `DB_NAME=vocabag`, user
`vocabag`. Credential n8n `Vocabag DB` (id `qZ2NnMkubbTE5fNX`). **Grant `@'%'` appliqué le
2026-09-01** (`channels/vocabag/scripts/grant_vocabag_remote_access.sql`, SELECT seul) — vérifié
fonctionnel en conditions réelles (workflow exécuté de bout en bout avec succès).

### Images — Pexels (pas `vocabulary.image_url`)

**Décision 2026-09-01** : ne plus utiliser l'`image_url` statique stockée en base — recherche
**Pexels en direct** par mot, avec des mots-clés pertinents (catégorie + traduction FR), pour des
visuels plus variés et mieux ciblés que le pool fixe déjà utilisé par tous les autres mots de la
même catégorie. Même pattern que le workflow muzrappel existant (`Get images`/`Get image1`) :

```
GET https://api.pexels.com/v1/search
  ?query={{ category_lisible }}, {{ translation }}
  &orientation=portrait
  &per_page=1
Authorization: <PEXELS_API_KEY>   (clé Pexels déjà utilisée par muzrappel, réutilisée telle quelle — non reproduite ici)
```
puis téléchargement direct de `{{ $json.photos[0].src.portrait }}` (déjà en orientation portrait,
pas besoin de recadrage).

> **⚠️ Requête obsolète depuis le 2026-09-19** (section 11) : envoyer du français à Pexels renvoyait des
> photos hors sujet (« Bonjour Café », un parc à Rennes). La requête est maintenant construite
> à partir de **mots-clés visuels anglais par catégorie + culture du pays de la langue**, avec
> `per_page=8` et un filtre sur la description des photos. **Note sécurité** : la clé Pexels a été
> retirée de ce document (2026-09-19, avant son déplacement dans le dépôt Vocabag) ; elle reste **en clair dans les
> nœuds du workflow n8n** (et dans l'historique git de l'ancien emplacement, dépôt RapidVideoMaker) — à déplacer
> vers une credential n8n, et à **renouveler** si le dépôt est partagé. **⚠️ Ce dépôt sert ses `.md` publiquement**
> (`https://vocabag.com/docs/CLAUDE.md` répond 200, contrairement à RapidVideoMaker qui les bloque) : ne pas
> déployer ce document en prod sans avoir bloqué l'accès HTTP aux `.md` (règle `.htaccess`) — il détaille
> l'architecture interne, des identifiants de credentials n8n et des ids de comptes.

## 2. Calendrier éditorial multilingue ("actualité")

> **⚠️ Section historique — remplacée le 2026-09-19** par un tirage aléatoire pondéré (section 11).
> Les listes fixes par mois ci-dessous ne sont plus dans le workflow.

Pilote **langue + catégorie**, indépendamment du genre (section 3). Même esprit que
`trends_by_month` dans `inori.py`.

### a) Vacances scolaires françaises × pays destination × langue

| Période | Destinations typiques | `language_code` | Catégories |
|---|---|---|---|
| Vacances d'hiver (février) | Maroc, Turquie | `ary`, `tr` | `travel`, `clothing`, `weather_nature` |
| Vacances de printemps (avril) | Pays-Bas, Corée | `nl`, `ko` | `weather_nature`, `sports_leisure`, `travel` |
| Été (juillet-août) | Espagne, Italie, Portugal, Turquie, Maroc | `es`, `it`, `pt`, `tr`, `ary` | `travel`, `food`, `transport`, `market_shopping` |
| Rentrée (septembre) | — | rotation 12 langues | `work_studies`, `basics`, `greetings` |
| Toussaint (fin octobre) | Allemagne, Pays-Bas | `de`, `nl` | `food`, `market_shopping` |
| Noël (décembre) | Allemagne | `de` | `family`, `food`, `money_banking` |
| Nouvel an (janvier) | Russie | `ru` | `family`, `numbers_time` |

### b) Fêtes propres à chaque langue/pays

| Événement | Période | `language_code` | Catégories |
|---|---|---|---|
| Nouvel An chinois | janv/fév | `zh` | `family`, `food` |
| Ramadan / Aïd | mobile | `ary`/`ar` | `religion_culture`, `food` |
| Oktoberfest | sept/oct | `de` | `food` |
| Carnaval de Rio | fév/mars | `pt` | `sports_leisure`, `emotions` |
| Chuseok | sept/oct | `ko` | `family`, `food` |
| Grand événement sportif | ponctuel | pays hôte/finaliste | `sports_leisure` |
| Nouvel An russe orthodoxe | 7 janvier | `ru` | `family` |

Implémenté dans le nœud `Choisir theme` (Code) — table mensuelle simplifiée en JS, pioche
aléatoirement une entrée du mois courant.

## 3. Genres de vidéos (rotation par jour de semaine)

**Décision 2026-09-01** : alterner 3 formats pour la variété, tous exploitables sans curation de
contenu supplémentaire (aucun ne nécessite d'ajout à la base `vocabag`).

```
Lundi / Mercredi / Vendredi → 3 mots
Mardi / Jeudi                → Duel de langues
Samedi / Dimanche            → Phrase du jour
```

Implémenté dans `Choisir genre` (Code, en tête de workflow) :
```js
const weekday = $now.weekday; // Luxon : Monday=1 ... Sunday=7
const genre = [1,3,5].includes(weekday) ? '3mots'
            : [2,4].includes(weekday)   ? 'duel'
            : 'phrase';
```

**Tous les genres produisent exactement 3 "reveals"** (mot/phrase/concept) pour garder une
architecture de fusion uniforme (toujours 8 clips : 1 intro + 3 reveals × 2 écrans question/réponse
+ 1 outro) — voir sections 4 et 4bis.

### a) 3 mots
3 mots de la catégorie/langue du mois (section 2), anti-répétition par langue+catégorie.
```sql
SELECT v.id, v.word, v.transliteration,
       vt.translation, vt.example_sentence, vt.example_transliteration, vt.example_translation,
       '{{ languageCode }}' AS target_language_code
FROM vocabulary v
JOIN vocabulary_translations vt ON vt.vocabulary_id = v.id AND vt.target_locale = 'fr'
WHERE v.language_id = {{ languageId }} AND v.category_id = {{ categoryId }} AND v.active = 1
ORDER BY FIND_IN_SET(v.id, '{{ usedIdsCsv }}') > 0, RAND()
LIMIT 3
```

### b) Duel de langues — refondu le 2026-09-05

**Ancien design abandonné** : tirage d'un concept partagé par ≥4 langues puis 3 langues au hasard
parmi elles (ex. un post publié montrait *rivière* en Darija + Chinois + Turc dans la même vidéo).
Retour utilisateur (2026-09-05) : une vidéo doit être associée à 1 langue, ou 2 maximum si la
comparaison a un sens — sinon les hashtags ne ciblent aucune langue précise et la vidéo n'apprend
rien d'actionnable à quelqu'un qui suit une langue donnée.

**Nouveau design** :
- **Paires de langues curées** (pas de tirage parmi les 12) — uniquement des langues cognates ou
  proches, où la comparaison a un intérêt pédagogique réel : `ary`↔`ar` (Darija/Arabe littéraire),
  `es`↔`it`, `es`↔`pt`, `it`↔`pt` (langues latines), `de`↔`nl` (langues germaniques proches). Les
  5 autres langues (`en`, `ru`, `tr`, `zh`, `ko`) restent hors du genre "duel", solo uniquement.
- **Calendrier dédié `duelCalendar`** (nœud `Choisir theme`, genre-aware) — même principe que le
  calendrier solo (section 2) mais indexé par paire + catégorie, pioché par mois. La catégorie du
  calendrier est maintenant **appliquée** à ce genre (elle était ignorée avant) : les 3 concepts
  comparés partagent tous la même catégorie thématique (ex. 3 animaux, pas un mélange).
- **SQL réécrit — 1 ligne par reveal, les 2 langues dans la même ligne** (au lieu de 1 ligne par
  langue) :
```sql
SELECT t.* FROM (
  SELECT va.id AS id_a, va.word AS word_a, va.transliteration AS transliteration_a,
         vb.id AS id_b, vb.word AS word_b, vb.transliteration AS transliteration_b,
         vta.translation AS translation,
         vta.example_sentence AS example_sentence_a, vta.example_transliteration AS example_transliteration_a, vta.example_translation AS example_translation_a,
         vtb.example_sentence AS example_sentence_b, vtb.example_transliteration AS example_transliteration_b, vtb.example_translation AS example_translation_b,
         ROW_NUMBER() OVER (PARTITION BY vta.translation ORDER BY RAND()) AS rn
  FROM vocabulary va
  JOIN vocabulary_translations vta ON vta.vocabulary_id = va.id AND vta.target_locale = 'fr'
  JOIN vocabulary vb ON vb.category_id = va.category_id AND vb.language_id = {{ languageIdB }} AND vb.active = 1
  JOIN vocabulary_translations vtb ON vtb.vocabulary_id = vb.id AND vtb.target_locale = 'fr' AND vtb.translation = vta.translation
  WHERE va.language_id = {{ languageIdA }} AND va.category_id = {{ categoryId }} AND va.active = 1
) t
WHERE t.rn = 1
ORDER BY RAND()
LIMIT 3
```
- **⚠️ Aucun garde-fou si <3 correspondances.** La requête est bornée à une seule catégorie
  (`va.category_id = {{ categoryId }}`) ET une seule paire de langues curée — une catégorie fine
  (ex. `money_banking`, `religion_culture`) sur une paire donnée peut ne partager que 1-2 concepts
  ce mois-ci. Vérifié dans le workflow réel (`Preparer etapes fusion`) : la liste des étapes de
  fusion est **fixe** (toujours 3 reveals attendus, `1_a2`/`2_a2`/`3_a2` inclus), aucun nœud ne
  vérifie le nombre de lignes retourné par cette requête avant de lancer la boucle de reveals — si
  elle retourne <3 lignes, la boucle de fusion tentera de lire des fichiers clip pour un reveal
  jamais généré et échouera. Non corrigé (hors périmètre de cette relecture doc, pas remonté par
  l'utilisateur) — à garder en tête si un genre "duel" échoue sur une paire/catégorie peu fournie.
- **Écran réponse en 2 clips distincts, même image, même texte affiché, audio différent**
  (retour utilisateur 2026-09-05 : plus simple à câbler que fusionner 2 pistes audio en une
  seule, et l'API RVM n'a de toute façon pas de mode concat audio-only). Pour chaque reveal, le
  nœud `Sauver clip question` bifurque via `IF genre duel (reponse)` : les vidéos "duel" génèrent
  **2 écrans réponse successifs** (`_a.mp4` voix+mot langue A, `_a2.mp4` voix+mot langue B), tous
  deux affichant le même texte bilingue (`answerDisplay` = les 2 mots + la traduction FR), sur la
  même image Pexels partagée (réutilisée une 3e fois). Écran Question resté unique, formulé pour
  les 2 langues à la fois : *« Comment dit-on X en {langue A} et en {langue B} ? »*.
- **Vidéo finale à 12 clips au lieu de 9** pour ce genre uniquement (intro + titre + 3×[question +
  réponse A + réponse B] + outro). **Assemblage générique, pas de branche dédiée** : depuis le
  refactor "fusion par paires" du 2026-09-05 (section 5), il n'existe plus de nœuds séparés
  `IF genre duel (assemblage)`/`Fusionner 11 clips (duel)`/`Creer video finale (duel)` — la même
  boucle `Boucle fusion par paires` traite les deux genres, `Preparer etapes fusion` construit
  simplement une liste plus longue pour `duel` (avec `_a2` intercalé, voir section 5). Vérifié
  dans le workflow réel : ces 3 nœuds n'existent plus (supprimés lors du refactor).
- `target_language_code` n'existe plus dans ce genre (remplacé par `_a`/`_b` suffixés sur les
  champs) — la voix et la requête Pexels sont résolues par reveal comme avant, mais pour 2 langues
  simultanément (`voiceA`/`voiceB`, `ttsLangA`/`ttsLangB`).

### c) Phrase du jour
3 phrases d'exemple (déjà en base : `example_sentence`/`example_translation`, pas de mot isolé)
de la langue/catégorie du mois — même requête que "3 mots", le nœud de préparation des reveals
utilise `example_sentence`/`example_translation` comme contenu principal au lieu de `word`.

## 4. Format vidéo — écrans Question/Réponse (2026-09-01)

Ancien format (mot qui apparaît en silence) remplacé par un **quiz en 2 écrans par reveal** :

| Écran | Voix | Texte à l'écran | Contenu audio |
|---|---|---|---|
| **Question** | FR (`fr-FR-DeniseNeural`) | "Comment dit-on *{mot FR}* en {langue} ?" | `text_to_mp3` texte FR |
| **Réponse** | langue cible (table section 1) | Mot/phrase cible (translittération) + rappel FR | `text_to_mp3` texte natif |

**Image partagée entre les 2 écrans** d'un même reveal (1 seule recherche Pexels par reveal, pas
par écran) — téléchargée une fois, réutilisée dans les 2 appels `image_to_video`.

**⚠️ Jamais afficher le mot natif en écriture arabe (`ary`/`ar`) à l'écran** — `drawtext` FFmpeg
n'a pas de shaping RTL/bidi. Texte à l'écran = `transliteration` (latin) + rappel FR ; la
prononciation réelle passe par l'audio TTS. Pour `zh`/`ko` (Hanzi/Hangul) : tester le rendu avant
publication, polices serveur actuelles (`worker/fonts/`, DejaVu Sans) ne couvrent pas les
idéogrammes — retomber sur translittération si glyphes manquants.

Options `image_to_video` par écran (identiques aux 2, seul le texte/l'audio change) :
```json
{
  "text": "<texte de l'écran>",
  "text_mode": "word_by_word",
  "word_reveal_speed": 0.7,
  "word_anim": "fade",
  "text_position": "bottom",
  "font_size": 64,
  "box": true,
  "box_color": "black@0.5",
  "enable_image_motion": true,
  "image_motion_effect": "ken_burns",
  "motion_intensity": 0.4,
  "width": 1080,
  "height": 1920
}
```

**Rythme ralenti (2026-09-01, suite 6)** — retour utilisateur : "trop rapide, on n'a pas le temps
de capter l'information". Quatre leviers combinés :
- `word_reveal_speed` : `1.2` → `0.7` mots/s (révélation du texte plus lente).
- `motion_intensity` : ajouté à `0.4` (était implicite à `1.0` par défaut — Ken Burns plus doux).
- `slow: true` sur **tous** les appels `text_to_mp3` (Question, Réponse, Intro, Outro) — débit
  vocal -25%, ce qui allonge aussi mécaniquement la durée du clip (la durée du clip
  `image_to_video` suit la durée de l'audio, pas un paramètre indépendant).
- `transition_duration` de la fusion : `0.4` → `0.7`s (coupures moins brusques entre écrans).

Effet mesuré : vidéo de test passée de ~20s à **30.8s** pour le même nombre de reveals.

**Rythme différencié par écran (2026-09-05)** — retour utilisateur : le ralenti uniforme
pénalisait aussi le FR (intro/outro/question), qui n'a pas besoin d'être ralenti pour un locuteur
natif. `slow` repassé à `false` sur `Generer audio question`, `Generer audio intro`,
`Generer audio outro` — **seul `Generer audio reponse` (et ses clones duel A/B, voir section 3b)
reste `slow: true`**, puisque c'est le seul écran qui prononce le mot dans la langue étrangère à
assimiler. `word_reveal_speed`/`motion_intensity`/`transition_duration` inchangés à l'époque —
**voir le bug et le fix ci-dessous, ce paragraphe est resté incomplet 1 jour.**

**Bug réel trouvé et corrigé (2026-09-06) : `word_reveal_speed=0.7` fixe, jamais réajusté après
le retour à `slow:false`.** Signalé par l'utilisateur après avoir regardé une vraie publication
("la vitesse d'écriture du texte est trop lente et ne finit pas avant la scène suivante" + "la
vidéo ne contenait que l'intro + le titre qui se répète x2"). Diagnostic par extraction de frames
sur la vidéo réellement publiée (`ffmpeg -ss ... -frames:v 1`) : le fond de la scène titre était
correct (vérifié isolément, ce n'était qu'un artefact de transition xfade vu dans la vidéo
fusionnée), mais **chaque écran `word_by_word` (titre, question, réponse, intro, outro, duel A/B —
les 7) restait figé sur les 1-3 premiers mots** jusqu'à la coupe — d'où l'impression de "titre
répété x2" (3 écrans Question différents, mais tous figés sur le même 1er mot "Comment").
- **Cause** : `word_reveal_speed` avait été réglé à `0.7` le 2026-09-01 pour des clips ralentis
  (`slow:true`, donc longs). Le 2026-09-05, `slow` est repassé à `false` sur intro/outro/question/
  titre → clips **raccourcis mécaniquement** (durée = durée audio TTS), mais `word_reveal_speed`
  n'a jamais été réajusté — explicitement noté "inchangé" dans le paragraphe ci-dessus. Résultat :
  à 0.7 mot/s, une question de 9 mots ("Comment dit-on « C'est bon » en Anglais ?") a besoin de
  ~13s pour se révéler entièrement, alors que le clip ne dure que ~3.1s (durée du TTS à débit
  normal) — coupée après le seul mot "Comment".
- **Fix : vitesse calculée dynamiquement par clip**, pas une valeur fixe. `edge-tts` produit du
  MP3 **CBR 48kbps mono constant** (vérifié en conditions réelles : 14976 octets = 2.496s TTS,
  exact) — donc la durée audio exacte se calcule sans aucun appel externe :
  `duree = octets*8/48000`. Les 7 nœuds `Telecharger audio *` (question/reponse/intro/outro/titre/
  reponse duel A/B) ont reçu `fullResponse:true` pour exposer le header `Content-Length` de la
  réponse HTTP (`api/download.php` le fixe correctement, vérifié dans le code RVM). Les 7 nœuds
  `Construire options *` calculent désormais `wordRevealSpeed = wordCount / (audioDuration * 0.85)`
  (clamp `[0.3, 5.0]`, même bornes que `parse_image_to_video_options()` côté RVM) avant d'appeler
  `image_to_video` — marge de 15% pour que le dernier mot ait le temps d'être lu avant la coupe.
  Repli sur `0.7` (try/catch) si le header est absent/invalide, pour ne jamais faire échouer une
  vidéo à cause de ce calcul.
- **Testé en conditions réelles (genre `3mots`, Allemand, catégorie `work_studies`, Instagram
  déconnecté pour ce test)** : les 3 écrans Question + la scène titre s'affichent désormais
  **entièrement** avant la coupe (vérifié par extraction de frames en fin de chaque clip) — contre
  1-3 mots avant le fix. Vidéo finale 29.5s, 8/8 fusions par paires réussies (aucune régression du
  fix OOM/décalage A-V du 2026-09-05), `words.json` écrit une seule fois (aucune régression du
  garde-fou multi-déclenchement). Sauvegarde : `/root/rvm-vocabag-channel/
  vocabag_workflow_word_reveal_speed_dynamic_2026-09-06.json`.
- **Non touché** : aucun code RVM modifié pour ce fix (contrairement au fix CPU/OOM du même jour,
  voir `ENDOVER.md` RapidVideoMaker) — entièrement contenu dans les nœuds Code du workflow vocabag.

**Bug distinct trouvé et corrigé le même jour : emoji 🌍 envoyé au TTS de la scène titre.**
Demande explicite utilisateur ("fait attention à ne pas lire les émoticônes dans l'audio") avant
le test de re-validation ci-dessus. `titleText` (nœud `Preparer scene titre`) sert à la fois de
texte affiché (`drawtext`, avec l'emoji, correct) ET de texte envoyé tel quel au nœud
`Generer audio titre` (`text_to_mp3`) — le seul écran concerné parmi les 7 (question/réponse/
intro/outro n'ont jamais d'emoji dans leur texte). Fix : nouveau champ `titleTextAudio` dans
`Preparer scene titre` = `titleText` avec les plages Unicode emoji retirées
(`\u{1F300}-\u{1FAFF}`, `\u{2600}-\u{27BF}`, `\u{FE0F}`) ; `Generer audio titre` envoie désormais
`titleTextAudio` au lieu de `titleText`. **Confirmé indirectement par la mesure** : durée du clip
titre passée de 3.9s (emoji envoyé au TTS) à 2.04s (emoji retiré) pour le même texte affiché — le
TTS vocalisait bien quelque chose pour l'emoji avant ce fix. Testé en conditions réelles avec
Instagram connecté (genre `3mots`, Allemand) : texte titre toujours affiché en entier (emoji
compris, visuellement) avant la coupe, malgré la durée audio plus courte — la vitesse de révélation
dynamique (fix précédent) s'est réajustée automatiquement à la nouvelle durée sans intervention.
Publié avec succès : `https://www.instagram.com/reel/Dc9aA74jcKn/`. Sauvegarde :
`/root/rvm-vocabag-channel/vocabag_workflow_no_emoji_tts_2026-09-06.json`.

## 4bis. Intro et outro (2026-09-01, suite 6)

Chaque vidéo est désormais encadrée par un clip d'intro et un clip d'outro, générés en parallèle
de la boucle de reveals (ne dépendent pas de la sélection des mots — démarrent dès que
genre+thème sont connus). Même mécanique que les écrans Question/Réponse (recherche Pexels →
`text_to_mp3` voix FR `slow:false` → `image_to_video` → sauvegarde), juste hors boucle. Voir
"Rythme différencié par écran" ci-dessus (section 4) : `slow` a été repassé à `false` sur
`Generer audio intro`/`Generer audio outro` le 2026-09-05, ce paragraphe (initialement écrit
le 2026-09-01 avec `slow:true`) reflète l'état actuel, pas l'état d'origine.

| Clip | Texte (voix FR) | Recherche Pexels |
|---|---|---|
| **Intro** | Genre-aware : *"Vocabag ! Aujourd'hui : 3 mots à connaître en {langue}."* (3mots) / *"Vocabag ! Un mot, plusieurs langues. Découvrons ça ensemble."* (duel) / *"Vocabag ! La phrase du jour, en {langue}."* (phrase) | `world languages education` (fixe, cohérence de marque) |
| **Outro** | *"Abonne-toi à Vocabag pour apprendre un nouveau mot chaque jour !"* (fixe, tous genres) | `notebook pen writing study` (fixe) |

Fichiers : `{folder}_0_intro.mp4` et `{folder}_9_outro.mp4` (numérotation volontairement hors de
la plage `1`-`3` des reveals, pour rester lisible sur disque). Nœud `Preparer intro et outro`
(Code) branché sur `Construire requete mots` (a besoin de `genre`+`theme`+`folder`, pas des mots
sélectionnés). Déclenchement des lectures de fichiers (`Lire clip intro`/`Lire clip outro`) **depuis
la fin de leur propre chaîne de rendu**, pas depuis la boucle des reveals — évite de dépendre de
l'ordre relatif de complétion entre les deux chaînes parallèles.

## 4ter. Scène titre (2026-09-05)

2e scène de chaque vidéo (juste après l'intro, avant le 1er reveal) — carte de titre avec fond
**fixe par langue thème** (pas de recherche Pexels dynamique, à la différence de toutes les autres
scènes) : mêmes mécanique/paramètres `image_to_video` que l'intro/outro (voix FR `slow:false`,
`word_reveal_speed`/`motion_intensity` identiques), mais `text_position: 'center'` et
`font_size: 72` (carte de titre, pas un sous-titre bas d'écran), et surtout **la source de l'image
est un fichier local du dossier `channels/vocabag/images/languages/`**, pas un téléchargement
Pexels — pattern copié du nœud `Select background` de "Video had creator free" (fond fixe par
catégorie pour muzrappel, ici fond fixe par langue thème pour vocabag).

**Volume Docker ajouté** : `channels/vocabag/images:/images/vocabag:ro` dans
`/root/n8n/docker-compose.yml` (redémarrage du conteneur nécessaire après ajout, comme pour tout
nouveau volume — voir `CLAUDE.md` racine RVM section "Docker n8n"). `N8N_RESTRICT_FILE_ACCESS_TO`
couvrait déjà `/images` en préfixe générique, aucun changement d'env nécessaire.

**Résolution du fond par langue thème** (nœud `Preparer scene titre`, genre-aware comme
`Preparer intro et outro`) :
- Genres solo (`3mots`/`phrase`) : `/images/vocabag/languages/{languageCode}.png` — 1 fichier par
  langue, 12 au total.
- Genre `duel` : `/images/vocabag/languages/{languageCodeA}_{languageCodeB}.png` — 1 fichier
  dédié par paire curée (section 3b), 5 au total (`ary_ar`, `es_it`, `es_pt`, `it_pt`, `de_nl`).
- **17 fichiers au total.** Le texte affiché (`titleText`) et parlé (voix FR) est identique au
  titre de la légende Instagram (`Construire legende Instagram`) : *"3 mots en {langue} 🌍"* /
  *"{langue A} vs {langue B} 🌍"* / *"Phrase du jour en {langue} 🌍"*.
- **Placeholders générés le 2026-09-05** (dégradés de couleur distincte par langue via PIL, 1080×
  1920, aucun texte pré-imprimé) — à remplacer par de vrais visuels par langue quand disponibles,
  simple remplacement de fichier (même chemin/nom), aucun changement de workflow nécessaire.
  Ownership `debian:debian` (comme `videos/` — le conteneur n8n tourne en uid 1000/`debian`).

**Fichier** : `{folder}_0b_titre.mp4` (numérotation entre l'intro `_0_` et les reveals `_1_`).
Nœud `Lire clip titre` déclenché depuis la fin de sa propre chaîne (`Sauver clip titre`), comme
intro/outro. **Note (post-refactor "fusion par paires", section 5)** : le paragraphe précédent sur
`dataTitre`/2 fusions à index de merge fixe décrivait l'assemblage d'origine du 2026-09-05
(avant-refactor). Depuis, le titre n'est qu'une entrée de plus (`'0b_titre'`, en tête de liste
juste après l'amorce intro) dans la liste générique construite par `Preparer etapes fusion` —
lu par le même nœud générique `Lire clip etape` que n'importe quel autre clip de la séquence,
aucun champ dédié `dataTitre`.

## 5. Séquence d'appels API RVM (9 clips solo / 12 clips duel)

Genres `3mots`/`phrase` : **9 clips** (1 intro + 1 titre + 3 reveals × 2 écrans + 1 outro).
Genre `duel` (voir section 3b) : **12 clips** (1 intro + 1 titre + 3 reveals × [question + réponse
A + réponse B] + 1 outro). **Assemblage générique unique** (pas de branche dédiée par genre) —
voir "Séquence d'assemblage final — fusion par paires" ci-dessous : `Preparer etapes fusion`
construit simplement une liste plus longue pour `duel`, la même `Boucle fusion par paires` et le
même nœud `Creer video finale` traitent les deux genres indifféremment.

**⚠️ Historique : 2 itérations avant la solution finale (2026-09-05).**

1. *Retrait pur des transitions* (`transition_type`/`transition_duration` supprimés) — corrige
   l'OOM du VPS (3.8 Go RAM, swap souvent >85% — `concat_xfade()` décodant 9-12 flux simultanés
   montait à ~2.5-2.7 Go de RSS, confirmé par 4 kills OOM exacts dans `dmesg -T`/syslog) en
   basculant sur `concat_stream_copy()` (remux, quasi zéro RAM côté serveur). **Mais** introduit
   un décalage texte/voix perceptible : chaque clip a un écart natif de 5-16ms entre durée vidéo
   (multiple entier de frames 30fps) et durée audio (durée TTS exacte), jamais recalé par un
   simple remux — ces écarts s'accumulent sur 9-12 clips concaténés (signalé par l'utilisateur
   après publication réelle).
2. **Solution retenue : fusion par paires** (section "Séquence d'assemblage final" ci-dessous) —
   remplace l'unique appel à N flux par une boucle de fusions à 2 flux avec un xfade **court**
   (`transition_duration=0.3`). Cumule les deux propriétés : jamais plus de 2 décodeurs ouverts
   (~450 Mo de RSS mesuré, contre 2.5-2.7 Go) ET recalage propre à chaque étape (ré-encodage,
   pas de remux) → écart mesuré ramené à **52ms sur toute la durée d'une vidéo de 26s** (contre
   un décalage cumulatif visible avant). C'est la méthode en production actuellement.

### Séquence d'assemblage final — fusion par paires (2026-09-05)

Après `Reduire a 1 item` (toutes les reveals terminées) :
1. `Lire clip intro (final)` lit `{folder}_0_intro.mp4` → `Sauver clip accum initial` l'écrit
   directement comme `{folder}_final.mp4` (amorce : le fichier "accum" ET "final" ne font qu'un,
   pas de fichier intermédiaire séparé).
2. `Preparer etapes fusion` (Code, genre-aware) construit la liste ORDONNÉE des clips restants à
   ajouter un par un : solo = `['0b_titre','1_q','1_a','2_q','2_a','3_q','3_a','9_outro']` (8
   étapes) ; duel = **`_a2` entrelacé après chaque `_a` de son reveal**, pas ajouté en bloc à la
   fin — `['0b_titre','1_q','1_a','1_a2','2_q','2_a','2_a2','3_q','3_a','3_a2','9_outro']` (11
   étapes), pour respecter l'ordre question→réponse A→réponse B par reveal décrit en section 3b.
   Une liste construite par simple concaténation (solo + `['1_a2','2_a2','3_a2']`) jouerait les
   3 clips réponse B après l'outro — vidéo dans le désordre.
3. `Boucle fusion par paires` (splitInBatches, batch=1) itère sur cette liste. À chaque étape :
   `Lire accum` (relit `{folder}_final.mp4`, mis à jour par l'étape précédente) + `Lire clip
   etape` (le prochain clip) → `Fusionner accum+clip` (merge combine 2) → `Creer video finale`
   (mode=fusion, **2** `videos[]`, `transition_type=fade`, `transition_duration=0.3`) → poll/if/
   wait (nœuds `Poll video finale`/`IF video finale prete`/`Wait video finale`, réutilisés
   inchangés) → `Telecharger video finale` → `Sauver video finale` **réécrit** `{folder}_final.mp4`
   → reboucle dans `Boucle fusion par paires` (même pattern que `Sauver clip reponse` →
   `Boucle sur les reveals`).
4. Sortie "done" (index 0) de `Boucle fusion par paires` → déclenche **UNE SEULE FOIS**
   `Preparer words.json` ET `Construire legende Instagram` (donc la publication Instagram).

**⚠️ Piège évité — multi-déclenchement Instagram.** `IF video finale prete` (true) fanait
initialement vers `Telecharger video finale` ET `Construire legende Instagram` directement — en
bouclant ce nœud à travers N-1 étapes, la légende (et donc l'appel Instagram) se serait
déclenchée à CHAQUE étape intermédiaire. Cette connexion directe a été retirée ; le déclenchement
Instagram vient exclusivement de la sortie "done" de la boucle. Vérifié par test :
`grep -c "Construire legende Instagram"` dans les logs d'exécution = exactement 1.

**⚠️ Piège rencontré et résolu — `executionOrder`.** Après ce refactor (150→136 nœuds), la
branche parallèle `Preparer scene titre` (3e sortie de `Construire requete mots`, câblage pourtant
identique à avant) ne s'exécutait plus jamais — reproductible sur 3 tests différents (genres et
paires de langues variés), sans lien avec le contenu. Cause : le réglage `executionOrder: "v1"`
du workflow (`wf.settings`, pas un nœud) — passage à **`executionOrder: "v2"`** résolu
immédiatement. **Si une branche parallèle semble ne jamais s'exécuter alors que son câblage est
correct dans le JSON exporté, vérifier `wf.settings.executionOrder` avant toute autre piste.**

**Coût** : le rendu final prend plus de temps qu'un appel unique (N-1 aller-retours API
séquentiels au lieu d'1), de l'ordre de +3 à 5 minutes selon le genre. Accepté par l'utilisateur
comme compromis pour la fiabilité (RAM) et la qualité (sync A/V).

`Authorization: Bearer <token>` — token admin `api_tokens.id=31` (`n8n-vocabag-automation`),
stocké hors dépôt (`/root/rvm-vocabag-channel/n8n-api-token.txt`). Host : `https://rapidvideomaker.com`
(prod — pipeline non isolé staging/prod, même convention que `inori.py`).

Par écran (Question/Réponse/Intro/Outro) : `text_to_mp3` (voix selon écran) → poll → download ;
`image_to_video` (image Pexels partagée + audio de l'écran) → poll → download → sauvegarde disque
— noms fixes pour permettre une fusion à arité fixe : `{folder}_0_intro.mp4`,
`{folder}_{revealIndex}_{q|a}.mp4`, `{folder}_9_outro.mp4`.

**⚠️ Fusion finale : voir "Séquence d'assemblage final — fusion par paires" ci-dessus.** Ce
paragraphe décrivait à l'origine (2026-09-01) un appel unique `mode=fusion` à 8 `videos[]`
(`transition_duration=0.7`) — design abandonné le 2026-09-05 car il causait des OOM (`concat_xfade`
décodant 8-11 flux simultanés, voir historique plus haut). **Ne pas implémenter la fusion selon
cette ancienne description** : la méthode en production actuelle est la boucle de fusions par
paires (2 `videos[]` à la fois, `transition_duration=0.3`), déjà détaillée en section 5 ci-dessus.

`text_mode=word_by_word`/`word_anim=fade` non documentés dans `docs/api.md` mais acceptés par
l'API (vérifié dans `api/v1/render.php` — dette documentaire pré-existante).

## 6. Écriture des résultats

1. `folder` = `{yyyyMMdd_HHmmss}_{genre}_{languageCode}_{category}` — calculé une seule fois dans
   `Construire requete mots`, propagé à tous les nœuds en aval (reveals, intro, outro).
2. Fichiers plats (pas de sous-dossier — `readWriteFile` ne crée pas les répertoires manquants,
   piège rencontré et corrigé le 2026-09-01) : `.../videos/{folder}_0_intro.mp4`,
   `{folder}_1_q.mp4` … `{folder}_3_a.mp4`, `{folder}_9_outro.mp4`, `{folder}_final.mp4`,
   `{folder}_words.json`.
3. `words.json` — array des 3 reveals complets (id, word/phrase, transliteration, translation,
   example_sentence, target_language_code, image Pexels utilisée) + `introText`/`outroText` —
   traçabilité + description Instagram.

## 7. État au 2026-09-01

- [x] Dossier `channels/vocabag/{videos,images,json,sounds,fonts,scripts}/` créé.
  **`videos/` en `debian:debian` 775** (pas `www-data`) — le conteneur n8n tourne en `uid 1000`
  (= `debian` sur l'hôte), piège rencontré et corrigé lors des tests.
- [x] Volume Docker `channels/vocabag/videos:/files/vocabag:rw`, conteneur n8n redémarré.
- [x] Token API admin RVM créé (`api_tokens.id=31`).
- [x] Credential MySQL `Vocabag DB` créée + grant `@'%'` appliqué et vérifié fonctionnel.
- [x] **Version 1 du workflow (3 mots, 1 écran/mot) testée de bout en bout avec succès** —
  2 bugs réels trouvés et corrigés en testant (permissions dossier, câblage boucle→fusion cassé),
  vidéo complète générée + publiée sur Instagram automatiquement.
- [x] **Version 2 (2026-09-01, suite 4) — 3 genres + écrans Q/R + Pexels dynamique — testée avec
  succès.** Un bug SQL réel trouvé et corrigé en testant : la requête "Duel de langues" utilisait
  une sous-requête scalaire contenant `RAND()` dans une clause `WHERE` — MySQL la réévalue à
  chaque ligne scannée au lieu de la mettre en cache (non déterministe), ce qui la faisait tourner
  indéfiniment. Corrigée en `JOIN` sur une derived table (matérialisée une seule fois) : passée
  d'un timeout à 0.23s. `GROUP BY l.id` remplacé par `ROW_NUMBER() OVER (PARTITION BY l.id ...)`
  pour la même raison (incompatible `sql_mode=only_full_group_by`). Test réel complet : genre
  "Duel de langues" tiré, concept "Destination" trouvé en base, décliné en 3 langues (PT/ZH/ES),
  6 clips générés (image Pexels dynamique + TTS par écran), fusionnés, publiés sur Instagram avec
  légende adaptée au genre.
- [x] **Bug de multiplication x3 trouvé et corrigé (2026-09-01, suite 5) — 3 publications
  Instagram identiques par exécution, corrigé.** Hypothèse initiale erronée (double trigger
  Manual+Schedule via `n8n execute` CLI) — **infirmée** : le test de reproduction avec le Schedule
  Trigger déconnecté a quand même produit 3 posts identiques. Cause réelle trouvée en inspectant
  directement les données d'exécution dans `database.sqlite` de n8n (format `flatted`, unflatten
  en Python) : la sortie "fin de boucle" (index 0) de `splitInBatches` transporte les **3 items
  agrégés** de la boucle, pas un simple signal de fin — branchée directement sur les 6 nœuds
  `Lire clip`, chacun traitait donc 3 items identiques (même fichier relu 3 fois) au lieu d'1,
  ce qui multipliait tout le reste (fusion, vidéo finale, conteneur Instagram, publication) par 3
  **en une seule exécution du workflow** (confirmé : `Construire legende Instagram` avait tourné
  3 fois dans la même `executionId`). Corrigé en insérant un nœud `Reduire a 1 item` (Code,
  `return [$input.first()];`) entre la sortie "done" et les 6 `Lire clip`. **Revalidé avec succès**
  après correction : chaque nœud de la chaîne (`Fusionner 6 clips`, `Creer video finale`,
  `Construire legende Instagram`, `Publier sur Instagram`) confirmé à exactement 1 exécution dans
  `execution_data`, et **exactement 1 nouveau post Instagram** créé (vs 3 avant correction).
  Suppression Instagram testée entre-temps : **non supportée** par l'API Content Publishing
  (`DELETE` retourne `does not support this operation`) — les doublons de test accumulés pendant
  le diagnostic doivent être supprimés manuellement depuis l'app.
- [x] **Accent voix française corrigé (2026-09-01, suite 5)** — le nœud `Generer audio question`
  envoyait `voice`/`lang` comme littéraux JS entre guillemets (`"'fr-FR-DeniseNeural'"`, `"'fr'"`)
  au lieu de valeurs texte n8n simples, donc l'API recevait les guillemets inclus dans la chaîne,
  ne matchait aucune voix connue, et retombait sur l'anglais par défaut (`docs/api.md` : "Retombe
  sur `en` si inconnu"). Corrigé (valeurs sans guillemets superflus, comme les autres paramètres
  du workflow). **Revérifié directement dans les métadonnées serveur des jobs RVM**
  (`storage/jobs/{id}.json` → `options.voice`/`options.lang`), pas seulement en relisant le code :
  les 3 écrans Question confirmés à `fr-FR-DeniseNeural`/`fr`, chaque écran Réponse confirmé à la
  voix de sa propre langue (`es-ES-AlvaroNeural`/`es`, `nl-NL-MaartenNeural`/`nl`,
  `it-IT-ElsaNeural`/`it` sur ce test).
- [ ] **Access token Instagram reste court (~1h)** — `ig_exchange_token` échoue systématiquement
  (`error 452/2207055`), cause non identifiée. Ne pas activer le Schedule Trigger tant que non
  résolu (échecs silencieux garantis sur toute exécution planifiée après expiration).
- [x] **~~Tester le rendu `zh`/`ko` en genre "Duel de langues"~~ — devenu sans objet (2026-09-05)** :
  le duel refondu (section 3b) ne pioche plus que dans 5 paires curées (`ary`↔`ar`, `es`↔`it`,
  `es`↔`pt`, `it`↔`pt`, `de`↔`nl`), `zh`/`ko` en sont exclus. Le caveat "jamais afficher le mot natif
  en écriture non-latine" (section 4) reste valable pour tous les genres, translittération toujours
  utilisée à l'écran.
- [x] **Intro/outro + rythme ralenti testés avec succès (2026-09-01, suite 6)** — retour
  utilisateur : vidéos trop rapides pour capter l'information, ajouter intro/outro. Implémenté
  (sections 4 et 4bis) : `word_reveal_speed` 1.2→0.7, `motion_intensity` ajouté à 0.4, `slow:true`
  sur tous les TTS, `transition_duration` 0.4→0.7s, + 2 clips intro/outro (fusion passée de 6 à 8
  clips). Test réel : durée vidéo passée de ~20s à **30.8s**, intro/outro présents et audibles,
  1 seul post Instagram (pas de régression du fix de multiplication).
- [x] **Refonte 2026-09-05 du genre "duel" + rythme différencié + hashtags par langue + scène
  titre — codée ET testée en conditions réelles avec succès le 2026-09-05.** Voir sections 3b/4/4ter/5
  pour le détail technique. Workflow n8n mis à jour par édition directe du JSON exporté
  (`n8n export:workflow`/`import:workflow` en CLI, pas d'accès navigateur) : 95 → 134 → **150
  nœuds**. Sauvegardes hors dépôt : `/root/rvm-vocabag-channel/vocabag_workflow_BACKUP_before_2026-09-05.json`
  (95 nœuds) et `..._titre.json` (134 nœuds, avant scène titre).
  - **Méthode de test sûre trouvée** : `docker exec -e N8N_RUNNERS_BROKER_PORT=<port_libre>
    n8n-n8n-1 n8n execute --id=<workflowId>` — le port par défaut 5679 du Task Broker interne
    entre en conflit avec l'instance n8n déjà démarrée (erreur "port already in use"), il faut lui
    en donner un autre à chaque exécution manuelle en CLI. Avant tout test : (1) déconnecter la
    branche `Construire legende Instagram → Creer conteneur Instagram` (aucun risque de post réel
    même si le bug de multi-déclenchement CLI documenté plus haut se reproduisait), (2)
    déconnecter `Schedule Trigger → Choisir genre` (ne laisser que `Manual Trigger` en entrée),
    (3) forcer temporairement le genre dans `Choisir genre` (le calendrier hebdo ne permet pas de
    choisir le genre à tester à la demande). Workflow restauré à l'identique après test (genre non
    forcé, Schedule Trigger + Instagram reconnectés) — re-exporter/vérifier après restauration.
  - **⚠️ Piège rencontré en testant `docker exec ... | timeout N` côté client** : envelopper la
    commande `docker exec` d'un `timeout` côté hôte ne tue pas fiablement le process **à
    l'intérieur** du conteneur — le process n8n continue de tourner (visible via `ps aux` dans le
    conteneur) mais se bloque en écriture stdout dès que le pipe côté client est fermé (plus rien
    ne lit l'autre bout), donnant l'illusion d'un hang silencieux (aucun fichier écrit pendant
    8+ minutes alors que les jobs RVM progressaient normalement côté serveur). Fix : ne jamais
    wrapper `docker exec n8n execute` d'un `timeout` externe — laisser tourner nativement (le
    harnais bascule automatiquement en arrière-plan après 120s et notifie à la fin), et si un
    process reste bloqué de cette façon, le tuer proprement (`docker exec ... kill -9 <pid>`) et
    relancer sans wrapper.
  - **Bug réel trouvé et corrigé en testant** : les nœuds clonés `Telecharger audio/video reponse
    (duel A/B)` et `Telecharger audio/video titre` gardaient une référence `$('Poll audio
    reponse')`/`$('Poll video reponse')`/`$('Poll audio intro')`/`$('Poll video intro')` **non
    renommée** vers leur propre nœud de poll cloné — erreur `Node 'Poll audio reponse' hasn't been
    executed` dès le premier test réel (le nœud original ne s'exécute jamais dans la branche
    duel/titre). Corrigé (6 références renommées). **Piège méthodologique à retenir** : lors d'un
    clonage de chaîne de nœuds n8n par script, ne pas se limiter aux champs qu'on a
    intentionnellement modifiés (texte/voix/nom de fichier) — auditer TOUTES les expressions
    `$('NomDeNoeud')` de chaque nœud cloné, y compris celles qu'on pense "neutres".
  - **2 tests réels complets réussis** (genre forcé tour à tour, un par un) :
    - **Duel Espagnol/Italien, catégorie "basics"** : vidéo finale 1080×1920 H.264/AAC, **49.2s**,
      12 clips fusionnés, 3 concepts liés (« Je ne comprends pas » / « Je m'appelle » / « Merci »),
      2 écrans réponse par reveal avec la bonne voix/le bon mot par langue, scène titre générée
      avec le fond `es_it.png`. `words.json` cohérent.
    - **3 mots solo Anglais, catégorie "basics"** : vidéo finale **36.8s**, 9 clips fusionnés,
      3 phrases liées (« Great! » / « Wonderful! » / « Do you speak English? »), scène titre
      générée avec le fond `en.png`.
    - **Aucun appel Instagram déclenché dans les deux cas** (vérifié : `Creer conteneur Instagram`
      absent des logs d'exécution — seul le nœud `Construire legende Instagram`, purement local,
      a tourné).
  - Fichiers de test conservés sur le serveur pour référence :
    `channels/vocabag/videos/20260905_192051_duel_esit_basics_*` et
    `20260905_192813_3mots_en_basics_*`.
  - **Point non testé** : le genre `phrase` (calendrier hebdo ne l'a pas fait tomber pendant la
    session, testé seulement `duel` et `3mots`) — mécaniquement identique à `3mots` (même requête,
    juste `example_sentence` au lieu de `word`), risque jugé faible mais à garder en tête.
  - **Prochaine étape avant activation réelle** : le Schedule Trigger reste déconnecté du problème
    de token Instagram court (~1h, voir plus haut) — ne pas activer tant que ce point n'est pas
    résolu, même si le reste du pipeline est maintenant validé de bout en bout.

- [x] **État final au 2026-09-05 (fin de session) — pipeline complet validé en conditions réelles
  pour les 3 genres, plusieurs vrais posts Instagram publiés.** Suite des points ci-dessus (le
  point "aucun Instagram déclenché dans les deux tests" est maintenant dépassé — Instagram a
  depuis été testé en conditions réelles avec succès, voir ci-dessous). Chronologie complète des
  correctifs de cette session, du plus ancien au plus récent :
  1. **Genre `phrase` jamais testé auparavant** → testé, 5 échecs consécutifs à la fusion finale
     (`FFmpeg xfade failed`), d'abord attribués à tort à la charge serveur/au contenu zh, puis
     identifiés comme des **kills OOM du kernel** (`dmesg -T`/syslog : 4 kills exacts aux
     timestamps des échecs, VPS à seulement 3.8 Go RAM, swap souvent >85%, `concat_xfade()`
     montant à ~2.5-2.7 Go de RSS pour fusionner 9-12 flux simultanés).
  2. **Fix 1 (transitions retirées)** : `transition_type`/`transition_duration` supprimés de
     `Creer video finale`/`Creer video finale (duel)` → bascule sur `concat_stream_copy()` côté
     RVM (remux, quasi zéro RAM). Résout l'OOM, 1er vrai post Instagram réussi
     (`reel/Dc67twlDNEy`, phrase Allemand) puis un 2e (`reel/Dc681F3FFWP`, duel Espagnol/Italien).
  3. **Bug annexe découvert et corrigé en marge** : `slow=false` ne fonctionnait pas réellement
     (`render.php:360` — `!empty("false")` = `true` en PHP, bug hors périmètre vocabag, non
     touché). Contourné côté workflow : le champ `slow` n'est plus envoyé du tout sur `Generer
     audio question`/`intro`/`outro`/`titre` (au lieu d'envoyer la chaîne `"false"`).
  4. **Signalement utilisateur après publication réelle : décalage texte/voix ("texte en retard,
     parfois coupé")** — diagnostiqué comme un défaut du remux simple (`concat_stream_copy` ne
     recale jamais les micro-écarts natifs de 5-16ms entre durée vidéo/audio de chaque clip, qui
     s'accumulent sur 9-12 clips concaténés).
  5. **Fix 2 (fusion par paires)** — remplace l'assemblage final unique (9-12 flux simultanés)
     par une boucle séquentielle de fusions à 2 flux avec xfade court (`0.3s`) : jamais plus de
     2 décodeurs ouverts (RAM mesurée ~450 Mo, contre 2.5-2.7 Go) ET recalage propre du timing à
     chaque étape (ré-encodage, pas remux). Refactor 150→136 nœuds (section 5 pour le détail
     complet : nœuds ajoutés/supprimés, piège du multi-déclenchement Instagram évité en découplant
     `Construire legende Instagram` de `IF video finale prete`).
  6. **Bug distinct rencontré et résolu pendant la validation du fix 2** : après ce refactor, la
     branche parallèle `Preparer scene titre` ne s'exécutait plus jamais (reproductible 3/3, tous
     genres/paires confondus) — cause : réglage `executionOrder: "v1"` du workflow (pas un nœud).
     **Passage à `executionOrder: "v2"` résolu immédiatement et durablement.**
  7. **Validation finale double** : (a) test technique genre `3mots` (Instagram déconnecté) —
     décalage ramené à 52ms sur 26.3s, `Construire legende Instagram`/`Creer conteneur
     Instagram`/`Publier sur Instagram` confirmés à **exactement 1 exécution chacun** (vérifié
     dans les données d'exécution n8n, pas juste par grep texte) ; (b) **vrai post Instagram**
     genre `duel` Espagnol/Italien (voyage) — `reel/Dc7EVdZAVHG`, 36.2s vidéo / 36.15s audio
     (47ms d'écart), publié avec succès.
  - **Total posts Instagram réels publiés cette session : 4** (`Dcwu...`/`Dcwr...` le 2026-09-01
    lors des tout premiers tests, `Dc67twlDNEy` phrase Allemand, `Dc681F3FFWP` duel Es/It basics,
    `Dc7EVdZAVHG` duel Es/It travel — ces 3 derniers avec le pipeline dans son état final validé).
  - **État workflow final** : 136 nœuds, `executionOrder: v2`, Schedule Trigger et Instagram
    connectés (Schedule Trigger toujours **non activé** — seul point réellement bloquant restant :
    le token Instagram court ~1h, voir point non résolu plus haut). Sauvegardes intermédiaires
    hors dépôt dans `/root/rvm-vocabag-channel/` (`vocabag_workflow_BACKUP_before_2026-09-05*.json`)
    en cas de besoin de rollback.
  - **Genre `phrase` maintenant testé et fonctionnel** (contrairement à la mention "non testé"
    plus haut, obsolète) — c'est même le genre sur lequel le fix OOM puis le fix décalage ont
    d'abord été validés en conditions réelles.

## 8. Hors périmètre

- Posting YouTube/Facebook — à concevoir séparément (Instagram résolu, voir section 9).
- Genres nécessitant du contenu curé (faux-amis, expressions idiomatiques) — évoqués mais pas
  retenus pour cette version : la base `vocabag` n'a aucun tag "faux-ami", il faudrait constituer
  une liste à part. À reconsidérer si les 3 genres actuels s'essoufflent.

## 9. Posting Instagram — résolu (2026-09-01)

> **⚠️ Section historique** : la chaîne de 8 nœuds HTTP ci-dessous (`Creer conteneur Instagram`, poll,
> `Publier sur Instagram`, permalink) a été **remplacée le 2026-09-19 par le nœud natif `instagram`**
> (et un nœud natif `youTube`) — voir section 11.

Contrairement à ce qui bloquait la publication sociale RVM (App Review Meta introuvable sur
`pages_manage_posts`, flux Facebook Login + Page), Instagram fonctionne ici via le **nouveau flux
"Instagram API with Instagram Login"** (`graph.instagram.com`) — pas de Page Facebook à lier, pas
d'App Review nécessaire en usage personnel/développement avec un compte ayant un rôle sur l'app.

**Testé et validé en conditions réelles** à plusieurs reprises, dont publication automatique
complète depuis le workflow n8n (pas seulement le script manuel).

- **App** : App ID `958816292844038`, Account ID `17841449858344452` — credentials dans
  `/root/rvm-vocabag-channel/instagram-app-credentials.txt` (hors dépôt).
- **Script standalone** : `channels/vocabag/scripts/instagram_upload.py` (hors dépôt RVM) — utile
  pour un test manuel isolé, mais le workflow n8n a sa propre implémentation native (8 nœuds,
  voir ci-dessous), pas d'appel à ce script depuis n8n.
- **Video URL publique requise** : Instagram télécharge lui-même la vidéo — `api/download.php?job_id=...`
  (public, fenêtre de 2h après rendu, largement suffisant pour le temps de transcodage Instagram
  observé, ~15s).
- **Intégré au workflow n8n** : 8 nœuds en branche parallèle sur `IF video finale prete` (sortie
  true), indépendants de la sauvegarde locale — utilisent directement `download_url` du job RVM
  comme `video_url`. Chaîne : `Construire legende Instagram` (Code — assemble les 3 reveals +
  hashtags, genre-aware) → `Creer conteneur Instagram` → poll `status_code` → `Publier sur
  Instagram` → `Recuperer permalink Instagram`.
- **`access_token` en dur dans 4 nœuds** — voir section 7 pour le statut (court, ~1h, échange
  longue durée non résolu).

## 10. Session 2026-09-07 — 3 bugs réels corrigés, `phrase` enfin validé, refonte intro/outro

Suite à un retour utilisateur précis ("la dernière vidéo postée sur Insta contient encore deux
scènes x2"). Deux bugs distincts se cachaient derrière cette même phrase.

**Bug 1 — redondance de texte intro/titre (cosmétique).** `Preparer intro et outro` faisait dire à
l'intro *"Vocabag ! Aujourd'hui : 3 mots à connaître en {langue}."* puis, juste après, la scène
titre redisait *"3 mots en {langue}"* — même information annoncée deux fois de suite. Corrigé en
rendant l'intro générique (hook, ne répète plus l'annonce du titre).

**Bug 2 — le vrai bug, trouvé en creusant les données d'exécution n8n (pas en relisant le code).**
`Creer conteneur Instagram` utilisait `$('Poll video finale').item.json.download_url`. Après une
boucle `splitInBatches` (`Boucle fusion par paires`), l'expression `.item` (résolution par
pairedItem) est **ambiguë** — elle résolvait systématiquement vers l'**item[0] du tableau agrégé**
de la sortie "done" de la boucle, c'est-à-dire la **1ère itération de fusion** (intro+titre
seulement, ~7s), jamais la vidéo complète. Instagram recevait donc une mini-vidéo qui **boucle en
lecture** — d'où l'impression réelle de "2 premières scènes envoyées en x2". Preuve obtenue en
lisant `execution_data` (format `flatted`, script node+sqlite3 in situ, sans copier la base de
2.5 Go) : le dernier item de `Boucle fusion par paires` (job vidéo complet) et `$('Poll video
finale').last()` pointent vers le même `job_id` une fois le fix appliqué, alors que `.item`
pointait vers un `job_id` différent (1er de la liste) avant. **Fix : `.item` → `.last()`** — prend
toujours la dernière exécution du nœud, insensible à l'ambiguïté du pairedItem après une boucle.
Validé par test réel : vidéo de 26.4s (pas ~7s) publiée sur Instagram (`reel/Dc-w7lOgi8Z`).
**Leçon générale à retenir pour tout futur nœud placé après une boucle `splitInBatches`** :
`$('Node').item` n'est fiable que dans la MÊME branche/itération que le nœud référencé — dès qu'on
sort du corps de la boucle (branche "done"), utiliser `.last()` (ou `.first()`/`.all()` selon le
besoin), jamais `.item`.

**Refonte intro/outro (demande explicite, structure hook + recap + CTA unique).** L'ancien texte
outro ("Abonne-toi à Vocabag pour apprendre un nouveau mot chaque jour !") était en plus incohérent
avec le contenu réel (3 mots, pas un). Nouvelle structure dans `Preparer intro et outro`, par
genre :
- **Hook (intro)** : 4-5 formulations tirées au hasard à chaque vidéo (jamais de texte fixe répété),
  sans jamais répéter l'annonce exacte de la scène titre juste après.
- **Ending** : mini-recap cohérent avec le contenu réel ("ces mots"/"ce mot"/"cette phrase" selon
  le genre) + **un seul** CTA tiré parmi 4 (abonnement / sauvegarde / question en commentaire /
  partage) — jamais plusieurs actions demandées à la fois.
Validé par test réel (`reel/Dc-8Yg0gacw`).

**Genre `phrase` enfin validé — historique 0/5, maintenant réussi au 1er essai après le fix.** Les
5 échecs précédents (section 7, "score final 0/5") étaient tous attribués à l'époque à une
particularité du genre `phrase` (texte plus long, `example_sentence` vs `word`). Rétrospectivement,
c'était très probablement le **même OOM générique** que celui déjà diagnostiqué et corrigé pour les
autres genres (transitions xfade multi-flux, voir section 5) — `phrase` était juste statistiquement
plus touché (clips plus longs). Retest complet après le fix "fusion par paires" (déjà en place
depuis la session du 2026-09-05, jamais retesté sur ce genre spécifiquement depuis) : **succès du
premier coup**, vidéo 36.4s, publiée réellement (`reel/Dc_NPuYis7Y`, Anglais/basics). **Les 3
genres (3mots, duel, phrase) sont désormais tous validés en conditions réelles.**

**Ménage — 4 exécutions n8n bloquées en "running" depuis le 2026-09-05, nettoyées.** Restes de la
session de debug OOM du 2026-09-05 (processus `n8n execute` tués par OOM killer/`kill -9` avant que
n8n ait pu écrire le statut final en base). Aucun processus fantôme trouvé (audité en détail :
host + intérieur du conteneur + PM2 + systemd + ports — seuls les 2 process normaux du serveur n8n
lui-même, censés tourner en continu). Les 4 lignes `execution_entity` orphelines (`status='running'`,
`stoppedAt=null`) corrigées directement en base (`status='crashed'`) via un script node+sqlite3
exécuté **dans le conteneur** (évite de copier la base de 2.5 Go sur l'hôte — cause de plusieurs
kills OOM côté hôte pendant cette même session, non liés à n8n). **N8n ne nettoie jamais
automatiquement ces lignes orphelines sur cette version** — à refaire manuellement si un futur test
CLI est tué de force.

**Sauvegardes de session** (hors dépôt, `/root/rvm-vocabag-channel/`) :
`vocabag_workflow_BACKUP_before_2026-09-07_introfix.json`,
`..._before_2026-09-07_test.json`, `..._before_2026-09-07_instagram_url_fix.json`,
`..._before_2026-09-07_hook_cta_fix.json`. **État final** : 136 nœuds, `active:false` (Schedule
Trigger toujours désactivé — le token Instagram court reste le seul point bloquant, voir section 7),
`video_url` avec `.last()`, hook/CTA varié en place.

## 11. Session 2026-09-19 — workflow en production (147 nœuds, actif), état final

Workflow n8n `Vocabag` (id `ixlsBGrzOeP8BmKk`) : **actif**, Schedule Trigger **19h00 Europe/Paris**
(`GENERIC_TIMEZONE`, pas UTC), **147 nœuds**, aucun `onError`, aucun nœud désactivé, aucun HTTP Request vers
un réseau social. Validé de bout en bout en conditions réelles (run complet manuel : Instagram + YouTube +
suivi en base, puis vidéo/Reel de test supprimés).

### a) Publication — nœuds natifs (remplace la section 9)

- **Instagram** : nœud communautaire `@mookielianhd/n8n-nodes-instagram` (ressource `reels`, opération
  `publish`), credential « Instagram account » (compte `vocabag_com`, token `IG…`). `videoUrl` =
  `$('Poll video soundtrack').last().json.download_url` (URL publique du job RVM avec soundtrack, valable 2 h).
  **Le nœud a dû être patché** (voir `CLAUDE.md` § Docker n8n) : v3.4.0 forçait `graph.facebook.com`, qui
  rejette un token `IG…`. L'upload binaire n'est pas possible avec ce type de token (l'API exige `video_url`,
  même en `upload_type=resumable`) — une extension « Binary Property » a été ajoutée au nœud, **inerte**,
  laissée en place (champ vide = comportement d'origine).
- **YouTube** : nœud natif `n8n-nodes-base.youTube` (upload), credential « YouTube account 3 » (chaîne
  VocaBag), `privacyStatus=public`, catégorie `27` (Éducation), `regionCode=FR`, `defaultLanguage=fr`, lit
  `{folder}_final_sound.mp4` sur disque. **Tags = liste séparée par des virgules, sans `#`** (un seul champ
  « #a #b » était envoyé avant : corrigé). Description : titre, contenu, question d'engagement par genre, lien
  `vocabag.com`, hashtags en dernier.
- Vérifié en réel : vidéo YouTube `public` (pas forcée en privé par Google), Reel Instagram publié.
- ⚠️ **Durée de vie du token Instagram non vérifiée** (`IG…` : un token long durée expire ~60 jours et doit
  être rafraîchi) — à surveiller ; un échec de publication fait maintenant échouer l'exécution (plus de
  `onError`), donc visible dans n8n.

### b) Soundtrack (`mix_audio`, volume 0.2)

- Volume Docker ajouté : `channels/vocabag/sounds` → `/sounds/vocabag` (`ro`), fichier `01.mp3`
  (164 s ; les vidéos font 25–45 s ; RVM utilise `amix duration=shortest` → jamais coupées).
- 10 nœuds après la fusion par paires (sortie « done » réduite à 1 item — elle en contient plusieurs) :
  `Reduire a 1 item (soundtrack)` → `Lire video pour soundtrack` + `Lire soundtrack` → `Fusionner video+soundtrack`
  → `Creer video avec soundtrack` (`mode=mix_audio`, `options={"mp3_volume":0.2}`) → poll / IF / wait →
  `Telecharger video soundtrack` → `Sauver video soundtrack` (`{folder}_final_sound.mp4`). Même schéma que
  `Create video concatened with soundtrack` du workflow Muzrappel.
- Effet mesuré : niveau moyen ≈ −24 dB → −20 dB, sans saturation. **Le volume 0.2 n'a pas été validé à l'oreille.**

### c) Suivi des vidéos — table `vocabag_videos` (base `vocabag`)

Remplace `staticData.usedWords` (perdue à chaque `n8n import:workflow`). Migration
`vocabag/database/migrations/046_vocabag_videos.sql`. 1 ligne = 1 vidéo créée : `folder` (UNIQUE), `genre`,
`language_id_a/b`, `category_id`, `word_ids` (JSON : 3 ids solo, 6 ids duel), `posted_on_youtube/instagram`,
`youtube_video_id`, `instagram_media_id`, dates.

- **Écriture** : `Preparer suivi video` → `Enregistrer video (suivi)` **avant** la publication (si la base est
  indisponible, rien n'est publié) ; `Marquer YouTube (suivi)` après `Upload a video`, `Marquer Instagram (suivi)`
  après `Publish`. SQL construit avec valeurs validées (entiers via `Number`, dossier par regex, ids assainis).
- **Droits** : la credential « Vocabag DB » est `vocabag`@`%` en **SELECT seul** ; `GRANT INSERT, UPDATE ON
  vocabag.vocabag_videos TO 'vocabag'@'%'` (root MySQL) appliqué le 2026-09-19 (moindre privilège : pas de DELETE).
- **Sélection** : les mots déjà utilisés **pour le même genre** passent en dernier
  (`EXISTS (... JSON_CONTAINS(vv.word_ids, CAST(id AS JSON)))`) ; si tous sont épuisés ils sont **réutilisés** (avant :
  le duel s'arrêtait en silence avec 0 ligne). Duel : préférence catégories avec ≥ 3 paires non utilisées, puis
  catégorie du calendrier, puis paires non utilisées — **repli de catégorie** pour la même paire de langues
  (ex. de/nl `work_studies` = 0 concept aligné → prend la catégorie qui en a le plus).
- **Reset** : vider `vocabag_videos` (le workflow n'a plus d'état interne). Les fichiers vidéo restent sur disque.
- ⚠️ **Piège n8n (MySQL)** : le nœud MySQL altère la séquence `$'` de la requête finale (même via `={{ }}`) →
  `JSON_TABLE(... PATH '$')` cassait le SQL. Aucune requête ne doit contenir `$'`, `$&`, `` $` `` ni `$$`
  (garde ajoutée dans `Construire requete mots`).

### d) Calendrier — tirage aléatoire pondéré (remplace la section 2)

Nœud `Choisir theme`. Plusieurs langues par mois (≈ 10,5 sur 30 jours en simulation, minimum 7) :
- **Solo** (3mots/phrase) : langue tirée au poids — `ary 22, ar 12, de 9, pt 8, es 7, ru 7, en 7, it 6, nl 6, tr 6,
  zh 5, ko 5` ; catégorie « de saison » (70 %, `SEASON[mois]`, 6 catégories/mois) ou libre (30 %).
- **Duel** : paire curée tirée au poids — `ary+ar 40, es+it 20, de+nl 15, es+pt 15, it+pt 10` ; catégories
  limitées à celles avec **≥ 12 concepts alignés** en base (de+nl : seulement `numbers_time`, `colors_desc`,
  `greetings`). `religion_culture` exclue.
- Répartition simulée : Darija ≈ 21,5 %, Arabe ≈ 14,4 %, autres 3,8–9,7 %. Tirage indépendant d'un jour à
  l'autre (pas de rotation garantie).
- **Forçage ponctuel** : dictionnaire `forcedByDate` (`'2026-09-20' → ary/greetings`, demande utilisateur) —
  s'applique à la date exacte, branche solo uniquement ; l'entrée reste inoffensive après la date.
- Genre par jour de semaine inchangé (section 3).

### e) Images Pexels

`Preparer reveals` : requête = **mots-clés visuels anglais par catégorie** (`PEX_VISUAL`, 3 variantes, rotation
quotidienne via `$now.ordinal`) préfixés par la **culture du pays de la langue** (`PEX_CULTURE`, ex. `Morocco`,
`Germany`) pour les catégories concrètes. Intro solo : `{pays} city street landmark`. `per_page=8` et les 3 nœuds
`Telecharger image …` prennent la **première photo dont la description ne contient pas** `couple|kiss|romantic|
intimate|lingerie|bikini|swimsuit|nude|sensual|seductive|passionate|lover|dating|wedding|bride|groom`, sinon une
**image de repli**. Motif : « Arab people greeting each other » renvoyait 7 couples romantiques sur 8. Catégorie
salutations : `friends greeting on the street`. Le filtre repose sur la description Pexels — ne remplace pas un
contrôle visuel.

### f) Leçons opérationnelles

- **Ne pas lancer deux `n8n execute` en parallèle** : la file RVM sature (un test solo a pris 47 min au lieu de
  ~10, le duel ~55 min). Les logs `n8n execute` peuvent être tronqués — vérifier `execution_entity.status` dans
  `database.sqlite` et les fichiers produits.
- `n8n import:workflow` **réécrit `staticData`** depuis le JSON importé ; pour modifier un workflow actif :
  export → patch du JSON → `import:workflow` → `publish:workflow` → **redémarrage** (ou `docker compose up -d`).
- Méthode de test sûre : copie du workflow (id différent) avec `Schedule Trigger`, `Publish` et `Upload a video`
  déconnectés + genre/langue forcés ; supprimer ensuite les lignes de test de `vocabag_videos` et la copie.
- Sauvegardes (hors dépôt, `/root/rvm-vocabag-channel/`) : `vocabag_workflow_BACKUP_before_2026-09-19_*.json`
  (une par étape) + `vocabag_workflow_PENDING_tracking_table_*.json` ; SQLite n8n avant suppression de copies :
  `database.sqlite.bak_before_testcopies_delete` (dans le volume, 2,5 Go — à supprimer si inutile).

### g) Reste à faire / limites

- Visuels de titre (`channels/vocabag/images/languages/`) : `ary.png`, `ar.png` et `en.png` sont de vrais visuels
  (remplacés le 2026-09-19). Restent des **dégradés placeholder** (~10 Ko) : `de`, `es`, `it`, `ko`, `nl`, `pt`,
  `ru`, `tr`, `zh` et les 5 **paires de duel** (`ary_ar`, `es_it`, `es_pt`, `it_pt`, `de_nl`).
- Voix darija/arabe et volume du soundtrack non validés à l'oreille.
- Non testé en réel dans le processus principal n8n : le run planifié de 19h (premier vrai run automatique).

## Instagram : Reels uniquement, pas dans le fil (2026-09-27)

Nœud « Publish » (`@mookielianhd/n8n-nodes-instagram` v3.4.0, ressource `reels`) du workflow **Vocabag Video**
(`ixlsBGrzOeP8BmKk`) : option `additionalFields.shareToFeed = false` → paramètre API `share_to_feed=false`,
le Reel n'apparaît que dans l'onglet Reels, pas dans le fil ni dans la grille principale du profil.
Appliqué par export → modification → `import:workflow` → `publish:workflow` → redémarrage de n8n.
Sauvegarde de la version précédente : `/root/vocabag-video-avant-reels-seuls-20260927.json`.
Vérifié : workflow actif, version active = version courante. Effet visible au prochain Reel (19h).

## 2026-09-28 — alertes d'erreur, attente des Reels, suivi

- **Alertes** : `settings.errorWorkflow = VbErreursAlerte1` → un plantage de Vocabag Video envoie un message sur
  @vocabagbot (détails : `vocabag-social-instagram.md` §18). Un échec Instagram toléré (`continueRegularOutput`) ne
  plante pas l'exécution : le vérifier par `vocabag_videos.posted_on_instagram`.
- **Attente des Reels** : le nœud Instagram communautaire attend désormais jusqu'à ~5 min (150 × 2 s) que le Reel soit
  prêt, au lieu de 80 s (cause des timeouts des 26 et 27/09). Détails et originaux : `muzrappel-n8n-publication.md`.
- **Utilisation par d'autres workflows** : Stories (Reel du jour en story, question tirée de `word_ids`) et Newsletter
  hebdo (vidéos de la semaine + mots) lisent `vocabag_videos` — ne pas changer ses colonnes sans les adapter.
- Premier jour vérifié en réel le 2026-09-28 : Reel 15h (nl, 3mots) publié sur Instagram + YouTube + commentaire.


## Facebook (ajouté le 2026-09-30)

Nœud `Publish Facebook` (Facebook Graph API) branché en parallèle de `Lire video finale (YT)` sur `Preparer metadata YouTube` :
`POST graph-video.facebook.com/v23.0/1361049150428275/videos` (id Graph de la page VocaBag ; ≠ `61594903742653` de l'URL),
`file_url` = `$('Poll video soundtrack').last().json.download_url` (même vidéo qu'Instagram), `title`/`description` = ceux de YouTube
(lien vocabag.com + contact `contact.rapidvideomaker@gmail.com`). onError continue (n'empêche pas YouTube/Instagram).
- Credential **« Facebook Graph account »** (`RL5TaCOZpmZmBEc8`) = token de **page** VocaBag (`GET me` → « VocaBag »).
- **Pas de suivi en base** : `vocabag_videos` n'a pas de colonnes Facebook (il faudrait une migration `posted_on_facebook`,
  `facebook_video_id`, `posted_facebook_at` + GRANT, puis un IF + UPDATE comme pour Instagram).
- Test manuel  : tests réels OK le 2026-09-30 (workflows de test supprimés ensuite ; pour revérifier un token, `GET me` doit renvoyer le nom de la page).
- **Suivi en base ajouté le 2026-09-30** : migration 048 (`posted_on_facebook`, `facebook_video_id`, `posted_facebook_at`,
  appliquée par l'utilisateur) ; `Publish Facebook` → `Facebook publié ?` → `Marquer Facebook (suivi)` (UPDATE vocabag_videos,
  credential « Vocabag DB »), 168 nœuds. Vidéo du 30/09 rattrapée à la main.

## Vérification quotidienne — « VocaBag - Vérification » (2026-10-04)
Workflow `FS8LRKUq8hyyVNUe`, actif, généré par `muz-video-template/social/setup/build_vocabag_verif.py` →
`social/workflows/09_vocabag_verif.json` (même principe que « Muzrappel - Vérification », helpers partagés avec `build_muz_verif.py`).
Pourquoi : « Vocabag Video » et les Stories restent en « success » quand un Publish échoue ; les 3-4/10 (tokens Meta invalidés)
rien n'a été publié sur Instagram/Facebook sans aucune alerte.
- **15h50** (Paris) : ligne du jour dans `vocabag_videos` (dossier préfixé `yyyyMMdd_`, credential « Vocabag DB ») + Reel du jour
  sur YouTube (« YouTube account 3 », playlist uploads), Instagram @vocabag (`REELS` du jour) et page Facebook (vidéo `/reel/` du jour).
- **21h50** : idem + stories du jour ≥ 3 (16h Reel, 18h question, 21h réponse + visuel final) sur Instagram et Facebook.
- Toujours : erreurs d'API (190 → token de page VocaBag ; 401 → YouTube) et suivi incohérent (publié mais `posted_on_* = 0`).
- Telegram @vocabagbot (chat `6980427615`) **uniquement en cas de problème** ; bouton « Execute workflow » → bilan complet.
  `Config.forcer_moment` = 'apres_reel' | 'soir'.

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
