# Engagement, statistiques et recyclage (2026-10-04)

## Commentaires
- **Muzrappel Commenter** (`eSABPiZmB8tjkT39`) : toutes les 3 h (h+05) au lieu de 21h ; YouTube + Instagram + **page Facebook**
  (`FB · Vidéos et commentaires` → `FB · Réponses à faire` → `FB · Répondre`, même détection « Amine » et mêmes textes).
  Répondre en tant que page exige `pages_manage_engagement` (absente du token au 2026-10-04) : la branche lit les
  commentaires mais ses réponses échouent sans rien bloquer tant que la permission n'est pas accordée.
- **VocaBag - Réponses commentaires** (`AFIa1WdJcKzrXQD5`, `social/setup/build_vocabag_reponses.py`, logique
  `social/setup/vocabag_correcteur.js` testable avec node) : toutes les 3 h (h+20), Reels des 7 derniers jours,
  Instagram + YouTube. Phrase du Reel écrite à ≥ 85 % → « Bravo 👏 … » ; 40-85 % → « Presque 💪 La phrase exacte : … » ;
  mot seul exact → « Bravo … = traduction ». Résumé Telegram (@vocabagbot) quand des réponses partent.
  `Config.simulation` = true → rien n'est publié.

## Statistiques — « Stats hebdo (VocaBag + Muz Rappel) » (`C7woZMtjjgcnTOm9`, `build_stats_hebdo.py`)
Lundi 9h, un message par compte (@vocabagbot / @muzrappelbot) : Reels de la semaine sur YouTube (vues, likes,
commentaires), Instagram (likes, commentaires), Facebook (vues, likes, commentaires), top 3, abonnés et évolution
(staticData, à partir du 2e bilan), vues YouTube moyennes par langue pour VocaBag (duels « X vs Y » regroupés).
Vues Instagram : apparaissent automatiquement quand le token aura `instagram_manage_insights`.

## Recyclage — « Recyclage Reels en story » (`NSD9NhRU6hgPpEcy`, `build_recyclage.py`)
Samedi : Muz Rappel 11h, VocaBag 17h. Reel Instagram de 14 à 120 jours au meilleur engagement (likes + 2 × com.),
jamais recyclé (staticData `recycles_MZ` / `recycles_VB`) → service média `POST /recycle` (extrait < 60 s coupé entre deux
phrases, fenêtre 40-59 s car la voix est mêlée à la musique ; bandeau « vidéo complète » pour Muz) → story Instagram
(conteneur STORIES) + story Facebook (video_stories en 3 temps) → résumé Telegram. `Config.simulation` = true → rien publié.

## Facebook
La story « Reel du jour » existe déjà sur Facebook dans les deux workflows de stories (VocaBag 16h, Muz 9h).

## Permissions à ajouter au prochain token (Graph API Explorer, app Favima3)
`instagram_manage_insights` (vues Instagram), `read_insights` (stats vidéo Facebook détaillées),
`pages_manage_engagement` (réponses en tant que page Facebook) — puis `me/accounts` et mise à jour des 4 credentials.
