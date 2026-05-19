# Passerelle — micro:bit USB (relais radio ⇄ série)

Code C/C++ de la **passerelle** de l'architecture IoT : une seconde carte micro:bit
reliée au PC en **USB**, qui fait le **pont transparent** entre le réseau radio des objets
connectés et le serveur.

> Côté chaîne IoT : `Objet ⇄ Passerelle ⇄ Serveur ⇄ App Android`.
> Voir le [rapport](../../RAPPORT.md) pour l'architecture complète.

---

## Rôle dans l'architecture

La passerelle ne contient **aucune logique métier** : c'est un **relais transparent**,
bidirectionnel, qui recopie les messages d'un médium vers l'autre sans les interpréter.

```
   Objet connecté                Passerelle (cette carte)              Serveur (PC)
   ──────────────                ────────────────────────             ────────────
   radio 2.4 GHz   ───────────►  onRadioReceive : radio → série  ───►  liaison série (UART/USB)
   radio 2.4 GHz   ◄───────────  onSerialReceive : série → radio ◄───  liaison série (UART/USB)
```

- **Radio → série** : toute trame radio reçue est réémise telle quelle sur la liaison
  série, suivie d'un `\n` (délimiteur de ligne attendu par le serveur).
- **Série → radio** : toute ligne reçue du PC (terminée par `\n`) est réémise telle quelle
  par radio vers les objets.

Les trames capteurs restent **chiffrées** de bout en bout (objet → serveur) : la passerelle
les transporte sans jamais les déchiffrer. Les ordres d'affichage `CONFIG` transitent en
clair.

---

## Structure du code

```
source/
└── main.cpp        Le relais complet : 2 écouteurs d'événements + initialisation
config.json         Configuration du DAL micro:bit (radio, Bluetooth)
Makefile            Cibles de build yotta
flash.sh            Script de flash de la carte
```

### `main.cpp`

| Élément | Rôle |
|---|---|
| `onRadioReceive()` | Déclenché à la réception d'un datagramme radio → `uBit.serial.send(message)` puis `"\n"`. |
| `onSerialReceive()` | Déclenché quand une ligne `\n` arrive sur la série → `uBit.radio.datagram.send(ligne)`. |
| `main()` | Initialise la radio (groupe 1), la série (115200 bauds, événement sur `\n`), et enregistre les deux écouteurs sur le `messageBus`. |

---

## Configuration radio / série

| Paramètre | Valeur | Pourquoi |
|---|---|---|
| Groupe radio | `1` | Identique à celui des objets connectés. |
| Débit série | `115200` bauds | Doit correspondre au `--baudrate` du serveur. |
| Délimiteur série | `\n` | Sépare les trames sur la liaison USB. |
| Bluetooth | désactivé (`config.json`) | Libère la pile pour la radio brute. |
| `radio_max_packet_size` | `251` (`config.json`) | Accueille les trames chiffrées (hex) plus longues. |

> La configuration radio et série de la passerelle **doit être cohérente** avec celle de
> l'objet connecté (`micro/`) et du serveur (`server/`).

---

## Compilation et flash

Toolchain **yotta** (micro:bit DAL, cible `bbc-microbit-classic-gcc`).

```bash
# Compilation
yt build

# Flash de la carte
./flash.sh
```

Le flash manuel se fait par copie du `.hex` généré sur le volume `MICROBIT` :
```bash
# Linux
cp build/bbc-microbit-classic-gcc/source/microbit-samples-combined.hex /media/$USER/MICROBIT/
# macOS
cp build/bbc-microbit-classic-gcc/source/microbit-samples-combined.hex /Volumes/MICROBIT/
```

Une fois flashée, brancher la passerelle en USB au PC et lancer le serveur en lui
indiquant le port série correspondant (`python main.py --serial_port …`).

---

> Le projet est basé sur le dépôt `microbit-samples` de Lancaster University ; seul
> `source/main.cpp` a été écrit pour le rôle de passerelle.
