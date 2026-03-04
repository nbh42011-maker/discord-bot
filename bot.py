import discord
from discord.ext import commands, tasks
from discord import app_commands
import json
import os

# ---------------- CONFIG ----------------
FREE_GEN_ROLE_ID = 111111111111111111   # Role to give for Free Gen
EXCLUSIVE_ROLE_ID = 222222222222222222
ADMIN_ROLE_ID = 333333333333333333
STAFF_NOTIFY_USER_ID = 444444444444444444

REQUIRED_CUSTOM_STATUS = ".gg/marcosstocks | BEST DROPS + GEN IN DISCORD"

STOCK_FILE = "stock.json"
CODES_FILE = "codes.json"
# ----------------------------------------

intents = discord.Intents.default()
intents.members = True
intents.message_content = True
intents.guilds = True

bot = commands.Bot(command_prefix="!", intents=intents)
tree = bot.tree

# ---------------- LOAD DATA ----------------
def load_json(file, default):
    if not os.path.exists(file):
        with open(file, "w") as f:
            json.dump(default, f, indent=4)
    with open(file, "r") as f:
        return json.load(f)

def save_json(file, data):
    with open(file, "w") as f:
        json.dump(data, f, indent=4)

stock_data = load_json(STOCK_FILE, {"FREE": {}, "EXCLUSIVE": {}})
codes_data = load_json(CODES_FILE, {"exclusive_codes": []})

# ---------------- EVENTS ----------------
@bot.event
async def on_ready():
    await tree.sync()
    check_boosts.start()
    await bot.change_presence(
        activity=discord.Activity(
            type=discord.ActivityType.watching,
            name=REQUIRED_CUSTOM_STATUS
        )
    )
    print(f"✅ Logged in as {bot.user}")

# ---------------- HELPER ----------------
def has_required_status(member):
    for activity in member.activities:
        if isinstance(activity, discord.CustomActivity) and activity.name:
            if REQUIRED_CUSTOM_STATUS.lower() in activity.name.lower():
                return True
    return False

# ---------------- STOCK EMBED ----------------
def format_stock():
    embed = discord.Embed(title="📦 Marcos Gen • Stock", color=discord.Color.blue())
    free_section = ""
    for cat, items in stock_data["FREE"].items():
        free_section += f"**{cat}** → {len(items) if items else 'Out of Stock'}\n"
    exclusive_section = ""
    for cat, items in stock_data["EXCLUSIVE"].items():
        exclusive_section += f"**{cat}** → {len(items) if items else 'Out of Stock'}\n"
    embed.add_field(name="🆓 Free Stock", value=free_section if free_section else "No categories.", inline=False)
    embed.add_field(name="💎 Exclusive Stock", value=exclusive_section if exclusive_section else "No categories.", inline=False)
    return embed

# ---------------- COMMANDS ----------------
@tree.command(name="stock", description="View current stock")
async def stock(interaction: discord.Interaction):
    await interaction.response.send_message(embed=format_stock(), ephemeral=True)

@tree.command(name="gen", description="Generate a Free item")
async def gen(interaction: discord.Interaction):
    member = interaction.user
    role_ids = [r.id for r in member.roles]

    # Check custom status
    if not has_required_status(member):
        await interaction.response.send_message(
            f"❌ You do not have the required custom status to access Free Gen.\n\n"
            f"Please set your Discord custom status to:\n"
            f"`{REQUIRED_CUSTOM_STATUS}`\n\n"
            f"Once you have it, the bot will automatically grant you Free Gen access.",
            ephemeral=True
        )
        return

    # Grant Free Gen role if not already
    free_role = interaction.guild.get_role(FREE_GEN_ROLE_ID)
    if free_role and free_role not in member.roles:
        await member.add_roles(free_role)

    # Send item from Free stock
    for category, items in stock_data["FREE"].items():
        if items:
            item = items.pop(0)
            save_json(STOCK_FILE, stock_data)
            await interaction.response.send_message(
                "✅ Your Free item has been sent to your DMs!", ephemeral=True
            )
            try:
                await member.send(f"🎉 **Here is your Free item from {category}:**\n```{item}```")
            except:
                await interaction.followup.send(
                    "❌ Could not send DM. Check your privacy settings.", ephemeral=True
                )
            return

    await interaction.response.send_message("⚠️ Free stock is currently out of items.", ephemeral=True)

# ---------------- REDEEM EXCLUSIVE ----------------
class RedeemModal(discord.ui.Modal, title="🔑 Redeem Exclusive Code"):
    code = discord.ui.TextInput(
        label="Enter Your Code",
        placeholder="Paste your exclusive code here",
        required=True
    )

    async def on_submit(self, interaction: discord.Interaction):
        user_code = self.code.value.strip()
        if user_code not in codes_data["exclusive_codes"]:
            await interaction.response.send_message("❌ Invalid or already used code.", ephemeral=True)
            return

        codes_data["exclusive_codes"].remove(user_code)
        save_json(CODES_FILE, codes_data)

        role = interaction.guild.get_role(EXCLUSIVE_ROLE_ID)
        await interaction.user.add_roles(role)

        staff_user = await bot.fetch_user(STAFF_NOTIFY_USER_ID)
        await staff_user.send(f"🔔 Code Redeemed\nUser: {interaction.user}\nCode: {user_code}")

        await interaction.response.send_message(
            "✅ **Exclusive Access Activated!** Enjoy shorter cooldowns and premium stock.", ephemeral=True
        )

class RedeemView(discord.ui.View):
    @discord.ui.button(label="Redeem Code", emoji="🔑", style=discord.ButtonStyle.green)
    async def redeem(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(RedeemModal())

@tree.command(name="redeem-exclusive", description="Redeem Exclusive access.")
async def redeem_exclusive(interaction: discord.Interaction):
    embed = discord.Embed(
        title="💎 Redeem Exclusive Access",
        description=(
            "**Get Exclusive Access to Marcos Gen**\n"
            "*Exclusive Accounts • Shorter Cooldowns • Premium Access*\n\n"
            "⚠️ **SECURITY WARNING**\n"
            "Only redeem codes through this official bot."
        ),
        color=discord.Color.purple()
    )
    embed.set_footer(text="Make a ticket if you need additional help.")
    await interaction.response.send_message(embed=embed, view=RedeemView(), ephemeral=True)

# ---------------- BOOST FEATURE ----------------
@tasks.loop(minutes=5)
async def check_boosts():
    for guild in bot.guilds:
        for member in guild.members:
            try:
                # This automatically grants/removes exclusive role based on boost
                if member.premium_since:
                    role = guild.get_role(EXCLUSIVE_ROLE_ID)
                    if role not in member.roles:
                        await member.add_roles(role)
                else:
                    role = guild.get_role(EXCLUSIVE_ROLE_ID)
                    if role in member.roles:
                        await member.remove_roles(role)
            except:
                continue

# ---------------- RUN ----------------
TOKEN = os.getenv("TOKEN")
bot.run(TOKEN)
