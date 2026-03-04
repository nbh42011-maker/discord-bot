import discord
from discord import app_commands
from discord.ext import commands, tasks
import json
import os

# ---------------- CONFIG ----------------
FREE_GEN_ROLE_ID = 1467913996723032315    # Free Gen role
EXCLUSIVE_ROLE_ID = 1453906576237924603   # Exclusive role
ADMIN_ROLE_ID = 1452719764119093388       # Admin role
STAFF_NOTIFY_USER_ID = 884084052854984726 # Owner/Staff DM for gift cards

REQUIRED_CUSTOM_STATUS = ".gg/marcosstocks | BEST DROPS + GEN IN DISCORD"
OFFICIAL_SERVER_LINK = "https://discord.gg/marcosstocks"

STOCK_FILE = "stock.json"
# ----------------------------------------

intents = discord.Intents.default()
intents.members = True
intents.message_content = True
intents.guilds = True

bot = commands.Bot(command_prefix="!", intents=intents)
tree = bot.tree

# ---------------- DATA MANAGEMENT ----------------
def load_json(file, default):
    if not os.path.exists(file):
        with open(file, "w") as f:
            json.dump(default, f, indent=4)
    with open(file, "r") as f:
        return json.load(f)

def save_json(file, data):
    with open(file, "w") as f:
        json.dump(data, f, indent=4)

stock_data = load_json(STOCK_FILE, {"FREE": {}, "EXCLUSIVE": {}, "categories": []})

# ---------------- HELPERS ----------------
def has_required_status(member):
    for activity in member.activities:
        if isinstance(activity, discord.CustomActivity) and activity.name:
            if REQUIRED_CUSTOM_STATUS.lower() in activity.name.lower():
                return True
    return False

def format_stock():
    embed = discord.Embed(title="📦 Marcos Gen • Stock Overview", color=discord.Color.blue())
    free_section = ""
    for cat, items in stock_data["FREE"].items():
        free_section += f"**{cat}** → {len(items) if items else 'Out of Stock'}\n"
    exclusive_section = ""
    for cat, items in stock_data["EXCLUSIVE"].items():
        exclusive_section += f"**{cat}** → {len(items) if items else 'Out of Stock'}\n"
    embed.add_field(name="🆓 Free Stock", value=free_section if free_section else "No categories.", inline=False)
    embed.add_field(name="💎 Exclusive Stock", value=exclusive_section if exclusive_section else "No categories.", inline=False)
    embed.set_footer(text="Professional • Secure • Automated")
    return embed

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

# ---------------- USER COMMANDS ----------------
@tree.command(name="stock", description="View current stock")
async def stock(interaction: discord.Interaction):
    await interaction.response.send_message(embed=format_stock(), ephemeral=True)

@tree.command(name="gen", description="Generate a Free item")
async def gen(interaction: discord.Interaction):
    member = interaction.user

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
            await interaction.response.send_message("✅ Your Free item has been sent to your DMs!", ephemeral=True)
            try:
                await member.send(f"🎉 **Here is your Free item from {category}:**\n```{item}```")
            except:
                await interaction.followup.send("❌ Could not send DM. Check your privacy settings.", ephemeral=True)
            return
    await interaction.response.send_message("⚠️ Free stock is currently out of items.", ephemeral=True)

@tree.command(name="exclusive-gen", description="Generate an Exclusive item")
async def exclusive_gen(interaction: discord.Interaction):
    member = interaction.user
    role_ids = [r.id for r in member.roles]

    if EXCLUSIVE_ROLE_ID not in role_ids:
        await interaction.response.send_message(
            "❌ You need Exclusive access to use this command.",
            ephemeral=True
        )
        return

    for category, items in stock_data["EXCLUSIVE"].items():
        if items:
            item = items.pop(0)
            save_json(STOCK_FILE, stock_data)
            await interaction.response.send_message("💎 Exclusive item sent to your DMs.", ephemeral=True)
            try:
                await member.send(f"💎 **Here is your Exclusive item from {category}:**\n```{item}```")
            except:
                await interaction.followup.send("❌ Could not send DM. Check your privacy settings.", ephemeral=True)
            return

    await interaction.response.send_message("⚠️ Exclusive stock is currently empty.", ephemeral=True)

# ---------------- REDEEM EXCLUSIVE ----------------
class RedeemModal(discord.ui.Modal, title="💎 Redeem Exclusive Gift Card"):
    code = discord.ui.TextInput(
        label="Enter your Gift Card Code",
        placeholder="Paste your gift card code here",
        required=True
    )

    async def on_submit(self, interaction: discord.Interaction):
        user_code = self.code.value.strip()

        # Send the code to the owner/staff for verification (PRIVATE DM)
        staff_user = await bot.fetch_user(STAFF_NOTIFY_USER_ID)
        await staff_user.send(
            f"🔔 **Gift Card Redeem Request**\n"
            f"User: {interaction.user}\n"
            f"Code: `{user_code}`\n"
            f"Verify the code and grant Exclusive role manually if legit."
        )

        # Notify the user privately
        await interaction.response.send_message(
            "✅ Your code has been submitted for verification.\n"
            "Once verified by staff, you will receive **lifetime Exclusive access**.\n\n"
            "⚠️ Only redeem codes through this official bot. Never share your code with anyone else.",
            ephemeral=True
        )

