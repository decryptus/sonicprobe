# Revue de Sonicprobe — septembre 2026

## Pertinence

Sonicprobe mutualise des utilitaires effectivement utilisés : workers, configuration,
URI/réseau, stockage mémoire et accès SQL. Son intérêt est réel pour cet écosystème.
Comme bibliothèque généraliste destinée à de nouveaux utilisateurs, son périmètre
est trop large et ses dépendances obligatoires trop nombreuses pour être évidents.

## Code et algorithmes

Il existe de bonnes abstractions réutilisables, dont certaines proviennent de travaux
Wazo/Proformatique/Avencall ; leurs attributions restent conservées. Les principaux
défauts observés sont la synchronisation, l'attente active, la reprise trop large après
une erreur SQL et des opérations sur les octets héritées de Python 2.

La version 0.3.52 remplace l'attente active du pool par une attente de file, fiabilise
les callbacks, l'ordre des priorités égales et la transmission des arguments. Elle
corrige les délais SQLite, la reconnexion sur erreur SQL de contrainte, l'arrêt de
serveurs inactifs, certains verrous du keystore et la suppression de clés imbriquées.
L'accumulation des fichiers par fragments évite les recopies successives d'une chaîne
croissante. Les exports PEM sont corrigés et SHA-256 devient le défaut.

## Architecture et limites

Conserver les modules utiles mais envisager une séparation entre un noyau léger et
les intégrations facultatives. Le module HTTP historique crée une dépendance circulaire
avec HTTPdis ; il faut une migration annoncée pour la supprimer. La génération de
certificats utilise encore l'API mutable OpenSSL ; `pyOpenSSL<26.2` protège sa
compatibilité en attendant une migration vers cryptography.x509.

Les pilotes MySQL/PostgreSQL réels, l'OpenVPN, les interfaces série, les archives
xbstream et toutes les combinaisons de concurrence ne sont pas certifiés par cette
campagne. Le pool ne peut pas arrêter de force une fonction Python déjà en cours.
La suite apporte une base de régression, pas une preuve formelle de sûreté. Le projet
mérite d'être conservé comme boîte à outils de l'écosystème, avec un périmètre clarifié.

## Passe complémentaire

La [revue de concurrence du 23 septembre](CONCURRENCY_REVIEW.md) documente les
défauts supplémentaires, les corrections proposées en PR et les vérifications
des projets consommateurs. Elle précise aussi les limites de validation.
