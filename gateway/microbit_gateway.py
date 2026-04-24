# Gateway micro:bit — MicroPython
# Relaie les paquets radio (groupe 67) depuis/vers l'ordinateur hote via USB serie.
#
# Protocole serie (lignes terminees par \n) :
#   RX:<payload>       paquet recu via radio, envoye vers l'hote
#   TX:<payload>       ligne recue de l'hote, a reemettre via radio

from microbit import uart, display, Image
import radio

RADIO_GROUP = 67

radio.on()
radio.config(group=RADIO_GROUP, length=251, queue=6)
uart.init(baudrate=115200)

display.show(Image.YES)

_tx_buffer = b""


def _flush_tx(line):
    # strip "TX:" prefix and any trailing CR/LF
    payload = line[3:].rstrip()
    if payload:
        try:
            radio.send(payload)
        except Exception:
            pass


while True:
    # 1. Radio -> serie
    msg = radio.receive()
    if msg is not None:
        uart.write("RX:" + msg + "\n")

    # 2. Serie -> radio (non bloquant, assemblage par ligne)
    if uart.any():
        chunk = uart.read()
        if chunk:
            _tx_buffer += chunk
            while b"\n" in _tx_buffer:
                line, _tx_buffer = _tx_buffer.split(b"\n", 1)
                try:
                    text = line.decode("utf-8")
                except Exception:
                    continue
                if text.startswith("TX:"):
                    _flush_tx(text)
