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

/**
 * Protocole UDP avec le serveur (voir server/protocol/codec.py) :
 *   INIT,<passkey>                   -> enregistre l'utilisateur
 *   ADD,<passkey>,<sensor_id>        -> revendique un capteur
 *   GET,<passkey>                    -> demande les dernieres valeurs
 *   <controller_id>,CONFIG,<ordre>   -> ordre d'affichage OLED de l'objet
 * Reponse GET : "ctrl,sensor,value\n..." (multi-lignes).
 */
public class MainActivity extends AppCompatActivity {

    private static final String PREFS_NAME = "server_config";
    private static final String KEY_IP = "ip";
    private static final String KEY_PORT = "port";
    private static final String KEY_CONTROLLER = "controller_id";
    private static final String KEY_PASSKEY = "passkey";
    private static final int DEFAULT_PORT = 10000;

    // Identifiants de capteurs revendiques via ADD
    private static final String[] SENSOR_IDS = {"T", "H", "L", "P"};

    // Server config views
    private TextInputEditText editTextIp, editTextPort;
    private MaterialButton buttonConnect;
    private TextView textStatus;

    // Pairing views
    private TextInputEditText editTextPassword, editTextPasswordConfirm, editTextMac;
    private MaterialButton buttonInit;
    private TextView textPairingStatus;

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
    private String passkey = "";
    private String controllerId = "";
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
        editTextIp = findViewById(R.id.editTextIp);
        editTextPort = findViewById(R.id.editTextPort);
        buttonConnect = findViewById(R.id.buttonConnect);
        textStatus = findViewById(R.id.textStatus);

        editTextPassword = findViewById(R.id.editTextPassword);
        editTextPasswordConfirm = findViewById(R.id.editTextPasswordConfirm);
        editTextMac = findViewById(R.id.editTextMac);
        buttonInit = findViewById(R.id.buttonInit);
        textPairingStatus = findViewById(R.id.textPairingStatus);

        chipTemperature = findViewById(R.id.chipTemperature);
        chipHumidity = findViewById(R.id.chipHumidity);
        chipLuminosity = findViewById(R.id.chipLuminosity);
        chipPressure = findViewById(R.id.chipPressure);
        textDisplayOrder = findViewById(R.id.textDisplayOrder);
        buttonSendOrder = findViewById(R.id.buttonSendOrder);
        buttonResetOrder = findViewById(R.id.buttonResetOrder);

        textTemperature = findViewById(R.id.textTemperature);
        textHumidity = findViewById(R.id.textHumidity);
        textLuminosity = findViewById(R.id.textLuminosity);
        textPressure = findViewById(R.id.textPressure);
        textLastUpdate = findViewById(R.id.textLastUpdate);
        buttonGetData = findViewById(R.id.buttonGetData);

