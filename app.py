import os
import json
import requests
import discord
from discord.ext import commands, tasks
from discord import ui
import asyncio
import ping3
import sys
import platform
import psutil
import logging
from datetime import datetime, timedelta, timezone

# Initialize logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Load configuration from files
CONFIG_FILE = 'config.json'
KEYS_FILE = 'keys.json'

def load_json(file_path):
    """Loads JSON data from a file."""
    with open(file_path, 'r') as f:
        return json.load(f)

config = load_json(CONFIG_FILE)
keys = load_json(KEYS_FILE)

# Constants - use uppercase for these
DROPLET_ID = config.get('droplet_id', '')
FX_API_URL = config.get('fx_api_url', '')
FX_PANEL_LINK = config.get('fx_panel_link', '')
SERVER_IP = config.get('server_ip', '')
LOG_CHANNEL_ID = config.get('log_channel_id', int)  # Ensure this is an integer
CHECK_INTERVAL = config.get('check_interval', int)  # Ensure this is an integer

# API Keys
DISCORD_BOT_TOKEN = keys.get('discord_bot_token', '')
CONFIRM_COMMAND = keys.get('confirm_command', '')
DIGITAL_OCEAN_KEY = keys.get('digital_ocean_key', '')

# Droplet Plans
PLANS = {
    'not_set': None,
    'off': 's-1vcpu-2gb-intel',  # 0.024/hr
    'low': 's-2vcpu-4gb-amd',   # 0.042/hr
    'medium': 's-4vcpu-8gb-amd',  # 0.083/hr
    'high': 's-4vcpu-16gb-amd',  # $0.125/hr
    'ultra': 's-v8cpu-16gb-amd'  # 0.167/hr
}

# Global Variables - use lowercase with underscores
temporary_schedule = {}
servers_not_resizing_count = 0
last_resize_time = None
reboot_scheduled = False
disable_resizing = False

# Discord Bot Setup
if sys.version_info[0] == 3 and sys.version_info[1] >= 8 and platform.system() == 'Windows':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)

# Load Permissions from config
def load_permissions():
    """Loads permissions from the configuration file."""
    if os.path.exists(CONFIG_FILE):
        return load_json(CONFIG_FILE)
    return {'droplet_perms': [], 'authorized_users': [], 'restart_perms': []}

permissions = load_permissions()
droplet_perms = permissions.get('droplet_perms', [])
authorized_users = permissions.get('authorized_users', [])
restart_perms = permissions.get('restart_perms', [])

def save_permissions():
    """Saves permissions to the configuration file."""
    with open(CONFIG_FILE, 'w') as f:
        json.dump({
            'droplet_perms': droplet_perms,
            'authorized_users': authorized_users,
            'restart_perms': restart_perms
        }, f)

# --- DigitalOcean API Interactions ---
def get_size_slug():
    """Retrieves the current size slug of the droplet from the DigitalOcean API."""
    url = f'https://api.digitalocean.com/v2/droplets/{DROPLET_ID}'
    headers = {'Content-Type': 'application/json', 'Authorization': f'Bearer {DIGITAL_OCEAN_KEY}'}
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        data = response.json()
        return data['droplet']['size']['slug']
    else:
        logging.error(f"Failed to retrieve size name: {response.content.decode()}")
        return "Unknown"

current_plan = get_size_slug()

def perform_droplet_action(action_type):
    """Performs an action (power on, power off, reboot) on the droplet."""
    url = f'https://api.digitalocean.com/v2/droplets/{DROPLET_ID}/actions'
    headers = {'Content-Type': 'application/json', 'Authorization': f'Bearer {DIGITAL_OCEAN_KEY}'}
    data = {'type': action_type}
    response = requests.post(url, headers=headers, json=data)

    if response.status_code == 201:
        return "Action initiated successfully. ✅"
    else:
        logging.error(f"Failed to perform action: {response.content.decode()}")
        return f"❌ Failed to perform action."

def resize_droplet(new_size):
    """Resizes the droplet to a new size."""
    url = f'https://api.digitalocean.com/v2/droplets/{DROPLET_ID}/actions'
    headers = {'Content-Type': 'application/json', 'Authorization': f'Bearer {DIGITAL_OCEAN_KEY}'}
    data = {'type': 'resize', 'size': new_size}
    response = requests.post(url, headers=headers, json=data)

    if response.status_code == 201:
        return "Droplet resizing initiated successfully. ✅"
    else:
        logging.error(f"Failed to resize droplet: {response.content.decode()}")
        return f"❌ Failed to resize droplet."

