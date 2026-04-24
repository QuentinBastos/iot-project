#include "MicroBit.h"
#include "nrf.h"
#include <string.h>
#include <stdio.h>

extern "C" {
#include "nrf_ecb.h"
}

#include "ssd1306.h"
#include "bme280.h"

MicroBit uBit;
MicroBitI2C i2c(I2C_SDA0, I2C_SCL0);
MicroBitPin P0(MICROBIT_ID_IO_P0, MICROBIT_PIN_P0, PIN_CAPABILITY_DIGITAL_OUT);

// =============================================================================
//                             SECURITE
// =============================================================================
//
// Cle AES-128 partagee micro:bit <-> serveur. Zero-padding du --shared-secret
// sur 16 octets : b"groupe67" + 8 octets nuls.
static const uint8_t AES_KEY[16] = {
    'g','r','o','u','p','e','6','7',
    0, 0, 0, 0, 0, 0, 0, 0
};

// Meme valeur au format chaine, utilisee uniquement dans la trame "PAIR|...".
static const char *SHARED_SECRET = "groupe67";

// Doit matcher le setGroup() de la passerelle.
static const int RADIO_GROUP = 1;

// =============================================================================
//                             ETAT PARTAGE
// =============================================================================
//
// Le listener radio et la boucle principale tournent sur le meme thread fiber :
// pas besoin de verrou, les acces sont serialises entre deux yields.

static ManagedString g_device_id;
static ManagedString g_display_order("T");  // ordre OLED courant (ex: "TLHP")

static int g_T_centi = 0;     // temperature * 100
static int g_H_centi = 0;     // humidite   * 100
static int g_P_hpa   = 0;     // pression en hPa
static int g_L_level = 0;     // luminosite 0..255 (LED matrix as photodiode)

// -----------------------------------------------------------------------------
// AES-128-ECB materiel via le HAL officiel du SDK Nordic
// (nrf_ecb_init / nrf_ecb_set_key / nrf_ecb_crypt).
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

