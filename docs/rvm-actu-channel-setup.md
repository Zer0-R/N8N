# Channel `rvm-actu` — setup et état (démarré 2026-09-07)

Workflow n8n de démonstration produit : génère automatiquement une vidéo courte (actu du jour) via
l'API publique RapidVideoMaker, dans le but de **donner envie d'utiliser RapidVideoMaker**
(démarche méta — le produit s'auto-démontre). CTA principal en fin de vidéo = découverte du
produit ("lien dans la bio"). Même famille que le channel `vocabag` (voir
[vocabag-channel-setup.md](vocabag-channel-setup.md)), architecture directement dérivée de
son pipeline déjà validé en conditions réelles (fusion par paires anti-OOM, TTS+image_to_video via
l'API publique RVM).

## 1. Sujets — FICTIFS pour l'instant

Pas de vraie source d'actualité intégrée. **16 sujets factices** codés en dur (liste d'ids) dans le
nœud `Choisir sujet`, contenu dans des fichiers JSON sur le VPS :
`/var/www/muz-video-template/channels/rvm-actu/topics/*.json` — 8 catégories (intelligence
artificielle, espace, environnement, économie, santé, culture, sport, sciences), 2 sujets chacune,
chaque sujet = `{id, categorySlug, headline, highlights: [{text, imageQuery} × 3]}`. Anti-répétition
via `$getWorkflowStaticData('global').usedTopics` (même mécanique que `usedWords` sur vocabag) —
cycle complet des 16 avant réutilisation.

**À faire quand une vraie source d'actu sera branchée** : remplacer le nœud `Choisir sujet` (liste
statique) par un appel API news + un nœud qui écrit le JSON du jour dans le même dossier (le reste
du pipeline, à partir de `Lire sujet`, n'a pas besoin de changer — même schéma JSON attendu).

## 2. Infra Docker

Nouveaux volumes ajoutés à `/root/n8n/docker-compose.yml` (conteneur redémarré le 2026-09-07 pour
les prendre en compte — bref downtime partagé avec tous les workflows n8n, sans impact car rien
n'était actif à ce moment) :

```yaml
- /var/www/muz-video-template/channels/rvm-actu/videos:/files/rvm-actu:rw
- /var/www/muz-video-template/channels/rvm-actu/topics:/files/rvm-actu-topics:ro
```

Les deux sont sous le préfixe `/files` déjà whitelisté par `N8N_RESTRICT_FILE_ACCESS_TO` — aucune
modification de cette variable nécessaire (contrairement à l'ajout d'un préfixe `/images` fait pour
vocabag).

## 3. Structure de la vidéo

Intro (hook) → titre (headline du sujet) → 3 highlights (les faits du sujet, un écran chacun) →
outro (recap + CTA). 6 clips fusionnés (vs 8-9 pour vocabag qui a 2 écrans par reveal — ici 1 seul
écran par highlight, pas de format question/réponse).

**Intro (hook, 0-3s)** — 2 styles demandés explicitement par l'utilisateur, tirés au hasard :
- **Meta** (~50%) : met en avant le fait que l'IA a créé la vidéo — *"Regarde ce que l'IA a créé
  toute seule sur ce sujet."*, *"Cette vidéo a été générée à 100% par une IA, en automatique."*, etc.
- **Direct** (~50%) : va droit au sujet — le `headline` du sujet, parfois préfixé (*"Aujourd'hui :
  ..."*, *"Ça bouge : ..."*).

**Titre** — le `headline` du sujet, fond Pexels choisi par requête générique par catégorie (pas
d'images fixes comme les PNG langue de vocabag — évite d'avoir à générer/maintenir des assets).

**3 highlights** — un écran chacun (texte + image Pexels cherchée via `imageQuery` du sujet), pas
de format Q/R.

**Outro** — recap (*"Voilà pour l'actu du jour."*, *"Et ça, c'est une vidéo 100% générée par IA, du
script au montage."*, etc.) + **un seul** CTA, tiré au hasard mais **pondéré ~70% vers le CTA
principal** (demande explicite utilisateur — "ça sera le CTA principal, de temps en temps on va
varier") : *"Envie d'apprendre à créer des vidéos gratuitement et automatiquement avec l'IA ?
Rejoins-nous via le lien dans la bio."* Les ~30% restants tirent parmi 4 alternatives (abonnement /
question commentaire / sauvegarde / partage).

## 4. Pipeline technique (identique à vocabag, sujets remplacés)

Même séquence par écran que vocabag : `Chercher image {clé} (Pexels)` → `Telecharger image` →
`Generer audio {clé} (text_to_mp3)` → poll/if/wait → `Telecharger audio` → `Fusionner image+audio`
→ `Construire options {clé}` (calcul dynamique de `word_reveal_speed` via `Content-Length` du MP3,
même méthode que vocabag — voir section 4 de `vocabag-channel-setup.md`) → `Creer video {clé}
(image_to_video)` → poll/if/wait → `Telecharger video` → `Sauver clip {clé}`.

**Fusion** : même méthode "par paires" que vocabag (anti-OOM, voir section 5 de
`vocabag-channel-setup.md`) — `Preparer etapes fusion` construit `['0b_titre','1_h','2_h','3_h',
'9_outro']`, `Boucle fusion par paires` (splitInBatches) fusionne 2 flux à la fois
(`transition_type:fade`, `transition_duration:0.3`), jamais plus de 2 décodeurs ouverts. **La
vidéo finale utilise `$('Poll video finale').last()`** (pas `.item`) dès la conception — le bug
`.item` découvert et corrigé sur vocabag le même jour (voir section 10 de
`vocabag-channel-setup.md`) a été évité d'emblée ici.

**Bug rencontré et corrigé pendant la construction** : le nœud `extractFromFile` (opération
`fromJson`, utilisé pour parser le JSON du sujet lu en binaire) place le contenu parsé sous une clé
`data` (`item.json.data`), **pas directement dans `item.json`**. `Preparer sujet` corrigé en
conséquence (`const topic = $input.item.json.data;`).

## 5. Test réel validé (2026-09-07)

Run complet réussi de bout en bout (contenu + assemblage, **sans publication** — voir section 6) :
sujet factice "restauration des récifs coralliens" (environnement), vidéo finale 31.9s, 8.96MB.
Metadata et clips intermédiaires dans `/files/rvm-actu/20260907_134109_environnement-recif-corail_*`.
Vidéo envoyée à l'utilisateur pour validation du style.

## 6. Publication — DÉCONNECTÉE, à brancher

Les comptes Instagram et YouTube RapidVideoMaker n'existent pas encore. Chaînes de publication
**construites mais volontairement déconnectées** du flux principal (aucun risque de post réel tant
qu'elles ne sont pas reliées) :

- **Instagram** : chaîne complète copiée du pattern vocabag déjà validé en réel (`Creer conteneur
  Instagram` → poll `status_code` → `Publier sur Instagram` → `Recuperer permalink Instagram`).
  Placeholders `TODO_IG_USER_ID` et `TODO_INSTAGRAM_ACCESS_TOKEN` (4 occurrences) à remplacer une
  fois le compte créé, puis relier `Construire legende Instagram-YouTube` →
  `Creer conteneur Instagram (A CONFIGURER)`.
- **YouTube** : un seul nœud natif n8n (`n8n-nodes-base.youTube`, resource video/upload,
  `privacyStatus: private` par défaut) — pas de credential OAuth2 configurée. Nécessite de créer un
  projet Google Cloud + OAuth2 côté n8n (Credentials → YouTube OAuth2 API) une fois le compte créé,
  puis relier au flux et repasser en `public` après validation manuelle.

Détail exact et checklist dans la sticky note "Publication Instagram / YouTube -- A CONNECTER" du
workflow n8n lui-même.

## 7. État du workflow

- **Nom n8n** : `RapidVideoMaker Actu`, id `fNztMtYeIcAUq1SH`, **97 nœuds**, `active:false`
  (Schedule Trigger réglé sur 9h mais pas activé — même prudence que vocabag).
- Sauvegarde de la version fonctionnelle (fichier local, pas juste dans n8n) :
  `/root/rvm-actu-channel/rvm-actu_workflow_2026-09-07_v1_working.json`.
- **Genre unique pour l'instant** — pas de variantes façon 3mots/duel/phrase de vocabag. À
  envisager plus tard si le format s'essouffle (ex. angle "comparatif", "explainer plus long").
