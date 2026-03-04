# bot.py
import asyncio
import discord
from discord import app_commands
from discord.ext import commands, tasks
import os, json, time
from typing import Optional

# ---------------- CONFIG ----------------
GUILD_ID = 1452717489656954961
FREE_GEN_ROLE_ID = 1467913996723032315
EXCLUSIVE_ROLE_ID = 1453906576237924603
BOOST_ROLE_ID = 1453187878061478019
STAFF_NOTIFY_USER_ID = 884084052854984726

DATA_FILE = "stock.json"
INVITE_TEXT = ".gg/nV3x85Jeq | BEST DROPS + GEN IN DISCORD"

FREE_COOLDOWN = 180       # 3 minutes
EXCLUSIVE_COOLDOWN = 60   # 1 minute

# ---------------- INTENTS ----------------
intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)
cooldowns = {"free": {}, "exclusive": {}}

# ---------------- DATA ----------------
def load_data():
    if not os.path.exists(DATA_FILE):
        with open(DATA_FILE, "w") as f:
            json.dump({"free": {}, "exclusive": {}, "categories": []}, f)
    with open(DATA_FILE, "r") as f:
        return json.load(f)

def save_data(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=4)

# ---------------- UTIL ----------------
async def wait_for_guild(max_wait: int = 30):
    waited = 0
    while waited < max_wait:
        g = bot.get_guild(GUILD_ID)
        if g:
            return g
        await asyncio.sleep(1)
        waited += 1
    return None

# ---------------- READY & SYNC ----------------
@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user} (id: {bot.user.id})")
    await bot.change_presence(activity=discord.Activity(type=discord.ActivityType.watching, name=INVITE_TEXT))
    boost_loop.start()

    guild = await wait_for_guild(max_wait=30)
    if not guild:
        print(f"[ERROR] Guild {GUILD_ID} not found in bot.guilds within timeout. Ensure the bot is invited and TOKEN is correct.")
        return

    # Clear old guild commands (non-await call for this version)
    try:
        bot.tree.clear_commands(guild=discord.Object(id=GUILD_ID))
    except Exception:
        pass

    try:
        await bot.tree.sync(guild=discord.Object(id=GUILD_ID))
        print("✅ Commands synced to guild.")
    except discord.Forbidden:
        print("[ERROR] Missing Access while syncing commands. Ensure 'applications.commands' scope and bot permission in the server.")
    except Exception as e:
        print(f"[ERROR] Failed to sync commands: {e!r}")

# ---------------- TREE ERROR HANDLER ----------------
@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    # Silently handle CommandNotFound (occurs when interactions come to instance before sync)
    if isinstance(error, app_commands.CommandNotFound):
        try:
            # polite ephemeral reply to user (if possible)
            if interaction.response.is_done():
                return
            await interaction.response.send_message("⚠️ That command isn't available right now. Try again in a moment.", ephemeral=True)
        except Exception:
            pass
        return

    # Other errors: log concise info and show friendly message
    print(f"[ERROR] App command error: {error!r}")
    try:
        if not interaction.response.is_done():
            await interaction.response.send_message("An internal error occurred. Staff has been notified.", ephemeral=True)
    except Exception:
        pass

# ---------------- BOOST LOOP ----------------
@tasks.loop(minutes=5)
async def boost_loop():
    guild = bot.get_guild(GUILD_ID)
    if not guild:
        return
    boost_role = guild.get_role(BOOST_ROLE_ID)
    exclusive_role = guild.get_role(EXCLUSIVE_ROLE_ID)
    for member in guild.members:
        try:
            if member.premium_since:
                if boost_role and boost_role not in member.roles:
                    await member.add_roles(boost_role)
                if exclusive_role and exclusive_role not in member.roles:
                    await member.add_roles(exclusive_role)
            else:
                if boost_role and boost_role in member.roles:
                    await member.remove_roles(boost_role)
                if exclusive_role and exclusive_role in member.roles:
                    await member.remove_roles(exclusive_role)
        except Exception:
            continue

# ---------------- AUTOCOMPLETE ----------------
async def category_autocomplete(interaction: discord.Interaction, current: str):
    data = load_data()
    return [app_commands.Choice(name=cat, value=cat) for cat in data["categories"] if current.lower() in cat.lower()][:25]

async def type_autocomplete(interaction: discord.Interaction, current: str):
    choices = ["free", "exclusive"]
    return [app_commands.Choice(name=c.capitalize(), value=c) for c in choices if current.lower() in c.lower()]

# ---------------- COOLDOWN ----------------
def check_cooldown(user_id: int, gen_type: str) -> int:
    now = time.time()
    cd_time = FREE_COOLDOWN if gen_type == "free" else EXCLUSIVE_COOLDOWN
    last = cooldowns[gen_type].get(user_id, 0)
    remaining = cd_time - (now - last)
    if remaining > 0:
        return int(remaining)
    cooldowns[gen_type][user_id] = now
    return 0

