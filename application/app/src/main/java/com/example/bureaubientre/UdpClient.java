package com.example.bureaubientre;

import android.os.Handler;
import android.os.Looper;

import java.net.DatagramPacket;
import java.net.DatagramSocket;
import java.net.InetAddress;
import java.net.SocketTimeoutException;
import java.nio.charset.StandardCharsets;

public class UdpClient {

    private static final int RECEIVE_TIMEOUT_MS = 5000;

    private final String serverIp;
    private final int serverPort;
    private final Handler mainHandler = new Handler(Looper.getMainLooper());

    public UdpClient(String serverIp, int serverPort) {
        this.serverIp = serverIp;
        this.serverPort = serverPort;
    }

    public interface SendCallback {
        void onSuccess();
        void onError(String error);
    }

    public interface DataCallback {
        void onDataReceived(String data);
        void onError(String error);
    }

    public void send(String message, SendCallback callback) {
        new Thread(() -> {
            try (DatagramSocket socket = new DatagramSocket()) {
                byte[] data = message.getBytes(StandardCharsets.UTF_8);
                InetAddress address = InetAddress.getByName(serverIp);
                DatagramPacket packet = new DatagramPacket(data, data.length, address, serverPort);
                socket.send(packet);
                mainHandler.post(callback::onSuccess);
            } catch (Exception e) {
                mainHandler.post(() -> callback.onError(e.getMessage()));
            }
        }).start();
    }

    public void sendAndReceive(String message, DataCallback callback) {
        new Thread(() -> {
            try (DatagramSocket socket = new DatagramSocket()) {
                socket.setSoTimeout(RECEIVE_TIMEOUT_MS);

                byte[] out = message.getBytes(StandardCharsets.UTF_8);
                InetAddress address = InetAddress.getByName(serverIp);
                socket.send(new DatagramPacket(out, out.length, address, serverPort));

                byte[] buffer = new byte[4096];
                DatagramPacket rx = new DatagramPacket(buffer, buffer.length);
                socket.receive(rx);

                String response = new String(rx.getData(), 0, rx.getLength(), StandardCharsets.UTF_8);
                mainHandler.post(() -> callback.onDataReceived(response));
            } catch (SocketTimeoutException e) {
                mainHandler.post(() -> callback.onError("Timeout: pas de reponse du serveur"));
            } catch (Exception e) {
                mainHandler.post(() -> callback.onError(e.getMessage()));
            }
        }).start();
    }
}
