import discord
from discord.ext import commands
import os

GUILD_ID = 1452717489656954961
TOKEN = os.getenv("TOKEN")

bot = commands.Bot(command_prefix="!", intents=discord.Intents.default())

@bot.event
async def on_ready():
    guild = bot.get_guild(GUILD_ID)
    # Clears all commands for this guild
    await bot.tree.clear_commands(guild=guild)
    print("✅ Old commands cleared")
    await bot.close()

bot.run(TOKEN)
