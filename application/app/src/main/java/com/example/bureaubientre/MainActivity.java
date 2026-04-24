package com.example.bureaubientre;

import android.content.SharedPreferences;
import android.os.Bundle;
import android.view.View;
import android.widget.AdapterView;
import android.widget.ArrayAdapter;
import android.widget.Spinner;
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
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Date;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;

/**
 * Protocole UDP avec le serveur (voir server/protocol/codec.py) :
 *   INIT,<passkey>                           enregistre / login
 *   LIST,<passkey>                           liste des controllers de l'utilisateur
 *   ADD,<passkey>,<controller_id>            revendique un micro:bit
 *   REMOVE,<passkey>,<controller_id>         libere un micro:bit + purge data
 *   GET,<passkey>,<controller_id>            donnees du micro:bit selectionne
 *   <controller_id>,CONFIG,<ordre>           ordre d'affichage OLED
 * Reponse LIST : "ctrl1\nctrl2\n..."
 * Reponse GET  : "ctrl,sensor,value\n..." (multi-lignes).
 */
public class MainActivity extends AppCompatActivity {

    private static final String PREFS_NAME = "server_config";
    private static final String KEY_IP = "ip";
    private static final String KEY_PORT = "port";
    private static final String KEY_PASSKEY = "passkey";
    private static final String KEY_SELECTED_CONTROLLER = "selected_controller";
    private static final int DEFAULT_PORT = 10000;

    // Server config views
    private TextInputEditText editTextIp, editTextPort;
    private TextInputEditText editTextPassword, editTextPasswordConfirm;
    private MaterialButton buttonConnect;
    private TextView textStatus;

