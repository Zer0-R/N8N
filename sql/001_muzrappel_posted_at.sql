-- favima_bdd.muzrappel : dates de publication par plateforme (2026-10-04)
-- À exécuter avec un compte qui a ALTER sur favima_bdd (ni z3r0 ni n8n_user ne l'ont).
-- MySQL 8.0 : à exécuter UNE seule fois (pas de IF NOT EXISTS). Les lignes déjà publiées gardent une date NULL.
ALTER TABLE favima_bdd.muzrappel
  ADD COLUMN posted_youtube_at   DATETIME NULL AFTER posted_on_youtube,
  ADD COLUMN posted_instagram_at DATETIME NULL AFTER posted_on_instagram,
  ADD COLUMN posted_facebook_at  DATETIME NULL AFTER posted_on_facebook;

-- Rattrapage connu : Reel du 2026-10-04 (ligne 3270) — YouTube 07:24, Instagram/Facebook republiés à 17:22 (heure de Paris)
UPDATE favima_bdd.muzrappel
   SET posted_youtube_at = '2026-10-04 07:24:00', posted_instagram_at = '2026-10-04 17:22:00', posted_facebook_at = '2026-10-04 17:22:00'
 WHERE id = 3270;
