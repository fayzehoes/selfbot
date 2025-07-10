import discord
from discord.ext import commands
import asyncio
import random
import threading
import logging
import requests
import time 
import websockets
import json
import string
from discord.ext.commands import HelpCommand
import re
from requestcord import HeaderGenerator
from curl_cffi.requests import AsyncSession
from typing import Optional, Dict, List, Tuple

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Constants and configurations
PREFIX = ""
TOKEN = "MTM5MjE3MDUzMjc0ODkyMjkzMw.G1xQNt.iQCBbm0_gPHr6rFHnfMMg2m-VhWRKlYwn4Oiz4"

CUSTOM_EMOJI_PATTERN = re.compile(r'<a?:([a-zA-Z0-9_]+):(\d+)>')
REACTION_URL_TEMPLATE = (
    "https://discord.com/api/v9/channels/{channel_id}/"
    "messages/{message_id}/reactions/{emoji}/@me"
    "?location=Message%20Reaction%20Picker&type=1"
)

intents = discord.Intents.default()
intents.members = True

bot = commands.Bot(command_prefix=PREFIX, self_bot=True, intents=intents)

# Bot state variables
pack_task = None
word_task = None
spam_counter = 0
running_threads = {}
custom_reactor_emoji = None
auto_reply_targets = {}
auto_reply_message = None
mass_dm_running = False
js_task = None
er_reply_target_id = None
er_messages = []
stam_loop = False
gc_name_counter = 0
spam_counter = 0
hushed_users = {}
er_reply_target_id = []  # List to store multiple user IDs
active_emoji: Optional[str] = None
dsuperreact_targets: Dict[int, Tuple[List[str], int]] = {}

session = AsyncSession()
headers = HeaderGenerator().generate_headers(token=TOKEN)

def encode_super_emoji(emoji: str) -> str:
    """Encodes emoji for URL use, handling both standard and custom emojis."""
    custom_match = CUSTOM_EMOJI_PATTERN.match(emoji)
    if custom_match:
        animated = "a" if emoji.startswith("<a") else ""
        return f"{animated}:{custom_match.group(1)}:{custom_match.group(2)}"
    return "".join(f"%{b:02X}" for b in emoji.encode("utf-8"))

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} ({bot.user.id})")
    print("------")
    
    # Set the bot's status
    await bot.change_presence(
        status=discord.Status.dnd,  # Options: dnd, idle, invisible, online
    )

async def react_to_message(message: discord.Message, emoji: str) -> None:
    """Add reaction to the specified message with the given emoji."""
    encoded_emoji = encode_super_emoji(emoji)
    url = REACTION_URL_TEMPLATE.format(
        channel_id=message.channel.id,
        message_id=message.id,
        emoji=encoded_emoji
    )

    try:
        response = await session.put(
            url,
            headers=headers,
            impersonate="chrome120"
        )
        
        if response.status_code not in (200, 204):
            logger.error(
                f"Reaction failed - Status: {response.status_code}, "
                f"Response: {response.text}"
            )
    except Exception as error:
        logger.error(f"Request failed: {str(error)}", exc_info=True)

