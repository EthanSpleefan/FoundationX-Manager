import os
import json
import requests
import discord
from discord.ext import commands
from discord import ui
import asyncio
import ping3 
import io
import sys
import platform
import psutil
import datetime
import subprocess
import discord.ext
from discord.ext import tasks
import sqlite3



DROPLET_ID = '448886902' 
FX_API_URL = 'https://api.foundationxservers.com/'
LOG_CHANNEL_ID = 1270361238697672736
CHECK_INTERVAL = 500  # 500seconds = 8.33 minutes
last_resize_time = None
reboot_scheduled = False
disable_resizing = False

PLANS = {
    'not_set': None,
    'off': 's-1vcpu-2gb-intel', #done 0.024/hr
    'low': 's-2vcpu-4gb-amd', #done 0.042/hr
    'medium': 's-4vcpu-8gb-amd', #done 0.083/hr
    'high': 's-4vcpu-16gb-amd', #done $0.125/hr
    'ultra': 's-v8cpu-16gb-amd' #done 0.167/hr
}

current_plan = PLANS['not_set']

PLAN_PRICES_USD = {
    's-2vcpu-8gb-intel': 0.024,  # off
    's-2vcpu-8gb-amd': 0.042,   # low
    's-4vcpu-16gb-amd': 0.063,  # medium
    's-v8cpu-16gb-amd': 0.125, # high
    's-v8cpu-16gb-amd': 0.167  # ultra 
}

AVERAGE_MONTHLY_COST_USD = 84.00
HOURS_IN_MONTH = 24 * 30  # Assuming 30 days in a month

if sys.version_info[0] == 3 and sys.version_info[1] >= 8 and platform.system() == 'Windows':
    import asyncio
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


