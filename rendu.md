---
title: "Rendu — Mini-architecture IoT"
module: "Développement embarqué et IoT"
année: 2026
groupe: 67
tags:
  - iot
  - microbit
  - android
  - python
  - embedded
  - aes-128
  - sqlite
  - bme280
  - ssd1306
---

# Rendu — Mini-architecture IoT

> [!info] Informations du groupe
> **Module** : Développement embarqué et IoT — 2026  
> **Groupe** : 67
>
> | Membre | Contribution principale |
> |---|---|
> | Quentin Bastos | Application Android, protocole serveur, sécurité |
> | Théo (EkkoFTW) | Serveur (architecture, alignement protocole) |
> | Adel Hocine Boudjadja | Objet connecté (capteurs, OLED) |
> | Arnaud Decourt | Serveur, intégration passerelle |
>
> Les rôles sont indicatifs ; chaque brique a été relue et testée en binôme.

---

## 1. Objectif du projet

L'objectif est de déployer une **architecture IoT complète** permettant de :

- **Collecter** des données environnementales (température, humidité, pression, luminosité) depuis un micro-contrôleur micro:bit installé dans un bureau.
- **Stocker et exposer** ces données via un serveur Python sur PC.
- **Configurer à distance** l'ordre d'affichage d'un écran OLED depuis un smartphone Android.
- **Gérer plusieurs objets** simultanément dans plusieurs bureaux, pour plusieurs utilisateurs.

---

## 2. Architecture générale

```mermaid
sequenceDiagram
    autonumber
    actor Utilisateur
    participant App as 📱 App Android<br/>(Bureau bien etre)
    participant Serveur as 💻 Serveur Python<br/>(PC · port UDP 10000)
    participant Passerelle as 📻 Passerelle<br/>(micro:bit USB)
    participant Objet as 🌡️ Objet connecté<br/>(micro:bit · BME280 · OLED)

    Note over Utilisateur, Objet: Sens 1 — Contrôle de l'affichage OLED
    Utilisateur->>App: Choisit l'ordre (ex: TLH) via Spinner
    App->>Serveur: UDP · 5E90D3CB,CONFIG,TLH
    Serveur->>Passerelle: UART · 5E90D3CB,CONFIG,TLH\n
    Passerelle->>Objet: Radio RF 2.4 GHz (en clair)
    Note right of Objet: g_display_order = "TLH"<br/>OLED mis à jour au prochain cycle

    Note over Utilisateur, Objet: Sens 2 — Remontée des données capteurs
    Objet->>Objet: Lit BME280 + readLightLevel() toutes les 2s
    Objet->>Passerelle: Radio RF · hex(IV‖AES-CBC(id|T:x,H:x,L:x,P:x))
    Passerelle->>Serveur: UART · même hex + \n
    Serveur->>Serveur: Déchiffre AES → stocke SQLite (throttle 10s)
    App->>Serveur: UDP · GET,passkey,5E90D3CB
    Serveur->>App: UDP · 5E90D3CB,T,22.3\n5E90D3CB,H,58\n...
    App->>Utilisateur: Affiche T · H · L · P
```

---

## 3. Vue d'ensemble des composants

```mermaid
graph TB
    subgraph OBJET["🔲 Objet connecté — micro/"]
        direction TB
        CPU_O["nRF51822\nARM Cortex-M0"]
        BME["BME280 I2C\nT · H · P\n(addr 0xEC)"]
        OLED["SSD1306 I2C\n128×64 OLED\n8 pages · 16 chars/ligne"]
        LED_M["Matrice LED 5×5\ncomme photodiode\nreadLightLevel() → 0-255"]
        ECB["NRF_ECB\nAES-128 matériel\n48 octets (key+plain+cipher)"]
        RNG["NRF_RNG\nEntropie matérielle\nIV aléatoire 16 octets"]
        RADIO_O["Radio 2.4 GHz\nGroupe 1 · paquet 251 o."]
        BME -- "I2C bus" --> CPU_O
        OLED -- "I2C bus" --> CPU_O
        LED_M --> CPU_O
        CPU_O --> ECB
        CPU_O --> RNG
        RNG --> ECB
        ECB --> RADIO_O
    end

    subgraph GW["🔌 Passerelle — gateway/microbit-samples/"]
        direction TB
        CPU_G["nRF51822\nevent-driven fiber"]
        RADIO_G["Radio 2.4 GHz\nGroupe 1 · paquet 251 o."]
        UART_G["UART USB\n115200 bauds · délim \\n"]
        CPU_G --> RADIO_G
        CPU_G --> UART_G
    end

    subgraph SRV["🖥️ Serveur — server/"]
        direction TB
        SERIAL_S["SerialServer\nThread UART"]
        UDP_S["UDPServer\nThreadingMixIn\nport 10000"]
        CODEC["ProtocolCodec\nAES·pipe·JSON·CSV"]
        SVC["ServerService\nlogique métier · throttle"]
        REPO["IoTRepository\nSQLite WAL"]
        DB[("SQLite\nreadings\nusers\nconfigs")]
        SERIAL_S --> CODEC
        UDP_S --> CODEC
        CODEC --> SVC
        SVC --> REPO
        REPO --> DB
        SVC --> SERIAL_S
    end

    subgraph APP["📱 Application Android — application/"]
        direction TB
        MA["MainActivity\n5 sections Material3"]
        UC["UdpClient\nsend() · sendAndReceive()\ntimeout 5s"]
        SD["SensorData\nparseMultiline()"]
        PREFS["SharedPreferences\nIP · port · passkey · ctrl"]
        MA --> UC
        MA --> SD
        MA --> PREFS
    end

    RADIO_O -- "hex chiffré\nRF 2.4 GHz" --> RADIO_G
    UART_G -- "même hex + \\n\nUSB" --> SERIAL_S
    SERIAL_S -- "CONFIG en clair\n+ \\n" --> UART_G
    UART_G -- "CONFIG\nRF 2.4 GHz" --> RADIO_O
    UDP_S -- "UDP WiFi" --> UC
    UC -- "UDP WiFi" --> UDP_S
```