@bot.event
async def on_message(message):
    global custom_reactor_emoji, hushed_users, pack_task, auto_reply_targets, er_reply_target_id, er_messages, active_emoji, dsuperreact_targets

    # Ignore messages from hushed users
    if message.author.id in hushed_users:
        try:
            await message.delete()
        except discord.errors.Forbidden:
            print("Bot does not have permission to delete messages in this channel.")
        return

    # Add reaction to the bot's own messages if a custom emoji is set
    if message.author == bot.user and custom_reactor_emoji:
        try:
            await message.add_reaction(custom_reactor_emoji)
        except discord.errors.HTTPException as e:
            if e.status != 400:
                print(f"Error adding custom reaction: {e}")
                raise

    # Handle dsuperreact logic
    if message.author.id in dsuperreact_targets:
        emoji_list, current_index = dsuperreact_targets[message.author.id]
        await react_to_message(message, emoji_list[current_index])
        dsuperreact_targets[message.author.id] = (emoji_list, (current_index + 1) % len(emoji_list))

    # Add reaction to bot's own messages if active_emoji is set
    if message.author == bot.user and active_emoji:
        await react_to_message(message, active_emoji)

    # Handle auto-reply logic (only for users in auto_reply_targets)
    if message.author.id in auto_reply_targets:
        reply_message = auto_reply_targets.get(message.author.id)
        if reply_message:
            await message.reply(reply_message)
        return  # Prevent further processing for auto-reply

    # Handle ER reply logic (only for users in the ER reply list)
    if message.author.id in er_reply_target_id and er_messages:
        random_message = random.choice(er_messages)
        await message.reply(random_message)

    # Handle "ur bitch loser" logic and start pack task if applicable
    if message.author.id == bot.user.id and "ur incapable" in message.content.lower() and message.mentions:
        if pack_task is not None:
            print("The pack sending task is already running. Use `urass` to stop it.")
            return

        mentioned_user = message.mentions[0]
        channel_id = message.channel.id

        # Load messages from the file
        with open('pack.txt', 'r') as file:
            pack_messages = [line.strip() for line in file.readlines()]

        async def send_pack_messages():
            try:
                while True:
                    pack_message = random.choice(pack_messages)
                    if "@mentioneduser" in pack_message.lower():
                        message_content = pack_message.replace("@mentioneduser", mentioned_user.mention)
                    else:
                        message_content = f"{mentioned_user.mention} {pack_message}"

                    response = requests.post(
                        f'https://discord.com/api/v10/channels/{channel_id}/messages',
                        headers=headers,
                        json={'content': message_content}
                    )

                    if response.status_code == 200:
                        print(f"Message sent: {message_content}")
                    else:
                        print(f"Failed to send message: {response.status_code}, {response.text}")

                    await asyncio.sleep(2)
            except asyncio.CancelledError:
                print("Pack task was cancelled.")
            except Exception as e:
                print(f"Error in send_pack_messages: {e}")

        pack_task = bot.loop.create_task(send_pack_messages())
        return

    # Handle the stop pack task command
    if message.content.lower() == 'urass':
        if pack_task is None:
            print("The pack sending task is not running.")
        else:
            pack_task.cancel()
            pack_task = None
            print("The pack sending task has been stopped.")
        return

    # Process bot commands
    await bot.process_commands(message)

async def handle_auto_reply(message):
    global auto_reply_targets
    if message.author.id in auto_reply_targets:
        reply_message = auto_reply_targets[message.author.id]
        await message.reply(reply_message)

async def handle_er_reply(message):
    global er_reply_target_id, er_messages
    if er_reply_target_id and message.author.id == er_reply_target_id:
        random_message = random.choice(er_messages)
        await message.reply(random_message)

@bot.command(name='stream')
async def stream(ctx, action: str = None, *, stream_content: str = None):
    try:
        if action == 'off':
            await bot.change_presence(activity=None)
            await ctx.send("Streaming status turned off.", delete_after=5)
        elif action == 'on' and stream_content:
            await bot.change_presence(activity=discord.Streaming(name=stream_content, url='https://twitch.tv/maniacs'))
            await ctx.send(f"Streaming status set to: **{stream_content}**", delete_after=5)
        else:
            await ctx.send("Invalid command. Use `,stream on <content>` or `,stream off`.", delete_after=5)
    except Exception as e:
        await ctx.send(f"An error occurred: {e}", delete_after=5)
        logger.error(f"Error in stream command: {e}")
    finally:
        await ctx.message.delete()

@bot.command()
async def react(ctx, emoji: str):
    global custom_reactor_emoji
    try:
        await ctx.message.add_reaction(emoji)
        custom_reactor_emoji = emoji
        await ctx.send(f"Custom reaction set to {emoji}", delete_after=5)
    except discord.errors.HTTPException as e:
        if e.status == 400:  # Invalid emoji error
            await ctx.send("Invalid emoji. Please use a valid emoji.", delete_after=5)
        else:
            logger.error(f"Error in react command: {e}")
            raise
    finally:
        await ctx.message.delete()

@bot.command()
async def reactoff(ctx):
    global custom_reactor_emoji
    custom_reactor_emoji = None
    await ctx.send("Custom reaction turned off.", delete_after=5)
    await ctx.message.delete()

@bot.command(name="superreact")
async def superreact_command(ctx: commands.Context, *, emoji: str) -> None:
    """Command to set the active emoji for automatic reactions."""
    global active_emoji
    active_emoji = emoji
    logger.info(f"Set active emoji to: {active_emoji}")
    await ctx.message.delete()

@bot.command(name="dsuperreact")
async def dsuperreact_command(ctx: commands.Context, user: discord.User, *, emojis: str) -> None:
    """Command to rotate reactions on a user's messages with specified emojis."""
    global dsuperreact_targets
    emoji_list = [emoji.strip() for emoji in emojis.split() if emoji.strip()]
    if not emoji_list:
        logger.warning("No valid emojis provided for dsuperreact")
        await ctx.message.delete()
        return
    dsuperreact_targets[user.id] = (emoji_list, 0)
    logger.info(f"Set dsuperreact for user {user} with emojis: {emoji_list}")
    await ctx.message.delete()

