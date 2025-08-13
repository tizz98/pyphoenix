import asyncio

from pyphoenix import ClientSocket


async def main():
    client = ClientSocket("ws://localhost:4000/socket")
    await client.connect()

    room = client.channel("room:lobby")

    @room.on("new_message")
    async def on_message(payload, ref):
        print(f"Message: {payload}")

    await room.join()
    await room.push("message", {"text": "Hello, world!"})

    await asyncio.sleep(10)
    await room.leave()
    await client.disconnect()


asyncio.run(main())
