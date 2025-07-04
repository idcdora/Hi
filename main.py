import discord
from discord.ext import commands
import asyncio
import aiohttp
import requests

watched_users = {}
watched_roles = set()
react_all_servers = {}
token_user_ids = set()
all_bots = []
blacklisted_users = {}

GENIUS_TOKEN = "ILkH7espIOfaqvoQ_PSxeUP9nsPonM7C65kb0bZL2l8lUh0B33vJiXN0whJ5mUKf"

with open("tokens.txt", "r") as f:
    tokens = [line.strip() for line in f if line.strip()]

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
            try:
                await session.post(url, json={"content": message})
            except:
                pass

async def run_bot(token):
    bot = commands.Bot(command_prefix="!", self_bot=True)
    all_bots.append(bot)
    typer_tasks = {}
    lyrics_tasks = {}

    @bot.event
    async def on_ready():
        print(f"[+] Logged in as {bot.user}")
        token_user_ids.add(bot.user.id)

    snipes = {}

    @bot.event
    async def on_message(message):
        if message.author.id in blacklisted_users:
            return

        author_id = message.author.id
        author_roles = {role.id for role in getattr(message.author, "roles", [])}
        should_react = (
            author_id == bot.user.id or
            author_id in token_user_ids or
            author_id in watched_users or
            watched_roles.intersection(author_roles) or
            (message.guild and message.guild.id in react_all_servers)
        )
        if should_react:
            try:
                if author_id in watched_users:
                    emojis = watched_users[author_id]
                elif message.guild and message.guild.id in react_all_servers:
                    emojis = react_all_servers[message.guild.id]
                else:
                    emojis = []
                for emoji in emojis:
                    await message.add_reaction(emoji)
            except:
                pass

        if message.content.startswith("[[SPAMALL_TRIGGER]]::") and message.author != bot.user:
            try:
                _, count, msg = message.content.split("::", 2)
                for _ in range(int(count)):
                    await message.channel.send(msg)
                    await asyncio.sleep(0.1)
            except:
                pass

        await bot.process_commands(message)

    @bot.event
    async def on_message_delete(message):
        if message.author.id == bot.user.id:
            return
        snipes[message.channel.id] = message

    @bot.command()
    async def snipe(ctx):
        msg = snipes.get(ctx.channel.id)
        if not msg:
            await ctx.send("Nothing to snipe!")
            return
        content = msg.content or "[embed/image]"
        await ctx.send(f"Sniped message from {msg.author}: {content}")

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

    @bot.command(name="h")
    async def help_cmd(ctx):
        help_message = (
            "**Commands:**\n\n"
            "**🔹 Reacting:**\n"
            "`!react`, `!unreact`, `!reactall`, `!unreactall`, `!watchrole`, `!unwatchrole`\n\n"
            "**🔹 Spamming:**\n"
            "`!spam`, `!spamall`, `!massdmspam`, `!webhookspam`\n\n"
            "**🔹 Status:**\n"
            "`!typer`, `!stoptyper`, `!lyrics`, `!stoplyrics`\n\n"
            "**🔹 Moderation:**\n"
            "`!blacklist`, `!unblacklist`, `!purge`, `!snipe`\n\n"
            "*:3*"
        )
        await ctx.send(help_message)
        await ctx.send("https://cdn.discordapp.com/attachments/1277997527790125177/1390331382718267554/3W1f9kiH.gif")
        await ctx.message.delete()

    # Lyrics with direct Genius API and updating STATUS every 4 sec
    @bot.command()
    async def lyrics(ctx, *, query: str):
        await ctx.send(f"Searching lyrics for `{query}`...")
        await ctx.message.delete()
        try:
            headers = {"Authorization": f"Bearer {GENIUS_TOKEN}"}
            search = requests.get("https://api.genius.com/search", params={"q": query}, headers=headers).json()
            hits = search["response"]["hits"]
            if not hits:
                await ctx.send("No lyrics found.")
                return
            song_id = hits[0]["result"]["id"]
            song_title = hits[0]["result"]["full_title"]

            song_page = requests.get(f"https://api.genius.com/songs/{song_id}", headers=headers).json()
            lyrics_url = song_page["response"]["song"]["url"]

            page_html = requests.get(lyrics_url).text
            lyrics_lines = page_html.split("\n")
            lyrics_lines = [line.strip() for line in lyrics_lines if line.strip()][:100]

            await ctx.send(f"🎵 Now updating status with lyrics from **{song_title}**...")

            async def lyrics_loop():
                for line in lyrics_lines:
                    await bot.change_presence(activity=discord.Game(name=line[:128]))
                    await asyncio.sleep(4)

            task = asyncio.create_task(lyrics_loop())
            lyrics_tasks[ctx.author.id] = task

        except Exception as e:
            await ctx.send(f"Error fetching lyrics or updating status: {e}")

    @bot.command()
    async def stoplyrics(ctx):
        task = lyrics_tasks.get(ctx.author.id)
        if task:
            task.cancel()
            lyrics_tasks.pop(ctx.author.id, None)
            await ctx.send("Stopped lyrics status.")
        else:
            await ctx.send("You don't have any active lyrics.")

    await bot.start(token)

async def main():
    await asyncio.gather(*(run_bot(token) for token in tokens if token))

asyncio.run(main())