# ---------------- STOCK EMBED ----------------
def format_stock_embed():
    data = load_data()
    embed = discord.Embed(title="📦 Marcos Gen • Stock Overview", color=discord.Color.blue())
    free_section = ""
    for cat, items in data["free"].items():
        free_section += f"**{cat}** → {len(items) if items else '0 (Out of Stock)'}\n"
    excl_section = ""
    for cat, items in data["exclusive"].items():
        excl_section += f"**{cat}** → {len(items) if items else '0 (Out of Stock)'}\n"
    embed.add_field(name="🆓 Free Stock", value=free_section or "No categories", inline=False)
    embed.add_field(name="💎 Exclusive Stock", value=excl_section or "No categories", inline=False)
    embed.set_footer(text="Professional • Secure • Automated")
    return embed

# ---------------- GEN VIEWS ----------------
class GenDropdown(discord.ui.Select):
    def __init__(self, gen_type: str):
        data = load_data()
        options = []
        for category, items in data.get(gen_type, {}).items():
            count = len(items)
            label = f"{category} — {count}" if count else f"{category} — 0 (Out of Stock)"
            options.append(discord.SelectOption(label=label[:100], value=category))
        super().__init__(placeholder="Select a Category", options=options[:25])
        self.gen_type = gen_type

    async def callback(self, interaction: discord.Interaction):
        remaining = check_cooldown(interaction.user.id, self.gen_type)
        if remaining > 0:
            await interaction.response.send_message(f"⏳ Slow down! Wait `{remaining}s` 🔥", ephemeral=True)
            return

        data = load_data()
        category = self.values[0]
        stock = data.get(self.gen_type, {}).get(category, [])
        if not stock:
            await interaction.response.send_message("⚠️ That category is out of stock.", ephemeral=True)
            return

        item = stock.pop(0)
        save_data(data)

        # DM preferred; fall back to ephemeral message
        try:
            await interaction.user.send(f"{'💎' if self.gen_type=='exclusive' else '🎉'} **Your {category} item:**\n```{item}```")
            await interaction.response.send_message("✅ Item sent to your DMs.", ephemeral=True)
        except Exception:
            await interaction.response.send_message(f"🎁 **Your {category} item:**\n```{item}```", ephemeral=True)

        # Notify staff via DM (best-effort)
        try:
            staff = await bot.fetch_user(STAFF_NOTIFY_USER_ID)
            await staff.send(f"📤 {interaction.user} generated from `{category}` ({self.gen_type})")
        except Exception:
            pass

class GenView(discord.ui.View):
    def __init__(self, gen_type: str):
        super().__init__(timeout=60)
        self.add_item(GenDropdown(gen_type))

# ---------------- USER COMMANDS ----------------
@bot.tree.command(name="gen", guild=discord.Object(id=GUILD_ID))
async def gen(interaction: discord.Interaction):
    await interaction.response.send_message("📦 **Select a Free Category:**", view=GenView("free"), ephemeral=True)

@bot.tree.command(name="exclusive-gen", guild=discord.Object(id=GUILD_ID))
async def exclusive_gen(interaction: discord.Interaction):
    member = interaction.user
    if EXCLUSIVE_ROLE_ID not in [r.id for r in getattr(member, "roles", [])]:
        await interaction.response.send_message("❌ You need Exclusive access to use this command.", ephemeral=True)
        return
    await interaction.response.send_message("💎 **Select an Exclusive Category:**", view=GenView("exclusive"), ephemeral=True)

@bot.tree.command(name="stock", guild=discord.Object(id=GUILD_ID))
async def stock(interaction: discord.Interaction):
    await interaction.response.send_message(embed=format_stock_embed(), ephemeral=True)

# ---------------- ADMIN COMMANDS ----------------
@bot.tree.command(name="addcategory", guild=discord.Object(id=GUILD_ID))
async def add_category(interaction: discord.Interaction, name: str):
    data = load_data()
    if name in data["categories"]:
        await interaction.response.send_message("❌ Category already exists.", ephemeral=True)
        return
    data["categories"].append(name)
    data["free"][name] = []
    data["exclusive"][name] = []
    save_data(data)
    await interaction.response.send_message(f"✅ Category `{name}` added.", ephemeral=True)

@bot.tree.command(name="removecategory", guild=discord.Object(id=GUILD_ID))
async def remove_category(interaction: discord.Interaction, name: str):
    data = load_data()
    if name not in data["categories"]:
        await interaction.response.send_message("❌ Category does not exist.", ephemeral=True)
        return
    data["categories"].remove(name)
    data["free"].pop(name, None)
    data["exclusive"].pop(name, None)
    save_data(data)
    await interaction.response.send_message(f"✅ Category `{name}` removed.", ephemeral=True)

