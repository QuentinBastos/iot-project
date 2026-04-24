package com.example.bureaubientre;

import android.os.Handler;
import android.os.Looper;

import java.net.DatagramPacket;
import java.net.DatagramSocket;
import java.net.InetAddress;
import java.net.SocketTimeoutException;
import java.nio.charset.StandardCharsets;

public class UdpClient {

    private final String serverIp;
    private final int serverPort;
    private final Handler mainHandler = new Handler(Looper.getMainLooper());

    private DatagramSocket listenerSocket;
    private volatile boolean listening = false;
    private Thread listenerThread;

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
            try {
                DatagramSocket socket = new DatagramSocket();
                byte[] data = message.getBytes(StandardCharsets.UTF_8);
                InetAddress address = InetAddress.getByName(serverIp);
                DatagramPacket packet = new DatagramPacket(data, data.length, address, serverPort);
                socket.send(packet);
                socket.close();
                mainHandler.post(callback::onSuccess);
            } catch (Exception e) {
                mainHandler.post(() -> callback.onError(e.getMessage()));
            }
        }).start();
    }

    public void requestData(DataCallback callback) {
        new Thread(() -> {
            DatagramSocket socket = null;
            try {
                socket = new DatagramSocket();
                socket.setSoTimeout(5000);

                // Send getValues() request
                byte[] requestData = "getValues()".getBytes(StandardCharsets.UTF_8);
                InetAddress address = InetAddress.getByName(serverIp);
                DatagramPacket sendPacket = new DatagramPacket(requestData, requestData.length, address, serverPort);
                socket.send(sendPacket);

                // Wait for response
                byte[] buffer = new byte[1024];
                DatagramPacket receivePacket = new DatagramPacket(buffer, buffer.length);
                socket.receive(receivePacket);

                String response = new String(receivePacket.getData(), 0, receivePacket.getLength(), StandardCharsets.UTF_8);
                mainHandler.post(() -> callback.onDataReceived(response));
            } catch (SocketTimeoutException e) {
                mainHandler.post(() -> callback.onError("Timeout: pas de reponse du serveur"));
            } catch (Exception e) {
                mainHandler.post(() -> callback.onError(e.getMessage()));
            } finally {
                if (socket != null && !socket.isClosed()) socket.close();
            }
        }).start();
    }

    public void startListening(int listenPort, DataCallback callback) {
        stopListening();
        listening = true;
        listenerThread = new Thread(() -> {
            try {
                listenerSocket = new DatagramSocket(listenPort);
                listenerSocket.setReuseAddress(true);
                listenerSocket.setSoTimeout(2000);
                byte[] buffer = new byte[1024];

                while (listening) {
                    try {
                        DatagramPacket packet = new DatagramPacket(buffer, buffer.length);
                        listenerSocket.receive(packet);
                        String message = new String(packet.getData(), 0, packet.getLength(), StandardCharsets.UTF_8);
                        mainHandler.post(() -> callback.onDataReceived(message));
                    } catch (SocketTimeoutException e) {
                        // Expected — loop to check listening flag
                    }
                }
            } catch (Exception e) {
                if (listening) {
                    mainHandler.post(() -> callback.onError(e.getMessage()));
                }
            } finally {
                if (listenerSocket != null && !listenerSocket.isClosed()) {
                    listenerSocket.close();
                }
            }
        });
        listenerThread.setDaemon(true);
        listenerThread.start();
    }

    public void stopListening() {
        listening = false;
        if (listenerSocket != null && !listenerSocket.isClosed()) {
            listenerSocket.close();
        }
        if (listenerThread != null) {
            listenerThread.interrupt();
            listenerThread = null;
        }
    }
}