---

## 4. Protocole réseau

### 4.1 Objet ⇄ Passerelle (radio RF 2.4 GHz)

Les deux cartes (objet et passerelle) partagent la même configuration radio :

```json
{
  "microbit-dal": {
    "bluetooth": { "enabled": 0 },
    "radio_max_packet_size": 251
  }
}
```

> [!note] Pourquoi 251 octets ?
> La trame chiffrée `hex(IV‖ciphertext)` est en ASCII hexadécimal. Pour un payload de ~40 chars, le PKCS#7 donne 2 blocs de 16 octets soit 32 octets de ciphertext + 16 octets IV = 48 octets → 96 chars hex. La limite par défaut du DAL (32 octets) est insuffisante.

| Sens | Contenu en clair | Sur la radio |
|---|---|---|
| Boot — appairage | `PAIR\|groupe67\|5E90D3CB` | Chiffrée AES-128-CBC, hex ASCII |
| Données capteurs | `5E90D3CB\|T:22.3,H:58,L:89,P:1012` | Chiffrée AES-128-CBC, hex ASCII |
| Ordre OLED (reçu) | `5E90D3CB,CONFIG,TLH` | En clair — relais passerelle |

### 4.2 App Android ⇄ Serveur (UDP port 10 000)

| Commande | Réponse |
|---|---|
| `INIT,<passkey>` | `OK` |
| `LIST,<passkey>` | `ctrl1\nctrl2\n…` |
| `ADD,<passkey>,<id>` | `OK` / `UNAUTHORIZED` |
| `REMOVE,<passkey>,<id>` | `OK` / `ERROR` |
| `GET,<passkey>,<id>` | `ctrl,T,22.3\nctrl,H,58\n…` |
| `HISTORY,<passkey>,<id>,<jours>` | CSV agrégé jour par jour |
| `<id>,CONFIG,<ordre>` | *(broadcast vers l'objet)* |

---

## 5. Sécurité

> [!warning] Exigence de l'énoncé
> "Pensez aussi à la sécurité des données envoyées." Le déploiement multi-bureaux expose les trames radio à tout récepteur sur le même groupe RF.

### 5.1 Chiffrement AES-128-CBC de bout en bout

```mermaid
flowchart LR
    subgraph MICRO["Côté micro:bit (C/C++)"]
        P["Payload clair\n5E90D3CB|T:22.3,H:58"] --> PAD["Padding PKCS#7\n→ N×16 octets"]
        PAD --> XOR
        RNG2["NRF_RNG\nIV[16] aléatoire"] --> XOR["bloc_i XOR prev\nprev_0 = IV"]
        XOR --> ECB["NRF_ECB\nAES-128 ECB matériel\nnrf_ecb_crypt(dst, src)"]
        ECB --> CHAIN["CBC chain\nprev = cipher_i"]
        CHAIN --> XOR
        ECB --> HEX["hex(IV ‖ ciphertext)\nASCII pur · safe UART"]
    end

    subgraph SERVER["Côté serveur (Python)"]
        HEX2["hex reçu"] --> PARSE["bytes.fromhex()"]
        PARSE --> SPLIT["iv = data[:16]\ncipher = data[16:]"]
        SPLIT --> DEC["AES-CBC decrypt\n(lib cryptography)"]
        DEC --> UNPAD["unpadder PKCS#7"]
        UNPAD --> PLAIN["Payload déchiffré\n5E90D3CB|T:22.3,..."]
    end

    HEX -- "UART + radio" --> HEX2
```

### 5.2 Détail du périphérique NRF_ECB

Le driver `nrf_ecb.c` expose une structure interne de **48 octets** directement mappée en mémoire matérielle :

```
ecb_data[0..15]  = clé AES (NRF_ECB->ECBDATAPTR pointe dessus)
ecb_data[16..31] = cleartext → entrée
ecb_data[32..47] = ciphertext ← sortie
```

`nrf_ecb_crypt()` écrit `TASKS_STARTECB = 1` et attend `EVENTS_ENDECB` (boucle de polling avec timeout à ~16 M cycles). Coût réel : ~6 µs par bloc sur 16 MHz.

### 5.3 Dérivation de la clé

```
shared_secret = "groupe67"  (8 chars)
AES_KEY[16]   = b"groupe67\x00\x00\x00\x00\x00\x00\x00\x00"
```

Même logique côté serveur (`derive_aes_key()` : zero-padding à 16 octets).

### 5.4 Couches de sécurité complètes

| Couche | Mécanisme | Détail |
|---|---|---|
| **Radio → UART** | AES-128-CBC | IV unique par trame (NRF_RNG), PKCS#7, hex ASCII |
| **Appairage** | `PAIR\|secret\|id` chiffré | Le serveur n'accepte que les devices connus |
| **Passkeys** | PBKDF2-SHA256 | 200 000 itérations + sel statique |
| **Anti-rejeu** | Timestamp Unix ±10 s | Valide sur `ADD` / `REMOVE` |
| **Rate-limit UDP** | 50 req / 10 s / IP | Protège contre brute-force passkey |
| **Ownership** | `user_controllers` en base | Un controller ne peut appartenir qu'à un seul utilisateur |

---

## 6. Objet connecté (`micro/`)

> [!success] Livrable ② — Code de l'objet connecté
> Dossier : `micro/` · Documentation : `micro/README.md` · Notes TP : `micro/NOTES-TP.md`

### 6.1 Pilote BME280 — lecture et compensation

```mermaid
flowchart TD
    INIT["bme280::bme280()\nI2C addr 0xEC\noversampling ×16 pour T·H·P\nmode NORMAL · standby 62ms"] --> PROBE["probe_sensor()\nLit register chip_id 0xD0\nAttendu : 0x60"]
    PROBE --> CAL["get_calibration_data()\n3 lectures I2C séparées :\nT[3] regs 0x88\nP[9] regs 0x8E\nH1 reg 0xA1 + H[7] regs 0xE1"]
    CAL --> READ_LOOP

    READ_LOOP["sensor_read()\n→ 8 octets depuis reg 0xF7"] --> COMP_T["compensate_temperature(raw_T)\ntmp1 = calibration T1·T2\ntmp2 = calibration T1·T3\nfine_temp = tmp1+tmp2\n→ retourne centièmes de °C"]
    READ_LOOP --> COMP_H["compensate_humidity(raw_H)\nutilise fine_temp\n→ retourne centièmes de %rH"]
    READ_LOOP --> COMP_P["compensate_pressure(raw_P)\nutilise fine_temp + P1..P9\n→ retourne Pa\n÷100 → hPa"]

    COMP_T --> SEND["Payload :\nT_centi/100 . (T_centi%100)/10\nH_centi/100\nP_pa/100"]
```

> [!note] Représentation interne
> - Température : entier en centièmes de °C — `g_T_centi = 2230` → `22.3°C`
> - Humidité : entier en centièmes de % — `g_H_centi = 5800` → `58%`
> - Pression : entier en hPa — `g_P_hpa = compensate_pressure() / 100`

### 6.2 Pilote SSD1306 — OLED 128×64

```mermaid
flowchart LR
    subgraph RAM["Buffer GDDRAM (en mémoire micro:bit)"]
        direction TB
        B0["gddram[0] = SSD130x_DATA_ONLY (0x40)"]
        B1["gddram[1..1024]\n128×8 pages de 8 bits\n= 1024 octets bitmap"]
    end
    subgraph API["API utilisée dans main.cpp"]
        CLEAR["screen.clear()\nbuffer_set(gddram, 0x00)"]
        LINE["screen.display_line(line, col, text)\npour chaque char → buffer_set_tile()\ntile = font[c - FIRST_FONT_CHAR]\n8 octets par caractère (police 8×8)"]
        UPDATE["screen.update_screen()\ni2c->write(SSD130x_ADDR, gddram, 1025)\nenvoi du buffer complet en I2C"]
    end
    CLEAR --> LINE --> UPDATE --> RAM
```

La séquence d'affichage dans `main.cpp` :
1. `screen.clear()` — efface le buffer
2. `screen.display_line(0, 0, "OBJET CONNECTE")`
3. `screen.display_line(1, 0, device_id)` — ex: `5E90D3CB`
4. Lignes 3 à 7 : itère sur `g_display_order`, appelle `display_sensor_line(screen, oled_line, code)`
5. `screen.update_screen()` — envoie les 1024 octets bitmap via I2C

### 6.3 Boucle principale et listener radio

```mermaid
flowchart TD
    BOOT["main()\nuBit.init()\nradio.setGroup(1) · radio.enable()\nnrf_ecb_init() · nrf_ecb_set_key(AES_KEY)\nInit SSD1306 + BME280\ng_device_id = hex(microbit_serial_number())"] --> PAIR["Envoi appairage\nPAIR|groupe67|5E90D3CB\n→ aes_cbc_encrypt_hex() → radio.send()"]

    PAIR --> LOOP["── while(1) ──"]
    LOOP --> S1["bme.sensor_read(&P, &T, &H)"]
    S1 --> S2["g_T_centi = compensate_temperature()\ng_H_centi = compensate_humidity()\ng_P_hpa   = compensate_pressure()/100\ng_L_level = display.readLightLevel()"]
    S2 --> S3["Construit payload\nid|T:x.x,H:x,L:x,P:x"]
    S3 --> S4["aes_cbc_encrypt_hex(payload)\n→ random_iv() via NRF_RNG\n→ CBC sur NRF_ECB bloc par bloc\n→ hex(IV‖ciphertext)"]
    S4 --> S5["radio.datagram.send(hex)"]
    S5 --> S6["screen.clear()\ndisplay_line 0 : OBJET CONNECTE\ndisplay_line 1 : device_id"]
    S6 --> S7["Parcourt g_display_order char par char\ndisplay_sensor_line(screen, line, code)\ncodes valides : T H L P"]
    S7 --> S8["screen.update_screen()"]
    S8 --> S9["uBit.sleep(2000 ms)"]
    S9 --> LOOP

    ISR["on_radio_receive()\n[fiber event · MICROBIT_RADIO_EVT_DATAGRAM]"] --> PARSE["Parse la trame reçue\n3 segments séparés par virgules\nseg0 = device_id ?"]
    PARSE -- "device_id correct\nCONFIG au milieu" --> UPDATE["g_display_order = segment tail\nex: TLH"]
    PARSE -- "device_id différent\nou format invalide" --> IGNORE["silently ignored"]
```

> [!note] Modèle de concurrence
> L'objet utilise le **scheduler fiber** du DAL micro:bit : `on_radio_receive` est enregistré sur le `messageBus`, il s'exécute entre deux instructions de la boucle principale (coopératif). Pas de mutex nécessaire — accès à `g_display_order` sérialisé par le scheduler.

### 6.4 Structure des fichiers

```
micro/source/
├── main.cpp       AES-CBC · boucle capteurs · OLED · listener CONFIG
├── bme280.cpp/.h  I2C addr 0xEC · oversampling ×16 · 13 coeffs calibration
├── ssd1306.cpp/.h I2C addr 0x7A · 128×64 · 8 pages · police 8×8
├── nrf_ecb.c/.h   NRF_ECB peripheral · nrf_ecb_init/set_key/crypt
└── font.h         Police bitmap 8×8 (FIRST_FONT_CHAR = espace ASCII 0x20)
```

### 6.5 Environnement de build

```bash
# Image Docker officielle du module
docker pull schoumi/yotta:latest
docker run -it -v "$PWD:/workspaces/microbit-samples" schoumi/yotta:latest

# Dans le conteneur
source /sync/Module_Dev_app_mobile/yotta/bin/activate
yt build

# Flash (Linux host)
make install   # → cp build/.../microbit-samples-combined.hex /media/$USER/MICROBIT/
```

Chaîne : `yotta` → `cmake` + `ninja` → `arm-none-eabi-gcc` → `.hex` + `srec_cat` → `-combined.hex`

---

## 7. Passerelle (`gateway/microbit-samples/`)

> [!success] Livrable ③ — Code de la passerelle
> Dossier : `gateway/microbit-samples/` · Documentation : `gateway/microbit-samples/README.md`

### 7.1 Principe — relais transparent événementiel

La passerelle ne contient **aucune logique métier**. Le `main()` se termine par `release_fiber()` qui endort la tâche principale mais laisse le **système d'événements** du DAL tourner indéfiniment.

```mermaid
flowchart LR
    subgraph GW["Passerelle (main.cpp — ~50 lignes)"]
        INIT2["main()\nuBit.init()\nradio.enable() · radio.setGroup(1)\nserial.baud(115200)\nserial.eventOn('\\n')\nrelease_fiber()"]

        EV1["onRadioReceive()\nMicroBitEvent MICROBIT_RADIO_EVT_DATAGRAM\n→ msg = radio.datagram.recv()\n→ serial.send(msg)\n→ serial.send('\\n')"]

        EV2["onSerialReceive()\nMicroBitEvent MICROBIT_SERIAL_EVT_DELIM_MATCH\n→ msg = serial.readUntil('\\n', ASYNC)\n→ radio.datagram.send(msg)"]

        INIT2 --> EV1
        INIT2 --> EV2
    end

    OBJ2["Objet\n(radio)"] -- "hex chiffré" --> EV1
    EV1 -- "même hex + \\n\nUART" --> SRV2["Serveur"]
    SRV2 -- "CONFIG + \\n\nUART" --> EV2
    EV2 -- "CONFIG" --> OBJ2
```

> [!note] `release_fiber()` vs `while(1)`
> Contrairement à `return 0` qui arrêterait l'exécution, `release_fiber()` libère le fiber du `main()` et laisse le scheduler DAL gérer les deux listeners. Pas de busy-wait, pas de polling.

### 7.2 Configuration détaillée

```
config.json (gateway/microbit-samples/)
├── bluetooth.enabled = 0      → libère la pile radio pour le mode datagram brut
└── radio_max_packet_size = 251 → accueille hex(IV 16o + payload ~48o) = ~128 chars hex

source/main.cpp
├── radio.setGroup(1)           → identique à l'objet (groupe alloué à l'équipe)
├── serial.baud(115200)         → doit correspondre à --baudrate du serveur
└── serial.eventOn("\n")        → déclenche onSerialReceive à chaque ligne complète
```

### 7.3 Build et flash

```bash
# Depuis gateway/microbit-samples/
source /sync/Module_Dev_app_mobile/yotta/bin/activate
make build    # yt build

make install  # copie le .hex sur /media/$USER/MICROBIT/
# ou :
./flash.sh    # cp build/.../microbit-samples-combined.hex /media/arnaud-dec/MICROBIT/
```

---

## 8. Serveur (`server/`)

> [!success] Livrable ④ — Application côté serveur
> Dossier : `server/` · Documentation : `server/README.md`
> Dépendances : `pyserial` · `cryptography` · `bcrypt` (3 libs Python seulement)

### 8.1 Architecture en couches (Domain-Driven Design)

```mermaid
graph TD
    subgraph INFRA["infrastructure/ — I/O (threads)"]
        UART_PY["SerialServer(Thread)\n· _looks_hex() → décrypte AES\n· parse_pairing() → handshake\n· decode_pipe_payload() → id|T:x,...\n· decode_json_batch() → JSON\n· decode() → CSV legacy\n· send_command() → UART out"]
        UDP_PY["UDPServer(ThreadingMixIn)\n· is_rate_limited() 50req/10s/IP\n· ThreadedUDPServer"]
    end

    subgraph PROTO["protocol/"]
        CODEC_PY["ProtocolCodec (static methods)\n· decrypt_aes_cbc_hex(hex, key)\n· encrypt_aes_cbc_hex(plain, key, iv)\n· decode_pipe_payload(raw)\n· decode_json_sensor_batch(raw, default_id)\n· decode(raw) → AppEvent\n· parse_pairing(raw)\n· encode_config(config)"]
        EVENTS_PY["AppEvent (frozen dataclasses)\nRegisterUserEvent · AddControllerEvent\nRemoveControllerEvent · ListControllersEvent\nDataRequestEvent · HistoryRequestEvent\nConfigCommandEvent\nSensorReadingEvent · SensorSnapshotEvent"]
    end

    subgraph CORE_PY["core/ — logique métier"]
        SVC_PY["ServerService\n· handle_event(event) → match\n· _handle_sensor_snapshot() + throttle 10s\n· _handle_config_command() → broadcast\n· _handle_register_user() → PBKDF2\n· _handle_add/remove_controller()\n· _handle_data/history_request()\n· _is_timestamp_valid() ±10s"]
        MODELS_PY["Models (frozen dataclasses)\nSensorReading · SensorSnapshot\nConfigCommand · User"]
    end

    subgraph DATA_PY["data/ — persistance"]
        REPO_PY["IoTRepository\n· insert_snapshot() / insert_reading()\n· get_latest_readings_for_user/controller()\n· get_daily_aggregates_for_controller()\n· register_user() · is_user_valid()\n· add/remove_user_controller()\n· user_owns_controller()\n· hash_passkey() — PBKDF2+sel"]
        DB_PY["Database\n· PRAGMA foreign_keys=ON\n· PRAGMA journal_mode=WAL\n· migration legacy schema auto\n· index (controller_id, timestamp DESC)"]
    end

    UART_PY --> CODEC_PY
    UDP_PY --> CODEC_PY
    CODEC_PY --> EVENTS_PY
    EVENTS_PY --> SVC_PY
    SVC_PY --> MODELS_PY
    SVC_PY --> REPO_PY
    REPO_PY --> DB_PY
    SVC_PY -- "command_sender callback" --> UART_PY
```

### 8.2 Schéma relationnel SQLite

```mermaid
erDiagram
    users {
        TEXT passkey_hash PK "PBKDF2-SHA256 + sel"
        DATETIME created_at
    }
    user_controllers {
        TEXT passkey_hash FK
        TEXT controller_id PK
    }
    readings {
        INTEGER id PK "AUTOINCREMENT"
        TEXT controller_id
        REAL temperature "NULL si absent"
        REAL humidity    "NULL si absent"
        REAL luminosity  "NULL si absent"
        REAL pressure    "NULL si absent"
        DATETIME timestamp
    }
    configurations {
        TEXT controller_id PK
        TEXT display_order "ex: TLH"
        DATETIME timestamp
    }

    users ||--o{ user_controllers : "possède"
    user_controllers }o--o{ readings : "controller_id"
    user_controllers }o--o| configurations : "controller_id"
```

> [!note] Migration automatique
> `database.py` détecte l'ancien schéma (colonne `sensor_id`) au démarrage et pivote les données en snapshots multi-capteurs sans perte. La migration vers `user_controllers` (depuis l'ancien `user_sensors`) est aussi automatique.

