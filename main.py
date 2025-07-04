import discord
from discord.ext import commands
import asyncio
import aiohttp
import re

# --- Globals ---
watched_users = {}
watched_roles = {}
react_all_servers = {}
token_user_ids = set()
all_bots = []
blacklisted_users = {}

lyrics_tasks = {}
lyrics_paused = {}

# Load tokens
with open("tokens.txt", "r") as f:
    tokens = [line.strip() for line in f if line.strip()]

# --- Utils ---
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

# --- Bot Runner ---
async def run_bot(token):
    bot = commands.Bot(command_prefix="!", self_bot=True)
    all_bots.append(bot)

    @bot.event
    async def on_ready():
        print(f"[+] Logged in as {bot.user}")
        token_user_ids.add(bot.user.id)

    last_deleted_message = {}

    @bot.event
    async def on_message_delete(message):
        if message.guild:
            last_deleted_message[message.channel.id] = message

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

        await bot.process_commands(message)

    # --- Commands ---
    @bot.command(help="Blacklist a user ID.")
    async def blacklist(ctx, user_id: int):
        blacklisted_users[user_id] = True
        await ctx.send(f"User {user_id} blacklisted.")
        await ctx.message.delete()

    @bot.command(help="Unblacklist a user ID.")
    async def unblacklist(ctx, user_id: int):
        blacklisted_users.pop(user_id, None)
        await ctx.send(f"User {user_id} unblacklisted.")
        await ctx.message.delete()

    @bot.command(help="React to a user with emojis.")
    async def react(ctx, user: discord.User, *emojis):
        watched_users[user.id] = list(emojis)
        await ctx.send(f"Now reacting to {user.name} with {''.join(emojis)}")
        await ctx.message.delete()

    @bot.command(help="Stop reacting to a user.")
    async def unreact(ctx, user: discord.User):
        watched_users.pop(user.id, None)
        await ctx.send(f"Stopped reacting to {user.name}")
        await ctx.message.delete()

    @bot.command(help="Watch a role.")
    async def watchrole(ctx, role: discord.Role):
        watched_roles.add(role.id)
        await ctx.send(f"Watching role {role.name}")
        await ctx.message.delete()

    @bot.command(help="Stop watching a role.")
    async def unwatchrole(ctx, role: discord.Role):
        watched_roles.discard(role.id)
        await ctx.send(f"Stopped watching role {role.name}")
        await ctx.message.delete()

    @bot.command(help="React to all in server.")
    async def reactall(ctx, server_id: int, *emojis):
        react_all_servers[server_id] = list(emojis)
        await ctx.send(f"Reacting in server {server_id} with {''.join(emojis)}")
        await ctx.message.delete()

    @bot.command(help="Stop reacting to all in server.")
    async def unreactall(ctx, server_id: int):
        react_all_servers.pop(server_id, None)
        await ctx.send(f"Stopped reacting in server {server_id}")
        await ctx.message.delete()

    @bot.command(help="Spam a message.")
    async def spam(ctx, *, args):
        msg, count = args.rsplit(" ", 1)
        count = int(count)
        await ctx.message.delete()
        for _ in range(count):
            await ctx.send(msg)

    @bot.command(help="Spam message in all bots.")
    async def spamall(ctx, *, args):
        msg, count = args.rsplit(" ", 1)
        count = int(count)
        await ctx.message.delete()
        trigger = f"[[SPAMALL_TRIGGER]]::{count}::{msg}"
        await ctx.send(trigger)

    @bot.command(help="Mass DM spam.")
    async def massdmspam(ctx, message, seconds: int):
        await ctx.send(f"Mass DM spam for {seconds}s")
        end_time = asyncio.get_event_loop().time() + seconds
        while asyncio.get_event_loop().time() < end_time:
            await mass_dm(ctx.guild, message)
        await ctx.send("Done mass DM spam.")

    @bot.command(help="Spam a webhook.")
    async def webhookspam(ctx, url, message, count: int):
        await ctx.send(f"Spamming webhook {count}x...")
        await webhook_spam(url, message, count)
        await ctx.send("Done.")

    @bot.command(help="Set RPC (custom status).")
    async def rpc(ctx, activity_type: str, *, activity_message: str):
        activity = discord.Game(name=activity_message)
        await bot.change_presence(activity=activity)
        await ctx.send(f"Status set to {activity_type} {activity_message}")
        await ctx.message.delete()

    @bot.command(help="Set status in all bots.")
    async def statusall(ctx, activity_type: str, *, activity_message: str):
        for b in all_bots:
            await b.change_presence(activity=discord.Game(name=activity_message))
        await ctx.send(f"All bots updated to {activity_type} {activity_message}")
        await ctx.message.delete()

    typer_tasks = {}

    @bot.command(help="Start typing in a channel forever.")
    async def typer(ctx, channel_id: int):
        channel = bot.get_channel(channel_id)
        await ctx.send(f"Typing forever in <#{channel_id}>")
        async def loop_typing():
            while True:
                async with channel.typing():
                    await asyncio.sleep(5)
        task = asyncio.create_task(loop_typing())
        typer_tasks[bot.user.id] = task
        await ctx.message.delete()

    @bot.command(help="Stop typing.")
    async def stoptyper(ctx):
        task = typer_tasks.pop(bot.user.id, None)
        if task:
            task.cancel()
            await ctx.send("Stopped typing.")
        else:
            await ctx.send("No typing task running.")
        await ctx.message.delete()

    @bot.command(help="Snipe the last deleted message.")
    async def snipe(ctx):
        msg = last_deleted_message.get(ctx.channel.id)
        if msg:
            await ctx.send(f"**{msg.author}:** {msg.content}")
        else:
            await ctx.send("Nothing to snipe.")
        await ctx.message.delete()

    # --- Lyrics & Music Features ---
    @bot.command(help="Set your status to song lyrics.")
    async def lyrics(ctx, *, song: str):
        await ctx.message.delete()
        if lyrics_tasks.get(bot.user.id):
            lyrics_tasks[bot.user.id].cancel()
            lyrics_tasks.pop(bot.user.id, None)
        lyrics_paused[bot.user.id] = False

        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(f"https://api.lyrics.ovh/v1/{' '.join(song.split()[:2])}/{song}") as resp:
                    data = await resp.json()
                    lyrics_text = data.get("lyrics", None)
            except:
                lyrics_text = None

        if not lyrics_text:
            await ctx.send("❌ Couldn't find lyrics.")
            return

        lines = [line.strip() for line in lyrics_text.split("\n") if line.strip()]
        await ctx.send(f"🎵 Now setting status to lyrics of **{song}**.")

        async def rotate_lyrics():
            i = 0
            while True:
                if not lyrics_paused.get(bot.user.id, False):
                    line = lines[i % len(lines)]
                    await bot.change_presence(activity=discord.Game(name=line))
                    i += 1
                await asyncio.sleep(10)

        task = asyncio.create_task(rotate_lyrics())
        lyrics_tasks[bot.user.id] = task

    @bot.command(help="Stop lyrics status.")
    async def stoplyrics(ctx):
        task = lyrics_tasks.pop(bot.user.id, None)
        if task:
            task.cancel()
            await ctx.send("🛑 Stopped lyrics status.")
        else:
            await ctx.send("No lyrics status running.")
        await ctx.message.delete()

    @bot.command(help="Pause lyrics cycling.")
    async def pauselyrics(ctx):
        lyrics_paused[bot.user.id] = True
        await ctx.send("⏸️ Paused lyrics.")
        await ctx.message.delete()

    @bot.command(help="Resume lyrics cycling.")
    async def resumelyrics(ctx):
        lyrics_paused[bot.user.id] = False
        await ctx.send("▶️ Resumed lyrics.")
        await ctx.message.delete()

    @bot.command(name="h", help="Show help menu.")
    async def help_cmd(ctx):
        await ctx.send("""**Commands**
**🔹 Reacting:** `!react`, `!unreact`, `!reactall`, `!unreactall`, `!watchrole`, `!unwatchrole`
**🔹 Spamming:** `!spam`, `!spamall`, `!massdmspam`, `!webhookspam`
**🔹 Status:** `!rpc`, `!statusall`, `!typer`, `!stoptyper`
**🔹 Moderation:** `!blacklist`, `!unblacklist`, `!purge`, `!snipe`
**🔹 Music:** `!lyrics`, `!stoplyrics`, `!pauselyrics`, `!resumelyrics`
*:3*""")
        await ctx.send("https://cdn.discordapp.com/attachments/1277997527790125177/1390331382718267554/3W1f9kiH.gif?ex=6867de80&is=68668d00&hm=e81e1b88994e14b6b51982fc91d4c3af07dba8bbae87d2c581e787f80b0dca68&")

    await bot.start(token)

async def main():
    await asyncio.gather(*(run_bot(token) for token in tokens if token))

asyncio.run(main())
