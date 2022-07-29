"""Websocket stress testing for resolwe/observers."""

import asyncio
import websockets
import requests


async def hello():
    async with websockets.connect("ws://localhost:8000/ws/ss") as websocket:
        await websocket.send("Hello world!")
        print(await websocket.recv())


asyncio.run(hello())
