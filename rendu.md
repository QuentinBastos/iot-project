# Rendu — Mini-architecture IoT

**Module** : Développement embarqué et IoT — 2026  
**Groupe** : 13

| Membre | Contribution principale |
|---|---|
| Quentin Bastos | Application Android, protocole serveur, sécurité |
| Théo Demaria | Serveur (architecture, alignement protocole) |
| Adel Hocine Boudjadja | Objet connecté (capteurs, OLED) |
| Arnaud Decourt | Serveur, intégration passerelle |

---

## 1. Objectif du projet

L'objectif est de déployer une **architecture IoT complète** permettant de :

- **Collecter** des données environnementales (température, humidité, pression, luminosité) depuis un micro-contrôleur micro:bit installé dans un bureau.
- **Stocker et exposer** ces données via un serveur Python sur PC.
- **Configurer à distance** l'ordre d'affichage d'un écran OLED depuis un smartphone Android.
- **Gérer plusieurs objets** simultanément dans plusieurs bureaux, pour plusieurs utilisateurs.

---

## 2. Architecture générale

La chaîne IoT repose sur quatre briques communicant en cascade :

```mermaid
graph TD
    A["Objet connecté\nmicro:bit + BME280 + OLED"]
    B["Passerelle\nmicro:bit USB"]
    C["Serveur Python\nPC · SQLite · UDP 10000"]
    D["App Android\nJava · Material 3"]

    A -- "Radio RF 2.4 GHz\nchiffré AES-128" --> B
    B -- "UART 115200 bauds" --> C
    C -- "UDP WiFi" --> D
    D -- "UDP WiFi" --> C
    C -- "UART" --> B
    B -- "Radio RF" --> A
```

| Brique | Rôle | Technologie |
|---|---|---|
| **Objet** | Mesure, chiffre, émet, affiche OLED | C/C++, micro:bit DAL, yotta |
| **Passerelle** | Relais transparent radio ⇄ UART | C/C++, micro:bit DAL, yotta |
| **Serveur** | Déchiffre, stocke, répond UDP | Python 3, SQLite |
| **App Android** | Configure, contrôle, consulte | Java, Material 3 |

---

## 3. Flux de données

### 3.1 Remontée d'une mesure capteur

```mermaid
sequenceDiagram
    participant OBJ as Objet
    participant GW as Passerelle
    participant SRV as Serveur
    participant APP as App Android

    OBJ->>OBJ: Lit température, humidité, pression, luminosité
    OBJ->>OBJ: Chiffre le message avec AES-128
    OBJ->>GW: Envoie par Radio RF
    GW->>SRV: Retransmet par câble USB (UART)
    SRV->>SRV: Déchiffre et enregistre dans la base
    APP->>SRV: Demande les données (UDP)
    SRV->>APP: Répond avec les dernières valeurs
```

### 3.2 Envoi d'une commande d'affichage

```mermaid
sequenceDiagram
    participant APP as App Android
    participant SRV as Serveur
    participant GW as Passerelle
    participant OBJ as Objet

    APP->>SRV: "Affiche T puis L puis H"
    SRV->>SRV: Sauvegarde la configuration
    SRV->>GW: Envoie la commande par UART
    GW->>OBJ: Retransmet par Radio RF
    OBJ->>OBJ: Met à jour l'ordre d'affichage OLED
    Note over OBJ: Au prochain cycle (≤2s) :<br/>l'écran affiche dans le bon ordre
```

### 3.3 Appairage d'un objet au démarrage

```mermaid
sequenceDiagram
    participant OBJ as Objet
    participant GW as Passerelle
    participant SRV as Serveur

    Note over OBJ: Démarrage / reset
    OBJ->>OBJ: Génère son identifiant unique (numéro de série)
    OBJ->>OBJ: Chiffre un message de présentation
    OBJ->>GW: Envoie par Radio RF
    GW->>SRV: Retransmet par UART
    SRV->>SRV: Déchiffre et vérifie le secret
    alt Secret correct
        SRV->>SRV: Ajoute l'objet à la liste des appareils de confiance
    else Secret incorrect
        SRV->>SRV: Message ignoré
    end
```

