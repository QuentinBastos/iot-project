#include "MicroBit.h"
#include "nrf.h"
#include <string.h>
#include "ssd1306.h"
#include "bme280.h"

MicroBit uBit;
MicroBitI2C i2c(I2C_SDA0, I2C_SCL0);
MicroBitPin P0(MICROBIT_ID_IO_P0, MICROBIT_PIN_P0, PIN_CAPABILITY_DIGITAL_OUT);

// =============================================================================
//                             SECURITE
// =============================================================================
//
// Cle AES-128 partagee micro:bit <-> serveur.
// Derivation cote serveur : zero-padding/troncature du --shared-secret sur 16
// octets. Ici on embarque directement le resultat pour "groupe67" :
//     b"groupe67" + 8 octets nuls.
//
// Si la passkey cote serveur change, il faut mettre a jour cette table ET
// re-flasher le micro:bit.
static const uint8_t AES_KEY[16] = {
    'g','r','o','u','p','e','6','7',
    0, 0, 0, 0, 0, 0, 0, 0
};

// Meme valeur au format chaine, utilisee uniquement dans la trame "PAIR|..."
// pour que le serveur puisse verifier que le device connait bien le secret.
static const char *SHARED_SECRET = "groupe67";

// Doit matcher le setGroup() de la passerelle.
static const int RADIO_GROUP = 1;

// Tampon aligne 4 octets pour le peripheral ECB (obligatoire sur nRF51).
static uint8_t ecb_buf[48] __attribute__((aligned(4)));

// -----------------------------------------------------------------------------
// AES-128-ECB (chiffrement d'un bloc 16 octets) via le peripheral materiel.
// -----------------------------------------------------------------------------

static void aes128_ecb_encrypt_block(const uint8_t key[16],
                                     const uint8_t in[16],
                                     uint8_t out[16]) {
    memcpy(ecb_buf + 0,  key, 16);   // KEY
    memcpy(ecb_buf + 16, in,  16);   // CLEARTEXT

    NRF_ECB->ECBDATAPTR    = (uint32_t)ecb_buf;
    NRF_ECB->EVENTS_ENDECB = 0;
    NRF_ECB->TASKS_STARTECB = 1;
    while (NRF_ECB->EVENTS_ENDECB == 0) { /* spin ~7 cycles */ }
    NRF_ECB->EVENTS_ENDECB = 0;

    memcpy(out, ecb_buf + 32, 16);   // CIPHERTEXT
}

// -----------------------------------------------------------------------------
// IV aleatoire via le peripheral RNG materiel (nRF51).
// -----------------------------------------------------------------------------

static void random_iv(uint8_t iv[16]) {
    NRF_RNG->TASKS_START = 1;
    for (int i = 0; i < 16; i++) {
        NRF_RNG->EVENTS_VALRDY = 0;
        while (NRF_RNG->EVENTS_VALRDY == 0) { /* spin */ }
        iv[i] = (uint8_t)NRF_RNG->VALUE;
    }
    NRF_RNG->TASKS_STOP = 1;
}

// -----------------------------------------------------------------------------
// AES-128-CBC + PKCS7 + hex encode. Sortie = hex(IV || ciphertext).
// -----------------------------------------------------------------------------

static ManagedString aes_cbc_encrypt_hex(const ManagedString &plain) {
    static const char HEX[] = "0123456789ABCDEF";

    int n = plain.length();
    int pad = 16 - (n % 16);                 // 1..16 (PKCS7)
    int padded_len = n + pad;

    uint8_t *buf = new uint8_t[padded_len];
    memcpy(buf, plain.toCharArray(), n);
    for (int i = n; i < padded_len; i++) buf[i] = (uint8_t)pad;

    uint8_t iv[16];
    random_iv(iv);

    uint8_t prev[16];
    memcpy(prev, iv, 16);

    // CBC : on XOR chaque bloc avec le precedent avant chiffrement.
    for (int off = 0; off < padded_len; off += 16) {
        uint8_t block[16];
        for (int j = 0; j < 16; j++) block[j] = buf[off + j] ^ prev[j];
        aes128_ecb_encrypt_block(AES_KEY, block, buf + off);
        memcpy(prev, buf + off, 16);
    }

    // Sortie : hex(IV || ciphertext).
    int total = 16 + padded_len;
    char *hex = new char[total * 2 + 1];
    for (int i = 0; i < 16; i++) {
        hex[2*i]     = HEX[(iv[i] >> 4) & 0xF];
        hex[2*i + 1] = HEX[iv[i] & 0xF];
    }
    for (int i = 0; i < padded_len; i++) {
        hex[32 + 2*i]     = HEX[(buf[i] >> 4) & 0xF];
        hex[32 + 2*i + 1] = HEX[buf[i] & 0xF];
    }
    hex[total * 2] = 0;

    ManagedString result(hex);
    delete[] buf;
    delete[] hex;
    return result;
}

// -----------------------------------------------------------------------------
// Helpers conversion texte.
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

// =============================================================================
//                             APPLICATION
// =============================================================================

int main() {
    uBit.init();
    uBit.radio.setGroup(RADIO_GROUP);
    uBit.radio.enable();

    ssd1306 screen(&uBit, &i2c, &P0);
    bme280 bme(&uBit, &i2c);

    // ID unique du micro:bit (FICR DEVICEID[0]) en hex compact.
    uint32_t serial_nr = microbit_serial_number();
    ManagedString device_id = id_to_hex(serial_nr);

    // 1. Pairing initial : "PAIR|<secret>|<id>" chiffre AES-128-CBC.
    ManagedString pair_plain = ManagedString("PAIR|")
                               + SHARED_SECRET
                               + ManagedString("|")
                               + device_id;
    uBit.radio.datagram.send(aes_cbc_encrypt_hex(pair_plain));

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

        ManagedString cipher = aes_cbc_encrypt_hex(payload);
        uBit.radio.datagram.send(cipher);

        screen.clear();
        screen.display_line(0, 0, "OBJET CONNECTE");
        screen.display_line(2, 0, "ID:");
        screen.display_line(3, 0, device_id.toCharArray());
        screen.display_line(5, 0, "AES-128-CBC -> gw");
        screen.update_screen();

        uBit.sleep(2000);
    }

    release_fiber();
}