def setup_database():
    conn = sqlite3.connect('server_resizes.db')
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS resizes (
            id INTEGER PRIMARY KEY,
            plan TEXT,
            start_time TEXT,
            end_time TEXT,
            duration INTEGER
        )
    ''')
    conn.commit()
    conn.close()

def log_resize(plan, duration):
    conn = sqlite3.connect('server_resizes.db')
    c = conn.cursor()
    start_time = datetime.datetime.now().isoformat()
    c.execute('INSERT INTO resizes (plan, start_time, duration) VALUES (?, ?, ?)',
              (plan, start_time, duration))
    conn.commit()
    conn.close()



async def get_current_exchange_rate(base_currency='USD', target_currency='AUD'):
    """Fetches the current exchange rate from the API."""
    url = f'https://api.exchangerate-api.com/v4/latest/{base_currency}'
    response = requests.get(url)
    data = response.json()
    
    if response.status_code == 200:
        return data['rates'][target_currency]
    else:
        print(f"Error fetching exchange rate: {data.get('error', 'Unknown error')}")
        return None
    


with open('keys/digitaloceanapi.key', 'r') as file:
    DigitalOceanSecret = file.read().strip()

with open('keys/discordapi.key', 'r') as file:
    discord_api_secret = file.read().strip()

with open('keys/sudo_command.key', 'r') as file:
    sudo_command = file.read().strip()

#Setup Variables
API_TOKEN = DigitalOceanSecret


intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)


# Load or initialize settings
def load_settings():
    if os.path.exists('settings.json'):
        with open('settings.json', 'r') as f:
            return json.load(f)
    return {'authorized_roles': [], 'authorized_users': []}

settings = load_settings()
authorized_roles = list(map(int, settings.get('authorized_roles', [])))  # Ensure integers
authorized_users = list(map(int, settings.get('authorized_users', [])))  # Ensure integers

def save_settings():
    with open('settings.json', 'w') as f:
        json.dump({'authorized_roles': authorized_roles, 'authorized_users': authorized_users}, f)

def perform_droplet_action(action_type):
        url = f'https://api.digitalocean.com/v2/droplets/{DROPLET_ID}/actions'
        headers = {'Content-Type': 'application/json', 'Authorization': f'Bearer {API_TOKEN}'}
        data = {'type': action_type}
        response = requests.post(url, headers=headers, json=data)
        
        if response.status_code == 201:
            return "Action initiated successfully."
        else:
            return f"❌ Failed to perform action: {response.content.decode()}"

async def send_embed(channel, title, description, color=discord.Color.blue()):
    embed = discord.Embed(title=title, description=description, color=color)
    await channel.send(embed=embed)


async def check_active_players():
    try:
        response = requests.get(FX_API_URL+'server-stats?page=0&perPage=20')
        if response.status_code == 200:
            data = response.json()
            total_players = sum(item['playerCount'] for item in data['items'])
            return total_players
        else:
            raise Exception(f"Failed to fetch player data. Status code: {response.status_code}")
    except Exception as e:
        print(f"Error fetching player data: {str(e)}")
        return 0


"""async def schedule_reboot_check(interaction):
    global last_resize_time, reboot_scheduled
    last_resize_time = datetime.now()
    reboot_scheduled = False
    await asyncio.sleep(300)  # Wait for 5 minutes
    
    if not reboot_scheduled:
        await prompt_auto_reboot(interaction)


async def prompt_auto_reboot(interaction):
    embed = discord.Embed(
        title="⚠️ Server AutoReboot",
        description="The server has not been rebooted since the last resize operation. Would you like to reboot now?",
        color=discord.Color.yellow()
    )
    view = AutoRebootView()
    await interaction.channel.send(embed=embed, view=view)

class AutoRebootView(ui.View):
    def __init__(self):
        super().__init__(timeout=300)  # 5 minutes timeout

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return (
            interaction.user.id in authorized_users or
            any(role.id in authorized_roles for role in interaction.user.roles)
        )

    @ui.button(label="Confirm Reboot", style=discord.ButtonStyle.danger)
    async def confirm_reboot(self, interaction: discord.Interaction, button: discord.ui.Button):
        result = perform_droplet_action("reboot")
        await interaction.response.send_message(f"Reboot initiated: {result}", ephemeral=False)
        self.stop()

    @ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel_reboot(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("Auto-reboot canceled.", ephemeral=False)
        self.stop()

"""

def resize_droplet(new_size):
    url = f'https://api.digitalocean.com/v2/droplets/{DROPLET_ID}/actions'
    headers = {'Content-Type': 'application/json', 'Authorization': f'Bearer {API_TOKEN}'}
    data = {'type': 'resize', 'size': new_size}
    response = requests.post(url, headers=headers, json=data)
    
    if response.status_code == 201:
        return "Droplet resizing initiated successfully."
    else:
        return f"❌ Failed to resize droplet: {response.content.decode()}"


class DropletManagementView(ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    async def check_permissions(self, interaction):
        has_permission = (
            not authorized_roles and not authorized_users or
            any(role.id in authorized_roles for role in interaction.user.roles) or
            interaction.user.id in authorized_users
        )
        if has_permission:
            return True
        await interaction.response.send_message("You do not have permission to use this.", ephemeral=True)
        return False
    
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

    @ui.button(label="Offline Plan (DO NOT START SERVER)", style=discord.ButtonStyle.primary, custom_id="resize_offline_mode")
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

    async def ask_for_confirmation(self, interaction, action_type, size=None):
        view = ConfirmationView(action_type, size)
        await interaction.response.send_message(
            f"Are you sure you want to {action_type} the droplet?",
            ephemeral=False,
            view=view
        )

class ConfirmationView(ui.View):
    def __init__(self, action_type, size=None):
        super().__init__(timeout=30)
        self.action_type = action_type
        self.size = size

    @ui.button(label="Confirm", style=discord.ButtonStyle.success)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.action_type == "resize":
            result = resize_droplet(self.size)
            if "successfully" in result:
                asyncio.create_task(schedule_reboot_check(interaction))
        else:
            result = perform_droplet_action(self.action_type)
        await interaction.response.send_message(result, ephemeral=False)
        self.stop()

    @ui.button(label="Cancel", style=discord.ButtonStyle.danger)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("Action canceled.", ephemeral=False)
        self.stop()

async def create_embed(ctx_or_interaction):
    embed = discord.Embed(
        title="🔧 FoundationX Droplet Management",
        description="Easily manage the FX DigitalOcean droplet using the functions below.",
        color=discord.Color.blue()
    )
    embed.add_field(name="🔄 Resize", value="Use buttons to resize the droplet for optimal performance during low usage and high usage.", inline=False)
    embed.add_field(name="⚡ Power", value="Power on/off the droplet or reboot it.", inline=False)
    embed.set_footer(text="Created by EthanSpleefan.")

    view = DropletManagementView()

    if isinstance(ctx_or_interaction, discord.Interaction):
        await ctx_or_interaction.response.send_message(embed=embed, view=view)
    else:
        await ctx_or_interaction.send(embed=embed, view=view)


async def log_action(message):
    channel = bot.get_channel(LOG_CHANNEL_ID)
    await channel.send(message)

@tasks.loop(seconds=CHECK_INTERVAL)
async def monitor_server():
    global current_plan
    global disable_resizing
    now = datetime.datetime.now()
    current_hour = now.hour
    active_players = await check_active_players()
    
    if disable_resizing:
        
        #await log_action(f"Autoresizer is disabled. Skipping resize.")
        return

    if 16 <= current_hour < 23:  # Peak hours: 4:30 PM to 11:30 PM
        target_plan = PLANS['high']  # High plan for peak hours
    elif 8 <= current_hour < 16:  # Moderate-use hours: 8:30 AM to 4:30 PM
        target_plan = PLANS['low'] if active_players == 0 else PLANS['high']
    else:  # Extreme low-use/off hours: 11:30 PM to 8:30 AM
        target_plan = PLANS['off'] if active_players == 0 else PLANS['low']

    if target_plan == current_plan:
        print("Current Plan == Target Plan")
        return

    if active_players in (0, 1):
        # Wait for 50 seconds to confirm the player count
        await asyncio.sleep(50)
        active_players = await check_active_players()

        if active_players in (0, 1):
            try:
                # Resize server
                resize_droplet(target_plan)
                
                # Log the action to the database
                duration = 0  # Placeholder for duration, adjust as needed
                log_resize(target_plan, duration)
                
                # Send embed notification
                channel = bot.get_channel(LOG_CHANNEL_ID)  # Replace with your channel ID
                await send_embed(channel, "Server Resized", f"Server resized to plan: {target_plan} at {now}. Active players: {active_players}.")

                # Update current_plan
                current_plan = target_plan
                
                # Schedule reboot 
                await asyncio.sleep(80)
                if target_plan != PLANS['off']:
                    perform_droplet_action("reboot")
                    await send_embed(channel, "Server Rebooted", f"Server rebooted after resizing to {target_plan} at {now}.")
                else:
                    await send_embed(channel, "Server Off", "Server resized to 'off' plan; will not reboot until the next day.")
            except Exception as e:
                await log_action(f"Error resizing server: {str(e)}")
        else:
            print("""log_action(f"No resizing needed. Active players: {active_players} at {now}.")""")
    else:
        print("""log_action(f"No resizing needed. Active players: {active_players} at {now}.")""")



@bot.tree.command(name="disable_auto", description="Temporarily disable auto-resizing for a specified duration in hours.")
async def toggle_disable_resizing(interaction: discord.Interaction, hours: int):
    global disable_resizing
    disable_resizing = True  # Set to True to disable auto-resizing
    channel = bot.get_channel(LOG_CHANNEL_ID)
    await interaction.response.send_message(f"Auto-resizing has been disabled for {hours} hours.")
    await send_embed(channel, "Auto Resizeing Disabled", f"Server auto-resizing has been disabled.")

    # Wait for the specified duration in hours (converted to seconds)
    await asyncio.sleep(hours * 3600)
    
    # Automatically re-enable resizing after the duration
    disable_resizing = False 
    await send_embed(channel, "Auto Resizeing Enabled", f"Server resizing has been re-enabled.")
    await interaction.response.send_message(f"Auto-resizing has been disabled for {hours} hours and will be restored automatically.")

@bot.tree.command(name="enable_auto", description="Enable auto-resizing.")
async def cancel_disable_resizing(interaction: discord.Interaction):
    global disable_resizing
    if disable_resizing:
        disable_resizing = False  # Set to False to enable auto-resizing
        await log_action("Auto-resizing has been manually enabled again.")
        await interaction.response.send_message("Auto-resizing has been manually enabled again.")
    else:
        await interaction.response.send_message("Auto-resizing is already enabled.")

@bot.event
async def on_message(message):
    if message.content.lower() == sudo_command:
        await message.delete()
        sent_message = await message.channel.send("Action confirmed! Performing the requested operation...")
        await asyncio.sleep(4)
        await sent_message.delete()
    await bot.process_commands(message)

@bot.event
async def on_ready():
    print(f'{bot.user} has connected to Discord!')
    await bot.change_presence(activity=discord.Activity(type=discord.ActivityType.watching, name="FoundationX Backend"))
    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} commands")
        monitor_server.start()
        channel = bot.get_channel(LOG_CHANNEL_ID)
        await send_embed(channel, "Auto Resizer Active", f"Server auto-resizing is online.")
    except Exception as e:
        print(e)

@bot.command(name='create_embed')
async def create_embed_command(ctx):
    await create_embed(ctx)

@bot.command(name='embed')
async def embed_command(ctx):
    await create_embed(ctx)

@bot.tree.command(name='players', description="Check the status of the server.")
async def check_players(ctx):
    active_players = await check_active_players()
    await ctx.send(f"Active players: {active_players}")

@bot.tree.command(name="reload", description="Reload the settings from the settings.json file.")
async def reload_json(ctx):
    global authorized_roles, authorized_users
    settings = load_settings()
    authorized_roles = list(map(int, settings.get('authorized_roles', [])))  # Ensure integers
    authorized_users = list(map(int, settings.get('authorized_users', [])))  # Ensure integers
    await ctx.send("Reloaded settings successfully! ✅")

@bot.command(name='add_role')
async def set_roles(ctx, *role_ids):
    global authorized_roles

    # Check if the user has permission to modify roles
    if any(role.id in authorized_roles for role in ctx.author.roles) or ctx.author.id in authorized_users:
        new_roles = list(map(int, role_ids))
        for role_id in new_roles:
            if role_id not in authorized_roles:
                authorized_roles.append(role_id)
        save_settings()
        await ctx.send("Authorized roles updated successfully ✅.")
    else:
        await ctx.send("ERROR ❌: You are not authorized to access this function!")
        print(f"Authorized Roles: {authorized_roles}")
        print(f"Authorized Users: {authorized_users}")

@bot.tree.command(name='uptime', description="Check the uptime of the bot!")
async def uptime(interaction: discord.Interaction):
    if interaction.user.id in authorized_users or any(role.id in authorized_roles for role in interaction.user.roles):
        uptime_seconds = int(psutil.time.time() - psutil.boot_time())
        hours, remainder = divmod(uptime_seconds, 3600)
        minutes, _ = divmod(remainder, 60)
        uptime_string = f"{hours} hours, {minutes} minutes"
        await interaction.response.send_message(f"Bot uptime: {uptime_string}")
    else:
        await interaction.response.send_message("You don't have permission to use this command.")

@bot.tree.command(name='reboot', description="Reboot the hosting device. Authorized Users Only.")
async def reboot(interaction: discord.Interaction):
    authorized_user_id = 980374069109227570  # Replace with the actual authorized user ID
    if interaction.user.id == authorized_user_id:
        try:
            # Use sudo with NOPASSWD option for the reboot command
            subprocess.run(['sudo', 'reboot'], check=True)
            await interaction.response.send_message("Reboot command executed successfully ✅. The device will restart momentarily ⚡.")
        except subprocess.CalledProcessError as e:
            await interaction.response.send_message(f"Error executing reboot command: {str(e)}")
    else:
        await interaction.response.send_message("You don't have permission to use this command 🔒.")

@bot.tree.command(name='halon', description="WARNING ⚠️ EMERGENCY HALON RELEASE❗")
async def halon(interaction: discord.Interaction):
    if interaction.user.id is not None:
        await interaction.response.send_message("HALON RELEASE ACTIVATED!")
        
        # Shutdown the Droplet
        shutdown_response = perform_droplet_action('shutdown')
        await interaction.followup.send(f"Droplet shutdown initiated: {shutdown_response}")
        
        # Wait for 30 seconds
        await asyncio.sleep(30)
        
        # Resize the Droplet to low usage size
        resize_response = perform_droplet_action('resize', size=PLANS['off'])
        await interaction.followup.send(f"Droplet resize initiated: {resize_response}")
        
        # Ping the server
        ip_address = "170.64.141.254"
        delay = ping3.ping(ip_address)
        
        if delay is None:
            # If the server doesn't respond, run sudo shutdown locally
            try:
                subprocess.run(['sudo', 'shutdown', '-h', 'now'], check=True)
                await interaction.followup.send("Server did not respond. Local shutdown initiated.")
            except subprocess.CalledProcessError as e:
                await interaction.followup.send(f"Error executing local shutdown: {str(e)}")
        else:
            await interaction.followup.send(f"Server responded to ping, Time: {delay * 1000:.2f} ms")
    else:
        await interaction.response.send_message("Error Halon Release Failed!") 

@bot.command(name='add_user')
async def authorized_user(ctx, *user_ids):
    global authorized_users

    # Check if the user has permission to modify users
    if any(role.id in authorized_roles for role in ctx.author.roles) or ctx.author.id in authorized_users:
        new_users = list(map(int, user_ids))
        for user_id in new_users:
            if user_id not in authorized_users:
                authorized_users.append(user_id)
        save_settings()
        await ctx.send("Authorized users updated successfully ✅.")
    else:
        await ctx.send("ERROR ❌: You are not authorized to access this function!")
        print(f"Authorized Roles: {authorized_roles}")
        print(f"Authorized Users: {authorized_users}")

@bot.tree.command(name="embed", description="Create the embed for FoundationX droplet management")
async def slash_create_embed(interaction: discord.Interaction):
    await create_embed(interaction)
    
@bot.tree.command(name="panel", description="FX Systems Pterodactyl Panel")
async def slash_panel_link(interaction: discord.Interaction):
    await interaction.response.send_message("Pterodactyl Panel: https://panel.foundationxservers.com/")

@bot.tree.command(name="ping", description="Ping the server to check if it is accessible from the public internet.")
async def ping_server(interaction: discord.Interaction):
    ip_address = "170.64.141.254"
    
    try:
        # Use ping3 to ping the server
        delay = ping3.ping(ip_address)
        if delay is not None:
            await interaction.response.send_message(f"✅ Ping successful, Time: {delay * 1000:.2f} ms")
        else:
            await interaction.response.send_message("❌ Ping failed: No response from the server!")
    except Exception as e:
        await interaction.response.send_message(f"⚠️ An unexpected error occurred while pinging: {str(e)}")

@bot.command(name='total_savings')
async def total_savings(ctx, target_currency='AUD'): 
    """Calculates and displays the total savings in USD and the specified target currency."""

    conn = sqlite3.connect('server_resizes.db')
    c = conn.cursor()
    c.execute('SELECT plan, duration FROM resizes')
    rows = c.fetchall()
    conn.close()

    # Calculate total cost based on the duration in hours for each plan
    total_cost_usd = AVERAGE_MONTHLY_COST_USD 
    for row in rows:
        plan, duration = row
        hours = duration / 3600  # Convert duration from seconds to hours
        if plan in PLAN_PRICES_USD:
            total_cost_usd -= hours * PLAN_PRICES_USD[plan] 

    # Calculate total savings in USD
    total_savings_usd = AVERAGE_MONTHLY_COST_USD - total_cost_usd

    # Get the exchange rate
    exchange_rate = await get_current_exchange_rate(target_currency=target_currency) 
    if exchange_rate is None:
        await ctx.send("Error fetching exchange rate. Please try again later.")
        return

    # Calculate costs and savings in the target currency
    total_cost_target = total_cost_usd * exchange_rate
    total_savings_target = total_savings_usd * exchange_rate

    # Calculate the percentage saved
    if AVERAGE_MONTHLY_COST_USD > 0:
        percent_saved = (total_savings_usd / AVERAGE_MONTHLY_COST_USD) * 100
    else:
        percent_saved = 0

    # Format the output message
    savings_message = (
        f"Total Cost with Auto Resizer: ${total_cost_usd:.2f} (USD) / {total_cost_target:.2f} ({target_currency})\n"
        f"Total Savings: ${total_savings_usd:.2f} (USD) / {total_savings_target:.2f} ({target_currency})\n"
        f"Percentage Saved: {percent_saved:.2f}%"
    )
    
    await ctx.send(savings_message)

setup_database()
bot.run(discord_api_secret)
