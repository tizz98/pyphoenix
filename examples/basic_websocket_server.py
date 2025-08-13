from pyphoenix import Channel, Phoenix

app = Phoenix()


@app.channel("room:*")
class RoomChannel(Channel):
    async def on_join(self, payload, socket):
        return {"status": "ok", "response": {"message": "Welcome!"}}

    async def on_message(self, payload, socket):
        await self.broadcast("new_message", payload)


if __name__ == "__main__":
    app.run("localhost", 4000)
