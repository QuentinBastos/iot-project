package com.example.bureaubientre;

import org.json.JSONException;
import org.json.JSONObject;

public class SensorData {

    private float temperature;
    private float humidity;
    private float luminosity;
    private float pressure;

    public SensorData(float temperature, float humidity, float luminosity, float pressure) {
        this.temperature = temperature;
        this.humidity = humidity;
        this.luminosity = luminosity;
        this.pressure = pressure;
    }

    public static SensorData parse(String raw) {
        float t = Float.NaN, h = Float.NaN, l = Float.NaN, p = Float.NaN;
        try {
            JSONObject json = new JSONObject(raw);
            if (json.has("T")) t = (float) json.getDouble("T");
            if (json.has("H")) h = (float) json.getDouble("H");
            if (json.has("L")) l = (float) json.getDouble("L");
            if (json.has("P")) p = (float) json.getDouble("P");
        } catch (JSONException e) {
            e.printStackTrace();
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
