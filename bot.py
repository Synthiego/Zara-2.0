import discord
from discord.ext import commands
import os
import aiohttp
import json
import re
from dotenv import load_dotenv

load_dotenv()

intents = discord.Intents.all()
# Zara prefix is her name — "zara ban @user" works as a command
bot = commands.Bot(command_prefix=["zara ", "Zara "], intents=intents, help_command=None)

COGS = ["cogs.antinuke", "cogs.ai_moderation", "cogs.admin"]

# Conversation history per user
conversation_history = {}

ZARA_SYSTEM = """You are Zara, a smart and friendly Discord server assistant bot.
You help server admins and members with tasks interactively.

When someone asks for help, list what you can do:
"Hey! Here's what I can help you with:
• 🔨 Moderation — ban, kick, warn, timeout, softban, purge
• 🔒 Channels — lock, unlock, hide, show, lockdown, slowmode
• 📋 Logs — userinfo, warnlog, clearwarns
• 🛡️ Security — whitelist, unwhitelist, antinuke status
• ❓ General — answer any server question

You can also just tell me what to do and I'll do it!
Example: 'zara ban @user spamming' or 'zara lock this channel'"

When a user asks you to DO something, respond naturally confirming what you did.
Keep replies short — under 4 sentences unless listing steps."""


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

    content_lower = message.content.lower().strip()
    bot_mentioned = bot.user in message.mentions

    # Let prefix commands (zara ban, zara kick etc) be handled by discord.py first
    ctx = await bot.get_context(message)
    if ctx.valid:
        await bot.invoke(ctx)
        return

    # If Zara is mentioned by name or ping but it's not a known command → chat
    if "zara" in content_lower or bot_mentioned:
        query = message.content
        for variant in [f"<@!{bot.user.id}>", f"<@{bot.user.id}>",
                        "zara, ", "zara: ", "Zara, ", "Zara: "]:
            query = query.replace(variant, "").strip()
        # Remove leading "zara" if left over
        if query.lower().startswith("zara"):
            query = query[4:].strip()
        if not query:
            query = "help"

        async with message.channel.typing():
            reply = await _chat(message.author.id, query)
            await message.reply(reply, mention_author=False)


async def _chat(user_id: int, query: str) -> str:
    groq_key = os.getenv("GROQ_API_KEY")
    if not groq_key:
        return "⚠️ No `GROQ_API_KEY` set in Railway variables!"

    if user_id not in conversation_history:
        conversation_history[user_id] = []

    conversation_history[user_id].append({"role": "user", "content": query})

    history = conversation_history[user_id][-10:]

    # Sanitize: strictly alternate roles, must start with user
    sanitized = []
    for msg in history:
        if sanitized and sanitized[-1]["role"] == msg["role"]:
            sanitized[-1]["content"] += "\n" + msg["content"]
        else:
            sanitized.append({"role": msg["role"], "content": msg["content"]})
    if sanitized and sanitized[0]["role"] != "user":
        sanitized = sanitized[1:]

    headers = {
        "Authorization": f"Bearer {groq_key}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": "llama-3.3-70b-versatile",
        "messages": [{"role": "system", "content": ZARA_SYSTEM}] + sanitized,
        "max_tokens": 400,
        "temperature": 0.7
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers=headers,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=10)
            ) as resp:
                body = await resp.text()
                if resp.status == 401:
                    conversation_history.pop(user_id, None)
                    return "⚠️ Invalid Groq API key! Check `GROQ_API_KEY` in Railway."
                if resp.status == 429:
                    return "I'm being rate limited — try again in a sec! 😅"
                if resp.status != 200:
                    print(f"Groq {resp.status}: {body}")
                    conversation_history.pop(user_id, None)
                    return f"⚠️ Groq error `{resp.status}`: {body[:300]}"

                data = json.loads(body)
                reply = data["choices"][0]["message"]["content"].strip()
                conversation_history[user_id].append({"role": "assistant", "content": reply})
                return reply

    except aiohttp.ClientConnectorError:
        return "⚠️ Can't reach Groq. Check Railway network settings."
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