### 8.3 Dispatch d'une ligne série

```mermaid
flowchart TD
    RAW["raw_line reçu de l'UART"] --> ISHEX{"_looks_hex() ?\nlongueur paire + chars 0-9A-F"}
    ISHEX -- oui --> DECRYPT["ProtocolCodec.decrypt_aes_cbc_hex()\nbytes.fromhex · iv=data[:16]\nAES-CBC décrypte · unpadder PKCS#7"]
    DECRYPT --> DECOK{"Déchiffrement OK ?"}
    DECOK -- non --> WARN["log warning — ignoré"]
    DECOK -- oui --> RAW2["raw_line = plaintext"]
    ISHEX -- non --> RAW2

    RAW2 --> PAIR{"parse_pairing() ?\nstartswith PAIR|"}
    PAIR -- oui --> SECRET{"secret == shared_secret ?"}
    SECRET -- oui --> TRUST["paired_devices.add(device_id)\nlog: Pairing OK"]
    SECRET -- non --> REJECT["log warning rejected"]
    PAIR -- non --> PIPE{"'|' ET ':'\ndans la ligne ?"}

    PIPE -- oui --> PIPE_DEC["decode_pipe_payload()\nid|T:x.x,H:x,L:x,P:x\n→ SensorSnapshotEvent"]
    PIPE_DEC --> SVC_EV["service.handle_event()"]

    PIPE -- non --> JSON_CHK{"startswith('{') ?"}
    JSON_CHK -- oui --> JSON_DEC["decode_json_sensor_batch()\n{T:x, H:x, id:x}\n→ SensorSnapshotEvent"]
    JSON_DEC --> SVC_EV

    JSON_CHK -- non --> CSV_DEC["ProtocolCodec.decode()\nctrl,sensor,value (CSV legacy)\n→ SensorReadingEvent / autre"]
    CSV_DEC --> SVC_EV

    SVC_EV --> THROTTLE{"(si SensorSnapshot)\nnow - last < 10s ?"}
    THROTTLE -- oui --> DROP["snapshot throttled — ignoré"]
    THROTTLE -- non --> INSERT["repository.insert_snapshot()\nINSERT INTO readings ..."]
```

