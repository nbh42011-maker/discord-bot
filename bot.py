import discord
import os

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

client = discord.Client(intents=intents)

TOKEN = os.getenv("TOKEN")

@client.event
async def on_ready():
    print(f"Logged in as {client.user}")

@client.event
async def on_message(message):
    if message.author.bot:
        return

    if message.content == "!ping":
        await message.channel.send("Pong!")

client.run(TOKEN)
