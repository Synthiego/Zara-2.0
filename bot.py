import discord
from discord.ext import commands
import os
import aiohttp
from dotenv import load_dotenv

load_dotenv()

intents = discord.Intents.all()
bot = commands.Bot(command_prefix="§§UNUSED§§", intents=intents, help_command=None)

COGS = ["cogs.antinuke", "cogs.ai_moderation", "cogs.admin"]

ZARA_SYSTEM = """You are Zara, a friendly and helpful Discord server bot assistant.
You help members, answer questions, and keep things fun.
Keep replies short and conversational — 1 to 3 sentences max.
Be warm, witty, and concise. You are NOT a general AI — you are Zara, this server's bot."""


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

    # Respond when Zara's name is mentioned
    content_lower = message.content.lower().strip()
    if "zara" in content_lower:
        # Extract the actual query by removing the name
        query = message.content
        for variant in ["zara, ", "zara: ", "zara ", "Zara, ", "Zara: ", "Zara "]:
            query = query.replace(variant, "").strip()
        if not query or query.lower() == "zara":
            query = "hello!"

        async with message.channel.typing():
            reply = await _ask_zara(query, message.author.display_name)
            await message.reply(reply, mention_author=False)

    await bot.process_commands(message)


async def _ask_zara(query: str, username: str) -> str:
    """Use Groq's free API (llama3) to generate Zara's reply."""
    groq_key = os.getenv("GROQ_API_KEY")
    if not groq_key:
        return "Hey! I'm Zara 👋 Add a `GROQ_API_KEY` in your Railway environment variables to chat with me!"

    headers = {
        "Authorization": f"Bearer {groq_key}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": "llama3-8b-8192",
        "messages": [
            {"role": "system", "content": ZARA_SYSTEM},
            {"role": "user", "content": f"{username} says: {query}"}
        ],
        "max_tokens": 150,
        "temperature": 0.8
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers=headers,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=8)
            ) as resp:
                if resp.status != 200:
                    return "Hmm, my brain glitched 😅 Try again in a sec!"
                data = await resp.json()
                return data["choices"][0]["message"]["content"].strip()
    except Exception:
        return "I zoned out for a second 😴 Ask me again!"


async def main():
    async with bot:
        for cog in COGS:
            await bot.load_extension(cog)
            print(f"✅ Loaded {cog}")
        await bot.start(os.getenv("DISCORD_TOKEN"))


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
