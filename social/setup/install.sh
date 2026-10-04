#!/usr/bin/env bash
# Installation « VocaBag Social » sur le VPS (idempotent). À lancer en root :
#   bash install.sh media     # service vocabag-media (systemd) + test depuis le conteneur n8n
#   bash install.sh apache    # médias publics https://staging.vocabag.com/social-media/ (+ PUBLIC_BASE_URL, redémarrage du service)
#   N8N_API_KEY=… bash install.sh n8n   # Data Tables, credentials, suppression des anciens, import, publication
#   … ou « all » pour les trois dans l'ordre.
set -euo pipefail
SOCIAL=/var/www/muz-video-template/social
VHOST=/etc/apache2/sites-enabled/vocabag-staging-le-ssl.conf
PUBLIC_URL=https://staging.vocabag.com/social-media
ENVF=/etc/vocabag-media.env

step_media() {
  if [ ! -f "$ENVF" ]; then
    umask 077
    printf 'MEDIA_TOKEN=%s\nPUBLIC_DIR=%s/public\nPUBLIC_BASE_URL=%s\nBIND_HOST=172.17.0.1\nBIND_PORT=8791\nRETENTION_DAYS=14\n' \
      "$(python3 -c 'import secrets;print(secrets.token_hex(24))')" "$SOCIAL" "$PUBLIC_URL" > "$ENVF"
    umask 022
    echo "+ $ENVF créé (jeton aléatoire)"
  fi
  mkdir -p "$SOCIAL/public" && chmod 755 "$SOCIAL/public"
  cp "$SOCIAL/media-service/vocabag-media.service" /etc/systemd/system/
  systemctl daemon-reload
  systemctl enable --now vocabag-media
  systemctl restart vocabag-media
  sleep 2
  systemctl is-active vocabag-media
  echo -n "health (hôte)      : "; curl -fsS http://172.17.0.1:8791/health; echo
  echo -n "health (conteneur) : "; docker exec n8n-n8n-1 sh -c 'wget -qO- http://host.docker.internal:8791/health'; echo
}

step_apache() {
  # Médias publics sur staging.vocabag.com/social-media/ : le site staging est protégé par mot de passe,
  # ce seul dossier (hors dépôt git) est ouvert en lecture (GET/HEAD), sans index de fichiers, noindex.
  if grep -q 'social-media' "$VHOST"; then
    echo "= alias déjà présent dans $VHOST"
  else
    cp "$VHOST" "/root/$(basename "$VHOST").bak-$(date +%Y%m%d%H%M%S)"
    python3 - "$VHOST" "$SOCIAL/public" <<'PY'
import sys
p, pub = sys.argv[1], sys.argv[2]
s = open(p).read()
bloc = f"""    # --- VocaBag Social : images publiques lues par Instagram/Pinterest (seule exception au mot de passe)
    Alias /social-media/ {pub}/
    <Directory {pub}/>
        Options -Indexes -FollowSymLinks
        AllowOverride None
        AuthType None
        <Limit GET HEAD>
            Require all granted
        </Limit>
        <LimitExcept GET HEAD>
            Require all denied
        </LimitExcept>
        <FilesMatch "\.(?i:php|phtml|phar|cgi|pl|py|sh)$">
            Require all denied
        </FilesMatch>
        Header set X-Robots-Tag "noindex, nofollow"
    </Directory>

"""
marque = "    ErrorLog "
assert s.count(marque) == 1, 'ErrorLog introuvable'
s = s.replace(marque, bloc + marque, 1)
open(p, 'w').write(s)
PY
    a2enmod headers >/dev/null
    if ! apachectl configtest; then
      cp "$(ls -t /root/$(basename "$VHOST").bak-* | head -1)" "$VHOST"; echo "!! config refusée, vhost restauré"; exit 1
    fi
    systemctl reload apache2
    echo "+ alias ajouté (sauvegarde : /root/$(basename "$VHOST").bak-*)"
  fi
  sed -i "s#^PUBLIC_BASE_URL=.*#PUBLIC_BASE_URL=$PUBLIC_URL#" "$ENVF"
  systemctl restart vocabag-media
  echo test > "$SOCIAL/public/.probe.txt"
  echo -n "image publique sans mot de passe (200 attendu) : "; curl -sS -o /dev/null -w '%{http_code}\n' "$PUBLIC_URL/.probe.txt"
  rm -f "$SOCIAL/public/.probe.txt"
  echo -n "listing du dossier (403/404 attendu)           : "; curl -sS -o /dev/null -w '%{http_code}\n' "$PUBLIC_URL/"
  echo -n "reste de staging (401 attendu)                 : "; curl -sS -o /dev/null -w '%{http_code}\n' https://staging.vocabag.com/
}

step_n8n() {
  : "${N8N_API_KEY:?N8N_API_KEY requis (clé API n8n avec les droits dataTable + credential + workflow)}"
  python3 "$SOCIAL/setup/build_workflows.py"
  python3 "$SOCIAL/setup/setup_n8n.py"
  running=$(python3 - <<'PY'
import sqlite3
c = sqlite3.connect('file:/var/lib/docker/volumes/n8n_n8n_data/_data/database.sqlite?mode=ro', uri=True)
print(c.execute("select count(*) from execution_entity where status in ('running','waiting')").fetchone()[0])
PY
)
  if [ "$running" != "0" ]; then
    echo "!! $running exécution(s) n8n en cours : relancer plus tard (le redémarrage final les couperait)."; exit 1
  fi
  docker exec -u root n8n-n8n-1 rm -rf /tmp/vb_social
  docker cp "$SOCIAL/workflows/import" n8n-n8n-1:/tmp/vb_social
  docker exec -u root n8n-n8n-1 sh -c 'chmod -R a+rX /tmp/vb_social'
  docker exec n8n-n8n-1 n8n import:workflow --separate --input=/tmp/vb_social
  # Publiés : Carrousel (webhook Telegram), Blog (21h, webhook, appelé par le Carrousel) et Erreurs (n8n 2.x
  # refuse d'exécuter un workflow d'erreur non publié) ; Stories si PUBLIER_STORIES=1.
  for id in VbSocialCarrous1 VbSocialBlog0001 VbErreursAlerte1 VbNewsletterHeb1 ${PUBLIER_STORIES:+VbSocialStories1}; do
    docker exec n8n-n8n-1 n8n publish:workflow --id="$id" || echo "!! publication $id à faire dans l'interface"
  done
  docker restart n8n-n8n-1 >/dev/null
  for i in $(seq 1 30); do curl -fsS http://localhost:5678/healthz >/dev/null 2>&1 && break; sleep 2; done
  echo -n "n8n : "; curl -fsS http://localhost:5678/healthz; echo
}

case "${1:-}" in
  media) step_media ;;
  apache) step_apache ;;
  n8n) step_n8n ;;
  all) step_media; step_apache; step_n8n ;;
  *) echo "usage : $0 media|apache|n8n|all"; exit 2 ;;
esac
