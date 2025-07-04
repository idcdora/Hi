import discord
from discord.ext import commands
import asyncio
import aiohttp
import base64
import requests
import lyricsgenius

watched_users = {}  # user_id -> list of emojis
watched_roles = set()
react_all_servers = {}  # guild_id -> list of emojis
token_user_ids = set()
all_bots = []
blacklisted_users = {}

# Genius API setup (your token)
GENIUS_TOKEN = "ILkH7espIOfaqvoQ_PSxeUP9nsPonM7C65kb0bZL2l8lUh0B33vJiXN0whJ5mUKf"
genius = lyricsgenius.Genius(GENIUS_TOKEN)
genius.remove_section_headers = True
genius.skip_non_songs = True
genius.excluded_terms = ["(Remix)", "(Live)"]

# Load tokens
with open("tokens.txt", "r") as f:
    tokens = [line.strip() for line in f if line.strip()]

# Email storage file
EMAILS_FILE = "emails.txt"

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
            except Exception as e:
                print("Reaction error:", e)

        if message.content.startswith("[[SPAMALL_TRIGGER]]::") and message.author != bot.user:
            try:
                _, count, msg = message.content.split("::", 2)
                for _ in range(int(count)):
                    await message.channel.send(msg)
                    await asyncio.sleep(0.1)
            except Exception as e:
                print("SPAMALL error:", e)

        await bot.process_commands(message)

    snipes = {}

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
        author = msg.author
        await ctx.send(f"Sniped message from {author}: {content}")

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
        if not emojis:
            await ctx.send("Please provide at least one emoji.")
            return
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
        if not emojis:
            await ctx.send("Please provide at least one emoji.")
            return
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
    async def rpc(ctx, activity_type: str, *, activity_message: str):
        types = {
            "playing": discord.Game,
            "streaming": discord.Streaming,
            "listening": discord.Activity,
            "watching": discord.Activity,
            "competing": discord.Activity
        }
        activity_type = activity_type.lower()
        if activity_type == "streaming":
            activity = discord.Streaming(name=activity_message, url="https://twitch.tv/yourchannel")
        elif activity_type in types:
            if activity_type == "playing":
                activity = types[activity_type](name=activity_message)
            else:
                enum_type = getattr(discord.ActivityType, activity_type)
                activity = discord.Activity(type=enum_type, name=activity_message)
        else:
            await ctx.send("Invalid activity type.")
            return
        await bot.change_presence(activity=activity)
        await ctx.send(f"Status set to {activity_type} {activity_message}")
        await ctx.message.delete()

    @bot.command()
    async def statusall(ctx, activity_type: str, *, activity_message: str):
        for b in all_bots:
            try:
                if activity_type == "streaming":
                    activity = discord.Streaming(name=activity_message, url="https://twitch.tv/yourchannel")
                elif activity_type == "playing":
                    activity = discord.Game(name=activity_message)
                else:
                    enum_type = getattr(discord.ActivityType, activity_type)
                    activity = discord.Activity(type=enum_type, name=activity_message)
                await b.change_presence(activity=activity)
            except:
                pass
        await ctx.send(f"All bots updated to {activity_type} {activity_message}")
        await ctx.message.delete()

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
            "**Commands:**\n"
            "\n"
            "**🔹 Reacting:**\n"
            "`!react`, `!unreact`, `!reactall`, `!unreactall`, `!watchrole`, `!unwatchrole`\n"
            "\n"
            "**🔹 Spamming:**\n"
            "`!spam`, `!spamall`, `!massdmspam`, `!webhookspam`\n"
            "\n"
            "**🔹 Status:**\n"
            "`!rpc`, `!statusall`, `!typer`, `!stoptyper`, `!lyrics`, `!stoplyrics`\n"
            "\n"
            "**🔹 Moderation:**\n"
            "`!blacklist`, `!unblacklist`, `!purge`, `!snipe`\n"
            "\n"
            "**🔹 Email:**\n"
            "`!tempmail [count]`, `!checkmail <email>`, `!emails`\n"
            "\n"
            "*:3*"
        )
        await ctx.send(help_message)
        await ctx.send("https://cdn.discordapp.com/attachments/1277997527790125177/1390331382718267554/3W1f9kiH.gif")
        await ctx.message.delete()

    # Lyrics commands
    @bot.command()
    async def lyrics(ctx, *, query: str):
        await ctx.message.delete()
        # Cancel any previous lyrics task for this user
        if ctx.author.id in lyrics_tasks:
            lyrics_tasks[ctx.author.id].cancel()
            lyrics_tasks.pop(ctx.author.id, None)
        try:
            song = genius.search_song(query)
            if not song:
                await ctx.send("No lyrics found for that song.")
                return
            # Start updating status with lyrics line by line
            lines = song.lyrics.split('\n')
            task = asyncio.create_task(update_lyrics_status(bot, lines, ctx.author.id))
            lyrics_tasks[ctx.author.id] = task
            await ctx.send(f"Lyrics found for **{song.title}** by *{song.artist}*. Status updating...")
        except Exception as e:
            await ctx.send(f"Error fetching lyrics: {e}")

    @bot.command()
    async def stoplyrics(ctx):
        task = lyrics_tasks.get(ctx.author.id)
        if task:
            task.cancel()
            lyrics_tasks.pop(ctx.author.id, None)
            await ctx.send("Lyrics status updating stopped.")
        else:
            await ctx.send("No active lyrics status to stop.")

    async def update_lyrics_status(bot, lines, user_id):
        try:
            idx = 0
            while True:
                line = lines[idx].strip()
                if line:
                    status_text = line if len(line) <= 128 else line[:125] + "..."
                    await bot.change_presence(activity=discord.Game(name=status_text))
                else:
                    # If empty line, show a default or clear
                    await bot.change_presence(activity=discord.Game(name=""))
                idx = (idx + 1) % len(lines)
                await asyncio.sleep(7)
        except asyncio.CancelledError:
            # Clear status when stopped
            await bot.change_presence(activity=None)

    # Temp mail commands
    @bot.command()
    async def tempmail(ctx, count: int = 1):
        await ctx.message.delete()
        if count < 1:
            await ctx.send("Count must be at least 1.")
            return
        emails = []
        async with aiohttp.ClientSession() as session:
            for _ in range(count):
                async with session.get("https://www.1secmail.com/api/v1/?action=genRandomMailbox&count=1") as resp:
                    if resp.status != 200:
                        await ctx.send("Failed to generate temp email.")
                        return
                    data = await resp.json()
                    emails.append(data[0])
        # Save emails with expiry days (e.g. 1 day)
        with open(EMAILS_FILE, "a") as f:
            for email in emails:
                f.write(f"{email} 1\n")  # 1 day expiry for example
        await ctx.send(f"Generated temp email(s):\n" + "\n".join(emails))

    @bot.command()
    async def checkmail(ctx, email: str):
        await ctx.message.delete()
        try:
            username, domain = email.split("@")
        except ValueError:
            await ctx.send("Invalid email format!")
            return
        url = f"https://www.1secmail.com/api/v1/?action=getMessages&login={username}&domain={domain}"
        headers = {
            "User-Agent": "Mozilla/5.0 (compatible; DiscordBot/1.0; +https://discord.com)"
        }
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as resp:
                if resp.status != 200:
                    await ctx.send(f"Failed to check email, HTTP status: {resp.status}")
                    return
                data = await resp.json()
                if not data:
                    await ctx.send(f"No emails found for {email}")
                    return
                messages = []
                for msg in data:
                    messages.append(f"From: {msg['from']}\nSubject: {msg['subject']}\nDate: {msg['date']}\nID: {msg['id']}\n---")
                await ctx.send(f"Emails for {email}:\n" + "\n".join(messages))

    @bot.command()
    async def emails(ctx):
        await ctx.message.delete()
        try:
            with open(EMAILS_FILE, "r") as f:
                lines = f.readlines()
            if not lines:
                await ctx.send("No stored emails.")
                return
            lines = [line.strip() for line in lines]
            await ctx.send("Stored temp emails (email + days left):\n" + "\n".join(lines))
        except FileNotFoundError:
            await ctx.send("No stored emails yet.")

    await bot.start(token)

async def main():
    await asyncio.gather(*(run_bot(token) for token in tokens if token))

asyncio.run(main())
