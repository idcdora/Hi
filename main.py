import discord
from discord.ext import commands
import asyncio
import requests
from bs4 import BeautifulSoup
import time
import re

watched_users = {}
watched_roles = set()
react_all_servers = {}
token_user_ids = set()
all_bots = []
blacklisted_users = {}
lyrics_tasks = {}

with open("tokens.txt", "r") as f:
    tokens = [line.strip() for line in f if line.strip()]

# ----------------
# AZLyrics lyric search
# ----------------
def get_lyrics_from_azlyrics(song_query):
    search_url = f"https://search.azlyrics.com/search.php?q={requests.utils.quote(song_query)}"
    headers = {"User-Agent": "Mozilla/5.0"}
    search_page = requests.get(search_url, headers=headers)

    if search_page.status_code != 200:
        return None, f"Could not perform search (status code {search_page.status_code})."

    soup = BeautifulSoup(search_page.text, "html.parser")
    table = soup.find("table", class_="table table-condensed")
    if not table:
        return None, "No results found."
    first_link = table.find("a")
    if not first_link or not first_link.get("href"):
        return None, "No valid link found."

    lyrics_url = first_link["href"]
    lyrics_page = requests.get(lyrics_url, headers=headers)
    if lyrics_page.status_code != 200:
        return None, f"Could not fetch lyrics page (status {lyrics_page.status_code})."

    lyrics_soup = BeautifulSoup(lyrics_page.text, "html.parser")
    divs = lyrics_soup.find_all("div")
    for div in divs:
        if div.attrs == {}:
            text = div.get_text(separator="\n").strip()
            return text.splitlines(), None

    return None, "Lyrics not found on the page."

