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
    private Spinner spinnerSensor;
    private TextView textDisplayOrder;
    private MaterialButton buttonAddToOrder, buttonSendOrder, buttonResetOrder;

    // Sensor data views
    private TextView textTemperature, textHumidity, textLuminosity, textPressure;
    private TextView textLastUpdate;
    private MaterialButton buttonGetData;

    // History views
    private MaterialButton buttonLoadHistory;
    private TextView textHistory, textHistoryHint;
    private Spinner spinnerHistoryFilter;

    private static final int HISTORY_DAYS = 7;
    // Dernier payload recu du serveur (pour re-rendu lors d'un changement de filtre).
    private String lastHistoryRaw = "";

    // Code interne du capteur actuellement mis en avant dans l'historique
    // ("", "T", "H", "L", "P"). "" = tous les capteurs.
    private String historyFilterCode = "";

    // State
    private final StringBuilder displayOrder = new StringBuilder();
    /** Letter -> full human-readable label, ordered like the spinner. */
    private final Map<String, String> sensorLabels = new LinkedHashMap<>();
    private final List<String> sensorLabelList = new ArrayList<>();
    private final List<String> controllers = new ArrayList<>();
    private ArrayAdapter<String> controllersAdapter;
    private ArrayAdapter<String> sensorsAdapter;
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
        initSensorCatalog();
        initViews();
        setupControllersSpinner();
        setupSensorSpinner();
        setupHistoryFilterSpinner();
        loadSavedConfig();
        setupListeners();
    }

    /** Mapping lettre <-> nom complet (ordre stable, source de verite pour le Spinner). */
    private void initSensorCatalog() {
        sensorLabels.put("T", getString(R.string.sensor_temperature));
        sensorLabels.put("H", getString(R.string.sensor_humidity));
        sensorLabels.put("L", getString(R.string.sensor_luminosity));
        sensorLabels.put("P", getString(R.string.sensor_pressure));
        sensorLabelList.addAll(sensorLabels.values());
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

        spinnerSensor = findViewById(R.id.spinnerSensor);
        textDisplayOrder = findViewById(R.id.textDisplayOrder);
        buttonAddToOrder = findViewById(R.id.buttonAddToOrder);
        buttonSendOrder = findViewById(R.id.buttonSendOrder);
        buttonResetOrder = findViewById(R.id.buttonResetOrder);

        textTemperature = findViewById(R.id.textTemperature);
        textHumidity = findViewById(R.id.textHumidity);
        textLuminosity = findViewById(R.id.textLuminosity);
        textPressure = findViewById(R.id.textPressure);
        textLastUpdate = findViewById(R.id.textLastUpdate);
        buttonGetData = findViewById(R.id.buttonGetData);

        buttonLoadHistory = findViewById(R.id.buttonLoadHistory);
        textHistory = findViewById(R.id.textHistory);
        textHistoryHint = findViewById(R.id.textHistoryHint);
        spinnerHistoryFilter = findViewById(R.id.spinnerHistoryFilter);
        textHistoryHint.setText(getString(R.string.history_limit_hint, HISTORY_DAYS));
    }

    private void setupHistoryFilterSpinner() {
        // Liste alignee entre libelles visibles et codes courts T/H/L/P ("" = all).
        List<String> labels = Arrays.asList(
                getString(R.string.history_filter_all),
                getString(R.string.history_filter_temp),
                getString(R.string.history_filter_humidity),
                getString(R.string.history_filter_luminosity),
                getString(R.string.history_filter_pressure));
        final String[] codes = {"", "T", "H", "L", "P"};

        ArrayAdapter<String> adapter = new ArrayAdapter<>(this,
                android.R.layout.simple_spinner_item, labels);
        adapter.setDropDownViewResource(android.R.layout.simple_spinner_dropdown_item);
        spinnerHistoryFilter.setAdapter(adapter);
        spinnerHistoryFilter.setOnItemSelectedListener(new AdapterView.OnItemSelectedListener() {
            @Override
            public void onItemSelected(AdapterView<?> parent, View view, int pos, long id) {
                historyFilterCode = codes[pos];
                if (!lastHistoryRaw.isEmpty()) {
                    textHistory.setText(formatHistoryLines(lastHistoryRaw));
                }
            }

            @Override
            public void onNothingSelected(AdapterView<?> parent) { }
        });
    }

    private void setupSensorSpinner() {
        sensorsAdapter = new ArrayAdapter<>(this, android.R.layout.simple_spinner_item, sensorLabelList);
        sensorsAdapter.setDropDownViewResource(android.R.layout.simple_spinner_dropdown_item);
        spinnerSensor.setAdapter(sensorsAdapter);
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

        buttonAddToOrder.setOnClickListener(v -> addSelectedSensorToOrder());
        buttonResetOrder.setOnClickListener(v -> resetOrder());
        buttonSendOrder.setOnClickListener(v -> sendDisplayOrder());
        buttonGetData.setOnClickListener(v -> requestSensorData());

        buttonAddController.setOnClickListener(v -> addController());
        buttonRemoveController.setOnClickListener(v -> removeController());
        buttonRefreshControllers.setOnClickListener(v -> refreshControllers());
        buttonLoadHistory.setOnClickListener(v -> requestHistory());
    }

    private void addSelectedSensorToOrder() {
        Object selected = spinnerSensor.getSelectedItem();
        if (selected == null) return;
        String letter = letterFor(selected.toString());
        if (letter == null) return;
        if (displayOrder.indexOf(letter) >= 0) return;   // deja present
        displayOrder.append(letter);
        updateOrderDisplay();
    }

    private String letterFor(String fullLabel) {
        for (Map.Entry<String, String> entry : sensorLabels.entrySet()) {
            if (entry.getValue().equals(fullLabel)) return entry.getKey();
        }
        return null;
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
            return;
        }
        StringBuilder pretty = new StringBuilder();
        String sep = getString(R.string.arrow_separator);
        for (int i = 0; i < displayOrder.length(); i++) {
            String letter = String.valueOf(displayOrder.charAt(i));
            String label = sensorLabels.get(letter);
            if (label == null) continue;
            if (pretty.length() > 0) pretty.append(sep);
            pretty.append(label);
        }
        textDisplayOrder.setText(getString(R.string.label_order, pretty.toString()));
    }

    private void resetOrder() {
        displayOrder.setLength(0);
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

    // ---- Historique (aggregats journaliers) ------------------------------

    private void requestHistory() {
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

        String req = "HISTORY," + passkey + "," + selected + "," + HISTORY_DAYS;
        udpClient.sendAndReceive(req, new UdpClient.DataCallback() {
            @Override
            public void onDataReceived(String data) {
                String trimmed = data.trim();
                if (trimmed.startsWith("UNAUTHORIZED") || trimmed.startsWith("ERROR")
                        || trimmed.startsWith("No data")) {
                    textHistory.setText(trimmed);
                    lastHistoryRaw = "";
                    return;
                }
                lastHistoryRaw = trimmed;
                textHistory.setText(formatHistoryLines(trimmed));
            }

            @Override
            public void onError(String error) {
                showSnackbar(getString(R.string.error_send_failed, error));
            }
        });
    }

    /**
     * Transforme la reponse aggregee (une ligne par jour) en bloc lisible.
     * Format serveur :
     *   day,t_avg,t_min,t_max,h_avg,h_min,h_max,l_avg,l_min,l_max,p_avg,p_min,p_max,samples
     * Le filtre du spinner (``historyFilterCode``) restreint l'affichage a un
     * seul capteur si selectionne.
     */
    private String formatHistoryLines(String raw) {
        String[] lines = raw.split("\\r?\\n");
        if (lines.length == 0) return getString(R.string.history_empty);

        StringBuilder sb = new StringBuilder();
        for (String line : lines) {
            String[] parts = line.split(",", -1);
            if (parts.length < 14) continue;

            String day = parts[0];
            String samples = parts[13];

            sb.append(getString(R.string.history_day_header, day, samples)).append('\n');
            appendStatIfMatch(sb, "T", "Temp ", parts[1], parts[2], parts[3]);
            appendStatIfMatch(sb, "H", "Hum  ", parts[4], parts[5], parts[6]);
            appendStatIfMatch(sb, "L", "Lum  ", parts[7], parts[8], parts[9]);
            appendStatIfMatch(sb, "P", "Pres ", parts[10], parts[11], parts[12]);
            sb.append('\n');
        }
        return sb.length() == 0 ? getString(R.string.history_empty) : sb.toString();
    }

    /**
     * Ajoute une ligne "moy X min Y max Z" si :
     *   - le filtre est "" (tous les capteurs) ou matche ``code``
     *   - et la moyenne est disponible (cellule non vide).
     */
    private void appendStatIfMatch(StringBuilder sb, String code, String label,
                                   String avg, String min, String max) {
        if (!historyFilterCode.isEmpty() && !historyFilterCode.equals(code)) return;
        if (avg == null || avg.isEmpty()) return;
        sb.append(getString(R.string.history_stat_line, label,
                shortNum(avg), shortNum(min), shortNum(max))).append('\n');
    }

    private String shortNum(String raw) {
        if (raw == null || raw.isEmpty()) return "--";
        try {
            float f = Float.parseFloat(raw);
            return String.format(Locale.getDefault(), "%.1f", f);
        } catch (NumberFormatException e) {
            return raw;
        }
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