        chipMap.put("T", chipTemperature);
        chipMap.put("H", chipHumidity);
        chipMap.put("L", chipLuminosity);
        chipMap.put("P", chipPressure);
    }

    private void loadSavedConfig() {
        editTextIp.setText(prefs.getString(KEY_IP, ""));
        editTextPort.setText(String.valueOf(prefs.getInt(KEY_PORT, DEFAULT_PORT)));
        editTextMac.setText(prefs.getString(KEY_CONTROLLER, ""));
        passkey = prefs.getString(KEY_PASSKEY, "");
        controllerId = prefs.getString(KEY_CONTROLLER, "");
        if (!passkey.isEmpty() && !controllerId.isEmpty()) {
            textPairingStatus.setText(getString(R.string.status_paired, controllerId));
            textPairingStatus.setTextColor(getColor(R.color.status_connected));
        }
    }

    private void setupListeners() {
        buttonConnect.setOnClickListener(v -> toggleConnection());

        for (Map.Entry<String, Chip> entry : chipMap.entrySet()) {
            String letter = entry.getKey();
            Chip chip = entry.getValue();
            chip.setOnClickListener(v -> {
                if (chip.isChecked()) {
                    if (displayOrder.indexOf(letter) < 0) {
                        displayOrder.append(letter);
                        updateOrderDisplay();
                    }
                } else {
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
        buttonInit.setOnClickListener(v -> sendInit());
    }

    // ---- Connexion serveur ------------------------------------------------

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

        prefs.edit().putString(KEY_IP, ip).putInt(KEY_PORT, port).apply();
        udpClient = new UdpClient(ip, port);

        connected = true;
        buttonConnect.setText(R.string.btn_disconnect);
        textStatus.setText(getString(R.string.status_connected, ip, port));
        textStatus.setTextColor(getColor(R.color.status_connected));
        editTextIp.setEnabled(false);
        editTextPort.setEnabled(false);
    }

    private void disconnect() {
        udpClient = null;
        connected = false;
        buttonConnect.setText(R.string.btn_connect);
        textStatus.setText(R.string.status_disconnected);
        textStatus.setTextColor(getColor(R.color.status_disconnected));
        editTextIp.setEnabled(true);
        editTextPort.setEnabled(true);
    }

    // ---- Enregistrement / appairage --------------------------------------

    private void sendInit() {
        if (udpClient == null) {
            showSnackbar(getString(R.string.error_no_server));
            return;
        }

        String pwd = editTextPassword.getText() != null ? editTextPassword.getText().toString() : "";
        String pwdConfirm = editTextPasswordConfirm.getText() != null ? editTextPasswordConfirm.getText().toString() : "";
        String ctrl = editTextMac.getText() != null ? editTextMac.getText().toString().trim() : "";

        if (pwd.isEmpty()) {
            showSnackbar(getString(R.string.error_password_empty));
            return;
        }
        if (!pwd.equals(pwdConfirm)) {
            showSnackbar(getString(R.string.error_password_mismatch));
            return;
        }
        if (ctrl.isEmpty()) {
            showSnackbar(getString(R.string.error_mac_empty));
            return;
        }

        final String finalPwd = pwd;
        final String finalCtrl = ctrl;

        udpClient.sendAndReceive("INIT," + finalPwd, new UdpClient.DataCallback() {
            @Override
            public void onDataReceived(String data) {
                if (!data.trim().startsWith("OK")) {
                    showSnackbar(getString(R.string.error_server, data.trim()));
                    return;
                }
                passkey = finalPwd;
                controllerId = finalCtrl;
                prefs.edit()
                        .putString(KEY_PASSKEY, passkey)
                        .putString(KEY_CONTROLLER, controllerId)
                        .apply();
                textPairingStatus.setText(getString(R.string.status_paired, controllerId));
                textPairingStatus.setTextColor(getColor(R.color.status_connected));
                claimSensors(0);
            }

            @Override
            public void onError(String error) {
                showSnackbar(getString(R.string.error_send_failed, error));
            }
        });
    }

    /** Revendique sequentiellement les 4 capteurs via ADD,passkey,sensor_id. */
    private void claimSensors(int index) {
        if (index >= SENSOR_IDS.length) {
            showSnackbar(getString(R.string.success_init));
            return;
        }
        if (udpClient == null) return;

        String sensorId = SENSOR_IDS[index];
        udpClient.sendAndReceive("ADD," + passkey + "," + sensorId, new UdpClient.DataCallback() {
            @Override
            public void onDataReceived(String data) {
                // "OK" ou "ERROR: Sensor already claimed" — dans les deux cas on continue
                claimSensors(index + 1);
            }

            @Override
            public void onError(String error) {
                showSnackbar(getString(R.string.error_send_failed, error));
            }
        });
    }

    // ---- Ordre d'affichage OLED ------------------------------------------

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
        if (controllerId.isEmpty()) {
            showSnackbar(getString(R.string.error_mac_empty));
            return;
        }
        if (displayOrder.length() == 0) {
            showSnackbar(getString(R.string.error_empty_order));
            return;
        }

        String payload = controllerId + ",CONFIG," + displayOrder;
        udpClient.send(payload, new UdpClient.SendCallback() {
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

    // ---- Recuperation des donnees -----------------------------------------

    private void requestSensorData() {
        if (udpClient == null) {
            showSnackbar(getString(R.string.error_no_server));
            return;
        }
        if (passkey.isEmpty()) {
            showSnackbar(getString(R.string.error_no_passkey));
            return;
        }

        udpClient.sendAndReceive("GET," + passkey, new UdpClient.DataCallback() {
            @Override
            public void onDataReceived(String data) {
                String trimmed = data.trim();
                if (trimmed.startsWith("UNAUTHORIZED") || trimmed.startsWith("ERROR")
                        || trimmed.startsWith("No data")) {
                    showSnackbar(getString(R.string.error_server, trimmed));
                    return;
                }
                updateSensorDisplay(trimmed);
            }

            @Override
            public void onError(String error) {
                showSnackbar(getString(R.string.error_send_failed, error));
            }
        });
    }

    private void updateSensorDisplay(String rawData) {
        SensorData data = SensorData.parseMultiline(rawData);
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
}
