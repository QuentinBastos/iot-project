# 🌐 IoT Server

A high-performance, modular Python bridge connecting **micro:bit sensor networks** (via Serial UART) with **mobile applications** (via UDP). This server handles real-time data persistence, device configuration, and multi-user sensor management.

## ✨ Key Features

- **🛡️ Modular Architecture**: Clean separation between business logic, data persistence, and IO protocols.
- **📡 Multi-Protocol Bridging**: Seamless translation between Serial (UART) and Network (UDP) packets.
- **🗄️ Robust Persistence**: SQLite-backed history tracking with a Repository Pattern.
- **🔐 User & Sensor Management**: Secure passkey-based registration and sensor ownership.
- **⚡ Fault Tolerant**: Automated serial reconnection and rate-limited UDP listeners.

---

## 🏗️ System Architecture

The project follows a **Layered Domain-Driven Design** to ensure scalability and ease of testing:

### 1. 📂 `core/` (The Brain)
- **`models.py`**: Immutable dataclasses representing the system state (`SensorReading`, `ConfigCommand`).
- **`service.py`**: Central `ServerService` that coordinates interactions without knowing about specific IO implementations.

### 2. 📂 `data/` (The Persistence Logic)
- **`database.py`**: SQLite connection pooling and schema management.
- **`repository.py`**: The `IoTRepository` handles all SQL queries and domain-to-database mapping.

### 3. 📂 `protocol/` (The Language)
- **`codec.py`**: A centralized `ProtocolCodec` for encoding/decoding raw string packets into domain events.
- **`events.py`**: Internal event definitions for cross-layer communication.

### 4. 📂 `infrastructure/` (The Senses)
- **`udp_server.py`**: High-concurrency threaded UDP server for mobile app communication.
- **`serial_server.py`**: Robust serial bridge for hardware interaction.

### 5. 📂 `storage/` (The Vault)
- **`server_data.db`**: Primary SQLite database for sensor readings and configurations.
- **`server.log`**: Centralized application logs for diagnostics.

---

## 🛠️ Setup & Installation

### Prerequisites
- Python 3.10+
- `pyserial` library

### Quick Start
```powershell
# 1. Clone the repository
git clone https://github.com/QuentinBastos/iot-project.git
cd iot-project/server

# 2. Setup Virtual Environment
python -m venv .venv
.\.venv\Scripts\activate

# 3. Install Dependencies
pip install -r requirements.txt
```

---

## 📋 usage Guide

### Running the Server
The gateway can be configured via command-line arguments. By default, it looks for data in the `storage/` directory.

```powershell
python main.py --serial_port COM3 --udp_port 10000
```

| Argument | Description | Default |
| :--- | :--- | :--- |
| `--serial_port` | The COM port or /dev/ path for the micro:bit | `COM3` |
| `--baudrate` | Serial communication speed | `115200` |
| `--udp_port` | The port to listen for UDP packets | `10000` |
| `--db` | Path to the SQLite database file | `storage/server_data.db` |
| `--serial-retry` | Seconds to wait before retrying serial connection | `5` |

---

## 📡 Communication Protocols

### 🔹 Micro:bit ➔ Gateway (Serial)
**Format**: `CONTROLLER_ID,SENSOR_ID,VALUE`
- Example: `MC01,TEMP,24.5`

### 🔹 Mobile App ➔ Gateway (UDP)
| Action | Packet Format | response |
| :--- | :--- | :--- |
| **Register** | `INIT,passkey` | `OK` / `ERROR` |
| **Add Sensor** | `ADD,passkey,sensor_id` | `OK` / `UNAUTHORIZED` |
| **Get Data** | `GET,passkey` | `ID,SENSOR,VAL\n...` |
| **Set Config** | `CTL_ID,CONFIG,display_order` | (Broadcast to Serial) |

---

## 🧪 Development & Testing

We use a modular testing approach to verify individual layers:

```powershell
# Run the test suite
python -m unittest discover tests
```

---
> [!TIP]
> To simulate a mobile app request without the Android client, you can use `ncat`:
> `echo "GET,mypasskey" | ncat -u 127.0.0.1 10000`