### 8.4 Réponse GET et HISTORY

**GET** — retourne les dernières valeurs "explosées" en lignes `(ctrl, sensor_id, value)` :

```
5E90D3CB,T,22.3
5E90D3CB,H,58.0
5E90D3CB,L,89.0
5E90D3CB,P,1012.0
```

**HISTORY** — agrégats journaliers (14 colonnes) :

```
day,t_avg,t_min,t_max,h_avg,h_min,h_max,l_avg,l_min,l_max,p_avg,p_min,p_max,samples
2026-05-19,22.50,20.10,24.80,57.20,52.00,63.00,,,,1011.30,1008.00,1015.00,12
```

Champs absents (ex: luminosité non reçue) → colonne vide.

### 8.5 Lancement

```bash
cd server
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt   # pyserial · cryptography · bcrypt

# Linux
python main.py --serial_port /dev/ttyACM0 --shared-secret groupe67
# Windows
python main.py --serial_port COM3 --shared-secret groupe67
# Options supplémentaires
python main.py --serial-retry 5 --debug --udp_port 10000
```

### 8.6 Tests automatisés — 57 tests

```mermaid
pie title 57 tests — répartition par couche
    "Unit — Codec & AES (test_protocol.py)" : 22
    "Unit — Repository SQL (test_repository.py)" : 14
    "Integration — Service (test_service.py)" : 15
    "Infrastructure — UDP (test_udp_server.py)" : 3
    "E2E — Cycle complet (test_system_flow.py)" : 3
```

