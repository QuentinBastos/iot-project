# Objet connecté — micro:bit (capteurs + OLED)

Code C/C++ de l'**objet connecté** de l'architecture IoT : une carte micro:bit installée
dans un bureau qui **mesure son environnement**, **émet les données par radio** (chiffrées)
et **affiche les valeurs sur un écran OLED** dans l'ordre demandé à distance.

> Côté chaîne IoT : `Objet ⇄ Passerelle ⇄ Serveur ⇄ App Android`.
> Voir le [rapport](../RAPPORT.md) pour l'architecture complète.
> Réponses aux questions du TP : [`NOTES-TP.md`](./NOTES-TP.md).

---

## Rôle dans l'architecture

À chaque cycle (toutes les 2 s), l'objet :

1. **Lit ses capteurs** : température, humidité, pression (BME280) et luminosité
   (matrice LED utilisée comme photodiode).
2. **Émet une trame chiffrée** par radio 2.4 GHz vers la passerelle.
3. **Met à jour l'écran OLED** avec les capteurs, dans l'ordre demandé par le serveur.

En parallèle, il **écoute la radio** pour recevoir les ordres d'affichage (`CONFIG`) qui
lui sont destinés, et au démarrage il envoie une trame d'**appairage** prouvant qu'il
connaît le secret partagé.

---

## Structure du code

```
source/
├── main.cpp        Orchestration : init, boucle de mesure/émission/affichage, réception radio, AES
├── bme280.cpp/.h   Pilote du capteur météo BME280 (température, humidité, pression) via I2C
├── ssd1306.cpp/.h  Pilote de l'écran OLED SSD1306 via I2C
├── nrf_ecb.c/.h    Chiffrement AES-128 matériel (périphérique NRF_ECB du nRF51)
└── font.h          Police de caractères pour le rendu texte sur l'OLED
```

| Fichier | Responsabilité |
|---|---|
| `main.cpp` | Initialise la radio, l'AES, les pilotes ; identifie la carte (`microbit_serial_number()`) ; boucle principale : lecture capteurs → trame chiffrée → OLED. Gère la réception des trames `CONFIG`. |
| `bme280.*` | Lecture des registres bruts du BME280 et fonctions de compensation (`compensate_temperature/humidity/pressure`). |
| `ssd1306.*` | Effacement, écriture de lignes de texte, rafraîchissement de l'écran OLED. |
| `nrf_ecb.*` | Accès au bloc matériel AES-128 ECB du nRF51 (`nrf_ecb_init / set_key / crypt`), utilisé comme primitive du mode CBC. |

---

## Capteurs

| Capteur | Source | Unité |
|---|---|---|
| Température | BME280 | °C (centièmes en interne) |
| Humidité | BME280 | % |
| Pression | BME280 | hPa |
| Luminosité | Matrice LED (`readLightLevel()`) | 0–255 |

Le BME280 et l'écran OLED partagent le **bus I2C** (`I2C_SDA0` / `I2C_SCL0`).

---

## Écran OLED

L'écran affiche un en-tête (`OBJET CONNECTE` + identifiant de la carte) puis les capteurs
**dans l'ordre exact** transmis par le serveur. L'ordre est une chaîne de codes :

| Code | Capteur |
|---|---|
| `T` | Température |
| `H` | Humidité |
| `L` | Luminosité |
| `P` | Pression |

Exemple : l'ordre `TLH` affiche température, puis luminosité, puis humidité.
Tout caractère inconnu est ignoré. L'ordre par défaut au démarrage est `T`.

---

## Protocole radio (objet ⇄ passerelle)

- **Groupe radio** : 1. **Taille de paquet** portée à 251 octets (`config.json`), Bluetooth désactivé.
- Le module radio n'inclut pas l'identité de l'émetteur : le **`device_id`**
  (identifiant matériel unique, en hexadécimal) est donc inséré dans chaque trame.

| Sens | Trame en clair | Sur la radio |
|---|---|---|
| Boot (appairage) | `PAIR\|<secret>\|<device_id>` | chiffrée AES-128-CBC, hex |
| Donnée capteur | `<device_id>\|T:25.3,H:42,L:147,P:999` | chiffrée AES-128-CBC, hex |
| Ordre d'affichage (reçu) | `<device_id>,CONFIG,<ordre>` | en clair (relais passerelle) |

### Chiffrement AES-128-CBC

- Primitive **AES-128 ECB matérielle** via `NRF_ECB`, composée en mode **CBC**.
- **IV aléatoire** par trame, généré par le périphérique matériel `NRF_RNG`.
- Padding **PKCS#7**, sortie `hex(IV ∥ ciphertext)` — ASCII pur, donc transmissible tel
  quel par la liaison série de la passerelle.
- Clé dérivée du **secret partagé** (identique côté objet et côté serveur).

> ⚠️ Le secret partagé et la clé AES sont définis en dur en haut de `main.cpp`
> (`SHARED_SECRET`, `AES_KEY`). Ils doivent correspondre à la configuration du serveur.

---

## Compilation et flash

Toolchain **yotta** (micro:bit DAL, cible `bbc-microbit-classic-gcc`).

```bash
# Compilation
yt build        # ou : make build

# Flash de la carte (le .hex est généré dans build/.../source/)
make install    # copie le .hex sur le volume MICROBIT
```

Sur macOS, le flash manuel se fait par copie :
```bash
cp build/bbc-microbit-classic-gcc/source/microbit-samples-combined.hex /Volumes/MICROBIT/
```

L'environnement de build (Docker / yotta) est décrit dans [`NOTES-TP.md`](./NOTES-TP.md).
