import discord
from discord.ext import commands
from discord import app_commands
from collections import defaultdict
import time
import asyncio
import datetime
import json
from config import ANTINUKE, LOG_CHANNEL_NAME


def load_whitelist():
    try:
        with open("whitelist.json", "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

def is_whitelisted(guild_id: int, user_id: int) -> bool:
    data = load_whitelist()
    return str(user_id) in data.get(str(guild_id), [])


class AntiNuke(commands.Cog):
    """Detects and stops server nuke attempts in real-time."""

    def __init__(self, bot):
        self.bot = bot
        self.action_log: dict = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))
        self.punished: set = set()

    def _record(self, guild_id: int, user_id: int, action: str) -> int:
        now = time.time()
        window = ANTINUKE["time_window"]
        timestamps = self.action_log[guild_id][user_id][action]
        timestamps[:] = [t for t in timestamps if now - t < window]
        timestamps.append(now)
        return len(timestamps)

    async def _get_log_channel(self, guild: discord.Guild):
        return discord.utils.get(guild.text_channels, name=LOG_CHANNEL_NAME)

    async def _punish(self, guild: discord.Guild, member: discord.Member, reason: str):
        # Skip if already punished recently
        key = (guild.id, member.id)
        if key in self.punished:
            return
        self.punished.add(key)
        asyncio.get_event_loop().call_later(30, self.punished.discard, key)

        # Skip bots and whitelisted members
        if member.bot or is_whitelisted(guild.id, member.id):
            await self._log(guild, member, reason, skipped=True)
            return

        punishment = ANTINUKE["punishment"]
        success = False
        try:
            if punishment == "ban":
                await guild.ban(member, reason=f"[AntiNuke] {reason}", delete_message_days=0)
            elif punishment == "kick":
                await guild.kick(member, reason=f"[AntiNuke] {reason}")
            elif punishment == "strip_roles":
                manageable = [r for r in member.roles if r.is_assignable()]
                await member.remove_roles(*manageable, reason=f"[AntiNuke] {reason}")
            success = True
        except discord.Forbidden:
            pass

        await self._log(guild, member, reason, skipped=False, success=success)

    async def _log(self, guild, member, reason, skipped=False, success=True):
        log = await self._get_log_channel(guild)
        if not log:
            return

        if skipped:
            embed = discord.Embed(
                title="Anti-Nuke — Action Skipped",
                color=discord.Color.gold(),
                timestamp=discord.utils.utcnow()
            )
            embed.add_field(name="User", value=f"{member.mention} (`{member.id}`)", inline=True)
            embed.add_field(name="Reason Skipped", value="Whitelisted or bot", inline=True)
            embed.add_field(name="Trigger", value=reason, inline=False)
        else:
            embed = discord.Embed(
                title="Anti-Nuke — Threat Neutralised",
                color=discord.Color.red() if success else discord.Color.orange(),
                timestamp=discord.utils.utcnow()
            )
            embed.add_field(name="User", value=f"{member.mention} (`{member.id}`)", inline=True)
            embed.add_field(name="Action Taken", value=f"`{ANTINUKE['punishment']}`" if success else "`Failed — Missing Permissions`", inline=True)
            embed.add_field(name="Trigger", value=reason, inline=False)

        embed.set_thumbnail(url=member.display_avatar.url)
        embed.set_footer(text="Zara Anti-Nuke System")
        await log.send(embed=embed)

    async def _get_audit_entry(self, guild: discord.Guild, action: discord.AuditLogAction):
        await asyncio.sleep(0.5)  # Small delay so audit log is populated
        try:
            async for entry in guild.audit_logs(limit=1, action=action):
                # Only count recent entries (within last 5 seconds)
                age = (discord.utils.utcnow() - entry.created_at).total_seconds()
                if age < 5:
                    return entry
        except discord.Forbidden:
            pass
        return None

    # ── Ban / Kick ────────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_member_ban(self, guild, user):
        entry = await self._get_audit_entry(guild, discord.AuditLogAction.ban)
        if not entry or entry.user.id == self.bot.user.id:
            return
        count = self._record(guild.id, entry.user.id, "ban")
        if count >= ANTINUKE["ban_threshold"]:
            member = guild.get_member(entry.user.id)
            if member:
                await self._punish(guild, member, f"Mass ban — {count} bans in {ANTINUKE['time_window']}s")

    @commands.Cog.listener()
    async def on_member_remove(self, member):
        guild = member.guild
        entry = await self._get_audit_entry(guild, discord.AuditLogAction.kick)
        if not entry or entry.user.id == self.bot.user.id:
            return
        if entry.target.id != member.id:
            return
        count = self._record(guild.id, entry.user.id, "kick")
        if count >= ANTINUKE["kick_threshold"]:
            kicker = guild.get_member(entry.user.id)
            if kicker:
                await self._punish(guild, kicker, f"Mass kick — {count} kicks in {ANTINUKE['time_window']}s")

    # ── Channels ──────────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel):
        guild = channel.guild
        entry = await self._get_audit_entry(guild, discord.AuditLogAction.channel_delete)
        if not entry or entry.user.id == self.bot.user.id:
            return
        count = self._record(guild.id, entry.user.id, "channel_delete")
        if count >= ANTINUKE["channel_delete_threshold"]:
            member = guild.get_member(entry.user.id)
            if member:
                await self._punish(guild, member, f"Mass channel delete — {count} in {ANTINUKE['time_window']}s")

    @commands.Cog.listener()
    async def on_guild_channel_create(self, channel):
        guild = channel.guild
        entry = await self._get_audit_entry(guild, discord.AuditLogAction.channel_create)
        if not entry or entry.user.id == self.bot.user.id:
            return
        count = self._record(guild.id, entry.user.id, "channel_create")
        if count >= ANTINUKE["channel_create_threshold"]:
            member = guild.get_member(entry.user.id)
            if member:
                await self._punish(guild, member, f"Mass channel create — {count} in {ANTINUKE['time_window']}s")

    # ── Roles ─────────────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_guild_role_delete(self, role):
        guild = role.guild
        entry = await self._get_audit_entry(guild, discord.AuditLogAction.role_delete)
        if not entry or entry.user.id == self.bot.user.id:
            return
        count = self._record(guild.id, entry.user.id, "role_delete")
        if count >= ANTINUKE["role_delete_threshold"]:
            member = guild.get_member(entry.user.id)
            if member:
                await self._punish(guild, member, f"Mass role delete — {count} in {ANTINUKE['time_window']}s")

    @commands.Cog.listener()
    async def on_guild_role_create(self, role):
        guild = role.guild
        entry = await self._get_audit_entry(guild, discord.AuditLogAction.role_create)
        if not entry or entry.user.id == self.bot.user.id:
            return
        count = self._record(guild.id, entry.user.id, "role_create")
        if count >= ANTINUKE["role_create_threshold"]:
            member = guild.get_member(entry.user.id)
            if member:
                await self._punish(guild, member, f"Mass role create — {count} in {ANTINUKE['time_window']}s")

    # ── Webhooks ──────────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_webhooks_update(self, channel):
        guild = channel.guild
        entry = await self._get_audit_entry(guild, discord.AuditLogAction.webhook_create)
        if not entry or entry.user.id == self.bot.user.id:
            return
        count = self._record(guild.id, entry.user.id, "webhook_create")
        if count >= ANTINUKE["webhook_create_threshold"]:
            member = guild.get_member(entry.user.id)
            if member:
                await self._punish(guild, member, f"Webhook spam — {count} in {ANTINUKE['time_window']}s")
            try:
                webhooks = await channel.webhooks()
                for wh in webhooks:
                    if wh.user and wh.user.id == entry.user.id:
                        await wh.delete(reason="Zara AntiNuke: webhook spam")
            except discord.Forbidden:
                pass

    # ── Test Command ──────────────────────────────────────────────────

    @app_commands.command(name="testnuke", description="Test the anti-nuke system — sends a simulated alert to mod-logs")
    @app_commands.checks.has_permissions(administrator=True)
    async def testnuke(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        log = await self._get_log_channel(interaction.guild)
        if not log:
            await interaction.followup.send(
                "No `mod-logs` channel found. Create a channel named `mod-logs` first.",
                ephemeral=True
            )
            return

        # Simulate a triggered alert
        embed = discord.Embed(
            title="Anti-Nuke — Threat Neutralised",
            color=discord.Color.red(),
            timestamp=discord.utils.utcnow()
        )
        embed.add_field(name="User", value=f"{interaction.user.mention} (`{interaction.user.id}`)", inline=True)
        embed.add_field(name="Action Taken", value=f"`{ANTINUKE['punishment']}` *(simulated)*", inline=True)
        embed.add_field(name="Trigger", value=f"Mass ban — 3 bans in {ANTINUKE['time_window']}s *(simulated)*", inline=False)
        embed.add_field(name="Thresholds Active", value=(
            f"Ban: `{ANTINUKE['ban_threshold']}` — "
            f"Kick: `{ANTINUKE['kick_threshold']}` — "
            f"Ch. Delete: `{ANTINUKE['channel_delete_threshold']}` — "
            f"Role Delete: `{ANTINUKE['role_delete_threshold']}` — "
            f"Webhook: `{ANTINUKE['webhook_create_threshold']}`"
        ), inline=False)
        embed.set_thumbnail(url=interaction.user.display_avatar.url)
        embed.set_footer(text="Zara Anti-Nuke System  •  This is a test")

        await log.send(embed=embed)
        await interaction.followup.send("Test alert sent to `mod-logs`. Anti-nuke is active.", ephemeral=True)

    @commands.command(name="testnuke")
    @commands.has_permissions(administrator=True)
    async def testnuke_prefix(self, ctx):
        log = await self._get_log_channel(ctx.guild)
        if not log:
            await ctx.send("No `mod-logs` channel found.")
            return

        embed = discord.Embed(
            title="Anti-Nuke — Threat Neutralised",
            color=discord.Color.red(),
            timestamp=discord.utils.utcnow()
        )
        embed.add_field(name="User", value=f"{ctx.author.mention} (`{ctx.author.id}`)", inline=True)
        embed.add_field(name="Action Taken", value=f"`{ANTINUKE['punishment']}` *(simulated)*", inline=True)
        embed.add_field(name="Trigger", value=f"Mass ban — 3 bans in {ANTINUKE['time_window']}s *(simulated)*", inline=False)
        embed.add_field(name="Thresholds Active", value=(
            f"Ban: `{ANTINUKE['ban_threshold']}` — "
            f"Kick: `{ANTINUKE['kick_threshold']}` — "
            f"Ch. Delete: `{ANTINUKE['channel_delete_threshold']}` — "
            f"Role Delete: `{ANTINUKE['role_delete_threshold']}` — "
            f"Webhook: `{ANTINUKE['webhook_create_threshold']}`"
        ), inline=False)
        embed.set_thumbnail(url=ctx.author.display_avatar.url)
        embed.set_footer(text="Zara Anti-Nuke System  •  This is a test")

        await log.send(embed=embed)
        await ctx.send("Test alert sent to `mod-logs`.")


async def setup(bot):
    await bot.add_cog(AntiNuke(bot))
