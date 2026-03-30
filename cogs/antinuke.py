import discord
from discord.ext import commands
from collections import defaultdict
import time
import asyncio
from config import ANTINUKE, LOG_CHANNEL_NAME


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
        key = (guild.id, member.id)
        if key in self.punished:
            return
        self.punished.add(key)
        asyncio.get_event_loop().call_later(30, self.punished.discard, key)

        punishment = ANTINUKE["punishment"]
        try:
            if punishment == "ban":
                await guild.ban(member, reason=f"[AntiNuke] {reason}", delete_message_days=0)
            elif punishment == "kick":
                await guild.kick(member, reason=f"[AntiNuke] {reason}")
            elif punishment == "strip_roles":
                manageable = [r for r in member.roles if r.is_assignable()]
                await member.remove_roles(*manageable, reason=f"[AntiNuke] {reason}")
        except discord.Forbidden:
            pass

        log = await self._get_log_channel(guild)
        if log:
            embed = discord.Embed(
                title="🚨 Anti-Nuke Triggered",
                description=(
                    f"**User:** {member.mention} (`{member.id}`)\n"
                    f"**Reason:** {reason}\n"
                    f"**Action:** `{punishment}`"
                ),
                color=discord.Color.red(),
            )
            embed.set_footer(text="Zara AntiNuke")
            await log.send(embed=embed)

    async def _get_audit_entry(self, guild: discord.Guild, action: discord.AuditLogAction):
        try:
            async for entry in guild.audit_logs(limit=1, action=action):
                return entry
        except discord.Forbidden:
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
                await self._punish(guild, member, f"Mass ban ({count} in {ANTINUKE['time_window']}s)")

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
                await self._punish(guild, kicker, f"Mass kick ({count} in {ANTINUKE['time_window']}s)")

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
                await self._punish(guild, member, f"Mass channel delete ({count} in {ANTINUKE['time_window']}s)")

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
                await self._punish(guild, member, f"Mass channel create ({count} in {ANTINUKE['time_window']}s)")

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
                await self._punish(guild, member, f"Mass role delete ({count} in {ANTINUKE['time_window']}s)")

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
                await self._punish(guild, member, f"Mass role create ({count} in {ANTINUKE['time_window']}s)")

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
                await self._punish(guild, member, f"Webhook spam ({count} in {ANTINUKE['time_window']}s)")
            try:
                webhooks = await channel.webhooks()
                for wh in webhooks:
                    if wh.user and wh.user.id == entry.user.id:
                        await wh.delete(reason="Zara AntiNuke: webhook spam")
            except discord.Forbidden:
                pass


async def setup(bot):
    await bot.add_cog(AntiNuke(bot))
