import discord
from discord.ext import commands
from collections import defaultdict, deque
import time
import re
import datetime
from config import AI_MOD, SPAM, LOG_CHANNEL_NAME

# ── Word/Pattern Lists ────────────────────────────────────────────────
# Add or remove words/patterns freely for your server

TOXIC_WORDS = [
    "nigger", "nigga", "faggot", "fag", "retard", "retarded",
    "kys", "kill yourself", "go die", "hang yourself",
    "cunt", "chink", "spic", "wetback", "tranny", "dyke",
    "rape", "raping", "raped",
]

NSFW_PATTERNS = [
    r"\bnude[s]?\b", r"\bporn\b", r"\bonlyfans\b", r"\bsex\b",
    r"\bdick pic\b", r"\bnaked\b", r"\bnsfw\b", r"\bhentai\b",
    r"\bcum\b", r"\bboobs\b", r"\btits\b", r"\bass pic\b",
]

SCAM_PATTERNS = [
    r"free nitro",
    r"discord.*gift",
    r"claim.*prize",
    r"bit\.ly", r"tinyurl", r"cutt\.ly",
    r"steam.*free",
    r"you (have|won|are) (been )?(selected|chosen|winner)",
]

# ─────────────────────────────────────────────────────────────────────

def _compile(patterns):
    return [re.compile(p, re.IGNORECASE) for p in patterns]

NSFW_RE = _compile(NSFW_PATTERNS)
SCAM_RE = _compile(SCAM_PATTERNS)


class AIMod(commands.Cog):
    """Rule-based chat moderation — no API needed, works instantly."""

    def __init__(self, bot):
        self.bot = bot
        self.message_history = defaultdict(lambda: defaultdict(lambda: deque(maxlen=20)))

    async def _get_log_channel(self, guild):
        return discord.utils.get(guild.text_channels, name=LOG_CHANNEL_NAME)

    def _check_spam(self, guild_id, user_id, content):
        now = time.time()
        history = self.message_history[guild_id][user_id]
        history.append((now, content))

        recent = [t for t, _ in history if now - t < SPAM["per_seconds"]]
        if len(recent) >= SPAM["max_messages"]:
            return True, f"Flooding ({len(recent)} messages in {SPAM['per_seconds']}s)"

        recent_contents = [c for t, c in history if now - t < SPAM["per_seconds"] * 2]
        if recent_contents.count(content) >= SPAM["duplicate_threshold"]:
            return True, f"Repeated identical message ({recent_contents.count(content)}x)"

        return False, ""

    def _check_toxic(self, content):
        lower = content.lower()
        for word in TOXIC_WORDS:
            if word in lower:
                return True, "Hate speech / slur detected"
        return False, ""

    def _check_nsfw(self, content):
        for pattern in NSFW_RE:
            if pattern.search(content):
                return True, "NSFW content detected"
        return False, ""

    def _check_scam(self, content):
        for pattern in SCAM_RE:
            if pattern.search(content):
                return True, "Scam / phishing link detected"
        return False, ""

    def _check_caps(self, content):
        letters = [c for c in content if c.isalpha()]
        if len(letters) > 10:
            caps_ratio = sum(1 for c in letters if c.isupper()) / len(letters)
            if caps_ratio > 0.85:
                return True, f"Excessive caps ({int(caps_ratio * 100)}%)"
        return False, ""

    def _check_mention_spam(self, message):
        mentions = len(message.mentions) + len(message.role_mentions)
        if mentions >= 5:
            return True, f"Mass mention spam ({mentions} pings)"
        return False, ""

    async def _act(self, message, reason, category):
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
    async def on_message(self, message):
        if not message.guild or message.author.bot or not message.content:
            return

        checks = [
            (self._check_spam(message.guild.id, message.author.id, message.content), "spam/flood"),
            (self._check_mention_spam(message), "mention spam"),
            (self._check_scam(message.content), "scam/phishing"),
            (self._check_toxic(message.content), "toxic/hate speech"),
            (self._check_nsfw(message.content), "nsfw"),
            (self._check_caps(message.content), "caps spam"),
        ]

        for (flagged, reason), category in checks:
            if flagged:
                await self._act(message, reason, category)
                return


async def setup(bot):
    await bot.add_cog(AIMod(bot))