@bot.command(name="dsuperreactstop")
async def dsuperreactstop_command(ctx: commands.Context, user: discord.User) -> None:
    """Command to stop rotating reactions for a specific user."""
    global dsuperreact_targets
    if user.id in dsuperreact_targets:
        del dsuperreact_targets[user.id]
        logger.info(f"Stopped dsuperreact for user {user}")
    else:
        logger.info(f"No active dsuperreact for user {user}")
    await ctx.message.delete()

@bot.command(name="stopsuperreact")
async def stopsuperreact_command(ctx: commands.Context) -> None:
    """Command to stop all automatic reactions."""
    global active_emoji, dsuperreact_targets
    active_emoji = None
    dsuperreact_targets.clear()
    logger.info("Stopped all automatic reactions")
    await ctx.message.delete()

@bot.command()
async def roffall(ctx):
    global auto_reply_targets
    auto_reply_targets.clear()
    await ctx.send("All auto-replies have been turned off.", delete_after=5)
    await ctx.message.delete()

@bot.command()
async def rstop(ctx, user: discord.User):
    global auto_reply_targets
    if user.id in auto_reply_targets:
        del auto_reply_targets[user.id]
        await ctx.message.delete()

@bot.command()
async def r(ctx, user: discord.User, *, message: str):
    global auto_reply_targets
    with open('spacing.txt', 'r') as file:
        spacing_format = file.read().strip()

    # Store the auto-reply message for the user
    auto_reply_targets[user.id] = f"{spacing_format}\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n\n {user.mention}{message}"
    await ctx.message.delete()

@bot.command()
async def whosared(ctx):
    global auto_reply_targets
    
    if not auto_reply_targets:
        await ctx.send("No auto-replies are currently active.", delete_after=5)
    else:
        reply_list = []
        for user_id in auto_reply_targets:
            user = bot.get_user(user_id)
            if user:
                reply_list.append(f"{user.name}#{user.discriminator} (ID: {user_id})")
            else:
                reply_list.append(f"User ID: {user_id} (User not found)")
        
        # Join the list with line breaks and send the message
        await ctx.send(f"Auto-replies are active for:\n" + "\n".join(reply_list), delete_after=10)

@bot.command(name='kill')
async def kill(ctx):
    def is_user(message):
        return message.author == ctx.author

    total_deleted = 0
    max_deletions = 2000  # Set the maximum number of deletions. You can change this value.
    
    try:
        # Fetch the user's message history in the current channel
        async for message in ctx.channel.history(limit=None):  # Set to None to scan entire channel history
            if is_user(message):
                try:
                    await message.delete()
                    total_deleted += 1
                    if total_deleted >= max_deletions:  # Stop once the max limit is reached
                        break
                except discord.errors.Forbidden:
                    return
                except discord.errors.HTTPException as e:
                    if e.status == 429:  # Handle rate limiting
                        retry_after = int(e.response.headers.get('Retry-After', 5))
                        await asyncio.sleep(retry_after)
                    else:
                        return

    except discord.errors.Forbidden:
        await ctx.send("Bot does not have permission to access the message history in this channel.", delete_after=5)
    except discord.errors.HTTPException as e:
        await ctx.send(f"An error occurred: {e}", delete_after=5)
    except Exception as e:
        await ctx.send(f"An unexpected error occurred: {e}", delete_after=5)

@bot.command(name="hush")
async def hush(ctx, user: discord.User):
    if user.id not in hushed_users:
        hushed_users[user.id] = user
        await ctx.send(f"{user.name} has been hushed.", delete_after=5)
    else:
        await ctx.send(f"{user.name} is already hushed.", delete_after=5)

@bot.command()
async def hushlist(ctx):
    global hushed_users
    try:
        if not hushed_users:
            await ctx.send("No users are currently hushed.", delete_after=5)
            return

        hushed_list = [f"{user.name}#{user.discriminator} (ID: {user.id})" for user in hushed_users.values()]
        await ctx.send(f"Hushed users:\n" + "\n".join(hushed_list), delete_after=10)
    except Exception as e:
        logger.error(f"Error in hushlist command: {e}")
        await ctx.send(f"An error occurred: {e}", delete_after=5)
    finally:
        await ctx.message.delete()

@bot.command(name="unhush")
async def unhush(ctx, user: discord.User):
    if user.id in hushed_users:
        del hushed_users[user.id]
        await ctx.send(f"{user.name} has been unhushed.", delete_after=5)
    else:
        await ctx.send(f"{user.name} is not hushed.", delete_after=5)

