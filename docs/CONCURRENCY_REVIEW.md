# Revue de concurrence — 23 septembre 2026

Cette revue accompagne la PR Sonicprobe #3. Les changements sont en attente de
fusion/publication ; ils ne décrivent pas la version 0.3.52 déjà publiée.

## Périmètre et défauts corrigés

| Composant | Défaut reproduit / risque vérifié | Correction et preuve |
| --- | --- | --- |
| Keystore | Exceptions laissant des verrous pris ; réentrance globale mal comptée ; opérations contournant le verrou exclusif | Garde commune avec `RWLock` : accès ordinaires partagés, verrou global exclusif, acquisitions imbriquées équilibrées. Tests entre threads, attente d'une opération déjà engagée et conservation des verrous de l'appelant. |
| Keystore | Initialisation concurrente d'une section pouvant remplacer ses premières données | Sérialisation de la création et test de deux premières écritures concurrentes. |
| ListLock | Libération par un thread qui n'est pas propriétaire | Refus par `RuntimeError`, sans modifier le compteur du propriétaire. |
| RWLock | Lecteurs non réveillés après expiration d'un écrivain ; écrivain interrompu restant dans la file | Retrait dans `finally` et notification des attentes. Horloge monotone si disponible, repli compatible Python 2.7. |
| WorkerPool | Échec du démarrage laissant un worker fictif ; exceptions hors du corps de tâche laissant des compteurs incohérents | Démarrage avant acceptation de la première tâche, rollback des compteurs, acquittement et retrait du worker dans `finally`. |
| WorkerPool | Soumission dans une file bornée bloquée avec le verrou nécessaire au worker | Attente de capacité sans conserver le verrou des compteurs ; tests de saturation et d'arrêt concurrent. |
| WorkerPool | `killable()` vrai entre retrait de la tâche et début d'exécution, pouvant annuler une notification DWho | Utilisation du compteur des tâches non acquittées ; test contrôlant cet intervalle. |
| WorkerPool | Arrêt bloquant demandé par son propre worker ; ajout de workers après arrêt | Refus explicite ; test de récupération, de recyclage et de producteurs concurrents (120 tâches exécutées exactement une fois). |
| Serveurs TCP/UDP fixes et dynamiques | Arrêt bloqué par une file pleine, requêtes en attente abandonnées sans fermeture | Admission interruptible, fermeture des requêtes annulées, acquittement des files. Tests avec saturation et vraies sockets TCP/UDP. |
| QueueSMTPHandler | Purge non synchronisée avec l'ajout de messages ; erreur de `quit()` interrompant la purge | Échange de la file sous le verrou du handler, envoi hors verrou, fermeture de secours du transport. |
| Verrou PID par fichier | Exclusion entre processus à préserver | Deux processus concurrents : un seul acquiert le même fichier, contenu du gagnant conservé. L'algorithme de fichier n'est pas modifié. |

La PR monit-docker #31 traite séparément `LocalState` : validation des clés et
horodatages de cooldown, refus d'entrée imbriquée sans perdre le descripteur,
refus d'écriture avec un verrou hérité après `fork`. Une erreur de synchronisation
du répertoire après `rename` est signalée, mais la réservation déjà visible reste
prise en compte à la prochaine ouverture. Les validations des observations et la
copie des listes fournies par l'appelant font partie de la passe précédente.

## Compatibilité et projets consommateurs

Les signatures publiques restent inchangées. Les comportements auparavant
incorrects sont désormais refusés : libérer le verrou symbolique d'un autre thread,
ajouter des workers à un pool arrêté, attendre son propre arrêt depuis un worker,
ou fixer un maximum de workers inférieur à un. `killall(0)` reste utilisable depuis
un worker. Les tâches en attente sont annulées à l'arrêt ; leurs callbacks de fin
ne sont pas exécutés. Les fonctions déjà en cours ne sont pas interrompues.

