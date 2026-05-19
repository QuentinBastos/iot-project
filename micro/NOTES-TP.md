# Notes de TP — Mise en œuvre micro:bit

> Réponses aux questions du TP, conservées ici pour mémoire. La documentation
> du **code de l'objet connecté** se trouve dans [`README.md`](./README.md).

## Exercice 1 — Choix de la carte

Quatre cartes étaient possibles : C8051F02x (SiliconLabs), Arduino Uno, STM32 (ST), micro:bit.

Le choix de la **micro:bit** (Nordic nRF52833 / ARM Cortex-M4) est privilégié pour l'IoT :
elle intègre nativement des capteurs (accéléromètre, magnétomètre), une matrice LED et une
connectivité Bluetooth/Radio, contrairement aux Arduino Uno (8 bits), C8051 (obsolète) ou
STM32 (plus complexe) — ce qui facilite un prototypage rapide sans câblage externe.

## Exercice 2 — Documentation technique

- micro:bit Tech Site (hardware) — guides simplifiés de la BBC.
- Nordic nRF52833 (CPU/Radio) et LSM303AGR (capteurs) — documentations exhaustives des
  fabricants (registres, électrique).
- Les fabricants fournissent la documentation complète ; la BBC propose des guides simplifiés.

Outils nécessaires pour passer du code source à un système fonctionnel :
- **Environnement** : Docker (image dédiée) + IDE (CLion ou VS Code avec Dev Containers).
- **Build** : `yotta` dans un environnement virtuel Python (`venv`).
- **Chaîne de compilation** : `arm-none-eabi-gcc`, `cmake`, `ninja`, `srecord`.

## Exercices 3 à 5

- Ex. 3 — LEDs fonctionnelles (flash du `.hex` sur le volume `MICROBIT`).
- Ex. 4 — Boutons fonctionnels, ajoutés dans `main.cpp`.
- Ex. 5 — Capteur de température fonctionnel
  (doc : <https://lancaster-university.github.io/microbit-docs/ubit/thermometer/>).

## Docker

```bash
docker pull schoumi/yotta:latest
docker run -it \
  -v "$PWD:/workspaces/microbit-samples" \
  schoumi/yotta:latest
```

Flash de la carte (macOS) :
```bash
cp build/bbc-microbit-classic-gcc/source/microbit-samples-combined.hex /Volumes/MICROBIT/
```
