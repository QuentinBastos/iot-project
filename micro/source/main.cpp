#include "MicroBit.h"
#include "ssd1306.h"
#include "bme280.h"

MicroBit uBit;
MicroBitI2C i2c(I2C_SDA0, I2C_SCL0);
MicroBitPin P0(MICROBIT_ID_IO_P0, MICROBIT_PIN_P0, PIN_CAPABILITY_DIGITAL_OUT);

// Secret partage micro:bit <-> serveur. Sert a la fois :
//   - a chiffrer chaque trame (XOR byte-a-byte) avant envoi radio
//   - a authentifier le device au pairing (PAIR|<SHARED_SECRET>|<id>)
// A maintenir identique cote serveur (argument --shared-secret).
static const char *SHARED_SECRET = "groupe67";
static const int   SHARED_SECRET_LEN = 8;

// Doit matcher le `setGroup()` de la passerelle (gateway/microbit-samples/source/main.cpp).
static const int RADIO_GROUP = 1;

// -----------------------------------------------------------------------------
// Helpers conversion / chiffrement
// -----------------------------------------------------------------------------

static ManagedString id_to_hex(uint32_t v) {
    char buf[12];
    snprintf(buf, sizeof(buf), "%lX", (unsigned long)v);
    return ManagedString(buf);
}

static ManagedString int_to_str(int v) {
    char buf[16];
    snprintf(buf, sizeof(buf), "%d", v);
    return ManagedString(buf);
}

/**
 * XOR de chaque octet avec le secret (cle repetee), puis encodage hexa.
 * Sortie purement ASCII [0-9A-F] -> traverse le lien serie sans probleme.
 */
static ManagedString encrypt_xor_hex(const ManagedString &plain) {
    static const char hex[] = "0123456789ABCDEF";
    int n = plain.length();
    if (n <= 0) return ManagedString("");

    char *buf = new char[n * 2 + 1];
    const char *p = plain.toCharArray();
    for (int i = 0; i < n; i++) {
        uint8_t c = (uint8_t)p[i] ^ (uint8_t)SHARED_SECRET[i % SHARED_SECRET_LEN];
        buf[2 * i]     = hex[(c >> 4) & 0xF];
        buf[2 * i + 1] = hex[c & 0xF];
    }
    buf[n * 2] = 0;
    ManagedString out(buf);
    delete[] buf;
    return out;
}

// -----------------------------------------------------------------------------
// Application
// -----------------------------------------------------------------------------

int main() {
    uBit.init();

    uBit.radio.setGroup(RADIO_GROUP);
    uBit.radio.enable();

    ssd1306 screen(&uBit, &i2c, &P0);
    bme280 bme(&uBit, &i2c);

    // ID unique du micro:bit (FICR DEVICEID[0]) -> base hexa compacte
    uint32_t serial_nr = microbit_serial_number();
    ManagedString device_id = id_to_hex(serial_nr);

    // 1. Pairing initial : "PAIR|<secret>|<id>"
    ManagedString pair_plain = ManagedString("PAIR|") + SHARED_SECRET
                               + ManagedString("|") + device_id;
    uBit.radio.datagram.send(encrypt_xor_hex(pair_plain));

    // Boucle d'emission des donnees capteurs
    uint32_t raw_pressure = 0;
    int32_t  raw_temp     = 0;
    uint16_t raw_humidity = 0;

    while (1) {
        bme.sensor_read(&raw_pressure, &raw_temp, &raw_humidity);

        int T_centi = bme.compensate_temperature(raw_temp);
        int H_centi = bme.compensate_humidity(raw_humidity);
        int P_hpa   = bme.compensate_pressure(raw_pressure) / 100;

        // 2. Format : "<id>|T:25.3,H:42,P:999"
        ManagedString payload =
            device_id + ManagedString("|")
            + ManagedString("T:") + int_to_str(T_centi / 100) + ManagedString(".") + int_to_str((T_centi % 100) / 10) + ManagedString(",")
            + ManagedString("H:") + int_to_str(H_centi / 100) + ManagedString(",")
            + ManagedString("P:") + int_to_str(P_hpa);

        ManagedString cipher = encrypt_xor_hex(payload);
        uBit.radio.datagram.send(cipher);

        // Visualisation locale
        screen.clear();
        screen.display_line(0, 0, "OBJET CONNECTE");
        screen.display_line(2, 0, "ID:");
        screen.display_line(3, 0, device_id.toCharArray());
        screen.display_line(5, 0, "ENC > gateway");
        screen.update_screen();

        uBit.sleep(2000);
    }

    release_fiber();
}
