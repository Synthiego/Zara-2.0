import discord
from discord.ext import commands
import os
import aiohttp
import json
import re
from dotenv import load_dotenv
from config import AUTHORIZED_IDS

load_dotenv()

intents = discord.Intents.all()
bot = commands.Bot(command_prefix=["zara ", "Zara "], intents=intents, help_command=None)

COGS = ["cogs.antinuke", "cogs.ai_moderation", "cogs.admin"]

conversation_history = {}

ZARA_SYSTEM = """You are Zara, a Discord bot assistant. You can chat AND perform real actions.

When a user asks you to perform a moderation action, you MUST respond with ONLY a JSON object and nothing else.
No explanation, no extra text — just the raw JSON.

Action JSON format:
{"action": "ACTION_NAME", "target": "USER_ID_OR_MENTION", "duration": MINUTES_OR_NULL, "reason": "reason or null"}

Supported actions: timeout, ban, kick, softban, warn, purge, lock, unlock, hide, show, lockdown, unlockdown, slowmode, userinfo, warnlog, clearwarns, whitelist, unwhitelist

Examples:
User: "timeout @john for 10 minutes"
Response: {"action": "timeout", "target": "@john", "duration": 10, "reason": null}

User: "ban 680763657428271117 raiding"
Response: {"action": "ban", "target": "680763657428271117", "duration": null, "reason": "raiding"}

User: "purge 20 messages"
Response: {"action": "purge", "target": null, "duration": 20, "reason": null}

User: "lock this channel"
Response: {"action": "lock", "target": null, "duration": null, "reason": null}

User: "slowmode 10 seconds"
Response: {"action": "slowmode", "target": null, "duration": 10, "reason": null}

If the user is just chatting (not requesting an action), respond normally as a friendly assistant.
When listing help, show: timeout, ban, kick, softban, warn, purge, lock, unlock, hide, show, lockdown, slowmode, userinfo, warnlog, clearwarns, whitelist."""


def extract_ids(text: str) -> list[str]:
    """Extract all Discord user IDs and mentions from text."""
    ids = re.findall(r'\d{17,19}', text)
    return ids

# ── Keyword Pre-Filter ────────────────────────────────────────────────
# Catches common phrases before hitting Groq so they never get misread

INTENT_MAP = {
    # Timeout / mute
    ("timeout", "mute", "shut up", "silence"): "timeout",
    # Unmute / untimeout
    ("unmute", "untimeout", "remove timeout", "remove mute", "unsilence", "unmuted", "un-mute", "un-timeout"): "unmute",
    # Ban
    ("ban", "get rid of", "remove permanently"): "ban",
    # Kick
    ("kick", "remove from server", "boot"): "kick",
    # Softban
    ("softban", "soft ban", "clean ban"): "softban",
    # Unban
    ("unban", "un-ban"): "unban",
    # Warn
    ("warn", "warning", "give warning"): "warn",
    # Purge
    ("purge", "clear messages", "delete messages", "clean chat", "clear chat"): "purge",
    # Delete channel
    ("delete this channel", "delete channel", "remove this channel", "remove channel"): "delete_channel",
    # Lock - more specific to avoid false matches
    ("lock channel", "lock this channel", "lock the channel"): "lock",
    # Unlock
    ("unlock channel", "unlock this", "unlock the channel"): "unlock",
    # Hide
    ("hide channel", "hide this"): "hide",
    # Show
    ("show channel", "unhide"): "show",
    # Lockdown
    ("lockdown", "lock down", "lock everything", "lock all"): "lockdown",
    # Unlockdown
    ("unlockdown", "unlock everything", "unlock all", "lift lockdown"): "unlockdown",
    # Slowmode
    ("slowmode", "slow mode", "slow down"): "slowmode",
    # Userinfo
    ("userinfo", "user info", "info on", "info about", "lookup", "look up", "who is", "check user"): "userinfo",
    # Warnlog
    ("warnlog", "warn log", "warnings for", "check warns", "show warns"): "warnlog",
    # Clearwarns
    ("clearwarns", "clear warns", "clear warnings", "remove warns", "delete warns"): "clearwarns",
    # Whitelist
    ("whitelist"): "whitelist",
    # Unwhitelist
    ("unwhitelist", "remove whitelist"): "unwhitelist",
}

