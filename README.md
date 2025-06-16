
# Watercooler Manager GUI

> **Based on** [tomups/watercooler-manager](https://github.com/tomups/watercooler-manager)  
> **Uses** [LibreHardwareMonitor/LibreHardwareMonitor](https://github.com/LibreHardwareMonitor/LibreHardwareMonitor) for real-time CPU and GPU temperature monitoring.

## Overview
![Picture1](https://i.imgur.com/EuxEdPa.png)
![Picture2](https://i.imgur.com/eKr77QT.png)

**Watercooler Manager GUI** is a standalone desktop application for Windows, designed for advanced control and monitoring of custom watercooling systems over BLE (Bluetooth Low Energy).  
It allows you to manage fan, pump, and RGB lighting settings, and provides both manual and automatic (curve-based) control modes.  
Real-time CPU/GPU temperature monitoring is implemented via LibreHardwareMonitor, ensuring safe and optimal system operation.

---

## Features

- **BLE communication** with compatible watercooling controllers (e.g., LCT21001, LCT22002).
- **Manual mode:** direct sliders to set fan speed, pump voltage, and RGB lighting.
- **Curve mode:** fully editable fan curve (drag points on the graph; temperature vs fan %).
- **Real-time temperature display:** always visible current CPU and GPU temperatures (°C).
- **Customizable polling rate** for temperature updates (0.5s to 10s).
- **Automatic fan control** in curve mode, with smooth adjustment based on CPU temperature.
- **System tray integration** for running in the background with Show/Exit options.
- **Robust error handling:** last known temperature is displayed if sensor polling fails.
- **Asynchronous UI** (no freezes; responsive at all times).

---

## Credits

- **BLE protocol reverse engineering and original CLI utility:**  
  [tomups/watercooler-manager](https://github.com/tomups/watercooler-manager)  
  Without this project, BLE packet structure and controller support would not be possible.

- **Hardware temperature monitoring:**  
  [LibreHardwareMonitor/LibreHardwareMonitor](https://github.com/LibreHardwareMonitor/LibreHardwareMonitor)  
  Used via `pythonnet` to access Windows sensors in real time.

---

## Supported Hardware

- Watercooling controllers with BLE protocol compatible with [tomups/watercooler-manager](https://github.com/tomups/watercooler-manager) (LCT21001, LCT22002, etc).
- Windows PC with supported CPU and GPU (Intel/AMD CPU, Nvidia/AMD GPU).

---

## Requirements

- Windows 10/11 (Python and LibreHardwareMonitor require Windows; BLE usually requires BT 4.0+).
- Python 3.8 or newer (recommended: 3.9 or 3.10 for maximum compatibility).

### Python Dependencies

- `PyQt5`
- `qasync`
- `bleak`
- `pythonnet`
- (Your actual requirements may also include: `setuptools`, `wheel`, `pyinstaller`, etc.)

Install all with:

```sh
pip install -r requirements.txt
```

**Sample `requirements.txt`:**

```
PyQt5>=5.15
qasync>=0.24
bleak>=0.18
pythonnet>=3.0
```

---

### Additional Files Needed

- Place **`LibreHardwareMonitorLib.dll`** (from [LibreHardwareMonitor releases](https://github.com/LibreHardwareMonitor/LibreHardwareMonitor/releases)) in the **same directory** as the Python script or executable.
- Place icon files (`icons/water_drop.ico` and/or `icons/water_drop.png`) in an `icons` subfolder next to the script for system tray support (optional but recommended).

---

## Usage

```sh
python watercooler_bt_gui.py
```

The application window will appear.  
If compatible BLE devices are nearby, the program will scan for them automatically.  
Connect, adjust settings, and monitor your system in real time!

---

## Building a Standalone Windows EXE

You can build a single-file Windows executable using [PyInstaller](https://pyinstaller.org/):

### 1. Install PyInstaller

```sh
pip install pyinstaller
```

### 2. Build the Executable

From the directory containing your script, run:

```sh
pyinstaller --onefile --add-data "LibreHardwareMonitorLib.dll;." --add-data "icons;icons" --noconsole watercooler_bt_gui.py
```

- The `--onefile` flag bundles everything into a single `.exe`.
- `--add-data` ensures `LibreHardwareMonitorLib.dll` and icons are included.  
  (On Windows, use `;` as a separator. On Linux/Mac, use `:`.)
- `--noconsole` disables the command prompt window.

The built `.exe` will appear in the `dist` folder.  
Copy any needed BLE drivers and run!

---

## Known Issues & Troubleshooting

- **Sensor errors / NullReferenceException:** If temperature readings fail, the app will display the last known value and retry next cycle.
- **BLE connection issues:** Ensure your device is powered, close other BLE tools, and try reconnecting. Some USB BT dongles may need a driver update.
- **LibreHardwareMonitorLib.dll not found:** Ensure the DLL is in the same folder as the EXE/script.

---

## Development Notes

- Code is fully asynchronous: no blocking UI even during hardware polling.
- To add support for new controllers, edit the BLE scan models and/or command structure in the Python source.
- The fan curve widget supports arbitrary points and drag-and-drop.
- All UI strings are isolated for easy localization.

---

## License

The code here is released under the **MIT License**, but please see the original licenses for  
- [tomups/watercooler-manager](https://github.com/tomups/watercooler-manager)  
- [LibreHardwareMonitor/LibreHardwareMonitor](https://github.com/LibreHardwareMonitor/LibreHardwareMonitor)  
as they may place additional requirements on redistribution.

---

**Enjoy your custom-cooled PC!**
