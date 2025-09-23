#!/usr/bin/env python3

import asyncio
from bleak import BleakScanner, BleakClient

async def connect_and_stream():
    devices = await BleakScanner.discover(timeout=10.0)
    gan_cube = None

    for device in devices:
        if device.name and ("GAN" in device.name.upper() or "GI" in device.name.upper()):
            gan_cube = device
            break

    if not gan_cube:
        return

    async with BleakClient(gan_cube.address) as client:
        def handler(sender, data):
            print(data.hex())

        await client.start_notify("28be4cb6-cd67-11e9-a32f-2a2ae2dbcce4", handler)

        while True:
            await asyncio.sleep(1)

asyncio.run(connect_and_stream())