# --- Discord Bot Functions ---
async def send_embed(channel, title, description, color=discord.Color.blue()):
    """Sends an embedded message to a Discord channel."""
    embed = discord.Embed(title=title, description=description, color=color)
    await channel.send(embed=embed)

async def check_active_players():
    """Checks the number of active players on the server using the provided API."""
    try:
        response = requests.get(FX_API_URL + 'server-stats?page=0&perPage=20')
        if response.status_code == 200:
            data = response.json()
            return sum(item['playerCount'] for item in data['items'])
        else:
            logging.error(f"Failed to fetch player data. Status code: {response.status_code}")
            return 0
    except Exception as e:
        logging.error(f"Error fetching player data: {str(e)}")
        return 0

# --- Discord Views for Interactions ---
class ConfirmationView(ui.View):
    """View for confirmation buttons."""

    def __init__(self, action_type, size=None):
        super().__init__(timeout=30)
        self.action_type = action_type
        self.size = size

    @ui.button(label="Confirm", style=discord.ButtonStyle.success)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        global current_plan  # Access the global variable
        message = ""
        if self.action_type == "resize":
            message = resize_droplet(self.size)
            if "successfully" in message:
                current_plan = self.size  # Update the current plan if successful
        else:
            message = perform_droplet_action(self.action_type)
        await interaction.response.send_message(message, ephemeral=False)
        self.stop()

    @ui.button(label="Cancel", style=discord.ButtonStyle.danger)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("Action canceled. ❌", ephemeral=False)
        self.stop()

class DropletManagementView(ui.View):
    """View for droplet management buttons."""

    def __init__(self):
        super().__init__(timeout=None)

    async def check_permissions(self, interaction):
        """Checks if the user has permission to interact with the view."""
        user_roles = [role.id for role in interaction.user.roles]
        has_permission = (
            not droplet_perms and not authorized_users or
            any(role in droplet_perms for role in user_roles) or
            interaction.user.id in authorized_users
        )
        if not has_permission:
            await interaction.response.send_message("You do not have permission to use this.", ephemeral=True)
        return has_permission

    async def ask_for_confirmation(self, interaction, action_type, size=None):
        """Presents a confirmation dialog to the user."""
        view = ConfirmationView(action_type, size)
        try:
            if size is not None:
                if action_type == "resize":
                    cost_mapping = {
                        "s-1vcpu-2gb-intel": "0.024",
                        "s-2vcpu-4gb-amd": "0.042",
                        "s-4vcpu-8gb-amd": "0.083",
                        "s-4vcpu-16gb-amd": "0.125",
                        "s-v8cpu-16gb-amd": "0.167"
                    }
                    target_cost = cost_mapping.get(size)

                    if target_cost is None:
                        raise ValueError(f"Invalid size provided: {size}")

                    await interaction.response.send_message(
                        f"Are you sure you want to {action_type} the droplet to {size}? This will cost {target_cost} USD/h",
                        ephemeral=False,
                        view=view
                    )
                    return

            # If no size or not resizing, send the generic confirmation
            await interaction.response.send_message(
                f"Are you sure you want to {action_type} the droplet?",
                ephemeral=False,
                view=view
            )

        except Exception as e:
            logging.error(f"Error in ask_for_confirmation: {str(e)}")
            await interaction.response.send_message(
                f"An error occurred while processing your request. Please try again later.",
                ephemeral=True
            )

    # Button Definitions for Droplet Management
    @ui.button(label="Super Usage (8vcpu-16gb)", style=discord.ButtonStyle.primary, custom_id="resize_super")
    async def resize_super(self, interaction: discord.Interaction, button: discord.ui.Button):
        if await self.check_permissions(interaction):
            await self.ask_for_confirmation(interaction, "resize", PLANS["ultra"])

    @ui.button(label="Peak Usage (4vcpu-16gb)", style=discord.ButtonStyle.primary, custom_id="resize_high")
    async def resize_high(self, interaction: discord.Interaction, button: discord.ui.Button):
        if await self.check_permissions(interaction):
            await self.ask_for_confirmation(interaction, "resize", PLANS["high"])

    @ui.button(label="Low Usage (2vcpu-8gb)", style=discord.ButtonStyle.primary, custom_id="resize_low")
    async def resize_low(self, interaction: discord.Interaction, button: discord.ui.Button):
        if await self.check_permissions(interaction):
            await self.ask_for_confirmation(interaction, "resize", PLANS['low'])

    @ui.button(label="Offline Mode", style=discord.ButtonStyle.danger, custom_id="resize_offline_mode")
    async def resize_offline_mode(self, interaction: discord.Interaction, button: discord.ui.Button):
        if await self.check_permissions(interaction):
            await self.ask_for_confirmation(interaction, "resize", PLANS['off'])

    @ui.button(label="Power On", style=discord.ButtonStyle.success, custom_id="poweron")
    async def power_on(self, interaction: discord.Interaction, button: discord.ui.Button):
        if await self.check_permissions(interaction):
            await self.ask_for_confirmation(interaction, "power_on")

    @ui.button(label="Power Off", style=discord.ButtonStyle.danger, custom_id="poweroff")
    async def power_off(self, interaction: discord.Interaction, button: discord.ui.Button):
        if await self.check_permissions(interaction):
            await self.ask_for_confirmation(interaction, "power_off")

    @ui.button(label="Reboot", style=discord.ButtonStyle.secondary, custom_id="reboot")
    async def reboot(self, interaction: discord.Interaction, button: discord.ui.Button):
        if await self.check_permissions(interaction):
            await self.ask_for_confirmation(interaction, "reboot")

