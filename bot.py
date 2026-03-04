# bot.py
import os
import json
import time
import asyncio
import datetime
import discord
from discord import app_commands
from discord.ext import commands, tasks
from typing import Optional, List

# ---------------- CONFIG (edit only IDs if they change) ----------------
GUILD_ID = 1452717489656954961        # your guild
FREE_GEN_ROLE_ID = 1467913996723032315
EXCLUSIVE_ROLE_ID = 1453906576237924603
BOOST_ROLE_ID = 1453187878061478019
ADMIN_ROLE_ID = 1452719764119093388   # admin role for command restrictions
STAFF_NOTIFY_USER_ID = 884084052854984726

STOCK_FILE = "stock.json"
PRESENCE_TEXT = ".gg/nV3x85Jeq | BEST DROPS + GEN IN DISCORD"

FREE_COOLDOWN = 180     # seconds
EXCL_COOLDOWN = 60      # seconds

# ---------------- BOT / INTENTS ----------------
intents = discord.Intents.default()
intents.members = True
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)
tree = bot.tree

# ---------------- STORAGE & LOCK ----------------
_file_lock = asyncio.Lock()

def _ensure_stock():
    if not os.path.exists(STOCK_FILE):
        with open(STOCK_FILE, "w") as f:
            json.dump({"FREE": {}, "EXCLUSIVE": {}, "categories": []}, f, indent=4)

def load_stock():
    _ensure_stock()
    with open(STOCK_FILE, "r") as f:
        return json.load(f)

def save_stock(data):
    with open(STOCK_FILE, "w") as f:
        json.dump(data, f, indent=4)

# in-memory cache (kept consistent with file using lock)
stock_data = load_stock()

# ---------------- COOLDOWNS & RESYNC GUARD ----------------
_cooldowns = {}  # { (user_id, "FREE"|"EXCLUSIVE") : timestamp }
_last_resync = 0
_RESYNC_COOLDOWN = 60 * 60  # 1 hour between manual resyncs to avoid rate limits

# ---------------- HELPERS ----------------
def now_ts():
    return time.time()

async def safe_load_stock():
    global stock_data
    async with _file_lock:
        stock_data = load_stock()
        return stock_data

async def safe_save_stock():
    async with _file_lock:
        save_stock(stock_data)

def check_cooldown_line(user_id: int, typ: str):
    key = (user_id, typ)
    ts = _cooldowns.get(key, 0)
    limit = FREE_COOLDOWN if typ == "FREE" else EXCL_COOLDOWN
    rem = int(limit - (now_ts() - ts)) if now_ts() - ts < limit else 0
    return rem

def set_cooldown(user_id: int, typ: str):
    _cooldowns[(user_id, typ)] = now_ts()

def format_stock_embed():
    data = stock_data
    embed = discord.Embed(title="📦 Marcos Gen • Stock Overview", color=discord.Color.blue())
    free_lines = []
    for cat in data.get("categories", []):
        free_lines.append(f"**{cat}** → {len(data['FREE'].get(cat, []))}")
    excl_lines = []
    for cat in data.get("categories", []):
        excl_lines.append(f"**{cat}** → {len(data['EXCLUSIVE'].get(cat, []))}")
    embed.add_field(name="🆓 Free Stock", value="\n".join(free_lines) or "No categories", inline=False)
    embed.add_field(name="💎 Exclusive Stock", value="\n".join(excl_lines) or "No categories", inline=False)
    embed.set_footer(text="Professional • Secure • Automated")
    return embed

def user_has_required_status(member: discord.Member) -> bool:
    for act in member.activities:
        if isinstance(act, discord.CustomActivity) and act.name:
            if PRESENCE_TEXT.lower() in act.name.lower():
                return True
    return False

# ---------------- AUTOCOMPLETE HELPERS ----------------
async def category_autocomplete(interaction: discord.Interaction, current: str):
    await safe_load_stock()
    choices = []
    for cat in stock_data.get("categories", []):
        if current.lower() in cat.lower():
            choices.append(app_commands.Choice(name=cat, value=cat))
    return choices[:25]

async def type_autocomplete(interaction: discord.Interaction, current: str):
    options = ["free", "exclusive"]
    return [app_commands.Choice(name=o.capitalize(), value=o) for o in options if current.lower() in o.lower()][:25]