```bash
python -m unittest discover tests   # ~2 secondes, 0 erreur
```

Cas couverts : round-trip AES, parsing pipe/JSON/CSV, throttling 10s, agrégats journaliers, multi-utilisateurs, purge sur REMOVE, rate-limit UDP, validation timestamp, vecteur CBC déterministe.

---

## 9. Application Android (`application/`)

> [!success] Livrable ① — Application Android
> Dossier : `application/` · Documentation : `application/README.md`
> APK : `bureau-bien-etre.apk` · `minSdk` 31 (Android 12+) · `targetSdk` 36

### 9.1 Architecture

```mermaid
graph TD
    subgraph ANDROID["App Android — com.example.bureaubientre"]
        MA2["MainActivity\nActivity unique (single Activity)\nSharedPreferences 'server_config'\nIP · port · passkey · controller sélectionné"]

        subgraph UI_CARDS["5 MaterialCardView"]
            C1["① Config serveur\nIP · port · passkey (avec confirmation)\nbouton Connecter → INIT UDP"]
            C2["② Micro:bit associés\nSpinner controllers\nADD · REMOVE · REFRESH"]
            C3["③ Ordre OLED\nSpinner T·H·L·P → Ajouter\ntextDisplayOrder · Envoyer · Reset"]
            C4["④ Données capteurs\n4 tuiles colorées\nT(orange)·H(bleu)·L(jaune)·P(vert)\nbouton Rafraîchir → GET UDP"]
            C5["⑤ Historique\nbouton Charger → HISTORY UDP\nSpinner filtre tout·T·H·L·P\nScrollView monospace"]
        end

        UC2["UdpClient\nsend() — fire & forget\nsendAndReceive() — timeout 5s\nThread dédié → Handler mainLooper"]
        SD2["SensorData\nparseMultiline(response)\nT·H·L·P Float (NaN si absent)\nformatTemperature/Humidity/…"]
        PREFS2["SharedPreferences\nIP · port · passkey\ncontroller sélectionné"]

        MA2 --> C1
        MA2 --> C2
        MA2 --> C3
        MA2 --> C4
        MA2 --> C5
        MA2 --> UC2
        MA2 --> SD2
        MA2 --> PREFS2
    end
```

