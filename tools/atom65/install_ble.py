#!/usr/bin/env python3
"""Read-only inspection or explicit OTA of the custom Atom65 GPIO1 firmware family."""
import argparse
import asyncio
import functools
import hashlib
import json
import struct
import time
from pathlib import Path
from bleak import BleakClient, BleakScanner

TARGET_BUILD = 19
TARGET_VERSION = '1.4.0-atom65-decaid-oled'
OTA = '12345678-1234-1234-1234-123456789abc'
SYS = '77889900-aabb-ccdd-eeff-112233445566'
DOSE_SERVICE = '5e5d6500-3f45-4b8c-9a65-28b4858d23d4'
UUID = {
    'build': '66666666-7777-8888-9999-000000000000',
    'info': '88990011-bbcc-ddee-ff11-223344556677',
    'control': '11111111-2222-3333-4444-555555555555',
    'data': '87654321-4321-4321-4321-cba987654321',
    'status': 'aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee',
    'dose': '5e5d6502-3f45-4b8c-9a65-28b4858d23d4',
}


def characteristic(client, name):
    """Never mix data/control handles from different duplicate service instances."""
    service_uuid = SYS if name == 'info' else DOSE_SERVICE if name == 'dose' else OTA
    services = [s for s in client.services if s.uuid.lower() == service_uuid]
    if not services:
        raise RuntimeError('Missing expected service ' + service_uuid)
    service = max(services, key=lambda s: s.handle)
    chars = [c for c in service.characteristics if c.uuid.lower() == UUID[name]]
    if len(chars) != 1:
        raise RuntimeError('Missing/ambiguous characteristic in selected service: ' + name)
    return chars[0]


def verify_artifacts(folder):
    hashes = {}
    for line in (folder / 'SHA256SUMS').read_text().splitlines():
        digest, name = line.split(None, 1)
        path = (folder / name.strip()).resolve()
        if not path.is_relative_to(folder.resolve()):
            raise RuntimeError('Checksum path escapes artifact directory')
        if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise RuntimeError('Checksum mismatch: ' + name)
        hashes[name.strip()] = digest
    for required in ('firmware.bin', 'firmware-full.ota'):
        if required not in hashes:
            raise RuntimeError('Missing release checksum: ' + required)
    binary = (folder / 'firmware.bin').read_bytes()
    patch = (folder / 'firmware-full.ota').read_bytes()
    if not 0 < len(binary) < 0x300000 or not 0 < len(patch) < 0x200000:
        raise RuntimeError('Image does not fit the existing partition map')
    return hashes, patch


async def find(address=None):
    advertisements = await BleakScanner.discover(timeout=8, return_adv=True)
    matches = []
    for device, adv in advertisements.values():
        if address and device.address.lower() != address.lower():
            continue
        if device.name == 'GrindByWeight' or adv.local_name == 'GrindByWeight' or DOSE_SERVICE in [u.lower() for u in adv.service_uuids]:
            matches.append(device)
    if len(matches) != 1:
        raise RuntimeError('Expected one grinder; enable Bluetooth, release other clients, move close, or use --address. Matches: ' + str([d.address for d in matches]))
    return matches[0]


async def info(client):
    for _ in range(25):
        raw = bytes(await client.read_gatt_char(characteristic(client, 'info')))
        if raw:
            return json.loads(raw.decode())
        await asyncio.sleep(.5)
    raise RuntimeError('Firmware information not available')


async def close(client):
    try:
        await asyncio.wait_for(client.disconnect(), 5)
    except Exception:
        pass


async def dose_status(client):
    raw = bytes(await client.read_gatt_char(characteristic(client, 'dose')))
    if len(raw) != 15 or raw[:2] != bytes([166, 1]) or functools.reduce(lambda a, b: a ^ b, raw) != 0:
        raise RuntimeError('Invalid dose status')
    return {'flags': raw[3], 'target_g': int.from_bytes(raw[6:8], 'little') / 10, 'slot': raw[8], 'mode': raw[9]}