# --- Embed Creation ---
async def create_embed(ctx_or_interaction):
    """Creates and sends the main droplet management embed."""
    global current_plan  # Access the global variable
    embed = discord.Embed(
        title="🔧 FoundationX Droplet Management",
        description="Easily manage the FX DigitalOcean droplet using the functions below.",
        color=discord.Color.blue()
    )
    current_plan = get_size_slug()  # Update the current plan
    embed.add_field(name="🔄 Resize", value="Use buttons to resize the droplet.", inline=False)
    embed.add_field(name="⚡ Power", value="Power on/off the droplet or reboot it.", inline=False)
    embed.add_field(name="📈 Current Plan: \n", value=f"{current_plan}", inline=False)
    embed.set_footer(text="Created by EthanSpleefan.")

    view = DropletManagementView()

    if isinstance(ctx_or_interaction, discord.Interaction):
        await ctx_or_interaction.response.send_message(embed=embed, view=view)
    else:
        await ctx_or_interaction.send(embed=embed, view=view)

# --- Server Monitoring and Auto-Resizing ---
@tasks.loop(seconds=CHECK_INTERVAL)
async def monitor_server():
    """Monitors the server and automatically resizes based on player count and time."""
    global current_plan
    global servers_not_resizing_count
    global disable_resizing
    global SERVER_IP

    if disable_resizing:
        return

    now = datetime.now(timezone(timedelta(hours=10)))  # Brisbane time
    sydney_time = now + timedelta(hours=1)  # Convert Brisbane to Sydney time (accounting for AEDT)
    current_hour, current_minute = sydney_time.hour, sydney_time.minute
    active_players = await check_active_players()

    delay = ping3.ping(SERVER_IP)
    if delay is None and active_players not in (0, 1) and current_plan != PLANS['off']:
        channel = bot.get_channel(LOG_CHANNEL_ID)
        await send_embed(channel, f"Server is not responding. Likely DDoS.", color=discord.Color.red())
        active_players = 0  # Treat as no players if server is down
    elif delay is not None and active_players not in (0, 1) and current_plan != PLANS["off"]:
        logging.info("Server Responding")
    else:
        return

    # Determine target plan based on time of day in Sydney
    if (current_hour == 7 and current_minute >= 30) or (7 < current_hour < 14):
        target_plan = PLANS['low']  # Morning, power on at 7:30 AEST
    elif (current_hour == 13 and current_minute >= 30) or (14 < current_hour < 16):
        target_plan = PLANS['medium']  # Upsize to medium at 14:30 AEST
    elif (current_hour == 16 and current_minute >= 0) or (16 < current_hour < 20):
        target_plan = PLANS['high']  # Upsize to high at 16:00 AEST
    elif (current_hour == 20) or (20 < current_hour < 2):
        target_plan = PLANS['medium']  # Back to medium at 20:00 AEST
    else:
        target_plan = PLANS['off']  # Shut off at 02:00 AEST

    if target_plan == current_plan:
        logging.info(f"Not Resizing: Current plan ({current_plan}) matches target plan ({target_plan}).")
        return

    channel = bot.get_channel(LOG_CHANNEL_ID)
    if active_players in (0, 1):
        await asyncio.sleep(50)  # Wait to confirm player count
        active_players = await check_active_players()

        if active_players in (0, 1):
            try:
                resize_droplet(target_plan)
                current_plan = target_plan  # Update current plan immediately
                servers_not_resizing_count = 0
                await send_embed(channel, "Server Resized", f"Server resized to plan: {target_plan} at {sydney_time}. Active players: {active_players}.")

                # Schedule reboot if not turning off
                if target_plan != PLANS['off']:
                    await asyncio.sleep(75)  # Wait before rebooting
                    perform_droplet_action("reboot")
                    await send_embed(channel, "Server Rebooted", f"Server rebooted after resizing to {target_plan} at {sydney_time}.")
                else:
                    await send_embed(channel, "Server Off", "Server resized to 'off' plan; will not reboot until the next day.")
                    await bot.change_presence(status=discord.Status.dnd)
            except Exception as e:
                await send_embed(channel, "Error Resizing Server", f"An error occurred while resizing the server: {str(e)}", color=discord.Color.red())
        else:
            await send_embed(channel, "No resizing needed", f"Active players: {active_players} at {sydney_time}.")
    else:
        if servers_not_resizing_count == 0:
            servers_not_resizing_count += 1
            await send_embed(channel, "Server Not Resizing", f"No resizing needed. Active players: {active_players} at {sydney_time}.")