### 9.2 Cycle de vie d'une requête UDP

```mermaid
sequenceDiagram
    participant UI as Thread UI (MainActivity)
    participant UDP as UdpClient (Thread dédié)
    participant SRV3 as Serveur Python

    UI->>UDP: sendAndReceive("GET,passkey,5E90D3CB", callback)
    Note over UDP: new Thread() { DatagramSocket socket }
    UDP->>SRV3: UDP datagram
    SRV3-->>UDP: réponse dans 4096 octets max
    Note over UDP: socket.setSoTimeout(5000ms)
    alt Réponse reçue
        UDP->>UI: mainHandler.post(callback.onDataReceived(response))
        UI->>UI: SensorData.parseMultiline(response)
        UI->>UI: Met à jour textTemperature, textHumidity...
    else Timeout 5s
        UDP->>UI: mainHandler.post(callback.onError("Timeout"))
    end
```

### 9.3 Parsing de la réponse `GET`

`SensorData.parseMultiline()` accepte toutes les variantes de noms de capteurs :

| Codes acceptés | Capteur |
|---|---|
| `T`, `TEMP`, `TEMPERATURE` | Température |
| `H`, `HUM`, `HUMIDITY`, `HUMIDITE` | Humidité |
| `L`, `LUM`, `LUMINOSITY`, `LUMINOSITE` | Luminosité |
| `P`, `PRES`, `PRESSURE`, `PRESSION` | Pression |

