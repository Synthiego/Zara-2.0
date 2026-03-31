import discord
from discord.ext import commands
from discord import app_commands
import datetime
import json
from config import ANTINUKE, AI_MOD, AUTHORIZED_IDS

WARNS_FILE = "warns.json"

# ── Warning Storage (simple JSON file) ───────────────────────────────
def load_warns():
    try:
        with open(WARNS_FILE, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

def save_warns(data):
    with open(WARNS_FILE, "w") as f:
        json.dump(data, f, indent=2)

def add_warn(guild_id: int, user_id: int, reason: str, mod: str):
    data = load_warns()
    key = f"{guild_id}_{user_id}"
    if key not in data:
        data[key] = []
    data[key].append({
        "reason": reason,
        "mod": mod,
        "time": datetime.datetime.utcnow().isoformat()
    })
    save_warns(data)

def get_warns(guild_id: int, user_id: int):
    data = load_warns()
    return data.get(f"{guild_id}_{user_id}", [])

def clear_warns(guild_id: int, user_id: int):
    data = load_warns()
    key = f"{guild_id}_{user_id}"
    if key in data:
        del data[key]
    save_warns(data)

# ── Whitelist Storage ─────────────────────────────────────────────────
WHITELIST_FILE = "whitelist.json"

def load_whitelist():
    try:
        with open(WHITELIST_FILE, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

def save_whitelist(data):
    with open(WHITELIST_FILE, "w") as f:
        json.dump(data, f, indent=2)

def is_whitelisted(guild_id: int, user_id: int) -> bool:
    data = load_whitelist()
    return str(user_id) in data.get(str(guild_id), [])

def add_whitelist(guild_id: int, user_id: int):
    data = load_whitelist()
    key = str(guild_id)
    if key not in data:
        data[key] = []
    if str(user_id) not in data[key]:
        data[key].append(str(user_id))
    save_whitelist(data)

def remove_whitelist(guild_id: int, user_id: int):
    data = load_whitelist()
    key = str(guild_id)
    if key in data and str(user_id) in data[key]:
        data[key].remove(str(user_id))
    save_whitelist(data)


class Admin(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.lockdown_active = {}  # guild_id -> previous overwrites backup

    def _is_admin(self, ctx_or_interaction):
        if isinstance(ctx_or_interaction, commands.Context):
            return ctx_or_interaction.author.guild_permissions.administrator
        return ctx_or_interaction.user.guild_permissions.administrator

    def admin_check():
        async def predicate(interaction: discord.Interaction):
            return interaction.user.id in AUTHORIZED_IDS
        return app_commands.check(predicate)

    # ═══════════════════════════════════════════════════════════════════
    # MODERATION COMMANDS
    # ═══════════════════════════════════════════════════════════════════

    # ── Ban ──────────────────────────────────────────────────────────
    @app_commands.command(name="ban", description="Ban a member")
    @app_commands.describe(member="Who to ban", reason="Why")
    @admin_check()
    async def ban_slash(self, interaction: discord.Interaction, member: discord.Member, reason: str = "No reason provided"):
        await member.ban(reason=reason)
        await interaction.response.send_message(f"🔨 {member.mention} banned. Reason: {reason}", ephemeral=True)

    @commands.command(name="ban")
    @commands.check(lambda ctx: ctx.author.id in AUTHORIZED_IDS)
    async def ban_prefix(self, ctx, member: discord.Member, *, reason="No reason provided"):
        await member.ban(reason=reason)
        await ctx.send(f"🔨 {member.mention} banned. Reason: {reason}")

    # ── Kick ─────────────────────────────────────────────────────────
    @app_commands.command(name="kick", description="Kick a member")
    @app_commands.describe(member="Who to kick", reason="Why")
    @admin_check()
    async def kick_slash(self, interaction: discord.Interaction, member: discord.Member, reason: str = "No reason provided"):
        await member.kick(reason=reason)
        await interaction.response.send_message(f"👢 {member.mention} kicked. Reason: {reason}", ephemeral=True)

    @commands.command(name="kick")
    @commands.check(lambda ctx: ctx.author.id in AUTHORIZED_IDS)
    async def kick_prefix(self, ctx, member: discord.Member, *, reason="No reason provided"):
        await member.kick(reason=reason)
        await ctx.send(f"👢 {member.mention} kicked. Reason: {reason}")

    # ── Softban ──────────────────────────────────────────────────────
    @app_commands.command(name="softban", description="Ban then unban to delete messages without permanent ban")
    @app_commands.describe(member="Who to softban", reason="Why")
    @admin_check()
    async def softban_slash(self, interaction: discord.Interaction, member: discord.Member, reason: str = "No reason provided"):
        await member.ban(reason=f"[Softban] {reason}", delete_message_days=7)
        await interaction.guild.unban(member, reason="Softban - automatic unban")
        await interaction.response.send_message(f"🧹 {member.mention} softbanned — messages deleted, can rejoin.", ephemeral=True)

    @commands.command(name="softban")
    @commands.check(lambda ctx: ctx.author.id in AUTHORIZED_IDS)
    async def softban_prefix(self, ctx, member: discord.Member, *, reason="No reason provided"):
        await member.ban(reason=f"[Softban] {reason}", delete_message_days=7)
        await ctx.guild.unban(member, reason="Softban - automatic unban")
        await ctx.send(f"🧹 {member.mention} softbanned — messages deleted, can rejoin.")

    # ── Unban ────────────────────────────────────────────────────────
    @app_commands.command(name="unban", description="Unban a user by ID")
    @app_commands.describe(user_id="Discord user ID to unban")
    @admin_check()
    async def unban_slash(self, interaction: discord.Interaction, user_id: str):
        try:
            user = await self.bot.fetch_user(int(user_id))
            await interaction.guild.unban(user)
            await interaction.response.send_message(f"✅ Unbanned `{user}`.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Failed: {e}", ephemeral=True)

    @commands.command(name="unban")
    @commands.check(lambda ctx: ctx.author.id in AUTHORIZED_IDS)
    async def unban_prefix(self, ctx, user_id: str):
        try:
            user = await self.bot.fetch_user(int(user_id))
            await ctx.guild.unban(user)
            await ctx.send(f"✅ Unbanned `{user}`.")
        except Exception as e:
            await ctx.send(f"❌ Failed: {e}")

    # ── Timeout ──────────────────────────────────────────────────────
    @app_commands.command(name="timeout", description="Timeout a member")
    @app_commands.describe(member="Who to timeout", minutes="Duration", reason="Why")
    @admin_check()
    async def timeout_slash(self, interaction: discord.Interaction, member: discord.Member, minutes: app_commands.Range[int, 1, 10080], reason: str = "No reason provided"):
        until = discord.utils.utcnow() + datetime.timedelta(minutes=minutes)
        await member.timeout(until, reason=reason)
        await interaction.response.send_message(f"⏱️ {member.mention} timed out for `{minutes}` min.", ephemeral=True)

    @commands.command(name="timeout")
    @commands.check(lambda ctx: ctx.author.id in AUTHORIZED_IDS)
    async def timeout_prefix(self, ctx, member: discord.Member, minutes: int, *, reason="No reason provided"):
        until = discord.utils.utcnow() + datetime.timedelta(minutes=minutes)
        await member.timeout(until, reason=reason)
        await ctx.send(f"⏱️ {member.mention} timed out for `{minutes}` min.")

    # ── Warn ─────────────────────────────────────────────────────────
    @app_commands.command(name="warn", description="Warn a member")
    @app_commands.describe(member="Who to warn", reason="Why")
    @admin_check()
    async def warn_slash(self, interaction: discord.Interaction, member: discord.Member, reason: str = "No reason provided"):
        add_warn(interaction.guild.id, member.id, reason, str(interaction.user))
        warns = get_warns(interaction.guild.id, member.id)
        embed = discord.Embed(title="⚠️ Warning Issued", color=discord.Color.yellow())
        embed.add_field(name="User", value=member.mention)
        embed.add_field(name="Reason", value=reason)
        embed.add_field(name="Total Warnings", value=str(len(warns)))
        await interaction.response.send_message(embed=embed)
        try:
            await member.send(f"⚠️ You were warned in **{interaction.guild.name}**.\n**Reason:** {reason}\n**Total warnings:** {len(warns)}")
        except discord.Forbidden:
            pass

    @commands.command(name="warn")
    @commands.check(lambda ctx: ctx.author.id in AUTHORIZED_IDS)
    async def warn_prefix(self, ctx, member: discord.Member, *, reason="No reason provided"):
        add_warn(ctx.guild.id, member.id, reason, str(ctx.author))
        warns = get_warns(ctx.guild.id, member.id)
        await ctx.send(f"⚠️ {member.mention} warned. Reason: {reason} | Total warnings: {len(warns)}")

    # ── Purge ────────────────────────────────────────────────────────
    @app_commands.command(name="purge", description="Bulk delete messages")
    @app_commands.describe(amount="How many to delete (1-100)")
    @admin_check()
    async def purge_slash(self, interaction: discord.Interaction, amount: app_commands.Range[int, 1, 100]):
        await interaction.response.defer(ephemeral=True)
        deleted = await interaction.channel.purge(limit=amount)
        await interaction.followup.send(f"🗑️ Deleted `{len(deleted)}` messages.", ephemeral=True)

    @commands.command(name="purge")
    @commands.check(lambda ctx: ctx.author.id in AUTHORIZED_IDS)
    async def purge_prefix(self, ctx, amount: int):
        await ctx.message.delete()
        deleted = await ctx.channel.purge(limit=min(amount, 100))
        msg = await ctx.send(f"🗑️ Deleted `{len(deleted)}` messages.")
        await msg.delete(delay=4)

    # ── Slowmode ─────────────────────────────────────────────────────
    @app_commands.command(name="slowmode", description="Set slowmode in this channel")
    @app_commands.describe(seconds="0 to disable, max 21600")
    @admin_check()
    async def slowmode_slash(self, interaction: discord.Interaction, seconds: app_commands.Range[int, 0, 21600]):
        await interaction.channel.edit(slowmode_delay=seconds)
        msg = f"⏱️ Slowmode set to `{seconds}s`." if seconds > 0 else "⏱️ Slowmode disabled."
        await interaction.response.send_message(msg, ephemeral=True)

    @commands.command(name="slowmode")
    @commands.check(lambda ctx: ctx.author.id in AUTHORIZED_IDS)
    async def slowmode_prefix(self, ctx, seconds: int):
        await ctx.channel.edit(slowmode_delay=min(seconds, 21600))
        msg = f"⏱️ Slowmode set to `{seconds}s`." if seconds > 0 else "⏱️ Slowmode disabled."
        await ctx.send(msg)

    # ═══════════════════════════════════════════════════════════════════
    # CHANNEL COMMANDS
    # ═══════════════════════════════════════════════════════════════════

    # ── Lock ─────────────────────────────────────────────────────────
    @app_commands.command(name="lock", description="Lock a channel so members can't send messages")
    @admin_check()
    async def lock_slash(self, interaction: discord.Interaction):
        overwrite = interaction.channel.overwrites_for(interaction.guild.default_role)
        overwrite.send_messages = False
        await interaction.channel.edit(overwrites={interaction.guild.default_role: overwrite})
        await interaction.response.send_message("🔒 Channel locked.")

    @commands.command(name="lock")
    @commands.check(lambda ctx: ctx.author.id in AUTHORIZED_IDS)
    async def lock_prefix(self, ctx):
        overwrite = ctx.channel.overwrites_for(ctx.guild.default_role)
        overwrite.send_messages = False
        await ctx.channel.edit(overwrites={ctx.guild.default_role: overwrite})
        await ctx.send("🔒 Channel locked.")

    # ── Unlock ───────────────────────────────────────────────────────
    @app_commands.command(name="unlock", description="Unlock a channel")
    @admin_check()
    async def unlock_slash(self, interaction: discord.Interaction):
        overwrite = interaction.channel.overwrites_for(interaction.guild.default_role)
        overwrite.send_messages = None
        await interaction.channel.edit(overwrites={interaction.guild.default_role: overwrite})
        await interaction.response.send_message("🔓 Channel unlocked.")

    @commands.command(name="unlock")
    @commands.check(lambda ctx: ctx.author.id in AUTHORIZED_IDS)
    async def unlock_prefix(self, ctx):
        overwrite = ctx.channel.overwrites_for(ctx.guild.default_role)
        overwrite.send_messages = None
        await ctx.channel.edit(overwrites={ctx.guild.default_role: overwrite})
        await ctx.send("🔓 Channel unlocked.")

    # ── Hide ─────────────────────────────────────────────────────────
    @app_commands.command(name="hide", description="Hide a channel from everyone")
    @admin_check()
    async def hide_slash(self, interaction: discord.Interaction):
        overwrite = interaction.channel.overwrites_for(interaction.guild.default_role)
        overwrite.view_channel = False
        await interaction.channel.edit(overwrites={interaction.guild.default_role: overwrite})
        await interaction.response.send_message("🙈 Channel hidden.", ephemeral=True)

    @commands.command(name="hide")
    @commands.check(lambda ctx: ctx.author.id in AUTHORIZED_IDS)
    async def hide_prefix(self, ctx):
        overwrite = ctx.channel.overwrites_for(ctx.guild.default_role)
        overwrite.view_channel = False
        await ctx.channel.edit(overwrites={ctx.guild.default_role: overwrite})
        await ctx.send("🙈 Channel hidden.")

    # ── Show ─────────────────────────────────────────────────────────
    @app_commands.command(name="show", description="Unhide a channel")
    @admin_check()
    async def show_slash(self, interaction: discord.Interaction):
        overwrite = interaction.channel.overwrites_for(interaction.guild.default_role)
        overwrite.view_channel = None
        await interaction.channel.edit(overwrites={interaction.guild.default_role: overwrite})
        await interaction.response.send_message("👁️ Channel visible again.", ephemeral=True)

    @commands.command(name="show")
    @commands.check(lambda ctx: ctx.author.id in AUTHORIZED_IDS)
    async def show_prefix(self, ctx):
        overwrite = ctx.channel.overwrites_for(ctx.guild.default_role)
        overwrite.view_channel = None
        await ctx.channel.edit(overwrites={ctx.guild.default_role: overwrite})
        await ctx.send("👁️ Channel visible again.")

    # ── Lockdown ─────────────────────────────────────────────────────
    @app_commands.command(name="lockdown", description="Lock ALL channels — emergency button")
    @admin_check()
    async def lockdown_slash(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        count = 0
        for channel in interaction.guild.text_channels:
            try:
                overwrite = channel.overwrites_for(interaction.guild.default_role)
                overwrite.send_messages = False
                await channel.edit(overwrites={interaction.guild.default_role: overwrite})
                count += 1
            except discord.Forbidden:
                pass
        self.lockdown_active[interaction.guild.id] = True
        await interaction.followup.send(f"🚨 Server lockdown! Locked `{count}` channels.", ephemeral=True)

    @commands.command(name="lockdown")
    @commands.check(lambda ctx: ctx.author.id in AUTHORIZED_IDS)
    async def lockdown_prefix(self, ctx):
        count = 0
        for channel in ctx.guild.text_channels:
            try:
                overwrite = channel.overwrites_for(ctx.guild.default_role)
                overwrite.send_messages = False
                await channel.edit(overwrites={ctx.guild.default_role: overwrite})
                count += 1
            except discord.Forbidden:
                pass
        self.lockdown_active[ctx.guild.id] = True
        await ctx.send(f"🚨 Server lockdown! Locked `{count}` channels.")

    # ── Unlockdown ───────────────────────────────────────────────────
    @app_commands.command(name="unlockdown", description="Unlock all channels after a lockdown")
    @admin_check()
    async def unlockdown_slash(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        count = 0
        for channel in interaction.guild.text_channels:
            try:
                overwrite = channel.overwrites_for(interaction.guild.default_role)
                overwrite.send_messages = None
                await channel.edit(overwrites={interaction.guild.default_role: overwrite})
                count += 1
            except discord.Forbidden:
                pass
        self.lockdown_active.pop(interaction.guild.id, None)
        await interaction.followup.send(f"✅ Lockdown lifted! Unlocked `{count}` channels.", ephemeral=True)

    @commands.command(name="unlockdown")
    @commands.check(lambda ctx: ctx.author.id in AUTHORIZED_IDS)
    async def unlockdown_prefix(self, ctx):
        count = 0
        for channel in ctx.guild.text_channels:
            try:
                overwrite = channel.overwrites_for(ctx.guild.default_role)
                overwrite.send_messages = None
                await channel.edit(overwrites={ctx.guild.default_role: overwrite})
                count += 1
            except discord.Forbidden:
                pass
        self.lockdown_active.pop(ctx.guild.id, None)
        await ctx.send(f"✅ Lockdown lifted! Unlocked `{count}` channels.")

    # ═══════════════════════════════════════════════════════════════════
    # LOGGING COMMANDS
    # ═══════════════════════════════════════════════════════════════════

    # ── Userinfo ─────────────────────────────────────────────────────
    @app_commands.command(name="userinfo", description="Get info about a member")
    @app_commands.describe(member="Who to look up")
    @admin_check()
    async def userinfo_slash(self, interaction: discord.Interaction, member: discord.Member = None):
        member = member or interaction.user
        embed = await self._build_userinfo(member, interaction.guild)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @commands.command(name="userinfo")
    @commands.check(lambda ctx: ctx.author.id in AUTHORIZED_IDS)
    async def userinfo_prefix(self, ctx, member: discord.Member = None):
        member = member or ctx.author
        embed = await self._build_userinfo(member, ctx.guild)
        await ctx.send(embed=embed)

    async def _build_userinfo(self, member: discord.Member, guild: discord.Guild) -> discord.Embed:
        warns = get_warns(guild.id, member.id)
        created = discord.utils.format_dt(member.created_at, style="R")
        joined = discord.utils.format_dt(member.joined_at, style="R") if member.joined_at else "Unknown"
        roles = [r.mention for r in member.roles if r != guild.default_role]

        embed = discord.Embed(title=f"👤 {member}", color=member.color)
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.add_field(name="ID", value=str(member.id), inline=True)
        embed.add_field(name="Account Created", value=created, inline=True)
        embed.add_field(name="Joined Server", value=joined, inline=True)
        embed.add_field(name="⚠️ Warnings", value=str(len(warns)), inline=True)
        embed.add_field(name="🤖 Bot", value="Yes" if member.bot else "No", inline=True)
        embed.add_field(name="🛡️ Whitelisted", value="Yes" if is_whitelisted(guild.id, member.id) else "No", inline=True)
        embed.add_field(name=f"Roles ({len(roles)})", value=" ".join(roles[:10]) or "None", inline=False)
        return embed

    # ── Warnlog ──────────────────────────────────────────────────────
    @app_commands.command(name="warnlog", description="See all warnings for a member")
    @app_commands.describe(member="Who to check")
    @admin_check()
    async def warnlog_slash(self, interaction: discord.Interaction, member: discord.Member):
        embed = self._build_warnlog(member, interaction.guild)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @commands.command(name="warnlog")
    @commands.check(lambda ctx: ctx.author.id in AUTHORIZED_IDS)
    async def warnlog_prefix(self, ctx, member: discord.Member):
        embed = self._build_warnlog(member, ctx.guild)
        await ctx.send(embed=embed)

    def _build_warnlog(self, member: discord.Member, guild: discord.Guild) -> discord.Embed:
        warns = get_warns(guild.id, member.id)
        embed = discord.Embed(title=f"⚠️ Warnings for {member}", color=discord.Color.yellow())
        if not warns:
            embed.description = "No warnings on record."
        else:
            for i, w in enumerate(warns, 1):
                embed.add_field(
                    name=f"#{i} — {w['time'][:10]}",
                    value=f"**Reason:** {w['reason']}\n**By:** {w['mod']}",
                    inline=False
                )
        return embed

    # ── Clearwarns ───────────────────────────────────────────────────
    @app_commands.command(name="clearwarns", description="Clear all warnings for a member")
    @app_commands.describe(member="Who to clear")
    @admin_check()
    async def clearwarns_slash(self, interaction: discord.Interaction, member: discord.Member):
        clear_warns(interaction.guild.id, member.id)
        await interaction.response.send_message(f"✅ Cleared all warnings for {member.mention}.", ephemeral=True)

    @commands.command(name="clearwarns")
    @commands.check(lambda ctx: ctx.author.id in AUTHORIZED_IDS)
    async def clearwarns_prefix(self, ctx, member: discord.Member):
        clear_warns(ctx.guild.id, member.id)
        await ctx.send(f"✅ Cleared all warnings for {member.mention}.")

    # ═══════════════════════════════════════════════════════════════════
    # SECURITY COMMANDS
    # ═══════════════════════════════════════════════════════════════════

    # ── Whitelist ────────────────────────────────────────────────────
    @app_commands.command(name="whitelist", description="Whitelist a member from antinuke")
    @app_commands.describe(member="Who to whitelist")
    @admin_check()
    async def whitelist_slash(self, interaction: discord.Interaction, member: discord.Member):
        add_whitelist(interaction.guild.id, member.id)
        await interaction.response.send_message(f"✅ {member.mention} is now whitelisted — antinuke will ignore them.", ephemeral=True)

    @commands.command(name="whitelist")
    @commands.check(lambda ctx: ctx.author.id in AUTHORIZED_IDS)
    async def whitelist_prefix(self, ctx, member: discord.Member):
        add_whitelist(ctx.guild.id, member.id)
        await ctx.send(f"✅ {member.mention} whitelisted from antinuke.")

    # ── Unwhitelist ──────────────────────────────────────────────────
    @app_commands.command(name="unwhitelist", description="Remove a member from the whitelist")
    @app_commands.describe(member="Who to remove")
    @admin_check()
    async def unwhitelist_slash(self, interaction: discord.Interaction, member: discord.Member):
        remove_whitelist(interaction.guild.id, member.id)
        await interaction.response.send_message(f"✅ {member.mention} removed from whitelist.", ephemeral=True)

    @commands.command(name="unwhitelist")
    @commands.check(lambda ctx: ctx.author.id in AUTHORIZED_IDS)
    async def unwhitelist_prefix(self, ctx, member: discord.Member):
        remove_whitelist(ctx.guild.id, member.id)
        await ctx.send(f"✅ {member.mention} removed from whitelist.")

    # ── Whitelisted ──────────────────────────────────────────────────
    @app_commands.command(name="whitelisted", description="Show all whitelisted members")
    @admin_check()
    async def whitelisted_slash(self, interaction: discord.Interaction):
        embed = self._build_whitelist_embed(interaction.guild)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @commands.command(name="whitelisted")
    @commands.check(lambda ctx: ctx.author.id in AUTHORIZED_IDS)
    async def whitelisted_prefix(self, ctx):
        embed = self._build_whitelist_embed(ctx.guild)
        await ctx.send(embed=embed)

    def _build_whitelist_embed(self, guild: discord.Guild) -> discord.Embed:
        data = load_whitelist()
        ids = data.get(str(guild.id), [])
        embed = discord.Embed(title="🛡️ Whitelisted Members", color=discord.Color.green())
        if not ids:
            embed.description = "No whitelisted members."
        else:
            members = []
            for uid in ids:
                m = guild.get_member(int(uid))
                members.append(m.mention if m else f"`{uid}`")
            embed.description = "\n".join(members)
        return embed

    # ── Antinuke Status ──────────────────────────────────────────────
    @app_commands.command(name="antinuke", description="Show antinuke status and settings")
    @admin_check()
    async def antinuke_slash(self, interaction: discord.Interaction):
        embed = self._build_antinuke_embed()
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @commands.command(name="antinuke")
    @commands.check(lambda ctx: ctx.author.id in AUTHORIZED_IDS)
    async def antinuke_prefix(self, ctx):
        embed = self._build_antinuke_embed()
        await ctx.send(embed=embed)

    def _build_antinuke_embed(self) -> discord.Embed:
        embed = discord.Embed(title="⚔️ Antinuke Status", color=discord.Color.blurple())
        embed.add_field(name="Mass Ban", value=f"`{ANTINUKE['ban_threshold']}` in `{ANTINUKE['time_window']}s`", inline=True)
        embed.add_field(name="Mass Kick", value=f"`{ANTINUKE['kick_threshold']}` in `{ANTINUKE['time_window']}s`", inline=True)
        embed.add_field(name="Channel Delete", value=f"`{ANTINUKE['channel_delete_threshold']}` in `{ANTINUKE['time_window']}s`", inline=True)
        embed.add_field(name="Channel Create", value=f"`{ANTINUKE['channel_create_threshold']}` in `{ANTINUKE['time_window']}s`", inline=True)
        embed.add_field(name="Role Delete", value=f"`{ANTINUKE['role_delete_threshold']}` in `{ANTINUKE['time_window']}s`", inline=True)
        embed.add_field(name="Role Create", value=f"`{ANTINUKE['role_create_threshold']}` in `{ANTINUKE['time_window']}s`", inline=True)
        embed.add_field(name="Webhook Spam", value=f"`{ANTINUKE['webhook_create_threshold']}` in `{ANTINUKE['time_window']}s`", inline=True)
        embed.add_field(name="Punishment", value=f"`{ANTINUKE['punishment']}`", inline=True)
        embed.set_footer(text="Change thresholds in config.py")
        return embed

    # ── Status (overall) ─────────────────────────────────────────────
    @app_commands.command(name="status", description="Show Zara's full status")
    @admin_check()
    async def status_slash(self, interaction: discord.Interaction):
        embed = discord.Embed(title="🌸 Zara — Status", color=discord.Color.blurple())
        embed.add_field(name="🤖 AI Mod Action", value=f"`{AI_MOD['action']}`", inline=True)
        embed.add_field(name="Toxic Threshold", value=f"`{AI_MOD['toxic_threshold']}`", inline=True)
        embed.add_field(name="NSFW Threshold", value=f"`{AI_MOD['nsfw_threshold']}`", inline=True)
        embed.add_field(name="🚨 Lockdown", value="Active 🔴" if self.lockdown_active.get(interaction.guild.id) else "Inactive 🟢", inline=True)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @commands.command(name="status")
    @commands.check(lambda ctx: ctx.author.id in AUTHORIZED_IDS)
    async def status_prefix(self, ctx):
        embed = discord.Embed(title="🌸 Zara — Status", color=discord.Color.blurple())
        embed.add_field(name="🤖 AI Mod Action", value=f"`{AI_MOD['action']}`", inline=True)
        embed.add_field(name="Toxic Threshold", value=f"`{AI_MOD['toxic_threshold']}`", inline=True)
        embed.add_field(name="NSFW Threshold", value=f"`{AI_MOD['nsfw_threshold']}`", inline=True)
        embed.add_field(name="🚨 Lockdown", value="Active 🔴" if self.lockdown_active.get(ctx.guild.id) else "Inactive 🟢", inline=True)
        await ctx.send(embed=embed)


async def setup(bot):
    await bot.add_cog(Admin(bot))
