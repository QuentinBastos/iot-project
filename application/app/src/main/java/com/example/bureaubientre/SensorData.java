package com.example.bureaubientre;

public class SensorData {

    private final float temperature;
    private final float humidity;
    private final float luminosity;
    private final float pressure;

    public SensorData(float temperature, float humidity, float luminosity, float pressure) {
        this.temperature = temperature;
        this.humidity = humidity;
        this.luminosity = luminosity;
        this.pressure = pressure;
    }

    /**
     * Parse la reponse du serveur au format "controller,sensor,value\n..."
     * (un triplet par ligne). Les noms de capteurs acceptes (en majuscules) :
     *   T, TEMP, TEMPERATURE
     *   H, HUM, HUMIDITY, HUMIDITE
     *   L, LUM, LUMINOSITY, LUMINOSITE
     *   P, PRES, PRESSURE, PRESSION
     * Les valeurs absentes restent NaN.
     */
    public static SensorData parseMultiline(String raw) {
        float t = Float.NaN, h = Float.NaN, l = Float.NaN, p = Float.NaN;
        if (raw == null) return new SensorData(t, h, l, p);

        String[] lines = raw.split("\\r?\\n");
        for (String line : lines) {
            String trimmed = line.trim();
            if (trimmed.isEmpty()) continue;

            String[] parts = trimmed.split(",");
            if (parts.length < 3) continue;

            String sensorId = parts[parts.length - 2].trim().toUpperCase();
            String valueStr = parts[parts.length - 1].trim();

            float value;
            try {
                value = Float.parseFloat(valueStr);
            } catch (NumberFormatException e) {
                continue;
            }

            switch (sensorId) {
                case "T":
                case "TEMP":
                case "TEMPERATURE":
                    t = value;
                    break;
                case "H":
                case "HUM":
                case "HUMIDITY":
                case "HUMIDITE":
                    h = value;
                    break;
                case "L":
                case "LUM":
                case "LUMINOSITY":
                case "LUMINOSITE":
                    l = value;
                    break;
                case "P":
                case "PRES":
                case "PRESSURE":
                case "PRESSION":
                    p = value;
                    break;
            }
        }
        return new SensorData(t, h, l, p);
    }

    public float getTemperature() { return temperature; }
    public float getHumidity() { return humidity; }
    public float getLuminosity() { return luminosity; }
    public float getPressure() { return pressure; }

    public String formatTemperature() {
        return Float.isNaN(temperature) ? "--" : String.format("%.1f", temperature);
    }

    public String formatHumidity() {
        return Float.isNaN(humidity) ? "--" : String.format("%.1f", humidity);
    }

    public String formatLuminosity() {
        return Float.isNaN(luminosity) ? "--" : String.format("%.0f", luminosity);
    }

    public String formatPressure() {
        return Float.isNaN(pressure) ? "--" : String.format("%.1f", pressure);
    }
}