    // Controllers views
    private Spinner spinnerControllers;
    private TextView textControllersStatus;
    private TextInputEditText editTextControllerId;
    private MaterialButton buttonAddController, buttonRemoveController, buttonRefreshControllers;

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
    private final List<String> controllers = new ArrayList<>();
    private ArrayAdapter<String> controllersAdapter;
    private UdpClient udpClient;
    private boolean connected = false;
    private String passkey = "";
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
        setupControllersSpinner();
        loadSavedConfig();
        setupListeners();
    }

    private void initViews() {
        editTextIp = findViewById(R.id.editTextIp);
        editTextPort = findViewById(R.id.editTextPort);
        editTextPassword = findViewById(R.id.editTextPassword);
        editTextPasswordConfirm = findViewById(R.id.editTextPasswordConfirm);
        buttonConnect = findViewById(R.id.buttonConnect);
        textStatus = findViewById(R.id.textStatus);

        spinnerControllers = findViewById(R.id.spinnerControllers);
        textControllersStatus = findViewById(R.id.textControllersStatus);
        editTextControllerId = findViewById(R.id.editTextControllerId);
        buttonAddController = findViewById(R.id.buttonAddController);
        buttonRemoveController = findViewById(R.id.buttonRemoveController);
        buttonRefreshControllers = findViewById(R.id.buttonRefreshControllers);

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

    private void setupControllersSpinner() {
        controllersAdapter = new ArrayAdapter<>(this, android.R.layout.simple_spinner_item, controllers);
        controllersAdapter.setDropDownViewResource(android.R.layout.simple_spinner_dropdown_item);
        spinnerControllers.setAdapter(controllersAdapter);
        spinnerControllers.setOnItemSelectedListener(new AdapterView.OnItemSelectedListener() {
            @Override
            public void onItemSelected(AdapterView<?> parent, View view, int pos, long id) {
                String selected = (String) parent.getItemAtPosition(pos);
                if (selected != null) {
                    prefs.edit().putString(KEY_SELECTED_CONTROLLER, selected).apply();
                }
            }

            @Override
            public void onNothingSelected(AdapterView<?> parent) { }
        });
    }

    private void loadSavedConfig() {
        editTextIp.setText(prefs.getString(KEY_IP, ""));
        editTextPort.setText(String.valueOf(prefs.getInt(KEY_PORT, DEFAULT_PORT)));
        passkey = prefs.getString(KEY_PASSKEY, "");
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

        buttonAddController.setOnClickListener(v -> addController());
        buttonRemoveController.setOnClickListener(v -> removeController());
        buttonRefreshControllers.setOnClickListener(v -> refreshControllers());
    }

    // ---- Connexion serveur + auto-register --------------------------------

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
        String pwd = editTextPassword.getText() != null ? editTextPassword.getText().toString() : "";
        String pwdConfirm = editTextPasswordConfirm.getText() != null ? editTextPasswordConfirm.getText().toString() : "";

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

        if (pwd.isEmpty()) {
            showSnackbar(getString(R.string.error_password_empty));
            return;
        }
        if (!pwd.equals(pwdConfirm)) {
            showSnackbar(getString(R.string.error_password_mismatch));
            return;
        }

        prefs.edit().putString(KEY_IP, ip).putInt(KEY_PORT, port).apply();
        udpClient = new UdpClient(ip, port);

        final String finalPwd = pwd;
        final String finalIp = ip;
        final int finalPort = port;

        udpClient.sendAndReceive("INIT," + finalPwd, new UdpClient.DataCallback() {
            @Override
            public void onDataReceived(String data) {
                if (!data.trim().startsWith("OK")) {
                    showSnackbar(getString(R.string.error_server, data.trim()));
                    return;
                }
                passkey = finalPwd;
                prefs.edit().putString(KEY_PASSKEY, passkey).apply();

                connected = true;
                buttonConnect.setText(R.string.btn_disconnect);
                textStatus.setText(getString(R.string.status_connected, finalIp, finalPort));
                textStatus.setTextColor(getColor(R.color.status_connected));
                editTextIp.setEnabled(false);
                editTextPort.setEnabled(false);
                editTextPassword.setEnabled(false);
                editTextPasswordConfirm.setEnabled(false);

                refreshControllers();
            }

            @Override
            public void onError(String error) {
                showSnackbar(getString(R.string.error_send_failed, error));
            }
        });
    }

    private void disconnect() {
        udpClient = null;
        connected = false;
        buttonConnect.setText(R.string.btn_connect);
        textStatus.setText(R.string.status_disconnected);
        textStatus.setTextColor(getColor(R.color.status_disconnected));
        editTextIp.setEnabled(true);
        editTextPort.setEnabled(true);
        editTextPassword.setEnabled(true);
        editTextPasswordConfirm.setEnabled(true);

        controllers.clear();
        controllersAdapter.notifyDataSetChanged();
        textControllersStatus.setText(R.string.label_no_controllers);
    }

    // ---- Gestion des controllers ------------------------------------------

    private void refreshControllers() {
        if (udpClient == null || passkey.isEmpty()) return;

        udpClient.sendAndReceive("LIST," + passkey, new UdpClient.DataCallback() {
            @Override
            public void onDataReceived(String data) {
                String trimmed = data.trim();
                if (trimmed.startsWith("UNAUTHORIZED") || trimmed.startsWith("ERROR")) {
                    showSnackbar(getString(R.string.error_server, trimmed));
                    return;
                }
                controllers.clear();
                if (!trimmed.isEmpty()) {
                    controllers.addAll(Arrays.asList(trimmed.split("\\r?\\n")));
                }
                controllersAdapter.notifyDataSetChanged();

                if (controllers.isEmpty()) {
                    textControllersStatus.setText(R.string.label_no_controllers);
                } else {
                    textControllersStatus.setText(getString(R.string.status_controllers_count, controllers.size()));
                    // Restore previously selected controller if present
                    String last = prefs.getString(KEY_SELECTED_CONTROLLER, null);
                    int idx = last != null ? controllers.indexOf(last) : -1;
                    spinnerControllers.setSelection(idx >= 0 ? idx : 0);
                }
            }

            @Override
            public void onError(String error) {
                showSnackbar(getString(R.string.error_send_failed, error));
            }
        });
    }

    private void addController() {
        if (udpClient == null || passkey.isEmpty()) {
            showSnackbar(getString(R.string.error_no_passkey));
            return;
        }
        String ctrl = editTextControllerId.getText() != null
                ? editTextControllerId.getText().toString().trim() : "";
        if (ctrl.isEmpty()) {
            showSnackbar(getString(R.string.error_controller_empty));
            return;
        }

        udpClient.sendAndReceive("ADD," + passkey + "," + ctrl, new UdpClient.DataCallback() {
            @Override
            public void onDataReceived(String data) {
                String trimmed = data.trim();
                if (!trimmed.startsWith("OK")) {
                    showSnackbar(getString(R.string.error_server, trimmed));
                    return;
                }
                editTextControllerId.setText("");
                showSnackbar(getString(R.string.success_controller_added));
                refreshControllers();
            }

            @Override
            public void onError(String error) {
                showSnackbar(getString(R.string.error_send_failed, error));
            }
        });
    }

    private void removeController() {
        if (udpClient == null || passkey.isEmpty()) {
            showSnackbar(getString(R.string.error_no_passkey));
            return;
        }
        String selected = selectedController();
        if (selected == null) {
            showSnackbar(getString(R.string.error_no_controller_selected));
            return;
        }

        udpClient.sendAndReceive("REMOVE," + passkey + "," + selected, new UdpClient.DataCallback() {
            @Override
            public void onDataReceived(String data) {
                String trimmed = data.trim();
                if (!trimmed.startsWith("OK")) {
                    showSnackbar(getString(R.string.error_server, trimmed));
                    return;
                }
                showSnackbar(getString(R.string.success_controller_removed));
                clearSensorValues();
                refreshControllers();
            }

            @Override
            public void onError(String error) {
                showSnackbar(getString(R.string.error_send_failed, error));
            }
        });
    }

    private String selectedController() {
        Object item = spinnerControllers.getSelectedItem();
        return item != null ? item.toString() : null;
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
        String selected = selectedController();
        if (selected == null) {
            showSnackbar(getString(R.string.error_no_controller_selected));
            return;
        }
        if (displayOrder.length() == 0) {
            showSnackbar(getString(R.string.error_empty_order));
            return;
        }

        String payload = selected + ",CONFIG," + displayOrder;
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

    // ---- Recuperation des donnees (filtre par controller) -----------------

    private void requestSensorData() {
        if (udpClient == null) {
            showSnackbar(getString(R.string.error_no_server));
            return;
        }
        if (passkey.isEmpty()) {
            showSnackbar(getString(R.string.error_no_passkey));
            return;
        }
        String selected = selectedController();
        if (selected == null) {
            showSnackbar(getString(R.string.error_no_controller_selected));
            return;
        }

        udpClient.sendAndReceive("GET," + passkey + "," + selected, new UdpClient.DataCallback() {
            @Override
            public void onDataReceived(String data) {
                String trimmed = data.trim();
                if (trimmed.startsWith("UNAUTHORIZED") || trimmed.startsWith("ERROR")
                        || trimmed.startsWith("No data")) {
                    showSnackbar(getString(R.string.error_server, trimmed));
                    clearSensorValues();
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

    private void clearSensorValues() {
        String placeholder = getString(R.string.value_placeholder);
        textTemperature.setText(placeholder);
        textHumidity.setText(placeholder);
        textLuminosity.setText(placeholder);
        textPressure.setText(placeholder);
        textLastUpdate.setText(R.string.last_update_never);
    }

    private void showSnackbar(String message) {
        Snackbar.make(findViewById(R.id.main), message, Snackbar.LENGTH_SHORT).show();
    }
}