@bot.command()
async def er(ctx, user: discord.User):
    global er_reply_target_id, er_messages

    # Check if user is already in the list
    if user.id not in er_reply_target_id:
        er_reply_target_id.append(user.id)

    # Load messages from `erwords.txt`
    with open('erwords.txt', 'r') as file:
        er_messages = [line.strip() for line in file.readlines()]

    await ctx.send(f"ER replies are now active for {user.name}#{user.discriminator}.", delete_after=5)
    await ctx.message.delete()

@bot.command()
async def erstop(ctx, user: discord.User):
    global er_reply_target_id

    # Check if the user is in the ER list
    if user.id in er_reply_target_id:
        er_reply_target_id.remove(user.id)  # Remove user from ER list
        await ctx.send(f"ER reply for {user.name}#{user.discriminator} has been stopped.", delete_after=5)
    else:
        await ctx.send(f"{user.name}#{user.discriminator} is not currently set for ER replies.", delete_after=5)

    await ctx.message.delete()

@bot.command()
async def eradd(ctx, *, new_message: str):
    with open('erwords.txt', 'a') as file:
        file.write(new_message + '\n')
    await ctx.send(f"Added new message: {new_message}", delete_after=5)

@bot.command()
async def erremove(ctx, line_number: int):
    try:
        with open('erwords.txt', 'r') as file:
            lines = file.readlines()

        # Remove the specified line (index is line_number - 1)
        if 0 < line_number <= len(lines):
            removed_line = lines.pop(line_number - 1)
            with open('erwords.txt', 'w') as file:
                file.writelines(lines)
            await ctx.send(f"Removed message: {removed_line.strip()}", delete_after=5)
        else:
            await ctx.send("Invalid line number.", delete_after=5)
    except Exception as e:
        await ctx.send(f"An error occurred: {e}", delete_after=5)

@bot.command()
async def ershow(ctx):
    try:
        with open('erwords.txt', 'r') as file:
            lines = file.readlines()

        # Split into chunks of 200 sentences
        total_sentences = [line.strip() for line in lines]
        chunks = [total_sentences[i:i + 200] for i in range(0, len(total_sentences), 200)]

        # Send each chunk with numbering
        for chunk_index, chunk in enumerate(chunks, 1):
            numbered_message = "\n".join([f"{i+1}. {chunk[i]}" for i in range(len(chunk))])
            
            # Split the message into smaller parts if it exceeds 2000 characters
            while len(numbered_message) > 2000:
                # Find the point to split the message without cutting off in the middle
                split_index = numbered_message.rfind("\n", 0, 2000)
                if split_index == -1:  # If no newline is found, split by characters
                    split_index = 2000

                # Send the part of the message that fits within the character limit
                await ctx.send(numbered_message[:split_index])

                # Update the message to send the remaining part
                numbered_message = numbered_message[split_index:]

            # Send the remaining part of the message
            if numbered_message:
                await ctx.send(f"**ER Messages (Chunk {chunk_index}):**\n{numbered_message}")
            await asyncio.sleep(1)  # Slight delay between chunks to avoid spamming

    except FileNotFoundError:
        await ctx.send("ER words file not found. Please make sure erwords.txt exists.", delete_after=5)

@bot.command()
async def erlist(ctx):
    if not er_reply_target_id:
        await ctx.send("No ER replies are currently active.", delete_after=5)
    else:
        # Create a list of users with ER replies enabled
        reply_list = []
        for user_id in er_reply_target_id:
            user = bot.get_user(user_id)
            if user:
                reply_list.append(f"{user.name}#{user.discriminator} (ID: {user_id})")
            else:
                reply_list.append(f"User ID: {user_id} (User not found)")

        # Join the list with line breaks and send the message
        await ctx.send(f"ER replies are active for:\n" + "\n".join(reply_list), delete_after=10)

@bot.command()
async def stam(ctx, *, user_message):
    global stam_loop
    await ctx.message.delete()  # Deletes the command message

    stam_loop = True
    while stam_loop:
        try:
            # Example API endpoint for sending messages to a channel
            api_url = f'https://discord.com/api/v9/channels/{ctx.channel.id}/messages'
            headers = {
                'Authorization': TOKEN,  # Replace with your bot token
                'Content-Type': 'application/json'
            }
            data = {
                'content': user_message  # Sends the message without a count
            }
            response = requests.post(api_url, headers=headers, json=data)
            response.raise_for_status()  # Raise error for bad response status
            await asyncio.sleep(4)  # Adjust the interval as needed
        except requests.exceptions.RequestException as e:
            print(f"Error making API request: {e}")
            await asyncio.sleep(10)  # Retry after 10 seconds on error

