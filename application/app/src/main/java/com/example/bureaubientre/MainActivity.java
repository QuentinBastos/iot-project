package com.example.bureaubientre;

import android.content.SharedPreferences;
import android.os.Bundle;
import android.widget.TextView;

import androidx.activity.EdgeToEdge;
import androidx.appcompat.app.AppCompatActivity;
import androidx.core.graphics.Insets;
import androidx.core.view.ViewCompat;
import androidx.core.view.WindowInsetsCompat;

import com.google.android.material.button.MaterialButton;
import com.google.android.material.chip.Chip;
import com.google.android.material.snackbar.Snackbar;
import com.google.android.material.textfield.TextInputEditText;

import java.text.SimpleDateFormat;
import java.util.Date;
import java.util.LinkedHashMap;
import java.util.Locale;
import java.util.Map;

public class MainActivity extends AppCompatActivity {

    private static final String PREFS_NAME = "server_config";
    private static final String KEY_IP = "ip";
    private static final String KEY_PORT = "port";
    private static final int DEFAULT_PORT = 10000;
    private static final int LISTEN_PORT = 10001;

    // Server config views
    private TextInputEditText editTextIp;
    private TextInputEditText editTextPort;
    private MaterialButton buttonConnect;
    private TextView textStatus;

    // Display order views
    private Chip chipTemperature, chipHumidity, chipLuminosity, chipPressure;
    private TextView textDisplayOrder;
    private MaterialButton buttonSendOrder, buttonResetOrder;

    // Sensor data views
    private TextView textTemperature, textHumidity, textLuminosity, textPressure;
    private TextView textLastUpdate;
    private MaterialButton buttonGetData;

    // State
    private final StringBuilder displayOrder = new StringBuilder();
    private final Map<String, Chip> chipMap = new LinkedHashMap<>();
    private UdpClient udpClient;
    private boolean connected = false;
    private SharedPreferences prefs;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        EdgeToEdge.enable(this);
        setContentView(R.layout.activity_main);
        ViewCompat.setOnApplyWindowInsetsListener(findViewById(R.id.main), (v, insets) -> {
            Insets systemBars = insets.getInsets(WindowInsetsCompat.Type.systemBars());
            v.setPadding(systemBars.left, systemBars.top, systemBars.right, systemBars.bottom);
            return insets;
        });