# ---------------- STARTUP (do NOT sync automatically) ----------------
@bot.event
async def on_ready():
    # Do NOT call tree.sync() here to avoid rate-limit on repeated restarts.
    # Commands should be registered once with a registrar or use /resync-commands manually (admin).
    print(f"✅ Logged in as {bot.user} (id: {bot.user.id})")
    await bot.change_presence(activity=discord.Activity(type=discord.ActivityType.watching, name=PRESENCE_TEXT))
    boost_loop.start()

# ---------------- ERROR HANDLER ----------------
@bot.tree.error
async def global_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    # If command isn't registered on this instance -> politely tell user, and avoid stack traces
    if isinstance(error, app_commands.CommandNotFound):
        try:
            if not interaction.response.is_done():
                await interaction.response.send_message("⚠️ That command isn't available on this instance. Ask an admin to run `/resync-commands`.", ephemeral=True)
        except Exception:
            pass
        return
    # Fallback: send concise message and log
    print(f"[AppCommandError] {error!r}")
    try:
        if not interaction.response.is_done():
            await interaction.response.send_message("An error occurred while processing the command.", ephemeral=True)
    except Exception:
        pass

# ---------------- BOOST AUTO-ROLE ----------------
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

# ---------------- GEN UI ----------------
class GenSelect(discord.ui.Select):
    def __init__(self, typ: str):
        # typ: "FREE" or "EXCLUSIVE"
        opts = []
        for cat in stock_data.get("categories", []):
            cnt = len(stock_data.get(typ, {}).get(cat, []))
            label = f"{cat} — {cnt}"
            opts.append(discord.SelectOption(label=label[:100], value=cat, description=f"{cnt} in stock" if cnt else "Out of stock"))
        super().__init__(placeholder="Choose a category", min_values=1, max_values=1, options=opts[:25])
        self.typ = typ

    async def callback(self, interaction: discord.Interaction):
        # heavy work - defer
        await interaction.response.defer(ephemeral=True)
        cat = self.values[0]
        # check stock & cooldown
        await safe_load_stock()
        items = stock_data.get(self.typ, {}).get(cat, [])
        if not items:
            await interaction.followup.send("⚠️ That category is out of stock.", ephemeral=True)
            return
        rem = check_cooldown_line(interaction.user.id, self.typ)
        if rem > 0:
            await interaction.followup.send(f"⏳ Wait {rem}s before generating again.", ephemeral=True)
            return
        # pop and save
        item = items.pop(0)
        await safe_save_stock()
        set_cooldown(interaction.user.id, self.typ)
        # try DM
        try:
            await interaction.user.send(f"{'💎' if self.typ == 'EXCLUSIVE' else '🎉'} **Here is your item from {cat}:**\n```{item}```")
            await interaction.followup.send("✅ Sent to your DMs.", ephemeral=True)
        except Exception:
            await interaction.followup.send(f"🎁 **Here is your item from {cat}:**\n```{item}```", ephemeral=True)
        # staff log best-effort
        try:
            staff = await bot.fetch_user(STAFF_NOTIFY_USER_ID)
            await staff.send(f"Generated: user={interaction.user} type={self.typ} category={cat}")
        except Exception:
            pass

class GenView(discord.ui.View):
    def __init__(self, typ: str):
        super().__init__(timeout=60)
        self.add_item(GenSelect(typ))

# ---------------- USER COMMANDS ----------------
@tree.command(name="gen", description="Generate a Free item")
async def slash_gen(interaction: discord.Interaction):
    # require custom status on user
    if not user_has_required_status(interaction.user):
        await interaction.response.send_message(f"❌ Set your custom status to:\n`{PRESENCE_TEXT}`", ephemeral=True)
        return
    await safe_load_stock()
    await interaction.response.send_message("Select a Free category:", view=GenView("FREE"), ephemeral=True)

