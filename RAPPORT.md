# Rapport — Mini-architecture IoT

**Module** : Développement embarqué et IoT — 2026
**Groupe** : 67

| Membre | Contribution principale |
|---|---|
| Quentin Bastos | Application Android, protocole serveur, sécurité |
| Théo (EkkoFTW) | Serveur (architecture, alignement protocole) |
| Adel Hocine Boudjadja | Objet connecté (capteurs, OLED) |
| Arnaud Decourt | Serveur, intégration passerelle |

> Les rôles ci-dessus sont indicatifs ; chaque brique a été relue et testée en binôme.

---

## 1. Objectif

Mettre en place une architecture IoT complète **objet → passerelle → serveur → application**
permettant de relever les données d'un capteur météo dans un bureau, de les stocker,
et de configurer à distance l'affichage d'un écran OLED depuis un smartphone Android.

---

## 2. Architecture générale

```
┌──────────────┐   RF 2.4 GHz    ┌──────────────┐   USB / UART   ┌────────────┐   UDP/WiFi   ┌─────────────┐
│ Objet        │ ◄─────────────► │ Passerelle   │ ◄────────────► │ Serveur    │ ◄──────────► │ App Android │
│ micro:bit    │   (chiffré)     │ micro:bit USB│                │ PC (Python)│              │             │
│ BME280 + OLED│                 │ (relais brut)│                │ SQLite     │              │             │
└──────────────┘                 └──────────────┘                └────────────┘              └─────────────┘
```

- **Objet** : micro:bit + capteur météo BME280 + écran OLED SSD1306. Lit les capteurs,
  émet les données chiffrées par radio, reçoit l'ordre d'affichage et met à jour l'OLED.
- **Passerelle** : second micro:bit relié au PC en USB. Relais transparent radio ⇄ série.
- **Serveur** : programme Python sur le PC. Lit la série, stocke en SQLite, répond aux
  requêtes UDP de l'application.
- **Application Android** : configure le serveur, gère les objets, envoie les ordres
  d'affichage, consulte les données et l'historique.

---

## 3. Protocole réseau

### 3.1 Objet ⇄ Passerelle (radio RF 2.4 GHz, groupe 67→1)

Le module radio du micro:bit n'inclut pas l'identité de l'émetteur : le `device_id`
(identifiant unique matériel, `microbit_serial_number()`) est donc inséré dans chaque trame.

| Sens | Trame en clair | Sur la radio |
|---|---|---|
| Boot (appairage) | `PAIR\|<secret>\|<device_id>` | chiffrée AES-128-CBC, hex |
| Donnée capteur | `<device_id>\|T:25.3,H:42,L:147,P:999` | chiffrée AES-128-CBC, hex |
| Ordre d'affichage | `<device_id>,CONFIG,<ORDRE>` | en clair (relais passerelle) |

### 3.2 Sécurité — chiffrement AES-128-CBC

Le protocole impose de « penser à la sécurité des données ». Nous avons d'abord prototypé
un chiffrement XOR (pédagogique mais trivialement cassable), puis l'avons remplacé par
**AES-128 en mode CBC** :

- Chiffrement matériel via le périphérique **`NRF_ECB`** du nRF51 (HAL officiel Nordic
  `nrf_ecb_init / nrf_ecb_set_key / nrf_ecb_crypt`).
- **IV aléatoire** généré à chaque trame par le périphérique matériel `NRF_RNG`.
- Padding **PKCS#7**, sortie `hex(IV ∥ ciphertext)` — ASCII pur, donc compatible avec
  la liaison série de la passerelle.
- Clé dérivée du secret partagé `--shared-secret` (identique côté micro:bit et serveur).
- Le serveur déchiffre avec la bibliothèque `cryptography`.

L'**appairage** (`PAIR|secret|id`) permet au serveur de n'accepter que les objets
connaissant le secret. L'identifiant unique permet de **gérer plusieurs objets** déployés
dans plusieurs bureaux, conformément à l'énoncé.

### 3.3 Application ⇄ Serveur (UDP, port 10000)

| Commande | Rôle |
|---|---|
| `INIT,<passkey>` | Enregistrement / connexion d'un utilisateur |
| `ADD,<passkey>,<controller_id>` | Associer un micro:bit à la passkey |
| `REMOVE,<passkey>,<controller_id>` | Dissocier un micro:bit (purge ses données) |
| `LIST,<passkey>` | Lister les micro:bit de l'utilisateur |
| `GET,<passkey>[,<controller_id>]` | Dernières valeurs capteurs |
| `HISTORY,<passkey>,<controller_id>,<days>` | Statistiques journalières (moy/min/max) |
| `<controller_id>,CONFIG,<ORDRE>` | Définir l'ordre d'affichage OLED |

