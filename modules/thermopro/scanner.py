# ═══════════════════════════════════════════════════════════
#  modules/thermopro/scanner.py
#  BLE-Scan für ThermoPro TP357 – läuft in eigenem Thread
# ═══════════════════════════════════════════════════════════

import asyncio
import threading
import time
import sys, os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

try:
    from bleak import BleakScanner
    BLEAK_OK = True
except ImportError:
    BLEAK_OK = False

# Callback: wird von scanner.py aufgerufen, wenn ein Gerät empfangen wird
_on_device_cb = None


def set_callback(cb):
    """Setzt die Callback-Funktion: cb(mac, name, temperature, humidity, battery)"""
    global _on_device_cb
    _on_device_cb = cb


# ── TP357 Advertisement-Parser ───────────────────────────

def _parse_tp357(device, advertisement_data):
    """
    Parst die BLE-Advertisementdaten des TP357.
    Gibt (temperature, humidity, battery) zurück oder None bei Fehler.

    Bekanntes Format (manufacturer data, company_id=0xEC88):
        Byte 0-1: Header
        Byte 2-3: Temperatur * 10 (big-endian int16, signed)
        Byte 4:   Luftfeuchtigkeit (uint8, %)
        Byte 5:   Batterie (uint8, %)
    """
    try:
        mfr = advertisement_data.manufacturer_data
        if not mfr:
            return None

        # ThermoPro nutzt company_id 0xEC88
        raw = None
        for cid, data in mfr.items():
            if cid == 0xEC88:
                raw = data
                break

        # Fallback: ersten Eintrag nehmen wenn genau einer vorhanden
        if raw is None and len(mfr) == 1:
            raw = list(mfr.values())[0]

        if raw is None or len(raw) < 6:
            return None

        # Temperatur: Bytes 2+3, big-endian, signed, /10
        temp_raw = int.from_bytes(raw[2:4], byteorder="big", signed=True)
        temperature = round(temp_raw / 10.0, 1)

        # Luftfeuchtigkeit: Byte 4
        humidity = int(raw[4])

        # Batterie: Byte 5 (manche Geräte 0-100, manche 0-10 → normalisieren)
        battery_raw = int(raw[5])
        battery = battery_raw if battery_raw <= 100 else round(battery_raw / 10)

        # Plausibilitätsprüfung
        if not (-40 <= temperature <= 85):
            return None
        if not (0 <= humidity <= 100):
            return None

        return temperature, humidity, battery

    except Exception as e:
        print(f"[TP357] Parse-Fehler ({device.name}): {e}")
        return None


# ── Asyncio BLE-Loop ─────────────────────────────────────

async def _scan_loop(stop_event: asyncio.Event):
    """Dauerhafter BLE-Scan. Ruft Callback für jeden TP357 auf."""

    def detection_callback(device, advertisement_data):
        name = device.name or ""
        if not (name.startswith("TP357") or name.startswith("TP358") or name.startswith("TP359")):
            return

        result = _parse_tp357(device, advertisement_data)
        if result is None:
            return

        temperature, humidity, battery = result

        if _on_device_cb:
            try:
                _on_device_cb(
                    mac=device.address,
                    name=name,
                    temperature=temperature,
                    humidity=humidity,
                    battery=battery,
                )
            except Exception as e:
                print(f"[TP357] Callback-Fehler: {e}")

    scanner = BleakScanner(detection_callback=detection_callback)

    print("[ThermoPro] BLE-Scanner gestartet (passiver Scan)")

    while not stop_event.is_set():
        try:
            async with scanner:
                # Scan läuft 30 Sekunden, dann kurze Pause und weiter
                await asyncio.sleep(30)
        except Exception as e:
            print(f"[ThermoPro] Scanner-Fehler: {e} – Neustart in 10s")
            await asyncio.sleep(10)

    print("[ThermoPro] BLE-Scanner gestoppt")


# ── Thread-Einstieg ─────────────────────────────────────

_thread = None
_loop   = None
_stop   = None


def start():
    """Startet den BLE-Scanner in einem Hintergrund-Thread."""
    global _thread, _loop, _stop

    if not BLEAK_OK:
        print("[ThermoPro] bleak nicht installiert – BLE-Scanner deaktiviert")
        print("[ThermoPro] Installation: pip install bleak --break-system-packages")
        return

    def run():
        global _loop, _stop
        _loop = asyncio.new_event_loop()
        asyncio.set_event_loop(_loop)
        _stop = asyncio.Event()
        _loop.run_until_complete(_scan_loop(_stop))
        _loop.close()

    _thread = threading.Thread(target=run, daemon=True, name="BLE-Scanner")
    _thread.start()
    print("[ThermoPro] BLE-Thread gestartet")


def stop():
    """Stoppt den BLE-Scanner sauber."""
    global _stop, _loop
    if _loop and _stop:
        _loop.call_soon_threadsafe(_stop.set)
