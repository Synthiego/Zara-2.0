import discord
from discord.ext import commands
import os
import aiohttp
from dotenv import load_dotenv

load_dotenv()

intents = discord.Intents.all()
bot = commands.Bot(command_prefix="§§UNUSED§§", intents=intents, help_command=None)

COGS = ["cogs.antinuke", "cogs.ai_moderation", "cogs.admin"]

# Conversation history per user so Zara remembers context
conversation_history = {}

ZARA_SYSTEM = """You are Zara, a smart and friendly Discord server assistant bot.
You help server admins and members with tasks interactively.

When someone asks for help or says "help me", always respond with a short friendly intro and then list what you can help with in a clean format, like:
"Hey! Here's what I can help you with:
• 🛡️ Antinuke — enable, disable, change settings
• 🤖 Automod — manage moderation rules
• 🔨 Moderation — ban, kick, warn, timeout, purge
• ⚙️ Bot Settings — change Zara's config
• ❓ General — answer any server question

Just tell me what you need and I'll walk you through it step by step!"

When a user picks a task, ask them what they want to do step by step. Ask ONE question at a time. Be concise, warm, and helpful.
If they ask you to do something you cannot do (like actually run code), explain clearly what they need to do manually and guide them through it.
Keep replies under 5 sentences unless showing a list or steps.
You are Zara — not a general AI. You are THIS server's bot assistant."""


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

    # Respond when Zara is mentioned by name or pinged
    bot_mentioned = bot.user in message.mentions
    name_mentioned = "zara" in content_lower

    if name_mentioned or bot_mentioned:
        # Build the user query (strip name/mention)
        query = message.content
        for variant in ["<@!" + str(bot.user.id) + ">", "<@" + str(bot.user.id) + ">",
                        "zara, ", "zara: ", "zara ", "Zara, ", "Zara: ", "Zara "]:
            query = query.replace(variant, "").strip()
        if not query or query.lower() in ("zara", ""):
            query = "help"

        async with message.channel.typing():
            reply = await _chat(message.author.id, query, message.author.display_name)
            await message.reply(reply, mention_author=False)

    await bot.process_commands(message)


async def _chat(user_id: int, query: str, username: str) -> str:
    """Send message to Groq with conversation memory per user."""
    groq_key = os.getenv("GROQ_API_KEY")
    if not groq_key:
        return "⚠️ No `GROQ_API_KEY` found! Add it to your Railway environment variables and redeploy."

    # Init history for this user
    if user_id not in conversation_history:
        conversation_history[user_id] = []

    # Add user message to history
    conversation_history[user_id].append({
        "role": "user",
        "content": f"{username}: {query}"
    })

    # Keep last 10 messages to avoid token limits
    history = conversation_history[user_id][-10:]

    headers = {
        "Authorization": f"Bearer {groq_key}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": "llama3-8b-8192",
        "messages": [{"role": "system", "content": ZARA_SYSTEM}] + history,
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
                if resp.status == 401:
                    return "⚠️ Invalid Groq API key! Check your `GROQ_API_KEY` in Railway variables."
                if resp.status == 429:
                    return "I'm being rate limited — give me a second and try again! 😅"
                if resp.status != 200:
                    error = await resp.text()
                    print(f"Groq error {resp.status}: {error}")
                    return f"⚠️ Groq returned error `{resp.status}`. Check Railway logs for details."

                data = await resp.json()
                reply = data["choices"][0]["message"]["content"].strip()

                # Save Zara's reply to history too
                conversation_history[user_id].append({
                    "role": "assistant",
                    "content": reply
                })

                return reply

    except aiohttp.ClientConnectorError:
        return "⚠️ Can't reach Groq's servers. Check Railway's network settings."
    except Exception as e:
        print(f"Zara chat error: {e}")
        return f"⚠️ Something went wrong: `{e}`"


async def main():
    async with bot:
        for cog in COGS:
            await bot.load_extension(cog)
            print(f"✅ Loaded {cog}")
        await bot.start(os.getenv("DISCORD_TOKEN"))


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
