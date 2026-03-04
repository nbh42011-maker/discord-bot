import discord
from discord import app_commands
from discord.ext import commands, tasks
import os
import json
import time

# ================= CONFIG =================
GUILD_ID = 1452717489656954961        # Your server ID
FREE_GEN_ROLE_ID = 1467913996723032315
EXCLUSIVE_ROLE_ID = 1453906576237924603
BOOST_ROLE_ID = 1453187878061478019
STAFF_NOTIFY_USER_ID = 884084052854984726  # Staff/owner to receive DMs

DATA_FILE = "stock.json"
INVITE_TEXT = ".gg/nV3x85Jeq | BEST DROPS + GEN IN DISCORD"

FREE_COOLDOWN = 180       # 3 min
EXCLUSIVE_COOLDOWN = 60   # 1 min

# ==========================================
intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)
cooldowns = {"free": {}, "exclusive": {}}

# ---------------- DATA MANAGEMENT ----------------
def load_data():
    if not os.path.exists(DATA_FILE):
        with open(DATA_FILE, "w") as f:
            json.dump({"free": {}, "exclusive": {}, "categories": []}, f)
    with open(DATA_FILE, "r") as f:
        return json.load(f)

def save_data(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=4)

# ---------------- PRESENCE & READY ----------------
@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")
    await bot.change_presence(
        activity=discord.Activity(
            type=discord.ActivityType.watching,
            name=INVITE_TEXT
        )
    )
    boost_loop.start()
    await bot.tree.sync(guild=discord.Object(id=GUILD_ID))

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
                if boost_role not in member.roles:
                    await member.add_roles(boost_role)
                if exclusive_role and exclusive_role not in member.roles:
                    await member.add_roles(exclusive_role)
            else:
                if boost_role in member.roles:
                    await member.remove_roles(boost_role)
                if exclusive_role and exclusive_role in member.roles:
                    await member.remove_roles(exclusive_role)
        except:
            continue

# ---------------- AUTOCOMPLETE ----------------
async def category_autocomplete(interaction, current):
    data = load_data()
    return [app_commands.Choice(name=cat, value=cat)
            for cat in data["categories"] if current.lower() in cat.lower()][:25]

async def type_autocomplete(interaction, current):
    types = ["free", "exclusive"]
    return [app_commands.Choice(name=t.capitalize(), value=t) for t in types if current.lower() in t.lower()]

# ---------------- COOLDOWN CHECK ----------------
def check_cooldown(user_id, gen_type):
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
    embed.add_field(name="🆓 Free Stock", value=free_section if free_section else "No categories", inline=False)
    embed.add_field(name="💎 Exclusive Stock", value=excl_section if excl_section else "No categories", inline=False)
    embed.set_footer(text="Professional • Secure • Automated")
    return embed

# ---------------- GEN VIEW ----------------
class GenDropdown(discord.ui.Select):
    def __init__(self, gen_type):
        data = load_data()
        options = []
        for category, items in data[gen_type].items():
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
        stock = data[self.gen_type].get(category, [])
        if not stock:
            await interaction.response.send_message("⚠️ That category is out of stock.", ephemeral=True)
            return
        item = stock.pop(0)
        save_data(data)
        await interaction.response.send_message(f"🎁 **Your {category} account:**\n```{item}```", ephemeral=True)
        try:
            staff_user = await bot.fetch_user(STAFF_NOTIFY_USER_ID)
            await staff_user.send(f"📤 {interaction.user} generated from `{category}` ({self.gen_type})")
        except:
            pass

class GenView(discord.ui.View):
    def __init__(self, gen_type):
        super().__init__(timeout=60)
        self.add_item(GenDropdown(gen_type))

# ---------------- USER COMMANDS ----------------
@bot.tree.command(name="gen", guild=discord.Object(id=GUILD_ID))
async def gen(interaction: discord.Interaction):
    await interaction.response.send_message("📦 **Select a Category:**", view=GenView("free"), ephemeral=True)

@bot.tree.command(name="exclusive-gen", guild=discord.Object(id=GUILD_ID))
async def exclusive_gen(interaction: discord.Interaction):
    await interaction.response.send_message("💎 **Select Exclusive Category:**", view=GenView("exclusive"), ephemeral=True)

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
async def addstock(interaction: discord.Interaction, type: str, category: str, stock: str):
    type = type.lower()
    data = load_data()
    if category not in data[type]:
        await interaction.response.send_message("❌ Invalid category.", ephemeral=True)
        return
    items = [x.strip() for x in stock.split("\n") if x.strip()]
    data[type][category].extend(items)
    save_data(data)
    await interaction.response.send_message(f"✅ Added {len(items)} stock to `{category}`.", ephemeral=True)
    role_id = FREE_GEN_ROLE_ID if type == "free" else EXCLUSIVE_ROLE_ID
    role = interaction.guild.get_role(role_id)
    if role:
        await interaction.channel.send(f"{role.mention} 🔔 `{category}` restocked!")

@bot.tree.command(name="restock", guild=discord.Object(id=GUILD_ID))
@app_commands.autocomplete(type=type_autocomplete, category=category_autocomplete)
async def restock(interaction: discord.Interaction, type: str, category: str, stock: str):
    type = type.lower()
    data = load_data()
    items = [x.strip() for x in stock.split("\n") if x.strip()]
    data[type][category] = items
    save_data(data)
    await interaction.response.send_message(f"♻️ `{category}` fully restocked with {len(items)} items.", ephemeral=True)
    role_id = FREE_GEN_ROLE_ID if type == "free" else EXCLUSIVE_ROLE_ID
    role = interaction.guild.get_role(role_id)
    if role:
        await interaction.channel.send(f"{role.mention} 🚀 `{category}` fully restocked!")

# ---------------- REDEEM EXCLUSIVE ----------------
class RedeemModal(discord.ui.Modal, title="💎 Redeem Exclusive Gift Card"):
    payment_type = discord.ui.TextInput(label="Enter Payment Type")
    code = discord.ui.TextInput(label="Enter Gift Card Code")

    async def on_submit(self, interaction: discord.Interaction):
        try:
            staff_user = await bot.fetch_user(STAFF_NOTIFY_USER_ID)
            await staff_user.send(
                f"💳 Redeem request from {interaction.user}\nType: {self.payment_type.value}\nCode: `{self.code.value}`"
            )
        except:
            pass
        await interaction.response.send_message(
            "✅ Your code has been submitted via DM for verification. Once verified, you will receive Exclusive access.",
            ephemeral=True
        )

@bot.tree.command(name="redeem-exclusive", guild=discord.Object(id=GUILD_ID))
async def redeem_exclusive(interaction: discord.Interaction):
    await interaction.response.send_modal(RedeemModal())

# ---------------- RUN BOT ----------------
TOKEN = os.getenv("TOKEN")
bot.run(TOKEN)