Les valeurs absentes restent `Float.NaN` et s'affichent `--` via les méthodes `format*()`.

### 9.4 Construction de l'ordre OLED

```mermaid
flowchart TD
    START2["initSensorCatalog()\nLinkedHashMap T→Température\nH→Humidité · L→Luminosité · P→Pression"] --> SPINNER2["Spinner bindé\nà sensorLabelList"]
    SPINNER2 --> ADD2["buttonAddToOrder.onClick()\nletterFor(selectedLabel)\ndisplayOrder.indexOf(letter) >= 0 ? skip\ndisplayOrder.append(letter)"]
    ADD2 --> DISPLAY2["textDisplayOrder.setText()\nTemperature → Humidité → ..."]
    DISPLAY2 --> SEND2["buttonSendOrder.onClick()\nudpClient.send(id + ',CONFIG,' + displayOrder)"]
```

> [!warning] Réseau
> Le smartphone et le PC doivent être sur le **même réseau WiFi**. L'IP du PC (pas `localhost`) doit être saisie dans la section Config. La configuration est persistée en `SharedPreferences` entre les sessions.

### 9.5 Build et installation

```bash
cd application
./gradlew assembleDebug
# APK → app/build/outputs/apk/debug/app-debug.apk

# Installation directe
adb install app/build/outputs/apk/debug/app-debug.apk
# ou depuis l'IDE : Run → installDebug
```