# ----------------
# Run bot
# ----------------
async def run_bot(token):
    bot = commands.Bot(command_prefix="!", self_bot=True)
    all_bots.append(bot)
    typer_tasks = {}
    snipes = {}

    @bot.event
    async def on_ready():
        print(f"[+] Logged in as {bot.user}")
        token_user_ids.add(bot.user.id)

    @bot.event
    async def on_message(message):
        if message.author.id in blacklisted_users:
            return
        await bot.process_commands(message)

    @bot.event
    async def on_message_delete(message):
        if message.author.id == bot.user.id:
            return
        snipes[message.channel.id] = message

    # ----------------
    # Lyrics commands
    # ----------------
    @bot.command()
    async def lyrics(ctx, *, query):
        await ctx.send(f"Searching lyrics for: `{query}`")
        lines, error = get_lyrics_from_azlyrics(query)
        if error:
            await ctx.send(f"❌ {error}")
            return

        await ctx.send(f"✅ Lyrics found for `{query}` — updating status...")

        old_task = lyrics_tasks.get(ctx.author.id)
        if old_task:
            old_task.cancel()

        task = asyncio.create_task(lyrics_status_loop(bot, lines))
        lyrics_tasks[ctx.author.id] = task

    async def lyrics_status_loop(bot_instance, lines):
        idx = 0
        while True:
            line = lines[idx % len(lines)].strip()
            if line:
                try:
                    await bot_instance.change_presence(activity=None)
                    await bot_instance.change_presence(activity=discord.Game(name=line))
                except Exception as e:
                    print("Error updating status:", e)
            idx += 1
            await asyncio.sleep(1.5)

    @bot.command()
    async def stoplyrics(ctx):
        task = lyrics_tasks.get(ctx.author.id)
        if task:
            task.cancel()
            lyrics_tasks.pop(ctx.author.id, None)
            await ctx.send("🛑 Stopped lyrics status.")
        else:
            await ctx.send("You don't have any active lyrics status.")

    # ----------------
    # Snipe command
    # ----------------
    @bot.command()
    async def snipe(ctx):
        msg = snipes.get(ctx.channel.id)
        if not msg:
            await ctx.send("Nothing to snipe!")
            return
        await ctx.send(f"Sniped message from {msg.author}: {msg.content or '[embed/image]'}")

    # ----------------
    # Blacklist
    # ----------------
    @bot.command()
    async def blacklist(ctx, user_id: int):
        blacklisted_users[user_id] = True
        await ctx.send(f"User {user_id} blacklisted.")
        await ctx.message.delete()

    @bot.command()
    async def unblacklist(ctx, user_id: int):
        blacklisted_users.pop(user_id, None)
        await ctx.send(f"User {user_id} unblacklisted.")
        await ctx.message.delete()

    # ----------------
    # React commands
    # ----------------
    @bot.command()
    async def react(ctx, user: discord.User, *emojis):
        watched_users[user.id] = list(emojis)
        await ctx.send(f"Now reacting to {user.name} with {''.join(emojis)}")
        await ctx.message.delete()

    @bot.command()
    async def unreact(ctx, user: discord.User):
        watched_users.pop(user.id, None)
        await ctx.send(f"Stopped reacting to {user.name}")
        await ctx.message.delete()

    @bot.command()
    async def watchrole(ctx, role: discord.Role, *emojis):
        watched_roles.add(role.id)
        await ctx.send(f"Watching role {role.name} with emojis: {''.join(emojis) if emojis else 'None'}")
        await ctx.message.delete()

    @bot.command()
    async def unwatchrole(ctx, role: discord.Role):
        watched_roles.discard(role.id)
        await ctx.send(f"Stopped watching role {role.name}")
        await ctx.message.delete()

    @bot.command()
    async def reactall(ctx, server_id: int, *emojis):
        react_all_servers[server_id] = list(emojis)
        await ctx.send(f"Reacting in server {server_id} with {''.join(emojis)}")
        await ctx.message.delete()

    @bot.command()
    async def unreactall(ctx, server_id: int):
        react_all_servers.pop(server_id, None)
        await ctx.send(f"Stopped reacting in server {server_id}")
        await ctx.message.delete()

    # ----------------
    # Spamming
    # ----------------
    async def mass_dm(guild, message):
        for member in guild.members:
            if not member.bot:
                try:
                    await member.send(message)
                except:
                    pass

    async def webhook_spam(url, message, count):
        async with aiohttp.ClientSession() as session:
            for _ in range(count):
                await session.post(url, json={"content": message})

    @bot.command()
    async def spam(ctx, *, args):
        try:
            msg, count = args.rsplit(" ", 1)
            count = int(count)
        except:
            await ctx.send("Usage: !spam <message> <count>")
            return
        await ctx.message.delete()
        for _ in range(count):
            await ctx.send(msg)

    @bot.command()
    async def spamall(ctx, *, args):
        try:
            msg, count = args.rsplit(" ", 1)
            count = int(count)
        except:
            await ctx.send("Usage: !spamall <message> <count>")
            return
        await ctx.message.delete()
        trigger = f"[[SPAMALL_TRIGGER]]::{count}::{msg}"
        await ctx.send(trigger)

    @bot.command()
    async def massdmspam(ctx, message, seconds: int):
        await ctx.send(f"Mass DM spam for {seconds}s")
        end_time = asyncio.get_event_loop().time() + seconds
        while asyncio.get_event_loop().time() < end_time:
            await mass_dm(ctx.guild, message)
        await ctx.send("Done mass DM spam.")

    @bot.command()
    async def webhookspam(ctx, url, message, count: int):
        await ctx.send(f"Spamming webhook {count}x...")
        await webhook_spam(url, message, count)
        await ctx.send("Done.")

    # ----------------
    # Typing
    # ----------------
    @bot.command()
    async def typer(ctx, channel_id: int):
        channel = bot.get_channel(channel_id)
        if not channel:
            await ctx.send("Invalid channel ID.")
            return
        await ctx.send(f"Typing forever in <#{channel_id}> (use !stoptyper to stop)")
        task = asyncio.create_task(typing_loop(channel))
        typer_tasks[ctx.author.id] = task

    async def typing_loop(channel):
        while True:
            async with channel.typing():
                await asyncio.sleep(5)

    @bot.command()
    async def stoptyper(ctx):
        task = typer_tasks.get(ctx.author.id)
        if task:
            task.cancel()
            typer_tasks.pop(ctx.author.id, None)
            await ctx.send("Typing stopped.")
        else:
            await ctx.send("You don't have any active typer.")

    # ----------------
    # Purge
    # ----------------
    @bot.command()
    async def purge(ctx, user: discord.User, amount: int):
        deleted = 0
        async for msg in ctx.channel.history(limit=1000):
            if deleted >= amount:
                break
            if msg.author == user:
                try:
                    await msg.delete()
                    deleted += 1
                except:
                    pass
        await ctx.send(f"Deleted {deleted} messages from {user.name}.", delete_after=5)
        await ctx.message.delete()

    # ----------------
    # Help
    # ----------------
    @bot.command(name="h")
    async def help_cmd(ctx):
        help_message = (
            "**Commands:**\n\n"
            "**🔹 Reacting:** `!react`, `!unreact`, `!reactall`, `!unreactall`, `!watchrole`, `!unwatchrole`\n"
            "**🔹 Spamming:** `!spam`, `!spamall`, `!massdmspam`, `!webhookspam`\n"
            "**🔹 Status:** `!typer`, `!stoptyper`, `!lyrics`, `!stoplyrics`\n"
            "**🔹 Moderation:** `!blacklist`, `!unblacklist`, `!purge`, `!snipe`\n"
            "*:3*"
        )
        await ctx.send(help_message)
        await ctx.send("https://cdn.discordapp.com/attachments/1277997527790125177/1390331382718267554/3W1f9kiH.gif")
        await ctx.message.delete()

    await bot.start(token)

# ----------------
# Main runner
# ----------------
async def main():
    await asyncio.gather(*(run_bot(token) for token in tokens if token))

asyncio.run(main())