---

## 4. Sécurité

### 4.1 Chiffrement AES-128-CBC

Toutes les trames émises par l'objet sont chiffrées avec AES-128 en mode CBC, en utilisant le module matériel **NRF_ECB** intégré au nRF51. Le vecteur d'initialisation (IV) est généré aléatoirement par le générateur matériel **NRF_RNG** à chaque trame.

```mermaid
flowchart TD
    A["Message en clair\nex: température, humidité, luminosité, pression"]
    B["Ajout de rembourrage\npour atteindre un multiple de 16 octets"]
    C["IV aléatoire de 16 octets\ngénéré par le matériel"]
    D["Chiffrement bloc par bloc\nAES-128 en mode CBC"]
    E["Assemblage\nIV + données chiffrées"]
    F["Encodage en hexadécimal\ntransmissible par Radio et UART"]

    A --> B --> D
    C --> D
    D --> E --> F

    G["Réception côté serveur"]
    H["Décodage hexadécimal"]
    I["Extraction de l'IV et du message"]
    J["Déchiffrement AES-128-CBC"]
    K["Suppression du rembourrage"]
    L["Message déchiffré"]

    F --> G --> H --> I --> J --> K --> L
```

### 4.2 Couches de sécurité complètes

| Couche | Mécanisme | Détail |
|---|---|---|
| **Radio → UART** | AES-128-CBC | IV unique par trame (matériel), encodage hex |
| **Appairage** | Message chiffré avec secret partagé | Seuls les objets connaissant le secret sont acceptés |
| **Passkeys** | PBKDF2-SHA256 | 200 000 itérations avant stockage |
| **Anti-rejeu** | Horodatage Unix ±10 s | Empêche la réutilisation d'anciens messages |
| **Rate-limit UDP** | 50 requêtes / 10 s / adresse IP | Protection contre le brute-force |
| **Ownership** | Table `user_controllers` SQLite | Un objet n'appartient qu'à un seul utilisateur |

---

## 5. Objet connecté (`micro/`)

### 5.1 Matériel embarqué

```mermaid
graph TD
    CPU["Processeur\nnRF51822 ARM Cortex-M0"]
    BME["Capteur BME280\nTempérature · Humidité · Pression"]
    OLED_H["Écran OLED SSD1306\n128×64 pixels"]
    LED_H["Matrice LED 5×5\nutilisée comme capteur de lumière"]
    ECB_H["Module AES matériel\nNRF_ECB"]
    RNG_H["Générateur aléatoire matériel\nNRF_RNG"]
    RADIO_H["Radio 2.4 GHz\ngroupe 1 · paquets 251 octets max"]

    BME -- "I2C" --> CPU
    OLED_H -- "I2C" --> CPU
    LED_H --> CPU
    CPU --> ECB_H
    CPU --> RNG_H
    RNG_H --> ECB_H
    ECB_H --> RADIO_H
```

### 5.2 Lecture et compensation BME280