// AES-128-CBC + PKCS7 + hex. Sortie = hex(IV || ciphertext), serial-safe.
static ManagedString aes_cbc_encrypt_hex(const ManagedString &plain) {
    static const char HEX[] = "0123456789ABCDEF";

    int n = plain.length();
    int pad = 16 - (n % 16);                 // PKCS7 : 1..16
    int padded_len = n + pad;

    uint8_t *buf = new uint8_t[padded_len];
    memcpy(buf, plain.toCharArray(), n);
    for (int i = n; i < padded_len; i++) buf[i] = (uint8_t)pad;

    uint8_t iv[16];
    random_iv(iv);

    uint8_t prev[16];
    memcpy(prev, iv, 16);

    for (int off = 0; off < padded_len; off += 16) {
        uint8_t block[16];
        for (int j = 0; j < 16; j++) block[j] = buf[off + j] ^ prev[j];
        nrf_ecb_crypt(buf + off, block);
        memcpy(prev, buf + off, 16);
    }

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
// Conversions texte.
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
//                             RECEPTION RADIO
// =============================================================================
//
// Format attendu, en clair (la passerelle relaie brut depuis UART) :
//     <device_id>,CONFIG,<ORDER>
// Exemple : "5E90D3CB,CONFIG,TLH".
// Les trames qui ne nous sont pas destinees ou qui ne matchent pas ce format
// (ex: trames AES chiffrees d'autres objets) sont ignorees silencieusement.

static void on_radio_receive(MicroBitEvent) {
    ManagedString msg = uBit.radio.datagram.recv();
    int n = msg.length();
    if (n == 0) return;

    const char *s = msg.toCharArray();

    // Trouver les deux virgules qui delimitent les 3 segments.
    int c1 = -1, c2 = -1;
    for (int i = 0; i < n; i++) {
        if (s[i] == ',') {
            if (c1 < 0) c1 = i;
            else if (c2 < 0) { c2 = i; break; }
        }
    }
    if (c1 < 0 || c2 < 0) return;

    // Segment du milieu doit valoir exactement "CONFIG".
    int mid_len = c2 - (c1 + 1);
    if (mid_len != 6 || strncmp(s + c1 + 1, "CONFIG", 6) != 0) return;

    // Segment de tete doit egaler notre device_id.
    const char *our_id = g_device_id.toCharArray();
    int our_id_len = (int)strlen(our_id);
    if (c1 != our_id_len || strncmp(s, our_id, our_id_len) != 0) return;

    // Segment de queue = nouvel ordre (on le stocke tel quel).
    int tail_len = n - (c2 + 1);
    if (tail_len <= 0 || tail_len > 8) return;  // borne defensive
    g_display_order = msg.substring(c2 + 1, tail_len);
}

// =============================================================================
//                             AFFICHAGE OLED
// =============================================================================

static void display_sensor_line(ssd1306 &screen, int line, char code) {
    char buf[32];
    switch (code) {
        case 'T':
            snprintf(buf, sizeof(buf), "T: %d.%d C",
                     g_T_centi / 100, (g_T_centi % 100) / 10);
            break;
        case 'H':
            snprintf(buf, sizeof(buf), "H: %d %%", g_H_centi / 100);
            break;
        case 'L':
            snprintf(buf, sizeof(buf), "L: %d lux", g_L_level);
            break;
        case 'P':
            snprintf(buf, sizeof(buf), "P: %d hPa", g_P_hpa);
            break;
        default:
            return;   // caractere inconnu dans l'ordre -> skip
    }
    screen.display_line(line, 0, buf);
}

// =============================================================================
//                             APPLICATION
// =============================================================================

int main() {
    uBit.init();
    uBit.radio.setGroup(RADIO_GROUP);
    uBit.radio.enable();

    // Listener radio : reception des commandes CONFIG envoyees par le serveur
    // a travers la passerelle.
    uBit.messageBus.listen(MICROBIT_ID_RADIO, MICROBIT_RADIO_EVT_DATAGRAM,
                           on_radio_receive);

    // Initialisation du peripheral AES.
    nrf_ecb_init();
    nrf_ecb_set_key(AES_KEY);

    ssd1306 screen(&uBit, &i2c, &P0);
    bme280 bme(&uBit, &i2c);

    uint32_t serial_nr = microbit_serial_number();
    g_device_id = id_to_hex(serial_nr);

    // 1. Pairing initial : "PAIR|<secret>|<id>" chiffre AES-128-CBC.
    ManagedString pair_plain = ManagedString("PAIR|")
                               + SHARED_SECRET
                               + ManagedString("|")
                               + g_device_id;
    uBit.radio.datagram.send(aes_cbc_encrypt_hex(pair_plain));

    uint32_t raw_pressure = 0;
    int32_t  raw_temp     = 0;
    uint16_t raw_humidity = 0;

    while (1) {
        // 1. Lecture des capteurs.
        bme.sensor_read(&raw_pressure, &raw_temp, &raw_humidity);
        g_T_centi  = bme.compensate_temperature(raw_temp);
        g_H_centi  = bme.compensate_humidity(raw_humidity);
        g_P_hpa    = bme.compensate_pressure(raw_pressure) / 100;
        // LED matrix utilisee comme photodiode (0..255). Ne gene pas l'OLED.
        g_L_level  = uBit.display.readLightLevel();

        // 2. Emission chiffree "<id>|T:..,H:..,L:..,P:.."
        ManagedString payload =
            g_device_id + ManagedString("|")
            + ManagedString("T:") + int_to_str(g_T_centi / 100) + ManagedString(".") + int_to_str((g_T_centi % 100) / 10) + ManagedString(",")
            + ManagedString("H:") + int_to_str(g_H_centi / 100) + ManagedString(",")
            + ManagedString("L:") + int_to_str(g_L_level) + ManagedString(",")
            + ManagedString("P:") + int_to_str(g_P_hpa);

        uBit.radio.datagram.send(aes_cbc_encrypt_hex(payload));

        // 3. Affichage OLED selon l'ordre courant (controle par le serveur).
        screen.clear();
        screen.display_line(0, 0, "OBJET CONNECTE");
        screen.display_line(1, 0, g_device_id.toCharArray());

        const char *order = g_display_order.toCharArray();
        int order_len = g_display_order.length();
        int oled_line = 3;
        for (int i = 0; i < order_len && oled_line < 8; i++) {
            display_sensor_line(screen, oled_line, order[i]);
            oled_line++;
        }
        screen.update_screen();

        uBit.sleep(2000);
    }

    release_fiber();
}