# Question words that indicate the user is asking, not commanding
QUESTION_PREFIXES = (
    "do you think", "should i", "should we", "what do you think",
    "would you", "can you explain", "why did", "what is", "what are",
    "how do", "is it", "does it", "tell me about", "what happens"
)

def detect_intent(text: str) -> str | None:
    """Check if the message matches a known action keyword before hitting Groq.
    Skips detection if the message is clearly a question, not a command."""
    lower = text.lower().strip()

    # If it sounds like a question, let Groq handle it conversationally
    for prefix in QUESTION_PREFIXES:
        if lower.startswith(prefix):
            return None
    # Also skip if it ends with a question mark and has no clear target
    if lower.endswith("?"):
        return None

    for keywords, action in INTENT_MAP.items():
        if isinstance(keywords, str):
            keywords = (keywords,)
        for kw in keywords:
            if kw in lower:
                return action
    return None



async def execute_action(message: discord.Message, action_data: dict) -> str:
    """Actually execute the requested Discord action."""
    action = action_data.get("action", "").lower()
    target_raw = action_data.get("target")
    duration = action_data.get("duration")
    reason = action_data.get("reason") or "Requested via Zara"
    guild = message.guild

    # Resolve target member
    member = None
    if target_raw:
        ids = extract_ids(str(target_raw))
        if ids:
            try:
                member = guild.get_member(int(ids[0])) or await guild.fetch_member(int(ids[0]))
            except Exception:
                pass
        if not member and message.mentions:
            member = message.mentions[0]

    try:
        # ── Channel actions (no target needed) ───────────────────────
        if action == "lock":
            ow = message.channel.overwrites_for(guild.default_role)
            ow.send_messages = False
            await message.channel.edit(overwrites={guild.default_role: ow})
            return f"🔒 Locked {message.channel.mention}."

        elif action == "unlock":
            ow = message.channel.overwrites_for(guild.default_role)
            ow.send_messages = None
            await message.channel.edit(overwrites={guild.default_role: ow})
            return f"🔓 Unlocked {message.channel.mention}."

        elif action == "hide":
            ow = message.channel.overwrites_for(guild.default_role)
            ow.view_channel = False
            await message.channel.edit(overwrites={guild.default_role: ow})
            return f"🙈 Hidden {message.channel.mention}."

        elif action == "show":
            ow = message.channel.overwrites_for(guild.default_role)
            ow.view_channel = None
            await message.channel.edit(overwrites={guild.default_role: ow})
            return f"👁️ Unhid {message.channel.mention}."

        elif action == "delete_channel":
            name = message.channel.name
            await message.channel.delete(reason=f"Deleted by {message.author} via Zara")
            return None  # Channel is gone, can't send here

        elif action == "slowmode":
            secs = int(duration) if duration else 0
            await message.channel.edit(slowmode_delay=secs)
            return f"⏱️ Slowmode set to `{secs}s` in {message.channel.mention}."

        elif action == "lockdown":
            count = 0
            for ch in guild.text_channels:
                try:
                    ow = ch.overwrites_for(guild.default_role)
                    ow.send_messages = False
                    await ch.edit(overwrites={guild.default_role: ow})
                    count += 1
                except discord.Forbidden:
                    pass
            return f"🚨 Server locked down! Locked `{count}` channels."

        elif action == "unlockdown":
            count = 0
            for ch in guild.text_channels:
                try:
                    ow = ch.overwrites_for(guild.default_role)
                    ow.send_messages = None
                    await ch.edit(overwrites={guild.default_role: ow})
                    count += 1
                except discord.Forbidden:
                    pass
            return f"✅ Lockdown lifted! Unlocked `{count}` channels."

        elif action == "purge":
            amount = int(duration) if duration else 10
            # Also delete Zara's own reply message if any
            deleted = await message.channel.purge(limit=min(amount + 1, 101))
            return f"🗑️ Deleted `{len(deleted)}` messages."

        # ── Member actions ────────────────────────────────────────────
        if not member:
            return f"❌ I couldn't find that user. Try mentioning them with @ or give me their exact ID."

        if action == "timeout":
            mins = int(duration) if duration else 10
            import datetime
            until = discord.utils.utcnow() + datetime.timedelta(minutes=mins)
            await member.timeout(until, reason=reason)
            return f"⏱️ Timed out {member.mention} for `{mins}` minutes. Reason: {reason}"

        elif action == "ban":
            await member.ban(reason=reason, delete_message_days=0)
            return f"🔨 Banned {member.mention}. Reason: {reason}"

        elif action == "kick":
            await member.kick(reason=reason)
            return f"👢 Kicked {member.mention}. Reason: {reason}"

        elif action == "softban":
            await member.ban(reason=f"[Softban] {reason}", delete_message_days=7)
            await guild.unban(member)
            return f"🧹 Softbanned {member.mention} — messages cleared, can rejoin."

        elif action == "warn":
            from cogs.admin import add_warn, get_warns
            add_warn(guild.id, member.id, reason, str(message.author))
            warns = get_warns(guild.id, member.id)
            try:
                await member.send(f"⚠️ You were warned in **{guild.name}**.\n**Reason:** {reason}")
            except discord.Forbidden:
                pass
            return f"⚠️ Warned {member.mention}. Total warnings: `{len(warns)}`. Reason: {reason}"

        elif action == "userinfo":
            from cogs.admin import get_warns, is_whitelisted
            warns = get_warns(guild.id, member.id)
            created = discord.utils.format_dt(member.created_at, style="R")
            joined = discord.utils.format_dt(member.joined_at, style="R") if member.joined_at else "Unknown"
            roles = [r.mention for r in member.roles if r != guild.default_role]
            embed = discord.Embed(title=f"👤 {member}", color=member.color)
            embed.set_thumbnail(url=member.display_avatar.url)
            embed.add_field(name="ID", value=str(member.id), inline=True)
            embed.add_field(name="Created", value=created, inline=True)
            embed.add_field(name="Joined", value=joined, inline=True)
            embed.add_field(name="⚠️ Warns", value=str(len(warns)), inline=True)
            embed.add_field(name="🛡️ Whitelisted", value="Yes" if is_whitelisted(guild.id, member.id) else "No", inline=True)
            embed.add_field(name=f"Roles ({len(roles)})", value=" ".join(roles[:10]) or "None", inline=False)
            await message.channel.send(embed=embed)
            return None  # Already sent embed

        elif action == "warnlog":
            from cogs.admin import get_warns
            warns = get_warns(guild.id, member.id)
            embed = discord.Embed(title=f"⚠️ Warnings for {member}", color=discord.Color.yellow())
            if not warns:
                embed.description = "No warnings on record."
            else:
                for i, w in enumerate(warns, 1):
                    embed.add_field(name=f"#{i} — {w['time'][:10]}", value=f"**Reason:** {w['reason']}\n**By:** {w['mod']}", inline=False)
            await message.channel.send(embed=embed)
            return None

        elif action == "clearwarns":
            from cogs.admin import clear_warns
            clear_warns(guild.id, member.id)
            return f"✅ Cleared all warnings for {member.mention}."

        elif action == "whitelist":
            from cogs.admin import add_whitelist
            add_whitelist(guild.id, member.id)
            return f"🛡️ {member.mention} whitelisted from antinuke."

        elif action == "unwhitelist":
            from cogs.admin import remove_whitelist
            remove_whitelist(guild.id, member.id)
            return f"✅ {member.mention} removed from whitelist."

        else:
            return f"❓ I don't know how to do `{action}` yet."

    except discord.Forbidden:
        return f"❌ I don't have permission to do that! Make sure my role is above {member.mention if member else 'the target'}."
    except Exception as e:
        return f"❌ Something went wrong: `{e}`"