# --- Bot Commands ---
@bot.tree.command(name="restart", description="Restart the droplet (Admin/Manager only)")
async def restart_server(interaction: discord.Interaction):
    """Restarts the server (requires appropriate permissions)."""
    user_roles = [role.id for role in interaction.user.roles]
    if (interaction.user.id in authorized_users or
            any(role in droplet_perms for role in user_roles) or
            any(role in restart_perms for role in user_roles)):
        view = ConfirmationView("reboot")
        await interaction.response.send_message("Are you sure you want to restart the server?", view=view)
    else:
        await interaction.response.send_message(
            "You do not have permission to use this command. "
            "If you believe this is an error, please try again or contact a developer. "
            "If you need to restart the server, please ask an admin, manager, or developer.",
            ephemeral=True  # Send the message only to the user
        )

@bot.tree.command(name="disable_auto", description="Temporarily disable auto-resizing (in hours)")
async def toggle_disable_resizing(interaction: discord.Interaction, hours: int):
    """Disables auto-resizing for a specified number of hours."""
    global disable_resizing
    disable_resizing = True
    channel = bot.get_channel(LOG_CHANNEL_ID)
    await interaction.response.send_message(f"Auto-resizing has been disabled for {hours} hours. ⛔")
    await send_embed(channel, "Auto Resizing Disabled", f"Server auto-resizing has been disabled for {hours} hours.", color=discord.Color.red())

    await asyncio.sleep(hours * 3600)  # Wait for the specified duration

    disable_resizing = False
    await send_embed(channel, "Auto Resizing Enabled", f"Server resizing has been re-enabled.")
    await interaction.followup.send(f"Auto-resizing has been re-enabled after {hours} hours. 🔄", ephemeral=True)

@bot.tree.command(name="enable_auto", description="Enable auto-resizing")
async def cancel_disable_resizing(interaction: discord.Interaction):
    """Manually re-enables auto-resizing."""
    global disable_resizing
    channel = bot.get_channel(LOG_CHANNEL_ID)
    if disable_resizing:
        disable_resizing = False
        await send_embed(channel, "Auto-resizing has been manually enabled again.", color=discord.Color.green())
        await interaction.response.send_message("Auto-resizing has been manually enabled again. ✅")
    else:
        await interaction.response.send_message("Auto-resizing is already enabled. ✅")

# --- Event Handlers ---
@bot.event
async def on_message(message):
    """Handles incoming messages."""
    if message.content.lower() == CONFIRM_COMMAND:
        await message.delete()
        sent_message = await message.channel.send("Action confirmed! Performing the requested operation...")
        await asyncio.sleep(4)
        await sent_message.delete()
    await bot.process_commands(message)

@bot.event
async def on_ready():
    """Handles the bot becoming ready."""
    print(f'{bot.user} has connected to Discord!')
    await bot.change_presence(activity=discord.Activity(status=discord.Status.online, type=discord.ActivityType.watching, name="FX Backend"))
    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} commands")
    except Exception as e:
        print(f"Error syncing commands: {e}")
    monitor_server.start()  # Start the server monitoring loop