---

## 4. Objet connecté (micro:bit)

- **Capteurs** (BME280) : température, humidité, pression. **Luminosité** mesurée via la
  matrice LED utilisée comme photodiode (`readLightLevel()`).
- **Émission** : toutes les 2 s, trame chiffrée envoyée par radio.
- **Réception** : un écouteur `MICROBIT_RADIO_EVT_DATAGRAM` capte les trames `CONFIG`
  destinées à ce `device_id` et met à jour l'ordre d'affichage.
- **Écran OLED** : affiche les valeurs des capteurs dans l'ordre exact demandé par le
  serveur (`TLH`, `LTH`, etc.), tous les cas de combinaison étant gérés.

---

## 5. Passerelle (micro:bit USB)

Implémentée en **C/C++** (toolchain yotta / micro:bit DAL). C'est un **relais transparent** :

- Trame radio reçue → réémise telle quelle sur la liaison série (UART).
- Ligne série reçue → réémise telle quelle sur la radio.
- Bluetooth désactivé et taille de paquet radio portée à 251 octets (`config.json`) pour
  accueillir les trames chiffrées.

---

## 6. Serveur (Python)

Architecture en couches (Domain-Driven Design) :

- **`core/`** — modèles (`SensorSnapshot`, `ConfigCommand`) et logique métier (`ServerService`).
- **`data/`** — base **SQLite** et `IoTRepository` (pattern Repository).
- **`protocol/`** — `ProtocolCodec` (encodage/décodage des trames, déchiffrement AES).
- **`infrastructure/`** — serveur UDP threadé et pont série.

Évolutions par rapport au minimum demandé (fichier texte) :

- **Base SQLite** : un *snapshot* multi-capteurs par ligne
  (`readings(id, controller_id, temperature, humidity, luminosity, pressure, timestamp)`).
- **Throttling** : un enregistrement toutes les 10 s par objet (au lieu de toutes les 2 s)
  pour ne pas saturer la base.
- **Historique agrégé** : moyenne / minimum / maximum **par jour** pour chaque capteur.
- **Multi-objets** : table `user_controllers`, chaque objet appartient à une passkey.
- **Sécurité** : passkey hachée PBKDF2 + sel, limitation de débit UDP (50 req / 10 s / IP),
  appairage des objets.
- **Tests** : 57 tests unitaires, d'intégration et end-to-end.

---

## 7. Application Android

Développée en **Java** (Android natif, Material 3). Fonctionnalités :

- **Configuration serveur** : adresse IP, port, passkey (avec confirmation), connexion.
- **Gestion des objets** : liste déroulante des micro:bit associés à la passkey,
  ajout / suppression / rafraîchissement.
- **Ordre d'affichage OLED** : sélection des capteurs un à un pour construire l'ordre,
  affiché en toutes lettres, envoyé au serveur via UDP.
- **Données capteurs** : affichage des dernières valeurs du micro:bit sélectionné.
- **Historique** : statistiques journalières (moyenne, min, max) du micro:bit sélectionné.

---

## 8. État d'avancement

| Domaine | État |
|---|---|
| Protocole objet ⇄ passerelle (bidirectionnel) | ✅ |
| Sécurité (AES-128-CBC + appairage) | ✅ |
| Gestion multi-objets | ✅ |
| Capteurs T / H / P / L | ✅ |
| Affichage OLED dans l'ordre demandé | ✅ |
| Passerelle (relais radio ⇄ série) | ✅ |
| Serveur UDP + SQLite + `getValues()` | ✅ |
| Format d'échange (JSON / pipe / CSV) | ✅ |
| Application Android (config, ordre, données, historique) | ✅ |
| Interface web type Grafana | ❌ (évolution optionnelle non réalisée) |
| Push automatique serveur → application | ❌ (l'app rafraîchit à la demande) |

Toutes les exigences **obligatoires** de l'énoncé sont couvertes ; les deux points non
réalisés sont des évolutions explicitement optionnelles.

---

## 9. Choix technologiques — synthèse

| Brique | Choix | Justification |
|---|---|---|
| Objet / Passerelle | C/C++ (micro:bit DAL, yotta) | Accès matériel (AES, RNG), conforme aux TP |
| Chiffrement | AES-128-CBC matériel | Sécurité réelle, coût CPU négligeable (`NRF_ECB`) |
| Serveur | Python | Référence fournie, rapidité de développement |
| Base de données | SQLite | Sans serveur, fichier unique, suffisant ici |
| Application | Android natif Java | Pas de dépendance, contrôle fin de l'UDP |
| Transport app | UDP | Imposé par l'énoncé |