@tree.command(name="exclusive-gen", description="Generate an Exclusive item")
async def slash_exclusive_gen(interaction: discord.Interaction):
    # check role
    if EXCLUSIVE_ROLE_ID not in [r.id for r in getattr(interaction.user, "roles", [])]:
        await interaction.response.send_message("❌ You need the Exclusive role to use this command.", ephemeral=True)
        return
    await safe_load_stock()
    await interaction.response.send_message("Select an Exclusive category:", view=GenView("EXCLUSIVE"), ephemeral=True)

@tree.command(name="stock", description="View current stock")
async def slash_stock(interaction: discord.Interaction):
    await safe_load_stock()
    await interaction.response.send_message(embed=format_stock_embed(), ephemeral=True)

# ---------------- ADMIN HELPERS ----------------
def admin_check(interaction: discord.Interaction) -> bool:
    return any(r.id == ADMIN_ROLE_ID for r in getattr(interaction.user, "roles", []))

def admin_check_predicate(interaction: discord.Interaction) -> None:
    if not admin_check(interaction):
        raise app_commands.MissingRole(ADMIN_ROLE_ID)

# ---------------- ADMIN COMMANDS ----------------
@tree.command(name="addcategory", description="Add a category (Admin only)")
@app_commands.check(admin_check_predicate)
async def slash_addcategory(interaction: discord.Interaction, category: str):
    await interaction.response.defer(ephemeral=True)
    await safe_load_stock()
    if category in stock_data.get("categories", []):
        await interaction.followup.send("❌ Category already exists.", ephemeral=True)
        return
    stock_data.setdefault("categories", []).append(category)
    stock_data.setdefault("FREE", {})[category] = []
    stock_data.setdefault("EXCLUSIVE", {})[category] = []
    await safe_save_stock()
    await interaction.followup.send(f"✅ Category `{category}` added.", ephemeral=True)

@tree.command(name="removecategory", description="Remove a category (Admin only)")
@app_commands.check(admin_check_predicate)
async def slash_removecategory(interaction: discord.Interaction, category: str):
    await interaction.response.defer(ephemeral=True)
    await safe_load_stock()
    if category not in stock_data.get("categories", []):
        await interaction.followup.send("❌ Category does not exist.", ephemeral=True)
        return
    stock_data["categories"].remove(category)
    stock_data["FREE"].pop(category, None)
    stock_data["EXCLUSIVE"].pop(category, None)
    await safe_save_stock()
    await interaction.followup.send(f"✅ Category `{category}` removed.", ephemeral=True)

@tree.command(name="addstock", description="Add stock (Admin only)")
@app_commands.autocomplete(type=type_autocomplete, category=category_autocomplete)
@app_commands.check(admin_check_predicate)
async def slash_addstock(interaction: discord.Interaction, type: str, category: str, stock: Optional[str] = None, file: Optional[discord.Attachment] = None):
    await interaction.response.defer(ephemeral=True)
    type = type.lower()
    if type not in ("free", "exclusive"):
        await interaction.followup.send("❌ Type must be `free` or `exclusive`.", ephemeral=True)
        return
    await safe_load_stock()
    if category not in stock_data.get("categories", []):
        await interaction.followup.send("❌ Invalid category.", ephemeral=True)
        return

    key = "FREE" if type == "free" else "EXCLUSIVE"
    new_items = []
    if file:
        try:
            content = await file.read()
            lines = [l.strip() for l in content.decode(errors="ignore").splitlines() if l.strip()]
        except Exception:
            await interaction.followup.send("❌ Could not read the attached file. Use a plain .txt file.", ephemeral=True)
            return
        for line in lines:
            if line not in stock_data[key].get(category, []):
                new_items.append(line)
    elif stock:
        lines = [l.strip() for l in stock.splitlines() if l.strip()]
        for line in lines:
            if line not in stock_data[key].get(category, []):
                new_items.append(line)
    else:
        await interaction.followup.send("❌ Provide stock via text or attach a .txt file.", ephemeral=True)
        return

    stock_data[key].setdefault(category, []).extend(new_items)
    await safe_save_stock()
    await interaction.followup.send(f"✅ Added {len(new_items)} items to `{category}`.", ephemeral=True)
    # ping role
    role_id = FREE_GEN_ROLE_ID if key == "FREE" else EXCLUSIVE_ROLE_ID
    role = interaction.guild.get_role(role_id)
    if role:
        await interaction.channel.send(f"{role.mention} 🔔 `{category}` restocked!")