@bot.event
async def on_ready():
    print(f"✅ Zara is online as {bot.user} ({bot.user.id})")
    await bot.tree.sync()
    print("✅ Slash commands synced")
    await bot.change_presence(activity=discord.Activity(
        type=discord.ActivityType.watching,
        name="the server 👀"
    ))


@bot.event
async def on_message(message: discord.Message):
    if message.author.bot or not message.guild:
        return

    # Let real prefix commands run first
    ctx = await bot.get_context(message)
    if ctx.valid:
        await bot.invoke(ctx)
        return

    content_lower = message.content.lower().strip()
    bot_mentioned = bot.user in message.mentions

    if "zara" in content_lower or bot_mentioned:
        # Only authorized IDs can interact with Zara
        if message.author.id not in AUTHORIZED_IDS:
            return

        query = message.content
        for variant in [f"<@!{bot.user.id}>", f"<@{bot.user.id}>",
                        "zara, ", "zara: ", "Zara, ", "Zara: "]:
            query = query.replace(variant, "").strip()
        if query.lower().startswith("zara"):
            query = query[4:].strip()
        if not query:
            query = "help"

        async with message.channel.typing():
            # Pre-filter: check for known intent before hitting Groq
            intent = detect_intent(query)
            if intent:
                ids = extract_ids(query)
                target = message.mentions[0].mention if message.mentions else (ids[0] if ids else None)
                # Extract duration if present
                dur_match = re.search(r'(\d+)\s*(min|minute|second|sec|hour|hr)', query.lower())
                duration = int(dur_match.group(1)) if dur_match else (10 if intent in ("timeout",) else None)
                # Extract reason
                reason_match = re.search(r'(?:for|reason)[:\s]+(.+)', query, re.IGNORECASE)
                reason = reason_match.group(1).strip() if reason_match else None
                action_data = {"action": intent, "target": target, "duration": duration, "reason": reason}
                result = await execute_action(message, action_data)
                if result:
                    await message.reply(result, mention_author=False)
                return

            response = await _chat(message.author.id, query, message)
            if response:
                await message.reply(response, mention_author=False)


