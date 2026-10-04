#!/bin/sh
# Supprime les fichiers de plus de RETENTION_DAYS jours dans channels/*/videos, puis les dossiers devenus vides.
# Ne supprime JAMAIS script.json (entrée du workflow n8n test Muzrappel : une ligne muzrappel avec script_create=1 en dépend).
# Ne touche jamais aux dossiers sounds/, images/, overlay/, fonts/, json/, topics/ ni à rien hors de channels/*/videos.
# Lancé chaque jour à 23h par /etc/cron.d/muz-video-cleanup. Usage : cleanup_videos.sh [--dry-run]
RETENTION_DAYS=7
BASE=/var/www/muz-video-template/channels
DRY=0
[ "$1" = "--dry-run" ] && DRY=1

files=0; bytes=0
for dir in "$BASE"/*/videos; do
  [ -d "$dir" ] || continue
  n=$(find "$dir" -type f ! -name script.json -mtime +"$RETENTION_DAYS" | wc -l)
  b=$(find "$dir" -type f ! -name script.json -mtime +"$RETENTION_DAYS" -printf '%s\n' | awk '{s+=$1} END {printf "%.0f", s+0}')
  files=$((files + n)); bytes=$((bytes + b))
  if [ "$DRY" = "0" ]; then
    find "$dir" -type f ! -name script.json -mtime +"$RETENTION_DAYS" -delete
    find "$dir" -mindepth 1 -type d -empty -delete
  fi
done

mode=""; [ "$DRY" = "1" ] && mode=" (dry-run, rien supprimé)"
echo "[$(date '+%Y-%m-%d %H:%M:%S')] cleanup_videos: $files fichiers, $((bytes / 1048576)) Mo (> ${RETENTION_DAYS} j)${mode}"
echo "[$(date '+%Y-%m-%d %H:%M:%S')] cleanup_videos: terminé"
