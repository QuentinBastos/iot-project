package com.example.bureaubientre;

import android.content.SharedPreferences;
import android.os.Bundle;
import android.view.View;
import android.widget.ScrollView;
import android.widget.LinearLayout;
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
    private static final String KEY_MAC = "mac";
    private static final int DEFAULT_PORT = 10000;
    private static final int LISTEN_PORT = 10001;

    // Server config views
    private TextInputEditText editTextIp;
    private TextInputEditText editTextPort;
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

    // Discussion views
    private MaterialButton buttonOpenChat, buttonSendMessage;
    private LinearLayout chatContainer;
    private ScrollView chatScroll;
    private TextInputEditText editTextMessage;
    private TextView textChatHistory;

    // State
    private final StringBuilder displayOrder = new StringBuilder();
    private final Map<String, Chip> chipMap = new LinkedHashMap<>();
    private UdpClient udpClient;
    private boolean connected = false;
    private boolean paired = false;
    private String pairedMac = "";
    private final StringBuilder chatHistory = new StringBuilder();
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

        // Pairing
        editTextPassword = findViewById(R.id.editTextPassword);
        editTextPasswordConfirm = findViewById(R.id.editTextPasswordConfirm);
        editTextMac = findViewById(R.id.editTextMac);
        buttonInit = findViewById(R.id.buttonInit);
        textPairingStatus = findViewById(R.id.textPairingStatus);

        // Discussion
        buttonOpenChat = findViewById(R.id.buttonOpenChat);
        buttonSendMessage = findViewById(R.id.buttonSendMessage);
        chatContainer = findViewById(R.id.chatContainer);
        chatScroll = findViewById(R.id.chatScroll);
        editTextMessage = findViewById(R.id.editTextMessage);
        textChatHistory = findViewById(R.id.textChatHistory);

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
        String savedMac = prefs.getString(KEY_MAC, "");
        editTextIp.setText(savedIp);
        editTextPort.setText(String.valueOf(savedPort));
        editTextMac.setText(savedMac);
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

        buttonInit.setOnClickListener(v -> sendPairing());
        buttonOpenChat.setOnClickListener(v -> toggleChat());
        buttonSendMessage.setOnClickListener(v -> sendChatMessage());
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
                handleIncomingData(data);
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

    private void handleIncomingData(String data) {
        String trimmed = data.trim();
        // Sensor payload looks like {"T":..,"H":..,...} or starts with T:/H:/L:/P:
        if (trimmed.startsWith("{") || trimmed.matches(".*[THLP]\\s*[:=].*")) {
            updateSensorDisplay(trimmed);
        } else if (trimmed.startsWith("MSG|") || trimmed.startsWith("CHAT|")) {
            appendChat(getString(R.string.chat_received, trimmed.substring(trimmed.indexOf('|') + 1)));
        } else {
            // Unknown payload → treat as chat by default
            appendChat(getString(R.string.chat_received, trimmed));
        }
    }

    private void sendPairing() {
        if (udpClient == null) {
            showSnackbar(getString(R.string.error_no_server));
            return;
        }

        String pwd = editTextPassword.getText() != null ? editTextPassword.getText().toString() : "";
        String pwdConfirm = editTextPasswordConfirm.getText() != null ? editTextPasswordConfirm.getText().toString() : "";
        String mac = editTextMac.getText() != null ? editTextMac.getText().toString().trim() : "";

        if (pwd.isEmpty()) {
            showSnackbar(getString(R.string.error_password_empty));
            return;
        }
        if (!pwd.equals(pwdConfirm)) {
            showSnackbar(getString(R.string.error_password_mismatch));
            return;
        }
        if (mac.isEmpty()) {
            showSnackbar(getString(R.string.error_mac_empty));
            return;
        }

        prefs.edit().putString(KEY_MAC, mac).apply();

        String payload = "INIT|" + pwd + "|" + mac;
        udpClient.send(payload, new UdpClient.SendCallback() {
            @Override
            public void onSuccess() {
                paired = true;
                pairedMac = mac;
                textPairingStatus.setText(getString(R.string.status_paired, mac));
                textPairingStatus.setTextColor(getColor(R.color.status_connected));
                showSnackbar(getString(R.string.success_init));
            }

            @Override
            public void onError(String error) {
                showSnackbar(getString(R.string.error_send_failed, error));
            }
        });
    }

    private void toggleChat() {
        if (chatContainer.getVisibility() == View.VISIBLE) {
            chatContainer.setVisibility(View.GONE);
        } else {
            chatContainer.setVisibility(View.VISIBLE);
        }
    }

    private void sendChatMessage() {
        if (udpClient == null) {
            showSnackbar(getString(R.string.error_no_server));
            return;
        }
        String msg = editTextMessage.getText() != null ? editTextMessage.getText().toString().trim() : "";
        if (msg.isEmpty()) {
            showSnackbar(getString(R.string.error_empty_message));
            return;
        }

        String payload = "MSG|" + (pairedMac.isEmpty() ? "?" : pairedMac) + "|" + msg;
        udpClient.send(payload, new UdpClient.SendCallback() {
            @Override
            public void onSuccess() {
                appendChat(getString(R.string.chat_sent, msg));
                editTextMessage.setText("");
            }

            @Override
            public void onError(String error) {
                showSnackbar(getString(R.string.error_send_failed, error));
            }
        });
    }

    private void appendChat(String line) {
        if (chatHistory.length() > 0) chatHistory.append("\n");
        chatHistory.append(line);
        textChatHistory.setText(chatHistory.toString());
        chatScroll.post(() -> chatScroll.fullScroll(View.FOCUS_DOWN));
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
