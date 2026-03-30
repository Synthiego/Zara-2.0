import discord
from discord.ext import commands
from collections import defaultdict, deque
import time
import aiohttp
import datetime
import os
from config import AI_MOD, SPAM, LOG_CHANNEL_NAME


class AIMod(commands.Cog):
    """Chat moderation using Google's free Perspective API + local spam detection."""

    def __init__(self, bot):
        self.bot = bot
        self.perspective_key = os.getenv("PERSPECTIVE_API_KEY")
        self.message_history: dict = defaultdict(lambda: defaultdict(lambda: deque(maxlen=20)))

    async def _get_log_channel(self, guild: discord.Guild):
        return discord.utils.get(guild.text_channels, name=LOG_CHANNEL_NAME)

    def _check_spam(self, guild_id: int, user_id: int, content: str) -> tuple[bool, str]:
        """Fast local spam check — no API needed, instant."""
        now = time.time()
        history = self.message_history[guild_id][user_id]
        history.append((now, content))

        recent = [t for t, _ in history if now - t < SPAM["per_seconds"]]
        if len(recent) >= SPAM["max_messages"]:
            return True, f"Flooding ({len(recent)} msgs in {SPAM['per_seconds']}s)"

        recent_contents = [c for t, c in history if now - t < SPAM["per_seconds"] * 2]
        if recent_contents.count(content) >= SPAM["duplicate_threshold"]:
            return True, f"Copy-pasting same message ({recent_contents.count(content)}x)"

        return False, ""

    async def _perspective_check(self, content: str) -> dict | None:
        """
        Google Perspective API — completely free.
        Sign up at: https://developers.perspectiveapi.com/s/docs-get-started
        Returns scores 0.0–1.0 for toxic/nsfw/threat.
        """
        if not self.perspective_key:
            return None

        url = f"https://commentanalyzer.googleapis.com/v1alpha1/comments:analyze?key={self.perspective_key}"
        payload = {
            "comment": {"text": content[:3000]},
            "requestedAttributes": {
                "TOXICITY": {},
                "SEVERE_TOXICITY": {},
                "SEXUALLY_EXPLICIT": {},
                "THREAT": {},
                "INSULT": {},
            },
            "doNotStore": True,
        }
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                    if resp.status != 200:
                        return None
                    data = await resp.json()
                    s = data.get("attributeScores", {})
                    return {
                        "toxic":  s.get("TOXICITY", {}).get("summaryScore", {}).get("value", 0),
                        "severe": s.get("SEVERE_TOXICITY", {}).get("summaryScore", {}).get("value", 0),
                        "nsfw":   s.get("SEXUALLY_EXPLICIT", {}).get("summaryScore", {}).get("value", 0),
                        "threat": s.get("THREAT", {}).get("summaryScore", {}).get("value", 0),
                        "insult": s.get("INSULT", {}).get("summaryScore", {}).get("value", 0),
                    }
        except Exception:
            return None

    async def _act(self, message: discord.Message, reason: str, category: str):
        """Delete the message, warn the user, optionally timeout."""
        try:
            await message.delete()
        except (discord.NotFound, discord.Forbidden):
            pass

        action = AI_MOD["action"]

        if action in ("delete_and_warn", "timeout"):
            try:
                await message.channel.send(
                    f"⚠️ {message.author.mention} Your message was removed for **{category}**.",
                    delete_after=8,
                )
            except discord.Forbidden:
                pass

        if action == "timeout":
            member = message.guild.get_member(message.author.id)
            if member:
                try:
                    until = discord.utils.utcnow() + datetime.timedelta(minutes=AI_MOD["timeout_minutes"])
                    await member.timeout(until, reason=f"Zara Mod: {reason}")
                except discord.Forbidden:
                    pass

        log = await self._get_log_channel(message.guild)
        if log:
            embed = discord.Embed(
                title=f"🤖 Zara Mod — {category.upper()}",
                color=discord.Color.orange(),
            )
            embed.add_field(name="User", value=f"{message.author.mention} (`{message.author.id}`)", inline=True)
            embed.add_field(name="Channel", value=message.channel.mention, inline=True)
            embed.add_field(name="Reason", value=reason, inline=False)
            embed.add_field(name="Message", value=f"||{message.content[:300]}||", inline=False)
            embed.set_footer(text="Zara Moderation")
            await log.send(embed=embed)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if not message.guild or message.author.bot or not message.content:
            return

        # 1️⃣ Fast spam check first (no API call needed)
        is_spam, spam_reason = self._check_spam(message.guild.id, message.author.id, message.content)
        if is_spam:
            await self._act(message, spam_reason, "spam/flood")
            return

        # 2️⃣ Skip very short messages (not worth an API call)
        if len(message.content) < 5:
            return

        # 3️⃣ Perspective API check
        scores = await self._perspective_check(message.content)
        if not scores:
            return

        toxic_score = max(scores["toxic"], scores["insult"])
        nsfw_score  = scores["nsfw"]
        threat_score = scores["threat"]

        if threat_score >= 0.80:
            await self._act(message, f"Threat detected (score: {threat_score:.2f})", "threat")
        elif toxic_score >= AI_MOD["toxic_threshold"]:
            await self._act(message, f"Toxic/hate speech (score: {toxic_score:.2f})", "toxic/hate speech")
        elif nsfw_score >= AI_MOD["nsfw_threshold"]:
            await self._act(message, f"NSFW content (score: {nsfw_score:.2f})", "nsfw")

        # Log borderline messages without acting
        elif AI_MOD["log_borderlines"]:
            worst = max(scores.values())
            if worst >= 0.5:
                label = max(scores, key=scores.get)
                log = await self._get_log_channel(message.guild)
                if log:
                    embed = discord.Embed(
                        title=f"🔍 Borderline — {label.upper()} ({worst:.2f})",
                        description="Below threshold — no action taken.",
                        color=discord.Color.yellow(),
                    )
                    embed.add_field(name="User", value=message.author.mention, inline=True)
                    embed.add_field(name="Channel", value=message.channel.mention, inline=True)
                    embed.add_field(name="Message", value=f"||{message.content[:200]}||", inline=False)
                    await log.send(embed=embed)


async def setup(bot):
    await bot.add_cog(AIMod(bot))
