import discord
from discord.ext import commands
from discord import app_commands
import datetime
from config import ANTINUKE, AI_MOD


class Admin(commands.Cog):
    """Slash commands for server admins."""

    def __init__(self, bot):
        self.bot = bot

    def is_admin():
        async def predicate(interaction: discord.Interaction):
            return interaction.user.guild_permissions.administrator
        return app_commands.check(predicate)

    @app_commands.command(name="status", description="Show Zara's current protection settings")
    @is_admin()
    async def status(self, interaction: discord.Interaction):
        embed = discord.Embed(title="🛡️ Zara — Status", color=discord.Color.blurple())

        embed.add_field(name="⚔️ Anti-Nuke", value=(
            f"Ban threshold: `{ANTINUKE['ban_threshold']}` in `{ANTINUKE['time_window']}s`\n"
            f"Kick threshold: `{ANTINUKE['kick_threshold']}` in `{ANTINUKE['time_window']}s`\n"
            f"Channel delete: `{ANTINUKE['channel_delete_threshold']}` in `{ANTINUKE['time_window']}s`\n"
            f"Channel create: `{ANTINUKE['channel_create_threshold']}` in `{ANTINUKE['time_window']}s`\n"
            f"Role delete: `{ANTINUKE['role_delete_threshold']}` in `{ANTINUKE['time_window']}s`\n"
            f"Role create: `{ANTINUKE['role_create_threshold']}` in `{ANTINUKE['time_window']}s`\n"
            f"Webhook spam: `{ANTINUKE['webhook_create_threshold']}` in `{ANTINUKE['time_window']}s`\n"
            f"Punishment: `{ANTINUKE['punishment']}`"
        ), inline=False)

        embed.add_field(name="🤖 AI Moderation", value=(
            f"Toxic threshold: `{AI_MOD['toxic_threshold']}`\n"
            f"NSFW threshold: `{AI_MOD['nsfw_threshold']}`\n"
            f"Action: `{AI_MOD['action']}`\n"
            f"Timeout duration: `{AI_MOD['timeout_minutes']} min`"
        ), inline=False)

        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="purge", description="Delete multiple messages at once")
    @app_commands.describe(amount="How many messages to delete (1–100)")
    @is_admin()
    async def purge(self, interaction: discord.Interaction, amount: app_commands.Range[int, 1, 100]):
        await interaction.response.defer(ephemeral=True)
        deleted = await interaction.channel.purge(limit=amount)
        await interaction.followup.send(f"🗑️ Deleted `{len(deleted)}` messages.", ephemeral=True)

    @app_commands.command(name="warn", description="Send a warning to a member")
    @app_commands.describe(member="Who to warn", reason="Why")
    @is_admin()
    async def warn(self, interaction: discord.Interaction, member: discord.Member, reason: str = "No reason provided"):
        embed = discord.Embed(
            title="⚠️ Warning Issued",
            description=f"{member.mention} has been warned.\n**Reason:** {reason}",
            color=discord.Color.yellow(),
        )
        await interaction.response.send_message(embed=embed)
        try:
            await member.send(f"⚠️ You were warned in **{interaction.guild.name}**.\n**Reason:** {reason}")
        except discord.Forbidden:
            pass

    @app_commands.command(name="timeout", description="Temporarily mute a member")
    @app_commands.describe(member="Who to timeout", minutes="Duration (minutes)", reason="Why")
    @is_admin()
    async def timeout_member(self, interaction: discord.Interaction, member: discord.Member, minutes: app_commands.Range[int, 1, 10080], reason: str = "No reason provided"):
        until = discord.utils.utcnow() + datetime.timedelta(minutes=minutes)
        await member.timeout(until, reason=reason)
        await interaction.response.send_message(
            f"⏱️ {member.mention} timed out for `{minutes}` min. Reason: {reason}", ephemeral=True
        )

    @app_commands.command(name="ban", description="Ban a member from the server")
    @app_commands.describe(member="Who to ban", reason="Why")
    @is_admin()
    async def ban_member(self, interaction: discord.Interaction, member: discord.Member, reason: str = "No reason provided"):
        await member.ban(reason=reason)
        await interaction.response.send_message(f"🔨 {member.mention} banned. Reason: {reason}", ephemeral=True)

    @app_commands.command(name="kick", description="Kick a member from the server")
    @app_commands.describe(member="Who to kick", reason="Why")
    @is_admin()
    async def kick_member(self, interaction: discord.Interaction, member: discord.Member, reason: str = "No reason provided"):
        await member.kick(reason=reason)
        await interaction.response.send_message(f"👢 {member.mention} kicked. Reason: {reason}", ephemeral=True)

    @app_commands.command(name="unban", description="Unban a user by their ID")
    @app_commands.describe(user_id="The Discord user ID to unban")
    @is_admin()
    async def unban(self, interaction: discord.Interaction, user_id: str):
        try:
            user = await self.bot.fetch_user(int(user_id))
            await interaction.guild.unban(user)
            await interaction.response.send_message(f"✅ Unbanned `{user}`.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Failed: {e}", ephemeral=True)


async def setup(bot):
    await bot.add_cog(Admin(bot))