async def run(args, record):
    hashes, patch = verify_artifacts(args.artifacts) if args.install else ({}, b'')
    if args.install and not args.idle_confirmed:
        raise RuntimeError('OTA restarts the controller. Confirm motor stopped/main weight screen with --idle-confirmed')
    device = await find(args.address)
    client = BleakClient(device, timeout=20)
    try:
        await client.connect()
        before = await info(client)
        build = int((await client.read_gatt_char(characteristic(client, 'build'))).decode())
        record.update(before=before, before_build=build, device_address=device.address)
        if not before['version'].startswith(('1.4.0-atom-v11-gpio1-motor-test', '1.4.0-atom65-decaid')):
            raise RuntimeError('Unsupported source family; match the board/interface before using this image')
        if any(s.uuid.lower() == DOSE_SERVICE for s in client.services):
            record['dose_before'] = await dose_status(client)
            if args.install and (not record['dose_before']['flags'] & 1 or record['dose_before']['flags'] & 14):
                raise RuntimeError('Grinder is not idle/ready')
        if not args.install:
            return
        if build == TARGET_BUILD and before['version'] == TARGET_VERSION:
            record['already_installed'] = True
        else:
            if build not in (12, 13, 14, 15, 17, 18):
                raise RuntimeError('Unexpected source build; refusing downgrade/unknown update: ' + str(build))
            record['hashes'] = hashes
            statuses = []
            await client.start_notify(characteristic(client, 'status'), lambda _, data: statuses.append(data[0] if data else None))
            b = str(TARGET_BUILD).encode()
            v = TARGET_VERSION.encode()
            start = bytes([1]) + struct.pack('<I', len(patch)) + bytes([1, len(b)]) + b + bytes([len(v)]) + v
            await asyncio.wait_for(client.write_gatt_char(characteristic(client, 'control'), start, response=True), 20)
            until = time.monotonic() + 20
            while 2 not in statuses and time.monotonic() < until:
                if any(s in (4, 5) for s in statuses):
                    raise RuntimeError('OTA start rejected')
                await asyncio.sleep(.1)
            if 2 not in statuses:
                raise RuntimeError('No receiving acknowledgement')
            previous = -1
            for offset in range(0, len(patch), 512):
                await asyncio.wait_for(client.write_gatt_char(characteristic(client, 'data'), patch[offset:offset + 512], response=True), 15)
                if any(s in (4, 5) for s in statuses):
                    raise RuntimeError('OTA transfer rejected')
                progress = min(100, (offset + 512) * 100 // len(patch))
                if progress // 10 != previous:
                    previous = progress // 10
                    print('Transfer: ' + str(progress) + '%', flush=True)
                await asyncio.sleep(.01)
            try:
                await asyncio.wait_for(client.write_gatt_char(characteristic(client, 'control'), bytes([3]), response=True), 12)
            except Exception as error:
                record['end_response'] = type(error).__name__ + ': ' + str(error)
    finally:
        await close(client)
    if not args.install:
        return
    await asyncio.sleep(5)
    last = None
    for _ in range(3):
        client = None
        try:
            client = BleakClient(await find(args.address), timeout=20)
            await client.connect()
            after = await info(client)
            if after.get('build') != TARGET_BUILD or after.get('version') != TARGET_VERSION:
                raise RuntimeError('Expected build19 after reboot: ' + str(after))
            record.update(after=after, dose_after=await dose_status(client), installed=True)
            return
        except Exception as error:
            last = error
        finally:
            if client:
                await close(client)
        await asyncio.sleep(2)
    raise RuntimeError('Post-update verification failed: ' + str(last))


def main():
    here = Path(__file__).resolve().parent
    default = here if (here / 'firmware.bin').exists() else here.parents[1] / 'release/atom65-build19'
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--inspect', action='store_true', help='Read-only (also the default)')
    mode.add_argument('--install', action='store_true')
    parser.add_argument('--idle-confirmed', action='store_true')
    parser.add_argument('--address', help='BLE address or macOS peripheral UUID')
    parser.add_argument('--artifacts', type=Path, default=default)
    parser.add_argument('--record', type=Path, default=Path('local-install-record.json'))
    args = parser.parse_args()
    record = {'installed': False, 'target_build': TARGET_BUILD, 'target_version': TARGET_VERSION, 'motor_commands_sent': False, 'read_only': not args.install}
    try:
        asyncio.run(run(args, record))
    except BaseException as error:
        record['error'] = type(error).__name__ + ': ' + str(error)
        raise
    finally:
        args.record.write_text(json.dumps(record, indent=2) + '\n')
        print(json.dumps(record, indent=2))


if __name__ == '__main__':
    main()