        prefs = getSharedPreferences(PREFS_NAME, MODE_PRIVATE);
        initViews();
        loadSavedConfig();
        setupListeners();
    }

    private void initViews() {
        // Server config
        editTextIp = findViewById(R.id.editTextIp);
        editTextPort = findViewById(R.id.editTextPort);
        buttonConnect = findViewById(R.id.buttonConnect);
        textStatus = findViewById(R.id.textStatus);

        // Display order
        chipTemperature = findViewById(R.id.chipTemperature);
        chipHumidity = findViewById(R.id.chipHumidity);
        chipLuminosity = findViewById(R.id.chipLuminosity);
        chipPressure = findViewById(R.id.chipPressure);
        textDisplayOrder = findViewById(R.id.textDisplayOrder);
        buttonSendOrder = findViewById(R.id.buttonSendOrder);
        buttonResetOrder = findViewById(R.id.buttonResetOrder);

        // Sensor data
        textTemperature = findViewById(R.id.textTemperature);
        textHumidity = findViewById(R.id.textHumidity);
        textLuminosity = findViewById(R.id.textLuminosity);
        textPressure = findViewById(R.id.textPressure);
        textLastUpdate = findViewById(R.id.textLastUpdate);
        buttonGetData = findViewById(R.id.buttonGetData);

        // Map sensor letters to chips
        chipMap.put("T", chipTemperature);
        chipMap.put("H", chipHumidity);
        chipMap.put("L", chipLuminosity);
        chipMap.put("P", chipPressure);
    }

    private void loadSavedConfig() {
        String savedIp = prefs.getString(KEY_IP, "");
        int savedPort = prefs.getInt(KEY_PORT, DEFAULT_PORT);
        editTextIp.setText(savedIp);
        editTextPort.setText(String.valueOf(savedPort));
    }

    private void setupListeners() {
        buttonConnect.setOnClickListener(v -> toggleConnection());

        // Chip tap listeners — build display order by tap sequence
        for (Map.Entry<String, Chip> entry : chipMap.entrySet()) {
            String letter = entry.getKey();
            Chip chip = entry.getValue();
            chip.setOnClickListener(v -> {
                if (chip.isChecked()) {
                    // Chip was just checked — add to order
                    if (!displayOrder.toString().contains(letter)) {
                        displayOrder.append(letter);
                        updateOrderDisplay();
                    }
                } else {
                    // Chip was unchecked — remove from order
                    int idx = displayOrder.indexOf(letter);
                    if (idx >= 0) {
                        displayOrder.deleteCharAt(idx);
                        updateOrderDisplay();
                    }
                }
            });
        }

        buttonResetOrder.setOnClickListener(v -> resetOrder());
        buttonSendOrder.setOnClickListener(v -> sendDisplayOrder());
        buttonGetData.setOnClickListener(v -> requestSensorData());
    }

    private void toggleConnection() {
        if (connected) {
            disconnect();
        } else {
            connect();
        }
    }

    private void connect() {
        String ip = editTextIp.getText() != null ? editTextIp.getText().toString().trim() : "";
        String portStr = editTextPort.getText() != null ? editTextPort.getText().toString().trim() : "";

        if (ip.isEmpty()) {
            showSnackbar(getString(R.string.error_no_server));
            return;
        }

        int port;
        try {
            port = Integer.parseInt(portStr);
            if (port < 1 || port > 65535) throw new NumberFormatException();
        } catch (NumberFormatException e) {
            showSnackbar("Port invalide (1-65535)");
            return;
        }

        // Save config
        prefs.edit().putString(KEY_IP, ip).putInt(KEY_PORT, port).apply();

        // Create UDP client and start listening
        if (udpClient != null) {
            udpClient.stopListening();
        }
        udpClient = new UdpClient(ip, port);
        udpClient.startListening(LISTEN_PORT, new UdpClient.DataCallback() {
            @Override
            public void onDataReceived(String data) {
                updateSensorDisplay(data);
            }

            @Override
            public void onError(String error) {
                // Listener error — non-fatal, just log
            }
        });

        connected = true;
        buttonConnect.setText(R.string.btn_disconnect);
        textStatus.setText(getString(R.string.status_connected, ip, port));
        textStatus.setTextColor(getColor(R.color.status_connected));

        // Disable IP/port editing while connected
        editTextIp.setEnabled(false);
        editTextPort.setEnabled(false);
    }

    private void disconnect() {
        if (udpClient != null) {
            udpClient.stopListening();
            udpClient = null;
        }

        connected = false;
        buttonConnect.setText(R.string.btn_connect);
        textStatus.setText(R.string.status_disconnected);
        textStatus.setTextColor(getColor(R.color.status_disconnected));

        editTextIp.setEnabled(true);
        editTextPort.setEnabled(true);
    }

    private void updateOrderDisplay() {
        if (displayOrder.length() == 0) {
            textDisplayOrder.setText(R.string.label_order_empty);
        } else {
            textDisplayOrder.setText(getString(R.string.label_order, displayOrder.toString()));
        }
    }

    private void resetOrder() {
        displayOrder.setLength(0);
        for (Chip chip : chipMap.values()) {
            chip.setChecked(false);
        }
        updateOrderDisplay();
    }

    private void sendDisplayOrder() {
        if (udpClient == null) {
            showSnackbar(getString(R.string.error_no_server));
            return;
        }
        if (displayOrder.length() == 0) {
            showSnackbar(getString(R.string.error_empty_order));
            return;
        }

        udpClient.send(displayOrder.toString(), new UdpClient.SendCallback() {
            @Override
            public void onSuccess() {
                showSnackbar(getString(R.string.success_send));
            }

            @Override
            public void onError(String error) {
                showSnackbar(getString(R.string.error_send_failed, error));
            }
        });
    }

    private void requestSensorData() {
        if (udpClient == null) {
            showSnackbar(getString(R.string.error_no_server));
            return;
        }

        udpClient.requestData(new UdpClient.DataCallback() {
            @Override
            public void onDataReceived(String data) {
                updateSensorDisplay(data);
            }

            @Override
            public void onError(String error) {
                showSnackbar(getString(R.string.error_send_failed, error));
            }
        });
    }

    private void updateSensorDisplay(String rawData) {
        SensorData data = SensorData.parse(rawData);
        textTemperature.setText(data.formatTemperature());
        textHumidity.setText(data.formatHumidity());
        textLuminosity.setText(data.formatLuminosity());
        textPressure.setText(data.formatPressure());

        String time = new SimpleDateFormat("HH:mm:ss", Locale.getDefault()).format(new Date());
        textLastUpdate.setText(getString(R.string.last_update, time));
    }

    private void showSnackbar(String message) {
        Snackbar.make(findViewById(R.id.main), message, Snackbar.LENGTH_SHORT).show();
    }

    @Override
    protected void onDestroy() {
        super.onDestroy();
        if (udpClient != null) {
            udpClient.stopListening();
        }
    }
}
