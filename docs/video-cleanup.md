# Nettoyage des vidéos générées (muz-video-template)

Script : `/var/www/muz-video-template/scripts/cleanup_videos.sh` (recréé le 2026-09-20), lancé chaque jour à 23h par `/etc/cron.d/muz-video-cleanup`
(log : `/var/log/muz_video_cleanup.log`).

- Supprime les **fichiers de plus de 7 jours** (`RETENTION_DAYS` en tête du script) dans `channels/*/videos`, puis les dossiers devenus vides.
  Ne touche à rien d'autre (sounds, images, overlay, fonts, json, topics, ebook).
- `cleanup_videos.sh --dry-run` : affiche le nombre de fichiers et la taille concernés sans rien supprimer.
- **Épargne `script.json`** (ajouté le 2026-09-21) : c'est l'entrée du workflow `test Muzrappel` (lignes `muzrappel.script_create=1`). Le premier nettoyage du 2026-09-20 les avait supprimés (> 7 j) → à régénérer.
- Ne vérifie **pas** si la vidéo a été publiée : tout fichier de plus de 7 jours part, publié ou non.

Historique : le script d'origine (avril 2026) avait disparu du disque après le 30/04/2026 ; le cron échouait en silence (`not found`, 142 lignes de log)
et Muzrappel a accumulé 4,3 Go de vidéos. Premier nettoyage le 2026-09-20 : 2 693 fichiers, 4,3 Go (disque 72 % → 64 %).
Voir aussi la rétention n8n (`EXECUTIONS_DATA_MAX_AGE=72`, exécutions manuelles non sauvegardées) dans `/root/n8n/docker-compose.yml`.

## Disque du VPS — nettoyage du 2026-09-20 (disque 91 % → 64 %)

Constat : n8n occupait 9,8 Go (`/var/lib/docker/volumes/n8n_n8n_data`) : fichiers binaires des exécutions (5 Go, vidéos/audios gardés 14 jours par défaut), base `database.sqlite` de 2,3 Go
dont 99 % de pages libres (jamais compactée), et une sauvegarde de 2,3 Go. `Coran tiktok` lancé ~170 fois à la main en 3 jours (exécutions manuelles sauvegardées avec leurs binaires).
Actions : suppression de 13 dossiers d'exécutions orphelins (1,4 Go), `VACUUM` de la base (2,34 Go → 26 Mo, n8n arrêté), suppression de `database.sqlite.bak_before_testcopies_delete` (2,3 Go),
`npm cache clean --force` (2,9 Go → 0,46 Go), nettoyage des vidéos de plus de 7 jours (4,3 Go).
Rétention n8n ajoutée dans `/root/n8n/docker-compose.yml` (sauvegarde `docker-compose.yml.bak_before_retention_2026-09-20`) : `EXECUTIONS_DATA_PRUNE=true`, `EXECUTIONS_DATA_MAX_AGE=72`,
`EXECUTIONS_DATA_SAVE_MANUAL_EXECUTIONS=false` (les exécutions manuelles de l'éditeur ne sont plus enregistrées ; celles lancées en CLI/planifiées le sont).
Suppression d'un workflow n8n : pas de commande CLI → arrêter n8n (`docker stop n8n-n8n-1`), `DELETE FROM workflow_entity WHERE id=…` avec `PRAGMA foreign_keys=ON` (les exécutions partent en cascade),
remettre `debian:debian` sur `database.sqlite*`, redémarrer. Sans sauvegarde complète possible (disque), exporter le JSON du workflow avant.
Autres gros postes restants : `/root/.cache/ms-playwright` 1,3 Go, `/tmp/claude-0` 2,6 Go, `/var/www/rapidvideomaker-staging` 5,3 Go.

## RapidVideoMaker staging (ajouté le 2026-09-27)

Le staging n'avait aucun nettoyage (le `worker/cleanup.py` de la prod purge les médias à 2 h ; non utilisé ici) :
`storage/uploads` + `storage/outputs` étaient montés à 5,2 Go. Cron root quotidien **3h17** : suppression des fichiers
de plus de 7 jours (sauf `.gitkeep`, seuls fichiers suivis par git) puis des dossiers vides ; fiches `storage/jobs`
conservées. Nettoyage du VPS le même jour : 31 → 22 Go utilisés sur 50 (détail dans la mémoire « n8n — opérations VPS »).