# --- Additional Commands ---
@bot.command(name='embed')
async def embed_command(ctx):
    """Command to display the droplet management embed."""
    await create_embed(ctx)

@bot.tree.command(name='players', description="Check the number of active players.")
async def check_players(interaction: discord.Interaction):
    """Displays the number of active players."""
    active_players = await check_active_players()
    await interaction.response.send_message(f"Active players: {active_players}")

@bot.tree.command(name="reload", description="Reload the configuration file.")
async def reload_json(interaction: discord.Interaction):
    """Reloads the configuration file."""
    global droplet_perms, authorized_users, restart_perms, current_plan
    try:
        permissions = load_permissions()
        droplet_perms = permissions.get('droplet_perms', [])
        authorized_users = permissions.get('authorized_users', [])
        restart_perms = permissions.get('restart_perms', [])
        current_plan = get_size_slug()  # Update the current plan
        await interaction.response.send_message("Reloaded configs successfully! ✅")
    except Exception as e:
        logging.error(f"Error reloading configs: {e}")
        await interaction.response.send_message(f"❌ Failed to reload configs: {e}")

@bot.tree.command(name="cmds", description="Display available commands.")
async def cmds(ctx):
    """(Not implemented) Would display available commands."""
    await ctx.send("Command list not yet implemented.")

@bot.command(name='add_role')
async def set_roles(ctx, *role_ids):
    """Adds roles to the droplet_perms list."""
    global droplet_perms
    if any(role.id in droplet_perms for role in ctx.author.roles) or ctx.author.id in authorized_users:
        new_roles = [int(role_id) for role_id in role_ids]
        droplet_perms.extend(role for role in new_roles if role not in droplet_perms)
        save_permissions()
        await ctx.send("Authorized roles updated successfully ✅.")
    else:
        await ctx.send("ERROR ❌: You are not authorized to access this function!")

@bot.tree.command(name='uptime', description="Check the bot's uptime.")
async def uptime(interaction: discord.Interaction):
    """Displays the bot's uptime."""
    if (interaction.user.id in authorized_users or
            any(role.id in droplet_perms for role in interaction.user.roles)):
        uptime_seconds = int(psutil.time.time() - psutil.boot_time())
        hours, remainder = divmod(uptime_seconds, 3600)
        minutes, _ = divmod(remainder, 60)
        uptime_string = f"{hours} hours, {minutes} minutes"
        await interaction.response.send_message(f"Bot uptime: {uptime_string}")
    else:
        await interaction.response.send_message("You don't have permission to use this command.", ephemeral=True)

@bot.command(name='add_user')
async def authorized_user(ctx, *user_ids):
    """Adds users to the authorized_users list."""
    global authorized_users
    if any(role.id in droplet_perms for role in ctx.author.roles) or ctx.author.id in authorized_users:
        new_users = [int(user_id) for user_id in user_ids]
        authorized_users.extend(user for user in new_users if user not in authorized_users)
        save_permissions()
        await ctx.send("Authorized users updated successfully ✅.")
    else:
        await ctx.send("ERROR ❌: You are not authorized to access this function!")

@bot.tree.command(name="embed", description="Display the droplet management embed.")
async def slash_create_embed(interaction: discord.Interaction):
    """Slash command to display the droplet management embed."""
    await create_embed(interaction)

@bot.tree.command(name="panel", description="Get a link to the FX Systems Pterodactyl Panel.")
async def slash_panel_link(interaction: discord.Interaction):
    """Provides a link to the Pterodactyl panel."""
    await interaction.response.send_message(f"Pterodactyl Panel: {FX_PANEL_LINK}")
    await interaction.followup.send("Need help? Contact a Manager or Developer for more info.", ephemeral=True)

@bot.tree.command(name="ping", description="Ping the server.")
async def ping_server(interaction: discord.Interaction):
    """Pings the server and reports the latency."""
    try:
        delay = ping3.ping(SERVER_IP)
        if delay is not None:
            await interaction.response.send_message(f"✅ Ping successful, Time: {delay * 1000:.2f} ms")
        else:
            await interaction.response.send_message("❌ Ping failed: No response from the server!")
    except Exception as e:
        await interaction.response.send_message(f"⚠️ An unexpected error occurred while pinging: {str(e)}")

# --- Run the Bot ---
bot.run(DISCORD_BOT_TOKEN)