@tree.command(name="restock", description="Replace stock for a category (Admin only)")
@app_commands.autocomplete(type=type_autocomplete, category=category_autocomplete)
@app_commands.check(admin_check_predicate)
async def slash_restock(interaction: discord.Interaction, type: str, category: str, stock: Optional[str] = None, file: Optional[discord.Attachment] = None):
    await interaction.response.defer(ephemeral=True)
    type = type.lower()
    if type not in ("free", "exclusive"):
        await interaction.followup.send("❌ Type must be `free` or `exclusive`.", ephemeral=True)
        return
    await safe_load_stock()
    if category not in stock_data.get("categories", []):
        await interaction.followup.send("❌ Invalid category.", ephemeral=True)
        return

    key = "FREE" if type == "free" else "EXCLUSIVE"
    items = []
    if file:
        try:
            content = await file.read()
            lines = [l.strip() for l in content.decode(errors="ignore").splitlines() if l.strip()]
        except Exception:
            await interaction.followup.send("❌ Could not read the attached file. Use a plain .txt file.", ephemeral=True)
            return
        items = list(dict.fromkeys(lines))
    elif stock:
        lines = [l.strip() for l in stock.splitlines() if l.strip()]
        items = list(dict.fromkeys(lines))
    else:
        await interaction.followup.send("❌ Provide stock via text or attach a .txt file.", ephemeral=True)
        return

    stock_data[key][category] = items
    await safe_save_stock()
    await interaction.followup.send(f"♻️ `{category}` restocked with {len(items)} items.", ephemeral=True)
    role_id = FREE_GEN_ROLE_ID if key == "FREE" else EXCLUSIVE_ROLE_ID
    role = interaction.guild.get_role(role_id)
    if role:
        await interaction.channel.send(f"{role.mention} 🚀 `{category}` fully restocked!")

# ---------------- REDEEM MODAL ----------------
class RedeemModal(discord.ui.Modal, title="Redeem Exclusive Gift Card"):
    payment_type = discord.ui.TextInput(label="Payment Type", placeholder="Paypal / CashApp / Giftcard")
    code = discord.ui.TextInput(label="Code", placeholder="Paste the code here")

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        try:
            staff = await bot.fetch_user(STAFF_NOTIFY_USER_ID)
            await staff.send(f"Redeem request:\nUser: {interaction.user}\nPayment: {self.payment_type.value}\nCode: `{self.code.value}`")
        except Exception:
            pass
        await interaction.followup.send("✅ Submitted. Staff will verify and grant Exclusive if valid.", ephemeral=True)

@tree.command(name="redeem-exclusive", description="Redeem Exclusive via gift card")
async def slash_redeem(interaction: discord.Interaction):
    await interaction.response.send_modal(RedeemModal())

# ---------------- ADMIN: RESYNC COMMANDS (manual, with cooldown) ----------------
@tree.command(name="resync-commands", description="(Admin) Sync slash commands to the guild (use only if needed)")
@app_commands.check(admin_check_predicate)
async def slash_resync(interaction: discord.Interaction):
    global _last_resync
    await interaction.response.defer(ephemeral=True)
    now = now_ts()
    if now - _last_resync < _RESYNC_COOLDOWN:
        await interaction.followup.send("❌ Commands were resynced recently. Wait before running again to avoid rate limits.", ephemeral=True)
        return
    try:
        guild = discord.Object(id=GUILD_ID)
        await tree.sync(guild=guild)
        _last_resync = now_ts()
        await interaction.followup.send("✅ Commands synced to guild.", ephemeral=True)
    except discord.Forbidden:
        await interaction.followup.send("❌ Missing access when syncing commands. Ensure bot has applications.commands scope & is in guild.", ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"❌ Sync failed: {e}", ephemeral=True)

# ---------------- RUN ----------------
if __name__ == "__main__":
    TOKEN = os.getenv("TOKEN")
    if not TOKEN:
        print("[ERROR] TOKEN env var not set. Set TOKEN to your bot token and restart.")
    else:
        # make sure stock file exists and in-memory is loaded
        _ensure_stock()
        stock_data = load_stock()
        bot.run(TOKEN)