Le BME280 ne fournit pas directement des degrés ou des pourcentages : il retourne des valeurs brutes (ADC) qui doivent être converties grâce à 18 coefficients de calibration (3 pour la température, 9 pour la pression, 6 pour l'humidité) lus au démarrage du capteur. Cette compensation est définie par Bosch dans la datasheet du capteur.

```mermaid
flowchart TD
    INIT_B["Initialisation du capteur\nConfiguration oversampling ×16"]
    PROBE["Vérification de présence\nLecture de l'identifiant du composant"]
    CAL["Chargement des coefficients\n18 valeurs de calibration en 4 lectures I2C"]
    READ_B["Lecture des valeurs brutes\nTempérature · Pression · Humidité"]
    COMP_T_B["Calcul de la température\nRetourne des centièmes de °C"]
    COMP_H_B["Calcul de l'humidité\nDépend du résultat température"]
    COMP_P_B["Calcul de la pression\nRetourne des Pascals → conversion hPa"]

    INIT_B --> PROBE --> CAL --> READ_B
    READ_B --> COMP_T_B
    READ_B --> COMP_H_B
    READ_B --> COMP_P_B
```

Exemple : valeur interne `2230` → affichage `22.3 °C`, valeur interne `5800` → affichage `58 %`.

### 5.3 Affichage sur l'écran OLED SSD1306

L'écran est géré via un **buffer image de 1024 octets** maintenu en mémoire. Chaque mise à jour de l'écran envoie ce buffer complet en un seul transfert I2C, ce qui garantit un affichage sans scintillement.

```mermaid
flowchart TD
    CLR["Effacement de l'écran\nRemplissage du buffer avec des zéros"]
    LINE1["Écriture du titre\n'OBJET CONNECTE'"]
    LINE2["Écriture de l'identifiant\nex: 5E90D3CB"]
    LINES["Affichage des capteurs\nselon l'ordre configuré\nex: T → H → L → P"]
    UPD["Envoi vers l'écran\nTransfert I2C du buffer complet"]

    CLR --> LINE1 --> LINE2 --> LINES --> UPD
```

Chaque caractère occupe une tuile de 8×8 pixels issue d'une police bitmap embarquée. L'ordre des lignes (`T`, `H`, `L`, `P`) est mis à jour dynamiquement via la commande `CONFIG` reçue depuis l'application.

### 5.4 Boucle principale — cycle de 2 secondes

```mermaid
flowchart TD
    BOOT_O["Démarrage\nInit AES · Init OLED · Init BME280\nEnvoi trame d'appairage"]
    LOOP_O["── Boucle infinie ──"]
    S1_O["Lecture des capteurs\nT · H · P via BME280\nLuminosité via matrice LED"]
    S2_O["Construction du message\nIdentifiant + 4 valeurs"]
    S3_O["Chiffrement AES-128-CBC\nIV aléatoire matériel"]
    S4_O["Émission Radio RF\nMessage chiffré en hexadécimal"]
    S5_O["Mise à jour de l'écran OLED\nSelon l'ordre configuré"]
    S6_O["Attente de 2 secondes"]
    ISR_O["Réception CONFIG\n(événement asynchrone)"]
    UPD_O["Mise à jour de l'ordre\nd'affichage OLED"]

    BOOT_O --> LOOP_O --> S1_O --> S2_O --> S3_O --> S4_O --> S5_O --> S6_O --> LOOP_O
    ISR_O --> UPD_O
```

La réception d'une commande `CONFIG` est traitée de façon asynchrone grâce au **scheduler fiber** du DAL micro:bit : l'événement s'intercale entre les étapes de la boucle principale sans bloquer les mesures.

### 5.5 Structure des fichiers

```
micro/source/
├── main.cpp       Boucle principale · chiffrement · réception CONFIG
├── bme280.cpp/.h  Pilote capteur T/H/P avec compensation Bosch
├── ssd1306.cpp/.h Pilote écran OLED 128×64
├── nrf_ecb.c/.h   Pilote module AES matériel
└── font.h         Police bitmap 8×8 pixels
```

### 5.6 Environnement de build

```bash
# Image Docker officielle du module
docker pull schoumi/yotta:latest
docker run -it -v "$PWD:/workspaces/microbit-samples" schoumi/yotta:latest

# Dans le conteneur
source /sync/Module_Dev_app_mobile/yotta/bin/activate
yt build

# Flash (Linux)
make install
# Flash (macOS)
cp build/bbc-microbit-classic-gcc/source/microbit-samples-combined.hex /Volumes/MICROBIT/
```

---

## 6. Passerelle (`gateway/microbit-samples/`)

### 6.1 Principe — relais transparent

La passerelle ne contient **aucune logique métier**. Son seul rôle est de faire suivre les messages dans les deux sens, sans les modifier. Elle est construite avec les mêmes outils que l'objet (yotta, micro:bit DAL) et repose sur deux gestionnaires d'événements enregistrés au démarrage. Le programme principal se termine immédiatement par `release_fiber()` qui passe la main au scheduler d'événements du DAL, lequel reste actif indéfiniment.

```mermaid
flowchart TD
    INIT_G["Démarrage\nConfig Radio groupe 1\nConfig UART 115200 bauds\nAttente d'événements"]

    EV1_G["Réception Radio\nMet le message sur le câble UART"]

    EV2_G["Réception UART\nRetransmet le message par Radio"]

    OBJ_G["Objet connecté"] -- "Message chiffré\nRadio RF" --> EV1_G
    EV1_G -- "Même message\nUART" --> SRV_G["Serveur Python"]
    SRV_G -- "Commande CONFIG\nUART" --> EV2_G
    EV2_G -- "Même commande\nRadio RF" --> OBJ_G

    INIT_G --> EV1_G
    INIT_G --> EV2_G
```

### 6.2 Configuration

| Paramètre | Valeur | Raison |
|---|---|---|
| Bluetooth | Désactivé | Libère la radio pour le mode datagramme |
| Taille max paquet radio | 251 octets | Accueille un message chiffré en hexadécimal |
| Groupe radio | 1 | Identique à l'objet connecté |
| Débit UART | 115 200 bauds | Correspond à la config du serveur |
| Délimiteur | `\n` | Sépare les trames côté Python |

### 6.3 Build et flash

```bash
source /sync/Module_Dev_app_mobile/yotta/bin/activate
make build      # yt build
make install    # copie le .hex vers /media/$USER/MICROBIT/
```

---

## 7. Serveur (`server/`)

Dépendances Python : `pyserial` · `cryptography` · `bcrypt` (3 bibliothèques seulement).

### 7.1 Architecture en couches

Le serveur est organisé en 4 couches indépendantes selon le principe de séparation des responsabilités (Domain-Driven Design). Chaque couche ne connaît que la couche en dessous d'elle.

```mermaid
graph TD
    subgraph INFRA2["infrastructure/"]
        S1["Lecture UART\n(thread dédié)"]
        S2["Serveur UDP\n(port 10000)"]
    end

    subgraph PROTO2["protocol/"]
        S3["Décodage des messages\n(tous formats)"]
    end

    subgraph CORE2["core/"]
        S5["Logique métier\n(throttle, validation, ownership)"]
    end

    subgraph DATA2["data/"]
        S7["Accès base de données"]
        S8[("SQLite")]
    end

    S1 --> S3
    S2 --> S3
    S3 --> S5
    S5 --> S7
    S7 --> S8
    S5 -- "Envoi commande" --> S1
```

**Responsabilités de chaque couche :**

- `infrastructure/` — Lecture UART avec déchiffrement AES et retransmission vers l'objet. Serveur UDP avec rate-limit (50 req/10s/IP).
- `protocol/` — Détecte et décode les 4 formats acceptés (hex chiffré, pipe, JSON, CSV) et encode les réponses.
- `core/` — Logique métier : throttle 10s (une insertion par contrôleur toutes les 10 secondes), validation horodatage ±10s, vérification d'ownership.
- `data/` — Toutes les requêtes SQL, migration automatique de l'ancien schéma, connection SQLite en mode WAL.

### 7.2 Schéma relationnel SQLite

```mermaid
erDiagram
    users {
        TEXT passkey_hash PK
        DATETIME created_at
    }
    user_controllers {
        TEXT passkey_hash FK
        TEXT controller_id PK
    }
    readings {
        INTEGER id PK
        TEXT controller_id
        REAL temperature
        REAL humidity
        REAL luminosity
        REAL pressure
        DATETIME timestamp
    }
    configurations {
        TEXT controller_id PK
        TEXT display_order
        DATETIME timestamp
    }

    users ||--o{ user_controllers : "possède"
    user_controllers }o--o{ readings : "controller_id"
    user_controllers }o--o| configurations : "controller_id"
```

Un index sur `(controller_id, timestamp DESC)` dans `readings` accélère les requêtes de consultation et d'historique.

### 7.3 Traitement d'un message serie

```mermaid
flowchart TD
    RAW2["Ligne reçue sur UART"]
    HEX2{"Format hexadécimal ?"}
    DEC2["Déchiffrement AES-128"]
    PAIR2{"Message d'appairage ?"}
    OK2{"Secret valide ?"}
    TRUST2["Objet ajouté comme de confiance"]
    PIPE2{"Format pipe — id|T:x,H:x ?"}
    JSON2{"Format JSON ?"}
    CSV2["Format CSV — ctrl,capteur,valeur"]
    SVC2["Traitement par le service"]
    THR2{"Dernier envoi < 10s ?"}
    DB2["Enregistrement en base"]

    RAW2 --> HEX2
    HEX2 -- oui --> DEC2 --> PAIR2
    HEX2 -- non --> PAIR2
    PAIR2 -- oui --> OK2
    OK2 -- oui --> TRUST2
    OK2 -- non --> IGN2["Ignoré"]
    PAIR2 -- non --> PIPE2
    PIPE2 -- oui --> SVC2
    PIPE2 -- non --> JSON2
    JSON2 -- oui --> SVC2
    JSON2 -- non --> CSV2 --> SVC2
    SVC2 --> THR2
    THR2 -- oui --> DROP2["Throttlé — ignoré"]
    THR2 -- non --> DB2
```

### 7.4 Format des réponses

**GET** — une ligne par capteur disponible :
```
5E90D3CB,T,22.3
5E90D3CB,H,58.0
5E90D3CB,L,89.0
5E90D3CB,P,1012.0
```

**HISTORY** — 14 colonnes par jour (moyenne/min/max pour T, H, L, P + nombre de mesures) :
```
2026-05-19,22.50,20.10,24.80,57.20,52.00,63.00,,,,1011.30,1008.00,1015.00,12
```

### 7.5 Lancement

```bash
cd server
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Linux
python main.py --serial_port /dev/ttyACM0 --shared-secret groupe67
# Windows
python main.py --serial_port COM3 --shared-secret groupe67
# Le secret doit rester identique a SHARED_SECRET dans micro/source/main.cpp.
# Options supplémentaires : --serial-retry 5 --debug --udp_port 10000
```

### 7.6 Tests automatisés — 57 tests

Le serveur dispose d'une suite de tests complète qui valide chaque couche indépendamment. Ces tests permettent de détecter rapidement les régressions et de garantir la fiabilité du comportement global.

```mermaid
pie title Répartition des 57 tests
    "Tests unitaires — Protocole et AES" : 30
    "Tests unitaires — Base de données" : 11
    "Tests intégration — Service métier" : 13
    "Tests infrastructure — UDP" : 2
    "Tests bout en bout — Cycle complet" : 1
```

Les cas couverts incluent notamment : le chiffrement/déchiffrement AES avec vecteur fixe, le parsing de tous les formats, le throttle 10s, les agrégats journaliers, les scénarios multi-utilisateurs, la purge des données lors d'un `REMOVE`, le rate-limit UDP et la validation des horodatages.

```bash
python -m unittest discover tests   # ~2 secondes, 0 erreur
```

---

## 8. Application Android (`application/`)

`minSdk` 31 (Android 12+) · `targetSdk` 36 · Java · Material 3

### 8.1 Structure du code

```
app/src/main/java/com/example/bureaubientre/
├── MainActivity.java   Activité unique — UI, état, appels réseau
├── UdpClient.java      Envoi simple ou envoi + attente réponse (timeout 5s)
└── SensorData.java     Parsing des données capteurs · NaN si absent
```

### 8.2 Interface utilisateur — 5 sections Material3

```mermaid
flowchart TD
    APP_A["Application Android\n(écran unique à défilement)"]

    C1_A["① Configuration serveur\nIP · port · passkey"]
    C2_A["② Micro:bit associés\nAjouter · Supprimer · Lister"]
    C3_A["③ Ordre OLED\nChoisir et ordonner T · H · L · P"]
    C4_A["④ Données en direct\nAffichage des 4 capteurs"]
    C5_A["⑤ Historique\nMoyenne · min · max par jour"]

    APP_A --> C1_A
    APP_A --> C2_A
    APP_A --> C3_A
    APP_A --> C4_A
    APP_A --> C5_A
```

### 8.3 Protocole UDP côté Android

| Commande envoyée | Réponse serveur |
|---|---|
| `INIT,<passkey>` | `OK` |
| `LIST,<passkey>` | `ctrl1\nctrl2\n…` |
| `ADD,<passkey>,<id>` | `OK` / `UNAUTHORIZED` |
| `REMOVE,<passkey>,<id>` | `OK` / `ERROR` |
| `GET,<passkey>,<id>` | `ctrl,T,22.3\nctrl,H,58\n…` |
| `HISTORY,<passkey>,<id>,7` | CSV agrégé (14 colonnes/jour) |
| `<id>,CONFIG,TLH` | *(transmis vers l'objet via le serveur)* |

Chaque appel réseau est exécuté sur un thread dédié. Les résultats reviennent sur le thread principal via un Handler, conformément aux bonnes pratiques Android.

### 8.4 Construction de l'ordre OLED

```mermaid
flowchart TD
    SP_A["Sélection dans la liste\nT · H · L · P"]
    ADD_A["Bouton Ajouter\nAjout à la séquence\n(les doublons sont ignorés)"]
    TXT_A["Aperçu textuel\nex: Température → Luminosité → Humidité"]
    SEND_A["Bouton Envoyer\nCommande envoyée au serveur puis à l'objet"]

    SP_A --> ADD_A --> TXT_A --> SEND_A
```

### 8.5 Build et installation

```bash
cd application
./gradlew assembleDebug
# APK → app/build/outputs/apk/debug/app-debug.apk

adb install app/build/outputs/apk/debug/app-debug.apk
```

Le smartphone et le PC doivent être sur le **même réseau WiFi**. Saisir l'**adresse IP du PC** (pas `localhost`) dans l'écran de configuration. La configuration est persistée automatiquement entre les sessions.

---

## 9. État d'avancement

| Fonctionnalité | État | Détail |
|---|---|---|
| Protocole objet ⇄ passerelle bidirectionnel | ✅ | Radio + UART, event-driven |
| Chiffrement AES-128-CBC + appairage | ✅ | NRF_ECB matériel, IV NRF_RNG |
| Gestion multi-objets | ✅ | Ownership par utilisateur |
| Capteurs T / H / P (BME280) | ✅ | Oversampling ×16, compensation Bosch |
| Capteur luminosité L | ✅ | Matrice LED utilisée comme photodiode |
| Affichage OLED dans l'ordre demandé | ✅ | Tous les cas T/H/L/P gérés |
| Passerelle relais radio ⇄ UART | ✅ | ~50 lignes, entièrement événementiel |
| Serveur UDP + SQLite | ✅ | Throttle 10s, mode WAL |
| Formats d'échange (pipe / JSON / CSV) | ✅ | Tous acceptés |
| App Android (config, ordre, données, historique) | ✅ | 5 sections Material3 |
| Sécurité passkeys PBKDF2 + rate-limit UDP | ✅ | 200 000 itérations |
| 57 tests automatisés | ✅ | Unitaires + intégration + bout en bout |
| Interface web type Grafana | ❌ | Optionnel — non réalisé |
| Push automatique serveur → app | ❌ | Optionnel — l'app rafraîchit à la demande |

Toutes les exigences **obligatoires** de l'énoncé sont couvertes.

---

## 10. Choix technologiques

| Brique | Choix | Justification |
|---|---|---|
| Objet / Passerelle | C/C++, micro:bit DAL, yotta | Accès direct aux modules AES et RNG matériels — impossible depuis MicroPython |
| Chiffrement | AES-128-CBC matériel (NRF_ECB) | Sécurité réelle, quelques µs par bloc, sans bibliothèque logicielle |
| IV | NRF_RNG (entropie matérielle) | Imprévisibilité garantie par le matériel |
| Serveur | Python 3 | Référence fournie, 3 dépendances seulement |
| Base de données | SQLite WAL | Sans serveur, fichier unique, agrégats SQL natifs |
| Passkeys | PBKDF2-SHA256 200k itér. | Standard industrie, résistance brute-force |
| Architecture serveur | DDD 4 couches | Testabilité par couche, séparation des responsabilités |
| Format radio → UART | Hexadécimal ASCII | Transmissible sur UART sans encodage supplémentaire |
| Application | Android natif Java | Contrôle fin des sockets UDP, zéro dépendance tierce |
| Transport app | UDP | Imposé par l'énoncé |