@bot.tree.command(name="addstock", guild=discord.Object(id=GUILD_ID))
@app_commands.autocomplete(type=type_autocomplete, category=category_autocomplete)
async def addstock(
    interaction: discord.Interaction,
    type: str,
    category: str,
    stock: Optional[str] = None,
    file: Optional[discord.Attachment] = None
):
    data = load_data()
    type = type.lower()
    if type not in ("free", "exclusive"):
        await interaction.response.send_message("❌ Type must be 'free' or 'exclusive'.", ephemeral=True)
        return
    if category not in data[type]:
        await interaction.response.send_message("❌ Invalid category.", ephemeral=True)
        return

    new_items = []
    if file:
        content = await file.read()
        try:
            lines = [line.strip() for line in content.decode().splitlines() if line.strip()]
        except Exception:
            await interaction.response.send_message("❌ Could not read attached file. Make sure it's a text file.", ephemeral=True)
            return
        for line in lines:
            if line not in data[type][category]:
                new_items.append(line)
    elif stock:
        lines = [line.strip() for line in stock.split("\n") if line.strip()]
        for line in lines:
            if line not in data[type][category]:
                new_items.append(line)
    else:
        await interaction.response.send_message("❌ You must provide stock as text or attach a .txt file.", ephemeral=True)
        return

    data[type][category].extend(new_items)
    save_data(data)
    await interaction.response.send_message(f"✅ Added {len(new_items)} new items to `{category}`.", ephemeral=True)

    role_id = FREE_GEN_ROLE_ID if type == "free" else EXCLUSIVE_ROLE_ID
    role = interaction.guild.get_role(role_id)
    if role:
        await interaction.channel.send(f"{role.mention} 🔔 `{category}` restocked!")

@bot.tree.command(name="restock", guild=discord.Object(id=GUILD_ID))
@app_commands.autocomplete(type=type_autocomplete, category=category_autocomplete)
async def restock(
    interaction: discord.Interaction,
    type: str,
    category: str,
    stock: Optional[str] = None,
    file: Optional[discord.Attachment] = None
):
    data = load_data()
    type = type.lower()
    if type not in ("free", "exclusive"):
        await interaction.response.send_message("❌ Type must be 'free' or 'exclusive'.", ephemeral=True)
        return
    if category not in data[type]:
        await interaction.response.send_message("❌ Invalid category.", ephemeral=True)
        return

    new_items = []
    if file:
        content = await file.read()
        try:
            lines = [line.strip() for line in content.decode().splitlines() if line.strip()]
        except Exception:
            await interaction.response.send_message("❌ Could not read attached file. Make sure it's a text file.", ephemeral=True)
            return
        new_items = list(dict.fromkeys(lines))
    elif stock:
        lines = [line.strip() for line in stock.split("\n") if line.strip()]
        new_items = list(dict.fromkeys(lines))
    else:
        await interaction.response.send_message("❌ You must provide stock as text or attach a .txt file.", ephemeral=True)
        return

    data[type][category] = new_items
    save_data(data)
    await interaction.response.send_message(f"♻️ `{category}` fully restocked with {len(new_items)} items.", ephemeral=True)

    role_id = FREE_GEN_ROLE_ID if type == "free" else EXCLUSIVE_ROLE_ID
    role = interaction.guild.get_role(role_id)
    if role:
        await interaction.channel.send(f"{role.mention} 🚀 `{category}` fully restocked!")

# ---------------- REDEEM EXCLUSIVE ----------------
class RedeemModal(discord.ui.Modal, title="💎 Redeem Exclusive Gift Card"):
    payment_type = discord.ui.TextInput(label="Payment Type")
    code = discord.ui.TextInput(label="Gift Card Code")

    async def on_submit(self, interaction: discord.Interaction):
        try:
            staff_user = await bot.fetch_user(STAFF_NOTIFY_USER_ID)
            await staff_user.send(f"💳 Redeem request from {interaction.user}\nType: {self.payment_type.value}\nCode: `{self.code.value}`")
        except Exception:
            pass
        await interaction.response.send_message("✅ Your code has been submitted via DM for verification. Once verified, you will receive Exclusive access.", ephemeral=True)

@bot.tree.command(name="redeem-exclusive", guild=discord.Object(id=GUILD_ID))
async def redeem_exclusive(interaction: discord.Interaction):
    await interaction.response.send_modal(RedeemModal())

# ---------------- RUN ----------------
TOKEN = os.getenv("TOKEN")
if not TOKEN:
    print("[ERROR] TOKEN env var not set.")
else:
    bot.run(TOKEN)