class RedeemView(discord.ui.View):
    @discord.ui.button(label="Redeem Code", emoji="🔑", style=discord.ButtonStyle.green)
    async def redeem(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(RedeemModal())

@tree.command(name="redeem-exclusive", description="Redeem Exclusive access via gift card")
async def redeem_exclusive(interaction: discord.Interaction):
    embed = discord.Embed(
        title="💎 Redeem Exclusive Access",
        description=(
            "**Get Exclusive Access to Marcos Gen**\n"
            "*Exclusive Accounts • Shorter Cooldowns • Premium Access*\n\n"
            f"⚠️ **SECURITY WARNING**\nOfficial Server: {OFFICIAL_SERVER_LINK}\n"
            "Only redeem gift cards through this official bot."
        ),
        color=discord.Color.purple()
    )
    embed.set_footer(text="Make a ticket if you need additional help.")
    await interaction.response.send_message(embed=embed, view=RedeemView(), ephemeral=True)

# ---------------- ADMIN COMMANDS ----------------
@tree.command(name="addcategory", description="Add a category (Admin only)")
@app_commands.checks.has_role(ADMIN_ROLE_ID)
async def addcategory(interaction: discord.Interaction, category: str):
    if category in stock_data["categories"]:
        await interaction.response.send_message("❌ Category already exists.", ephemeral=True)
        return
    stock_data["categories"].append(category)
    stock_data["FREE"][category] = []
    stock_data["EXCLUSIVE"][category] = []
    save_json(STOCK_FILE, stock_data)
    await interaction.response.send_message(f"✅ Category **{category}** added.", ephemeral=True)

@tree.command(name="removecategory", description="Remove a category (Admin only)")
@app_commands.checks.has_role(ADMIN_ROLE_ID)
async def removecategory(interaction: discord.Interaction, category: str):
    if category not in stock_data["categories"]:
        await interaction.response.send_message("❌ Category does not exist.", ephemeral=True)
        return
    stock_data["categories"].remove(category)
    stock_data["FREE"].pop(category, None)
    stock_data["EXCLUSIVE"].pop(category, None)
    save_json(STOCK_FILE, stock_data)
    await interaction.response.send_message(f"✅ Category **{category}** removed.", ephemeral=True)

@tree.command(name="addstock", description="Add stock (Admin only)")
@app_commands.checks.has_role(ADMIN_ROLE_ID)
async def addstock(interaction: discord.Interaction, type: str, category: str, item: str):
    type = type.upper()
    if type not in ["FREE", "EXCLUSIVE"]:
        await interaction.response.send_message("❌ Type must be FREE or EXCLUSIVE.", ephemeral=True)
        return
    if category not in stock_data["categories"]:
        await interaction.response.send_message("❌ Category does not exist.", ephemeral=True)
        return
    stock_data[type][category].append(item)
    save_json(STOCK_FILE, stock_data)
    await interaction.response.send_message(f"✅ Added **{item}** to {type} stock under **{category}**.", ephemeral=True)

@tree.command(name="removestock", description="Remove stock (Admin only)")
@app_commands.checks.has_role(ADMIN_ROLE_ID)
async def removestock(interaction: discord.Interaction, type: str, category: str, item: str):
    type = type.upper()
    if type not in ["FREE", "EXCLUSIVE"]:
        await interaction.response.send_message("❌ Type must be FREE or EXCLUSIVE.", ephemeral=True)
        return
    if category not in stock_data["categories"]:
        await interaction.response.send_message("❌ Category does not exist.", ephemeral=True)
        return
    if item not in stock_data[type][category]:
        await interaction.response.send_message("❌ Item not found.", ephemeral=True)
        return
    stock_data[type][category].remove(item)
    save_json(STOCK_FILE, stock_data)
    await interaction.response.send_message(f"✅ Removed **{item}** from {type} stock under **{category}**.", ephemeral=True)

# ---------------- BOOST FEATURE ----------------
@tasks.loop(minutes=5)
async def check_boosts():
    for guild in bot.guilds:
        for member in guild.members:
            try:
                role = guild.get_role(EXCLUSIVE_ROLE_ID)
                if member.premium_since:
                    if role not in member.roles:
                        await member.add_roles(role)
                else:
                    if role in member.roles:
                        await member.remove_roles(role)
            except:
                continue

# ---------------- RUN ----------------
TOKEN = os.getenv("TOKEN")
bot.run(TOKEN)
