# Vocabag — workflow n8n : message de contact (description YouTube + légende Instagram)

> Complète la spec du workflow Vocabag (section 11 de `vocabag-channel-setup.md`, dans le dépôt vocabag-staging).
> Aucune valeur de secret dans ce document. Workflow : `Vocabag`, id `ixlsBGrzOeP8BmKk`, actif, 19h00 Europe/Paris.

## Message de contact en fin de description / légende (2026-09-20)

Chaque description YouTube et légende Instagram se termine par (en français, **après les hashtags**, formulé comme une
recommandation pour un service tiers — pas de « nous ») :

> 🎬 Envie d’apprendre à générer gratuitement des vidéos similaires avec l’IA ? Contacte RapidVideoMaker : contact.rapidvideomaker@gmail.com

Modifié dans le workflow actif (`ixlsBGrzOeP8BmKk`), 2 nœuds Code, constante `CONTACT_MSG` :
- **`Preparer metadata YouTube`** → `description` du nœud `Upload a video` (ajouté en dernière ligne du tableau `description`) ;
- **`Construire legende Instagram`** → `caption` du nœud `Publish` (`…\n\n${hashtags}\n\n${CONTACT_MSG}`).

Procédure suivie (workflow actif) : export → patch JSON → `n8n import:workflow` (désactive le workflow) → `n8n publish:workflow`
→ `docker restart n8n-n8n-1`, sans exécution en cours. Vérifié : seuls ces 2 nœuds diffèrent, connexions identiques, workflow actif.
Essai à blanc du JS avec données factices : 466 caractères (YouTube, limite 5 000) / 284 (Instagram, limite 2 200).
**Non prouvé en réel** : le premier run planifié (19h Paris) qui publie avec ce message. Pour le retirer : supprimer `CONTACT_MSG`
et sa concaténation dans ces deux nœuds (les originaux exportés ont été supprimés — pas de sauvegarde automatique).
