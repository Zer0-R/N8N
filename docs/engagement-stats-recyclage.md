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

## Tokens Meta — utilisateur système (2026-10-04)
Utilisateur système Business Manager « n8n » (app Favima3) : token SYSTEM_USER sans expiration, indépendant de la session
Facebook personnelle (un changement de mot de passe ne le révoque plus). Permissions : pages_show_list, pages_read_engagement,
pages_manage_posts, pages_manage_engagement, read_insights, business_management, instagram_basic, instagram_content_publish,
instagram_manage_comments, instagram_manage_insights (+ instagram_manage_contents). Tokens de page tirés de `me/accounts`
(type PAGE, sans expiration) → credentials « Instagram account » / « Facebook Graph account » (VocaBag) et « … 2 » (Muz Rappel).
Vues Instagram désormais dans le bilan hebdo ; réponses Facebook de Muzrappel Commenter autorisées.
Régénération : business.facebook.com/settings/system-users → n8n → Générer un nouveau token (mêmes permissions).

## Corrections après revue de code (2026-10-04)
- **Correcteur VocaBag** : seuls les mots de 3 lettres ou plus servent à reconnaître une phrase (« la », « de », « mi »
  ne suffisent plus) ; « Presque » = ≥ 50 % des mots significatifs dont au moins 2 ; « Bravo » exige aussi les petits mots ;
  chinois / japonais comparés caractère par caractère. 21 cas de test (`node` + vocabag_correcteur.js).
- **Rattrapage sans doublon** : fiche du jour « en_cours » avant publication puis « termine » (+ instagram_id / facebook_id).
  Le rattrapage n'agit pas si une publication est en cours depuis moins d'1 h, ni sur une plateforme déjà publiée selon la fiche.
- **Bilan hebdo** : un compteur d'abonnés n'est mémorisé que si son appel API a réussi (« ? » sinon, base conservée).

## Corrections après la 2e revue (2026-10-04)
- **Correcteur** : mots entiers uniquement (plus de « a » trouvé dans « chats ») ; phrase reconnue dès 3 mots ;
  « Bravo » ≥ 85 % de la phrase complète et des mots significatifs, « Presque » ≥ 50 % avec 2 mots communs dont 1 significatif ;
  chinois / japonais : un mot seul n'est validé que si le commentaire est exactement ce mot (« 我不好意思 » ne valide plus « 好 »).
  Tests : `node social/setup/test_vocabag_correcteur.js` (30 cas, dont les exemples des revues ; phrases intégrées, sans dépendance à channels/).
- **Rattrapage** : si la fiche contient un ID, l'objet est lu directement (`R · IG objet` / `R · FB objet`, `GET /{id}`) :
  toujours en ligne → ligne ℹ️, pas de republication ; introuvable ou vidéo en erreur → 🚨 et republication (4e revue,
  remplace le délai d'1 h de la 3e revue) ;
  après un rattrapage, la fiche du jour est réécrite avec les nouveaux ID (`R · Fiche à jour`) → pas de doublon le soir.
