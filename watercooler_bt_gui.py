#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Standalone PyQt5 application with a system tray icon for managing a liquid-cooling system over BLE,
showing connection status, controlling RGB lighting, and dynamic fan curve or manual control based on CPU/GPU temperatures.

Features:
- Manual mode: direct sliders for fan, pump, and RGB controls.
- Curve mode: editable fan curve (temperature vs fan %) with draggable points.
- Axis labels on fan curve: temperatures on X, Low/Med/Max on Y.
- Automatic fan control in curve mode, polling temps every 2s.
- System tray with Show/Exit.

Uses PyQt5 + qasync + pythonnet + bleak.
"""
import sys
import asyncio
from pathlib import Path
from enum import IntEnum

from PyQt5 import QtWidgets, QtCore, QtGui
import clr
from bleak import BleakScanner, BleakClient
import qasync
from qasync import asyncSlot

# === UI STRINGS ===
UI = {
    'mode_manual': "Manual Mode",
    'mode_curve': "Fan Curve (not Pump!)",
    'searching': "Looking for Watercooler...",
    'select_prompt': "Please select your device and press Connect",
    'no_device': "No BLE watercooler found, retrying...",
    'connecting': "Connecting to {}...",
    'connected': "Connected to {}",
    'label_fan': "Fan Power (%):",
    'label_pump': "Pump Voltage (V):",
    'label_rgb': "RGB Lighting:",
    'label_curve': "Fan Curve (Temp °C vs Fan %):",
    'btn_connect': "Connect",
    'btn_apply_manual': "Apply",
    'btn_apply_rgb': "Apply RGB",
    'btn_apply_all': "Apply everything",
    'btn_apply_curve': "Apply Fan Curve",
    'tray_exit': "Exit",
    'tray_show': "Show",
    'label_update_speed': "Update speed:"
}

COLOR_MAP = {
    'Red':     (255, 0, 0),
    'Green':   (0, 255, 0),
    'Blue':    (0, 0, 255),
    'White':   (255, 255, 255),
    'Yellow':  (255, 255, 0),
    'Cyan':    (0, 255, 255),
    'Magenta': (255, 0, 255)
}

DLL = Path(__file__).with_name("LibreHardwareMonitorLib.dll")
if not DLL.exists():
    QtWidgets.QMessageBox.critical(None, "Error", f"{DLL.name} not found alongside the script.")
    sys.exit(1)
clr.AddReference(str(DLL))
from LibreHardwareMonitor import Hardware

class Commands:
    FAN  = 0x1B
    PUMP = 0x1C
    RGB  = 0x1E

class PumpVoltage(IntEnum):
    V7  = 0x02
    V8  = 0x03
    V11 = 0x00
    V12 = 0x01

class RGBMode(IntEnum):
    STATIC  = 0x00
    BREATH  = 0x01
    RAINBOW = 0x02

class NordicUART:
    SERVICE_UUID = '6e400001-b5a3-f393-e0a9-e50e24dcca9e'
    CHAR_TX      = '6e400002-b5a3-f393-e0a9-e50e24dcca9e'

async def scan_devices(models=("LCT21001", "LCT22002")):
    devices = await BleakScanner.discover()
    return [(d.name, d.address) for d in devices if d.name and any(m in d.name for m in models)]

async def write_fan_mode(client: BleakClient, duty: int):
    packet = bytearray([0xFE, Commands.FAN, 0x01 if duty else 0x00, duty, 0, 0, 0, 0xEF])
    await client.write_gatt_char(NordicUART.CHAR_TX, packet)

async def write_pump_mode(client: BleakClient, voltage: PumpVoltage):
    packet = bytearray([0xFE, Commands.PUMP, 0x01, 100, int(voltage), 0, 0, 0xEF])
    await client.write_gatt_char(NordicUART.CHAR_TX, packet)

async def write_rgb_mode(client: BleakClient, mode: RGBMode, color: tuple):
    red, green, blue = color
    packet = bytearray([0xFE, Commands.RGB, 0x01, red, green, blue, int(mode), 0xEF])
    await client.write_gatt_char(NordicUART.CHAR_TX, packet)

def get_temperatures():
    try:
        comp = Hardware.Computer()
        comp.IsCpuEnabled = True
        comp.IsGpuEnabled = True
        comp.Open()
        cpu_temp = gpu_temp = None
        for hw in comp.Hardware:
            try:
                hw.Update()
                if hw.HardwareType == Hardware.HardwareType.Cpu:
                    for s in hw.Sensors:
                        if s.SensorType == Hardware.SensorType.Temperature and "Package" in s.Name:
                            cpu_temp = s.Value
                elif hw.HardwareType in (Hardware.HardwareType.GpuNvidia, Hardware.HardwareType.GpuAmd):
                    for s in hw.Sensors:
                        if s.SensorType == Hardware.SensorType.Temperature and "Core" in s.Name:
                            gpu_temp = s.Value
            except Exception:
                pass
        comp.Close()
        return cpu_temp, gpu_temp
    except Exception:
        return None, None

class FanCurveWidget(QtWidgets.QWidget):
    def __init__(self, points):
        super().__init__()
        self.points = points  # list of (temp, pct)
        self.selected = None
        self.setMinimumHeight(200)
        self.setMouseTracking(True)

    def paintEvent(self, event):
        qp = QtGui.QPainter(self)
        w, h = self.width(), self.height()
        # Draw grid (light gray)
        qp.setPen(QtGui.QPen(QtGui.QColor(200, 200, 200), 1, QtCore.Qt.DotLine))
        # Vertical grid (every 10°C from 20 to 100)
        for t in range(20, 101, 10):
            x = int(40 + (t - 20) / (100 - 20) * (w - 50))
            qp.drawLine(x, h-40, x, 10)
        # Horizontal grid (every 10%)
        for p in range(0, 101, 10):
            y = int((h - 40) - p / 100 * (h - 50))
            qp.drawLine(40, y, w-10, y)
        # Draw axes (black)
        qp.setPen(QtGui.QPen(QtCore.Qt.black, 1))
        qp.drawLine(40, h-40, w-10, h-40)  # X-axis
        qp.drawLine(40, h-40, 40, 10)      # Y-axis
        # Use small font for labels
        font = qp.font()
        font.setPointSize(8)
        qp.setFont(font)
        # X-axis ticks & labels (20°C … 100°C)
        for t, _ in self.points:
            x = int(40 + (t - 20) / (100 - 20) * (w - 50))
            qp.drawLine(x, h-40, x, h-36)
            qp.drawText(x - 10, h - 20, f"{t}°C")
        # Y-axis ticks & labels (Low=31%, Med=58%, Max=100%)
        y_labels = {31: "Low", 58: "Med", 100: "Max"}
        y_values = [31, 58, 100]
        for p in y_values:
            y = int((h - 40) - p / 100 * (h - 50))
            qp.drawLine(40, y, 44, y)
            label = f"{y_labels[p]} ({p}%)"
            qp.drawText(5, y + 4, label)
        # Draw the curve
        pts = []
        for t, p in self.points:
            x = int(40 + (t - 20) / (100 - 20) * (w - 50))
            y = int((h - 40) - p / 100 * (h - 50))
            pts.append(QtCore.QPointF(x, y))
        qp.setPen(QtGui.QPen(QtCore.Qt.blue, 2))
        qp.drawPolyline(QtGui.QPolygonF(pts))
        qp.setBrush(QtCore.Qt.red)
        for pt in pts:
            qp.drawEllipse(pt, 5, 5)

    def mousePressEvent(self, event):
        x, y = event.x(), event.y()
        w, h = self.width(), self.height()
        for i, (t, p) in enumerate(self.points):
            px = 40 + (t-20)/(100-20)*(w-50)
            py = (h-40) - p/100*(h-50)
            if abs(px-x) <= 6 and abs(py-y) <= 6:
                self.selected = i
                return

    def mouseMoveEvent(self, event):
        if self.selected is None:
            return
        x, y = event.x(), event.y()
        w, h = self.width(), self.height()
        x = min(max(x, 40), w-10)
        y = min(max(y, 10), h-40)
        t = 20 + (x-40)/(w-50)*(100-20)
        p = (h-40 - y)/(h-50)*100
        self.points[self.selected] = (int(min(max(t,20),100)), int(min(max(p,0),100)))
        self.update()

    def mouseReleaseEvent(self, event):
        self.selected = None

    def interpolate(self, temp):
        pts = sorted(self.points)
        for i in range(len(pts)-1):
            t0, p0 = pts[i]
            t1, p1 = pts[i+1]
            if t0 <= temp <= t1:
                return p0 + (p1-p0)*(temp-t0)/(t1-t0)
        return pts[-1][1]

class MainWindow(QtWidgets.QMainWindow):
    UPDATE_INTERVALS = [
        (0.5, "0.5 s"),
        (1.0, "1 s"),
        (2.0, "2 s"),
        (5.0, "5 s"),
        (10.0, "10 s"),
    ]
    DEFAULT_INTERVAL_SEC = 2.0

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Watercooler Manager")
        self.setMinimumWidth(700)
        self.setAttribute(QtCore.Qt.WA_QuitOnClose, False)
        icon_dir = Path(__file__).parent / 'icons'
        ico = icon_dir / 'water_drop.ico'
        png = icon_dir / 'water_drop.png'
        icon_file = str(ico if ico.exists() else png)
        icon = QtGui.QIcon(icon_file)
        self.tray_icon = QtWidgets.QSystemTrayIcon(icon, self)
        self.setWindowIcon(icon)
        tray_menu = QtWidgets.QMenu()
        tray_menu.addAction(UI['tray_show'], self.show_window)
        tray_menu.addAction(UI['tray_exit'], self.exit_app)
        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.activated.connect(self.on_tray_activated)
        self.tray_icon.show()
        self.client = None
        self.curve_points = [(20,31),(60,58),(100,100)]
        self.curve_mode_active = False
        self.last_cpu_temp = None
        self.last_gpu_temp = None
        self._build_ui()
        self.temp_timer = QtCore.QTimer(self)
        self.temp_timer.timeout.connect(self.update_temperatures)
        self.set_update_interval(self.DEFAULT_INTERVAL_SEC)
        self.temp_timer.start()

    def _build_ui(self):
        main = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(main)
        mode_box = QtWidgets.QHBoxLayout()
        mode_box.addWidget(QtWidgets.QLabel("Mode:"))
        self.mode_combo = QtWidgets.QComboBox()
        self.mode_combo.addItem(UI['mode_manual'])
        self.mode_combo.addItem(UI['mode_curve'])
        mode_box.addWidget(self.mode_combo)
        layout.addLayout(mode_box)
        self.pages = QtWidgets.QStackedWidget()
        # ---- Manual page
        manual = QtWidgets.QWidget()
        mlay = QtWidgets.QVBoxLayout(manual)
        dlay = QtWidgets.QHBoxLayout()
        self.device_combo = QtWidgets.QComboBox(); self.device_combo.setEnabled(False)
        self.connect_btn = QtWidgets.QPushButton(UI['btn_connect']); self.connect_btn.setEnabled(False)
        dlay.addWidget(self.device_combo); dlay.addWidget(self.connect_btn)
        mlay.addLayout(dlay)
        # Fan Power
        mlay.addWidget(QtWidgets.QLabel(UI['label_fan']))
        self.fan_slider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.fan_slider.setRange(0,2)
        self.fan_slider.setTickInterval(1)
        self.fan_slider.setTickPosition(QtWidgets.QSlider.TicksBelow)
        mlay.addWidget(self.fan_slider)
        # Fan Power Labels
        fan_labels = QtWidgets.QHBoxLayout()
        duties = [80, 150, 255]
        for label in ["Low", "Medium", "Max"]:
            lab = QtWidgets.QLabel(label)
            lab.setAlignment(QtCore.Qt.AlignCenter)
            fan_labels.addWidget(lab)
        mlay.addLayout(fan_labels)
        # Fan Power Values
        fan_vals = QtWidgets.QHBoxLayout()
        for val in duties:
            lab = QtWidgets.QLabel(f"0x{val}")
            lab.setAlignment(QtCore.Qt.AlignCenter)
            fan_vals.addWidget(lab)
        mlay.addLayout(fan_vals)
        # Pump Voltage
        mlay.addWidget(QtWidgets.QLabel(UI['label_pump']))
        self.pump_slider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.pump_slider.setRange(0,3)
        self.pump_slider.setTickInterval(1)
        self.pump_slider.setTickPosition(QtWidgets.QSlider.TicksBelow)
        mlay.addWidget(self.pump_slider)
        # Pump Voltage Labels
        pump_labels = QtWidgets.QHBoxLayout()
        volts_labels = ["7V", "8V", "11V", "12V"]
        for label in volts_labels:
            lab = QtWidgets.QLabel(label)
            lab.setAlignment(QtCore.Qt.AlignCenter)
            pump_labels.addWidget(lab)
        mlay.addLayout(pump_labels)
        # RGB
        self.apply_manual_btn = QtWidgets.QPushButton(UI['btn_apply_manual']); self.apply_manual_btn.setEnabled(False)
        mlay.addWidget(self.apply_manual_btn)
        mlay.addWidget(QtWidgets.QLabel(UI['label_rgb']))
        rlay = QtWidgets.QHBoxLayout()
        self.rgb_mode = QtWidgets.QComboBox()
        for n,m in RGBMode.__members__.items(): self.rgb_mode.addItem(n,m)
        self.rgb_color = QtWidgets.QComboBox()
        for n,c in COLOR_MAP.items(): self.rgb_color.addItem(n,c)
        self.apply_rgb_btn = QtWidgets.QPushButton(UI['btn_apply_rgb']); self.apply_rgb_btn.setEnabled(False)
        rlay.addWidget(self.rgb_mode); rlay.addWidget(self.rgb_color); rlay.addWidget(self.apply_rgb_btn)
        mlay.addLayout(rlay)
        self.apply_all_btn = QtWidgets.QPushButton(UI['btn_apply_all']); self.apply_all_btn.setEnabled(False)
        mlay.addWidget(self.apply_all_btn)
        self.pages.addWidget(manual)
        # ---- Curve page
        curve = QtWidgets.QWidget()
        clay = QtWidgets.QVBoxLayout(curve)
        clay.addWidget(QtWidgets.QLabel(UI['label_curve']))
        self.curve_widget = FanCurveWidget(self.curve_points)
        clay.addWidget(self.curve_widget)
        self.apply_curve_btn = QtWidgets.QPushButton(UI['btn_apply_curve']); self.apply_curve_btn.setEnabled(False)
        clay.addWidget(self.apply_curve_btn)
        self.pages.addWidget(curve)
        layout.addWidget(self.pages)
        self.status_label = QtWidgets.QLabel(UI['searching'],alignment=QtCore.Qt.AlignCenter)
        layout.addWidget(self.status_label)
        temp_row = QtWidgets.QHBoxLayout()
        temp_row.addStretch()
        temp_row.addWidget(QtWidgets.QLabel(UI['label_update_speed']))
        self.update_speed_combo = QtWidgets.QComboBox()
        for sec, text in self.UPDATE_INTERVALS:
            self.update_speed_combo.addItem(text, sec)
        def_index = [i for i,(v,_) in enumerate(self.UPDATE_INTERVALS) if v == self.DEFAULT_INTERVAL_SEC][0]
        self.update_speed_combo.setCurrentIndex(def_index)
        self.update_speed_combo.currentIndexChanged.connect(self.update_interval_changed)
        temp_row.addWidget(self.update_speed_combo)
        temp_row.addSpacing(20)
        self.temp_label = QtWidgets.QLabel("CPU: -- °C   GPU: -- °C", alignment=QtCore.Qt.AlignCenter)
        font = self.temp_label.font()
        font.setPointSize(11)
        font.setBold(True)
        self.temp_label.setFont(font)
        temp_row.addWidget(self.temp_label)
        temp_row.addStretch()
        layout.addLayout(temp_row)
        self.setCentralWidget(main)
        self.mode_combo.currentIndexChanged.connect(self.on_mode_changed)
        self.connect_btn.clicked.connect(self.connect_device)
        self.apply_manual_btn.clicked.connect(self.apply_fan_and_pump)
        self.apply_rgb_btn.clicked.connect(self.apply_rgb)
        self.apply_all_btn.clicked.connect(self.apply_all)
        self.apply_curve_btn.clicked.connect(self.apply_curve)
        self.rgb_mode.currentIndexChanged.connect(lambda i: self.rgb_color.setEnabled(self.rgb_mode.currentData()!=RGBMode.RAINBOW))
        self.pages.setCurrentIndex(0)

    def set_update_interval(self, sec):
        self.temp_timer.setInterval(int(sec * 1000))

    def update_interval_changed(self):
        interval = self.update_speed_combo.currentData()
        self.set_update_interval(interval)

    def closeEvent(self, event):
        event.ignore(); self.hide()

    def show_window(self):
        self.show(); self.raise_(); self.activateWindow()

    def exit_app(self):
        QtWidgets.qApp.quit()

    def on_tray_activated(self, reason):
        if reason == QtWidgets.QSystemTrayIcon.Trigger:
            self.show_window()

    def on_mode_changed(self, index):
        self.pages.setCurrentIndex(index)
        if index == 0:
            self.curve_mode_active = False

    @asyncSlot()
    async def set_default_fan_and_pump(self):
        if not self.client or not self.client.is_connected:
            return
        await write_fan_mode(self.client, 150)
        await write_pump_mode(self.client, PumpVoltage.V8)

    @asyncSlot()
    async def scan_and_populate(self):
        devices = await scan_devices()
        self.device_combo.clear()
        for n,a in devices: self.device_combo.addItem(f"{n} [{a}]", a)
        if devices:
            self.device_combo.setEnabled(True)
            self.connect_btn.setEnabled(True)
            self.status_label.setText(UI['select_prompt'])
        else:
            self.status_label.setText(UI['no_device'])
            await asyncio.sleep(5)
            await self.scan_and_populate()

    @asyncSlot()
    async def connect_device(self):
        addr = self.device_combo.currentData()
        self.status_label.setText(UI['connecting'].format(addr))
        client = BleakClient(addr)
        try:
            await client.connect(timeout=5.0)
            if client.is_connected:
                self.client = client
                self.status_label.setText(UI['connected'].format(self.device_combo.currentText()))
                for btn in (self.apply_manual_btn,self.apply_rgb_btn,self.apply_all_btn,self.apply_curve_btn): btn.setEnabled(True)
                await self.set_default_fan_and_pump()
        except:
            self.status_label.setText(UI['no_device'])

    @asyncSlot()
    async def update_temperatures(self):
        loop = asyncio.get_running_loop()
        try:
            cpu, gpu = await loop.run_in_executor(None, get_temperatures)
        except Exception:
            cpu = gpu = None
        if cpu is not None:
            self.last_cpu_temp = cpu
        if gpu is not None:
            self.last_gpu_temp = gpu
        cpu_txt = f"{int(self.last_cpu_temp)} °C" if self.last_cpu_temp is not None else "-- °C"
        gpu_txt = f"{int(self.last_gpu_temp)} °C" if self.last_gpu_temp is not None else "-- °C"
        self.temp_label.setText(f"CPU: {cpu_txt}   GPU: {gpu_txt}")
        if not self.curve_mode_active or self.last_cpu_temp is None:
            return
        if not self.client or not self.client.is_connected:
            return
        pct = self.curve_widget.interpolate(self.last_cpu_temp)
        await write_fan_mode(self.client, int(pct))

    @asyncSlot()
    async def apply_fan_and_pump(self):
        if not self.client or not self.client.is_connected:
            return
        self.curve_mode_active = False
        duties = [80,150,255]
        await write_fan_mode(self.client, duties[self.fan_slider.value()])
        volts = [PumpVoltage.V7,PumpVoltage.V8,PumpVoltage.V11,PumpVoltage.V12]
        await write_pump_mode(self.client, volts[self.pump_slider.value()])

    @asyncSlot()
    async def apply_rgb(self):
        if not self.client or not self.client.is_connected:
            return
        mode = self.rgb_mode.currentData()
        color = self.rgb_color.currentData()
        if mode == RGBMode.RAINBOW:
            await write_rgb_mode(self.client, mode, (0,0,0))
        else:
            await write_rgb_mode(self.client, mode, color)

    @asyncSlot()
    async def apply_all(self):
        await self.apply_fan_and_pump()
        await self.apply_rgb()

    @asyncSlot()
    async def apply_curve(self):
        if not self.client or not self.client.is_connected:
            return
        self.curve_mode_active = True
        cpu,_ = get_temperatures()
        if cpu is None:
            return
        pct = self.curve_widget.interpolate(cpu)
        await write_fan_mode(self.client, int(pct))

def main():
    app = QtWidgets.QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    loop = qasync.QEventLoop(app)
    asyncio.set_event_loop(loop)
    window = MainWindow()
    window.show()
    asyncio.ensure_future(window.scan_and_populate())
    with loop:
        loop.run_forever()

if __name__ == '__main__':
    main()
