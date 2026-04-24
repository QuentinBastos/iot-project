/*
The MIT License (MIT)

Copyright (c) 2016 British Broadcasting Corporation.
This software is provided by Lancaster University by arrangement with the BBC.

Permission is hereby granted, free of charge, to any person obtaining a
copy of this software and associated documentation files (the "Software"),
to deal in the Software without restriction, including without limitation
the rights to use, copy, modify, merge, publish, distribute, sublicense,
and/or sell copies of the Software, and to permit persons to whom the
Software is furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in
all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL
THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING
FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER
DEALINGS IN THE SOFTWARE.
*/

#include "MicroBit.h"

MicroBit uBit;

// Fonction déclenchée (comme un thread) à chaque réception de message Radio
void onRadioReceive(MicroBitEvent) {
    // Lecture du message envoyé par l'objet connecté
    ManagedString messageRadio = uBit.radio.datagram.recv();
    
    // Transfert des données brutes au serveur (PC) via la liaison série USB (UART)
    uBit.serial.send(messageRadio);
    
    // Ajout d'un saut de ligne pour faciliter la lecture côté script Python
    uBit.serial.send("\n"); 
}

// Fonction déclenchée à chaque réception de données depuis le PC (USB)
void onSerialReceive(MicroBitEvent) {
    // Lecture du message (ex: les lettres majuscules "TLH") envoyé par le PC
    // On lit jusqu'au saut de ligne de manière asynchrone
    ManagedString messageUSB = uBit.serial.readUntil("\n", ASYNC);
    
    // Transfert de l'ordre de configuration à l'objet via la Radio RF
    uBit.radio.datagram.send(messageUSB);
}

int main()
{
    // Initialisation globale de l'environnement micro:bit
    uBit.init();

    // 1. Configuration de la Radio (RF 2.4GHz)
    uBit.radio.enable();
    // ATTENTION : L'objet connecté et la passerelle doivent être sur le même groupe radio !
    // Groupe 67 = groupe alloué à notre équipe
    uBit.radio.setGroup(1);

    // 2. Configuration de la communication série (UART via USB)
    uBit.serial.baud(115200);
    // On indique à la carte de déclencher un événement à chaque fois qu'elle reçoit un '\n'
    uBit.serial.eventOn("\n"); 

    // 3. Enregistrement de nos écouteurs d'événements (qui remplacent tes threads)
    uBit.messageBus.listen(MICROBIT_ID_RADIO, MICROBIT_RADIO_EVT_DATAGRAM, onRadioReceive);
    uBit.messageBus.listen(MICROBIT_ID_SERIAL, MICROBIT_SERIAL_EVT_DELIM_MATCH, onSerialReceive);

    // 4. Libération de la tâche principale. 
    // Contrairement à un return 0;, release_fiber() endort le main() 
    // mais laisse le système d'événements tourner en arrière-plan à l'infini.
    release_fiber();
}