async def _chat(user_id: int, query: str, message: discord.Message) -> str:
    groq_key = os.getenv("GROQ_API_KEY")
    if not groq_key:
        return "⚠️ No `GROQ_API_KEY` set in Railway variables!"

    if user_id not in conversation_history:
        conversation_history[user_id] = []

    conversation_history[user_id].append({"role": "user", "content": query})
    history = conversation_history[user_id][-10:]

    sanitized = []
    for msg in history:
        if sanitized and sanitized[-1]["role"] == msg["role"]:
            sanitized[-1]["content"] += "\n" + msg["content"]
        else:
            sanitized.append({"role": msg["role"], "content": msg["content"]})
    if sanitized and sanitized[0]["role"] != "user":
        sanitized = sanitized[1:]

    headers = {"Authorization": f"Bearer {groq_key}", "Content-Type": "application/json"}
    payload = {
        "model": "llama-3.3-70b-versatile",
        "messages": [{"role": "system", "content": ZARA_SYSTEM}] + sanitized,
        "max_tokens": 400,
        "temperature": 0.3
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers=headers, json=payload,
                timeout=aiohttp.ClientTimeout(total=10)
            ) as resp:
                body = await resp.text()
                if resp.status != 200:
                    print(f"Groq {resp.status}: {body}")
                    conversation_history.pop(user_id, None)
                    return f"⚠️ Groq error `{resp.status}`: {body[:200]}"

                data = json.loads(body)
                reply = data["choices"][0]["message"]["content"].strip()

                # Check if Zara returned an action JSON
                try:
                    # Strip markdown code blocks if present
                    clean = re.sub(r"```json|```", "", reply).strip()
                    if clean.startswith("{"):
                        action_data = json.loads(clean)
                        if "action" in action_data:
                            result = await execute_action(message, action_data)
                            if result:
                                conversation_history[user_id].append({"role": "assistant", "content": result})
                            return result
                except (json.JSONDecodeError, KeyError):
                    pass

                conversation_history[user_id].append({"role": "assistant", "content": reply})
                return reply

    except aiohttp.ClientConnectorError:
        return "⚠️ Can't reach Groq. Check Railway network."
    except Exception as e:
        print(f"Zara error: {e}")
        conversation_history.pop(user_id, None)
        return f"⚠️ Error: `{e}`"


async def main():
    async with bot:
        for cog in COGS:
            await bot.load_extension(cog)
            print(f"✅ Loaded {cog}")
        await bot.start(os.getenv("DISCORD_TOKEN"))


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