@bot.command()
async def stamstop(ctx):
    global stam_loop
    if stam_loop:
        stam_loop = False
        await ctx.message.delete()  # Deletes the command message

@bot.command(name='gc')
async def change_group_name(ctx, *, new_name: str):
    global loop_active
    await ctx.message.delete()
    channel_id = ctx.channel.id
    loop_active = True
    add_period = False  # Flag to alternate between adding a period or not

    while loop_active:
        try:
            # Example API endpoint for editing channel details
            api_url = f'https://discord.com/api/v9/channels/{channel_id}'
            headers = {
                'Authorization': TOKEN,  # Replace with your bot token
                'Content-Type': 'application/json'
            }
            
            # Alternate between adding a period or not
            data = {
                'name': f"{new_name}{' .' if add_period else ''}"
            }
            
            response = requests.patch(api_url, headers=headers, json=data)
            response.raise_for_status()  # Raise error for bad response status
            
            # Toggle the flag for the next iteration
            add_period = not add_period
            
            await asyncio.sleep(0.001)  # Adjust the interval as needed
        except requests.exceptions.RequestException as e:
            print(f"Error making API request: {e}")
            await asyncio.sleep(5)  # Retry after 5 seconds on error

@bot.command(name='gcstop')
async def stop_change_group_name(ctx):
    global loop_active
    if loop_active:
        loop_active = False
        await ctx.message.delete()  # Deletes the command message

@bot.command(name='jvc')
async def join_vc(ctx, vc_id: int):
    # Get the voice channel by its ID
    voice_channel = bot.get_channel(vc_id)

    # Check if the ID corresponds to a valid voice channel
    if not isinstance(voice_channel, discord.VoiceChannel):
        await ctx.send("Invalid VC ID. Please provide a valid voice channel ID.", delete_after=5)
        return

    # Try to connect to the voice channel
    try:
        # If the bot is already in a voice channel, move it
        if ctx.voice_client:
            if ctx.voice_client.channel.id == voice_channel.id:
                await ctx.send(f"I'm already in {voice_channel.name}.", delete_after=5)
            else:
                await ctx.voice_client.move_to(voice_channel)
                await ctx.send(f"Moved to {voice_channel.name}.")
        else:
            await voice_channel.connect()
            await ctx.send(f"Successfully connected to {voice_channel.name}!")
    except discord.errors.Forbidden:
        await ctx.send("I do not have permission to join this voice channel.", delete_after=5)
    except discord.ClientException as e:
        await ctx.send(f"Failed to connect to the voice channel: {e}", delete_after=5)
    except Exception as e:
        await ctx.send(f"An unexpected error occurred: {e}", delete_after=5)

@bot.command()
async def pfp(ctx, user_id: int = None):
    if user_id is None:
        user = ctx.author  # Default to the command author (self-bot user)
    else:
        # Attempt to fetch the user by ID
        user = bot.get_user(user_id)
        
        if user is None:
            await ctx.send("User not found or the bot cannot access them.")
            return
    
    await ctx.send(user.avatar_url)

@bot.command()
async def changestatus(ctx, status: str, *, activity: str = None):
    # Map user input to discord.Status
    status_map = {
        "online": discord.Status.online,
        "dnd": discord.Status.dnd,
        "idle": discord.Status.idle,
        "invisible": discord.Status.invisible,
        "offline": discord.Status.invisible,  # Alias for invisible
    }

    try:
        # Check if the provided status is valid
        if status.lower() not in status_map:
            await ctx.send("Invalid status. Use `online`, `dnd`, `idle`, or `invisible`.", delete_after=5)
            return

        # Change the bot's presence
        discord_status = status_map[status.lower()]
        if activity:
            # Set activity if provided
            await bot.change_presence(status=discord_status, activity=discord.Game(name=activity))
            await ctx.send(f"Status changed to **{status.lower()}** with activity: **{activity}**", delete_after=5)
        else:
            # No activity
            await bot.change_presence(status=discord_status)
            await ctx.send(f"Status changed to **{status.lower()}**", delete_after=5)

    except Exception as e:
        await ctx.send(f"An error occurred: {e}", delete_after=5)
        logger.error(f"Error in changestatus command: {e}")

    finally:
        await ctx.message.delete()

if __name__ == "__main__":
    bot.run(TOKEN, bot=False)