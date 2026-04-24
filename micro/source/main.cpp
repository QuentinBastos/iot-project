#include "MicroBit.h"
#include "ssd1306.h"
#include "bme280.h"

MicroBit uBit;
MicroBitI2C i2c(I2C_SDA0, I2C_SCL0);
MicroBitPin P0(MICROBIT_ID_IO_P0, MICROBIT_PIN_P0, PIN_CAPABILITY_DIGITAL_OUT);

int main() {
    uBit.init();
    
    // --- CONFIGURATION RADIO ---
    uBit.radio.setGroup(1);
    uBit.radio.enable();
    
    ssd1306 screen(&uBit, &i2c, &P0);
    bme280 bme(&uBit, &i2c);

    uint32_t raw_pressure = 0;
    int32_t raw_temp = 0;
    uint16_t raw_humidity = 0;

    while(1) {
        // 1. Lecture de toutes les données du BME280
        bme.sensor_read(&raw_pressure, &raw_temp, &raw_humidity);

        // 2. Calcul des valeurs réelles compensées
        int T_centi = bme.compensate_temperature(raw_temp);
        int H_centi = bme.compensate_humidity(raw_humidity);
        int P_hpa = bme.compensate_pressure(raw_pressure) / 100;

        // 3. Construction du JSON (sans la luminosité)
        ManagedString json = "{";
        json = json + "\"T\":" + ManagedString(T_centi/100) + "." + ManagedString((T_centi%100)/10) + ", ";
        json = json + "\"H\":" + ManagedString(H_centi/100) + ", ";
        json = json + "\"P\":" + ManagedString(P_hpa);
        json = json + "}";
        
        // 4. Envoi Radio du JSON vers la passerelle
        uBit.radio.datagram.send(json);
        
        // 5. Affichage sur l'écran OLED
        screen.clear();
        screen.display_line(0, 0, "OBJET CONNECTE");
        screen.display_line(2, 0, "Donnees (JSON):");
        screen.display_line(4, 0, json.toCharArray());
        screen.update_screen();

        uBit.sleep(2000);
    }

    release_fiber();
}