Le workflow `tests.yml` ajoute deux jobs consommateurs (Python 3.10 et 3.12).
Ils installent le Sonicprobe candidat et vérifient que ses fichiers sont ceux
réellement importés, puis exécutent les suites de :

- DWho `3ea4a1002a37fd84c45b6c13e158ed61c67b5c95` : suite complète, Redis réel en CI,
  notifications asynchrones et dispatch inotify avec le vrai pool.
- HTTPdis `f91ee525cd36d5519db73cb9c5a8f66c6754abd9` : suite et échanges HTTP réels.
- Auton `502a0dc6ac9e8b8d550685c2ab9b66ec1d893130` : suite, client/daemon HTTP,
  sorties, authentification et isolation des propriétaires de jobs.
- Covenant `b7d875ad35320c65bd13c6688442202452ced8f1` : collecteurs/templates et
  contrats de verrouillage des modules ; pas une validation de tout le daemon.
  Le filtre optionnel `pyjq` n'est pas installé pour cette suite documentée.
- monit-docker `1f6e6a0134bd2eb81d7ec7a3ef0590063853c10d` : régressions du consommateur
  actuellement sur master. La fonctionnalité de la PR #31 a sa propre CI.

La matrice du socle conserve Python 2.7 et 3.5–3.14 et les tests des distributions
wheel/source. `integration/test_consumers.py` complète les tests propres aux projets
avec les vrais dispatchers DWho, les verrous des modules Auton/Covenant et un contrat
de verrou par zone reproduisant l'usage NSAProxy.

## Limites et règles d'utilisation

- `Keystore`, `RWLock`, `ListLock`, `WorkerPool` et les serveurs sont des objets
  de **threads dans un processus**. Ils ne partagent pas leurs données entre
  processus. Initialiser les workers et leurs verrous après la création des
  processus ; ne pas réutiliser dans l'enfant les objets actifs du parent.
- Les entrées Auton/Covenant inspectées démonisent avant `start_endpoints()` et
  la boucle HTTP. Les plugins peuvent exécuter du code d'initialisation propre :
  cette lecture ne certifie pas qu'aucun plugin ne démarre un thread avant le fork.
  Aucun reset automatique des verrous hérités n'est introduit.
- Pour combiner les verrous explicites Keystore, prendre le global avant les
  sections, puis libérer dans l'ordre inverse. Ne pas prendre le global en gardant
  une section : cela peut créer une inversion avec un autre thread. Supprimer une
  section exige l'absence d'utilisateurs de cette section (ou une coordination
  globale). Les objets retournés ne deviennent pas automatiquement thread-safe.
- `killable()` reste un instantané, pas une barrière contre de nouveaux producteurs.
  `tasks.join()` attend l'acquittement ; un arrêt avec délai peut revenir alors
  qu'une fonction applicative est encore active. Une tâche ne doit pas attendre
  un travail qu'elle a soumis à son propre pool saturé.
- Les files personnalisées du pool doivent fournir le contrat de `queue.Queue`,
  dont `task_done`, `unfinished_tasks` et `all_tasks_done`. La priorité reste celle
  de la file ; aucune garantie d'équité entre producteurs n'est ajoutée.
- La purge SMTP ne fournit pas de livraison garantie/reprise après panne réseau.
  La correction protège la file en mémoire pendant sa permutation.
- NSAProxy a fait l'objet d'une lecture de son usage du verrou par zone et d'un
  test de ce contrat, pas d'un test de son service DNS. MJCast et FD-Replay ont
  des usages recensés ; leurs environnements applicatifs historiques ne sont pas
  validés par ces jobs. Aucun changement n'est poussé dans ces projets.
- MySQL/PostgreSQL réels, matériel série, OpenVPN et toutes les combinaisons de
  plugins ne font pas partie de cette passe. Les tests de concurrence réduisent
  les risques identifiés ; ils ne constituent pas une preuve formelle d'absence
  de course dans tous les entrelacements possibles.
