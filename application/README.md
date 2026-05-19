# Application Android — Contrôle de l'architecture IoT

Application Android native (Java, Material 3) qui sert de **télécommande et de tableau
de bord** pour l'architecture IoT du projet : elle configure le serveur, gère les objets
connectés, pilote l'affichage de leur écran OLED et consulte les données capteurs.

> Côté chaîne IoT : `App Android ⇄ Serveur ⇄ Passerelle ⇄ Objet`.
> Voir le [rapport](../RAPPORT.md) pour l'architecture complète.

---

## Rôle dans l'architecture

L'application est le point d'entrée de l'utilisateur. Elle dialogue **uniquement avec le
serveur**, en **UDP**, et ne connaît ni la passerelle ni les objets directement.

Deux fonctions principales :

1. **Télécommande** — l'utilisateur choisit l'ordre des capteurs à afficher sur l'écran
   OLED de l'objet ; l'ordre est transmis au serveur, qui le relaie jusqu'à l'objet.
2. **Écran de contrôle** — l'application demande au serveur les dernières valeurs des
   capteurs et leur historique, et les affiche.

---

## Structure du code

```
app/src/main/
├── java/com/example/bureaubientre/
│   ├── MainActivity.java   Écran unique : UI, configuration, gestion des objets, appels réseau
│   ├── UdpClient.java      Client UDP (envoi simple + envoi/réception) sur threads de fond
│   └── SensorData.java     Modèle des données capteurs + parsing de la réponse serveur
└── res/layout/
    └── activity_main.xml   Mise en page de l'écran principal
```

| Fichier | Responsabilité |
|---|---|
| `MainActivity.java` | Cycle de vie de l'écran, saisie de la configuration, listes déroulantes des objets, construction de l'ordre d'affichage, affichage des données et de l'historique. La configuration (IP, port, passkey, objet sélectionné) est persistée via `SharedPreferences` (`server_config`). |
| `UdpClient.java` | Encapsule les sockets UDP. `send()` envoie sans attendre de réponse ; `sendAndReceive()` envoie puis attend une réponse (timeout 5 s). Tout le réseau tourne sur un thread dédié, les *callbacks* reviennent sur le thread UI. |
| `SensorData.java` | Objet immuable (température, humidité, luminosité, pression). `parseMultiline()` transforme la réponse texte du serveur (`controller,capteur,valeur` par ligne) en objet ; les valeurs absentes restent `NaN`. |

---

## Protocole serveur (UDP)

L'application échange des trames texte avec le serveur (port `10000` par défaut).
Référence : `server/protocol/codec.py`.

| Commande envoyée | Rôle | Réponse |
|---|---|---|
| `INIT,<passkey>` | Enregistrement / connexion d'un utilisateur | `OK` / `ERROR` |
| `LIST,<passkey>` | Liste des objets associés à l'utilisateur | `ctrl1\nctrl2\n…` |
| `ADD,<passkey>,<controller_id>` | Associer un micro:bit à la passkey | `OK` / `UNAUTHORIZED` |
| `REMOVE,<passkey>,<controller_id>` | Dissocier un micro:bit (purge ses données) | `OK` / `ERROR` |
| `GET,<passkey>,<controller_id>` | Dernières valeurs des capteurs | `ctrl,capteur,valeur\n…` |
| `HISTORY,<passkey>,<controller_id>,<days>` | Statistiques journalières (moyenne / min / max) | lignes agrégées |
| `<controller_id>,CONFIG,<ordre>` | Ordre d'affichage OLED (ex. `TLH`) | diffusé vers l'objet |

---

## Fonctionnalités

- **Configuration serveur** — adresse IP, port, passkey (avec confirmation), bouton de connexion.
- **Gestion des objets** — liste déroulante des micro:bit de l'utilisateur ; ajout,
  suppression et rafraîchissement.
- **Ordre d'affichage OLED** — sélection des capteurs un par un pour construire l'ordre
  (T = température, H = humidité, L = luminosité, P = pression), puis envoi au serveur.
- **Données capteurs** — dernières valeurs de l'objet sélectionné.
- **Historique** — statistiques journalières (moyenne, min, max) de l'objet sélectionné.

---

## Compilation et exécution

### Prérequis
- Android Studio (ou le SDK Android en ligne de commande)
- `compileSdk` / `targetSdk` 36, `minSdk` 31 (Android 12+)

### Build
```bash
# APK de debug
./gradlew assembleDebug
# → app/build/outputs/apk/debug/app-debug.apk
```

### Installation sur un appareil
```bash
./gradlew installDebug
# ou
adb install app/build/outputs/apk/debug/app-debug.apk
```

### Permissions
L'application déclare `INTERNET` et `ACCESS_NETWORK_STATE` (voir `AndroidManifest.xml`).
Le téléphone et le PC serveur doivent être sur le **même réseau** ; renseigner l'**IP du
PC** (et non `localhost`) dans l'écran de configuration.

---

## Tests rapides sans serveur

On peut vérifier le parsing/réseau en simulant le serveur avec `ncat` :
```bash
# Sur le PC, en écoute UDP :
ncat -u -l 10000
```
puis lancer une action depuis l'application et observer la trame reçue.
