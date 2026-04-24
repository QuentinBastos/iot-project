# microbit-samples
## Réponse : 

### Exercice 1

Dans le cas de ce TP, quatre choix étaient possibles.

Utiliser des cartes C8051F02x de SiliconLabs.
Utiliser des cartes Arduino Uno.
Utiliser des cartes STM32 de ST Micro-electronics.
Utiliser des cartes Micro:bit
Question 1 :

Recherchez les caractéristiques des diverses cartes en question et les micro-contrôleurs utilisés par chacune d’entre elles.
Réponse :

Le choix de la Micro:bit (basée sur un Nordic nRF52833 / ARM Cortex-M4) est privilégié pour l'IoT car elle intègre nativement des capteurs (accéléromètre, magnétomètre), une matrice LED et une connectivité Bluetooth/Radio, contrairement aux cartes Arduino Uno (8-bit), C8051 (obsolète) ou STM32 (plus complexe), facilitant ainsi un prototypage rapide sans câblage externe.

### Exercice 2

Question 2 :

Recherchez les différentes documentations techniques pour la carte Micro:bit et de ses composants. Est-ce que le site du distributeur (BBC) propose des documentations plus complètes que ceux des fabricants ?
Réponse :

Micro:bit Tech Site (Hardware)
Nordic nRF52833 (CPU/Radio)
LSM303AGR (Capteurs)
Non, les fabricants (Nordic/ST) fournissent les documentations exhaustives (registres, électrique), tandis que la BBC propose des guides simplifiés.

Question 3 :

Quels sont les outils dont vous aurez besoin pour passer de votre code source à un système fonctionnant avec la carte Micro:bit ?
Réponse :

Environnement : Docker (image dédiée) et un IDE (CLion ou VS Code avec Dev Containers).
Gestionnaire de build : yotta installé dans un environnement virtuel Python (venv).
Chaîne de compilation : arm-none-eabi-gcc, cmake, ninja et srecord.
Configuration : Des correctifs sed sur les templates yotta pour assurer la compatibilité avec CMake 3.0+.

### Exercice 3 :
Leds fonctionnel avec : cp build/bbc-microbit-classic-gcc/source/microbit-samples-combined.hex /Volumes/MICROBIT/ sur MACOS.

### Exercice 4 : 

Fait buttons fonctionnel et ajouté dans le main.cpp

### Exercie 5 :

Capteur de température fonctionnel et ajouté dans le main.cpp
- Doc dispo dans https://lancaster-university.github.io/microbit-docs/ubit/thermometer/

### Exercice 6 : 



## Docker
Pour docker, il faut pull https://github.com/carlosperate/docker-microbit-toolchain en faisant :
- docker pull schoumi/yotta:latest
- docker run -it \
  -v "/Users/quentinbastos/Desktop/cours/iot/iot-a3/microbit-samples:/workspaces/microbit-samples" \
  schoumi/yotta:latest

Pour flasher la carte, il faut faire : (remplacer le PATH par le $USER)

- cp build/bbc-microbit-classic-gcc/source/microbit-samples-combined.hex /Volumes/MICROBIT/

- A collection of example programs using the micro:bit runtime.

The source/examples folder contains a selection of samples demonstrating the capabilities and usage of the runtime APIs.
To select a sample, simply copy the .cpp files from the relevant folder into the source/ folder.

e.g. to select the "invaders" example:

```
cp source/examples/invaders/* source
```

and then to compile your sample:

```
yt clean
yt build
```

The HEX file for you micro:bit with then be generated and stored in build\bbc-microbit-classic-gcc\source\microbit-samples-combined.hex

n.b. Any samples using the low level RADIO APIs (such as simple-radio-rx and simple-radio-tx) require the bluetooth capabilities of the
micro:bit to be disabled. To do this, simply copy the config.json file from the sample to the top level of your project. Don't forget to
remove this file again later if you then want to use Bluetooth! For example:


```
cp source/examples/simple-radio-rx/config.json .
```


## Overview

The micro:bit runtime provides an easy to use environment for programming the BBC micro:bit in the C/C++ language, written by Lancaster University. It contains device drivers for all the hardware capabilities of the micro:bit, and also a suite of runtime mechanisms to make programming the micro:bit easier and more flexible. These range from control of the LED matrix display to peer-to-peer radio communication and secure Bluetooth Low Energy services. The micro:bit runtime is proudly built on the ARM mbed and Nordic nrf51 platforms.

In addition to supporting development in C/C++, the runtime is also designed specifically to support higher level languages provided by our partners that target the micro:bit. It is currently used as a support library for all the languages on the BBC www.microbit.co.uk website, including Microsoft Block, Microsoft TouchDevelop, Code Kingdoms JavaScript and Micropython languages.

## Links

[micro:bit runtime docs](http://lancaster-university.github.io/microbit-docs/) | [microbit-dal](https://github.com/lancaster-university/microbit-dal) |  [uBit](https://github.com/lancaster-university/microbit)

## Build Environments

| Build Environment | Documentation |
| ------------- |-------------|
| ARM mbed online | http://lancaster-university.github.io/microbit-docs/online-toolchains/#mbed |
| yotta  | http://lancaster-university.github.io/microbit-docs/offline-toolchains/#yotta |

##  microbit-dal Configuration

The DAL also contains a number of compile time options can be modified. A full list and explanation
can be found in our [documentation](http://lancaster-university.github.io/microbit-docs/advanced/#compile-time-options-with-microbitconfigh).

Alternately, `yotta` can be used to configure the dal regardless of module/folder structure, through providing a
`config.json` in this directory.

Here is an example of `config.json` with all available options configured:
```json
{
    "microbit-dal":{
        "bluetooth":{
            "enabled": 1,
            "pairing_mode": 1,
            "private_addressing": 0,
            "open": 0,
            "whitelist": 1,
            "advertising_timeout": 0,
            "tx_power": 0,
            "dfu_service": 1,
            "event_service": 1,
            "device_info_service": 1
        },
        "reuse_sd": 1,
        "default_pullmode":"PullDown",
        "gatt_table_size": "0x300",
        "heap_allocator": 1,
        "nested_heap_proportion": 0.75,
        "system_tick_period": 6,
        "system_components": 10,
        "idle_components": 6,
        "use_accel_lsb": 0,
        "min_display_brightness": 1,
        "max_display_brightness": 255,
        "display_scroll_speed": 120,
        "display_scroll_stride": -1,
        "display_print_speed": 400,
        "panic_on_heap_full": 1,
        "debug": 0,
        "heap_debug": 0,
        "stack_size":2048,
        "sram_base":"0x20000008",
        "sram_end":"0x20004000",
        "sd_limit":"0x20002000",
        "gatt_table_start":"0x20001900"
        "radio_max_packet_size":248,
        "radio_max_rx_buffers":4
    }
}
```
##  Debug on Visual Studio Code (Windows)

1. build sample. You can build "HELLO WORLD! :)" program.
2. Copy microbit-samples\build\bbc-microbit-classic-gcc\source\microbit-samples-combined.hex to micro:bit.
3. Launch the Visual Studio Code
4. File -> Open Folder... and select "microbit-samples" folder.
5. Set break point to "main()" function.
6. View -> Debug (Ctrl + Shift + D)
7. Debug -> Start Debugging (F5)

![Debug on Visual Studio Code](/debugOnVisualStudioCode.gif)

## BBC Community Guidelines

[BBC Community Guidelines](https://www.microbit.co.uk/help#sect_cg)
