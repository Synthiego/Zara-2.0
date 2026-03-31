import discord
from discord.ext import commands
import os
import aiohttp
from dotenv import load_dotenv

load_dotenv()

intents = discord.Intents.all()
bot = commands.Bot(command_prefix="§§UNUSED§§", intents=intents, help_command=None)

COGS = ["cogs.antinuke", "cogs.ai_moderation", "cogs.admin"]

# Conversation history per user
conversation_history = {}

ZARA_SYSTEM = """You are Zara, a smart and friendly Discord server assistant bot.
You help server admins and members with tasks interactively.

When someone asks for help or says "help", always respond with a short friendly intro and list what you can help with:
"Hey! Here's what I can help you with:
• 🛡️ Antinuke — enable, disable, change settings
• 🤖 Automod — manage moderation rules
• 🔨 Moderation — ban, kick, warn, timeout, purge
• ⚙️ Bot Settings — change Zara's config
• ❓ General — answer any server question

Just tell me what you need and I'll walk you through it step by step!"

When a user picks a task, ask them what they want to do step by step. Ask ONE question at a time.
Be concise, warm, and helpful. Keep replies under 5 sentences unless showing a list or steps.
You are Zara — this server's bot assistant."""


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
    name_mentioned = "zara" in content_lower

    if name_mentioned or bot_mentioned:
        query = message.content
        for variant in [f"<@!{bot.user.id}>", f"<@{bot.user.id}>",
                        "zara, ", "zara: ", "zara ", "Zara, ", "Zara: ", "Zara "]:
            query = query.replace(variant, "").strip()
        if not query or query.lower() in ("zara", ""):
            query = "help"

        async with message.channel.typing():
            reply = await _chat(message.author.id, query)
            await message.reply(reply, mention_author=False)

    await bot.process_commands(message)


async def _chat(user_id: int, query: str) -> str:
    groq_key = os.getenv("GROQ_API_KEY")
    if not groq_key:
        return "⚠️ No `GROQ_API_KEY` found! Add it to Railway variables and redeploy."

    if user_id not in conversation_history:
        conversation_history[user_id] = []

    conversation_history[user_id].append({
        "role": "user",
        "content": query
    })

    # Keep last 10 messages only
    history = conversation_history[user_id][-10:]

    # Ensure messages strictly alternate (Groq requirement)
    sanitized = []
    for msg in history:
        if sanitized and sanitized[-1]["role"] == msg["role"]:
            sanitized[-1]["content"] += "\n" + msg["content"]
        else:
            sanitized.append({"role": msg["role"], "content": msg["content"]})

    # Must start with user role
    if sanitized and sanitized[0]["role"] != "user":
        sanitized = sanitized[1:]

    headers = {
        "Authorization": f"Bearer {groq_key}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": "llama3-8b-8192",
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
                    return "⚠️ Invalid Groq API key! Double-check `GROQ_API_KEY` in Railway."
                if resp.status == 429:
                    return "I'm being rate limited — try again in a second! 😅"
                if resp.status != 200:
                    print(f"Groq {resp.status}: {body}")
                    conversation_history.pop(user_id, None)
                    return f"⚠️ Groq error `{resp.status}`: {body[:300]}"

                import json
                data = json.loads(body)
                reply = data["choices"][0]["message"]["content"].strip()

                conversation_history[user_id].append({
                    "role": "assistant",
                    "content": reply
                })

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