---

## 10. État d'avancement

| Fonctionnalité | État | Détail |
|---|---|---|
| Protocole objet ⇄ passerelle bidirectionnel | ✅ | Radio + UART, event-driven |
| Chiffrement AES-128-CBC + appairage | ✅ | NRF_ECB matériel, IV NRF_RNG |
| Gestion multi-objets | ✅ | `user_controllers` + device_id matériel |
| Capteurs T / H / P | ✅ | BME280, oversampling ×16 |
| Capteur luminosité L | ✅ | Matrice LED comme photodiode |
| Affichage OLED dans l'ordre demandé | ✅ | Tous les cas T/H/L/P gérés |
| Passerelle relais radio ⇄ UART | ✅ | ~50 lignes, `release_fiber()` |
| Serveur UDP + SQLite + getValues() | ✅ | Throttle 10s, WAL mode |
| Format d'échange défini | ✅ | Pipe + JSON + CSV acceptés |
| App Android — config · CRUD · ordre · data · historique | ✅ | 5 sections Material3 |
| Sécurité passkeys PBKDF2 + rate-limit | ✅ | 200 000 itérations |
| 57 tests automatisés | ✅ | Unit + intégration + E2E |
| Interface web type Grafana | ❌ | Optionnel — non réalisé |
| Push automatique serveur → app | ❌ | Optionnel — rafraîchissement à la demande |

> [!success] Toutes les exigences **obligatoires** de l'énoncé sont couvertes.

---

## 11. Choix technologiques

| Brique | Choix | Justification |
|---|---|---|
| Objet / Passerelle | C/C++, micro:bit DAL, yotta | Accès direct NRF_ECB et NRF_RNG — impossible depuis MicroPython |
| Chiffrement | AES-128-CBC matériel (NRF_ECB) | Sécurité réelle, ~6 µs/bloc, pas de lib logicielle |
| IV | NRF_RNG (entropie matérielle) | Garantit l'imprévisibilité, pas de PRNG logiciel |
| Dérivation de clé | Zero-padding 16 octets | Simple à reproduire en compile-time sur le micro:bit |
| Serveur | Python 3 | Référence fournie dans l'énoncé, 3 dépendances seulement |
| Base de données | SQLite WAL | Sans serveur, fichier unique, agrégats SQL natifs |
| Passkeys | PBKDF2-SHA256 200k itér. | Standard industrie, résistance brute-force hors-ligne |
| Architecture serveur | DDD 4 couches | Testabilité par couche, séparation des responsabilités |
| Format radio → UART | Hex ASCII | Transmissible sur UART sans encodage supplémentaire |
| Application | Android natif Java | Contrôle fin des sockets UDP, pas de dépendance tierce |
| Transport app | UDP | Imposé par l'énoncé |

---

## 12. Livrables du rendu

| # | Livrable | Emplacement | Documentation |
|---|---|---|---|
| 1 | **Rapport synthétique** | `rendu.md` (ce document) | — |
| 2 | **Application Android** | `application/` | `application/README.md` |
| 3 | **Code de l'objet connecté** | `micro/` | `micro/README.md` · `micro/NOTES-TP.md` |
| 4 | **Code de la passerelle** | `gateway/microbit-samples/` | `gateway/microbit-samples/README.md` |
| 5 | **Application côté serveur** | `server/` | `server/README.md` |

> [!note] APK de démonstration
> L'APK de debug `bureau-bien-etre.apk` est disponible dans `application/` pour installation directe sans compilation (`adb install`).
