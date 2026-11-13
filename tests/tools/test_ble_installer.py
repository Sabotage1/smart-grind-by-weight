"""Exercise the new updater without radio access or a connected motor."""
import asyncio
import hashlib
import importlib.util
from pathlib import Path
import sys
import tempfile
from types import ModuleType, SimpleNamespace
import unittest

ROOT = Path(__file__).resolve().parents[2]
bleak = ModuleType('bleak')
bleak.BleakClient = bleak.BleakScanner = None
sys.modules['bleak'] = bleak
spec = importlib.util.spec_from_file_location('installer', ROOT / 'tools/atom65/install_ble.py')
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)


class InstallerTest(unittest.TestCase):
    def artifacts(self, folder, binary=b'app', patch=b'patch'):
        for name, data in [('firmware.bin', binary), ('firmware-full.ota', patch)]:
            (folder / name).write_bytes(data)
        (folder / 'SHA256SUMS').write_text(''.join(
            hashlib.sha256((folder / name).read_bytes()).hexdigest() + '  ' + name + '\n'
            for name in ['firmware.bin', 'firmware-full.ota']))

    def test_checksums_and_tampering(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            self.artifacts(folder)
            self.assertEqual(installer.verify_artifacts(folder)[1], b'patch')
            (folder / 'firmware-full.ota').write_bytes(b'changed')
            with self.assertRaisesRegex(RuntimeError, 'Checksum mismatch'):
                installer.verify_artifacts(folder)

    def test_partition_bounds(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            for app, patch in [(b'', b'p'), (b'a', b''), (b'a' * 0x300000, b'p'), (b'a', b'p' * 0x200000)]:
                self.artifacts(folder, app, patch)
                with self.assertRaisesRegex(RuntimeError, 'partition map'):
                    installer.verify_artifacts(folder)

    def test_checksum_path_cannot_escape(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            (folder / 'SHA256SUMS').write_text('0' * 64 + '  ../outside\n')
            with self.assertRaisesRegex(RuntimeError, 'escapes'):
                installer.verify_artifacts(folder)

    def test_install_requires_stopped_motor_confirmation_before_radio(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            self.artifacts(folder)
            args = SimpleNamespace(install=True, idle_confirmed=False, artifacts=folder)
            with self.assertRaisesRegex(RuntimeError, 'motor stopped'):
                asyncio.run(installer.run(args, {}))

    def test_duplicate_services_choose_one_coherent_latest_instance(self):
        def service(handle):
            return SimpleNamespace(uuid=installer.OTA, handle=handle, characteristics=[
                SimpleNamespace(uuid=installer.UUID[name], handle=handle + index)
                for index, name in enumerate(['build', 'control', 'data', 'status'], 1)])
        client = SimpleNamespace(services=[service(100), service(20)])
        for index, name in enumerate(['build', 'control', 'data', 'status'], 1):
            self.assertEqual(installer.characteristic(client, name).handle, 100 + index)
        client.services[0].characteristics = []
        with self.assertRaisesRegex(RuntimeError, 'Missing/ambiguous'):
            installer.characteristic(client, 'data')

    def test_dose_frame_checksum_and_offsets(self):
        frame = bytearray([166, 1, 0, 1, 0, 0, 125, 0, 2, 0, 50, 0, 16, 39, 0])
        frame[-1] = installer.functools.reduce(lambda a, b: a ^ b, frame[:-1])
        async def read(_):
            return frame
        char = SimpleNamespace(uuid=installer.UUID['dose'])
        client = SimpleNamespace(services=[SimpleNamespace(uuid=installer.DOSE_SERVICE, handle=1, characteristics=[char])], read_gatt_char=read)
        self.assertEqual(asyncio.run(installer.dose_status(client)), {'flags': 1, 'target_g': 12.5, 'slot': 2, 'mode': 0})
        frame[6] ^= 1
        with self.assertRaisesRegex(RuntimeError, 'Invalid dose status'):
            asyncio.run(installer.dose_status(client))


if __name__ == '__main__':
    unittest.main()
