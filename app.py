import os
import json
import requests
import discord
from discord.ext import commands
from discord import ui
import asyncio
import aioping

with open('keys/digitaloceanapi.key', 'r') as file:
    do_api_secret = file.read().strip()

with open('keys/discordapi.key', 'r') as file:
    discord_api_secret = file.read().strip()

with open('keys/vinnycommand.key', 'r') as file:
    VINNY_COMMAND = file.read().strip()

API_TOKEN = do_api_secret
DROPLET_ID = '448886902' #set this to your droplet id you can get this from the dashboard by copying the link for example https://cloud.digitalocean.com/droplets/448886902/graphs?i=89d5ef&period=hour and then 448886902 would be your id
LOW_USAGE = 's-2vcpu-8gb-amd'
PEAK_USAGE = 's-4vcpu-16gb-amd'
HIGH_USAGE = 's-v8cpu-16gb-amd'

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
        if not authorized_roles and not authorized_users:
            return True
        if any(role.id in authorized_roles for role in interaction.user.roles) or interaction.user.id in authorized_users:
            return True
        await interaction.response.send_message("You do not have permission to use this.", ephemeral=True)
        return False
    
    @ui.button(label="Resize HIGH Usage (s-8vcpu-16gb-amd)", style=discord.ButtonStyle.primary, custom_id="resize_super")
    async def resize_super(self, interaction: discord.Interaction, button: discord.ui.Button):
        if await self.check_permissions(interaction):
            await self.ask_for_confirmation(interaction, "resize", HIGH_USAGE)


    @ui.button(label="Resize Peak Usage (s-4vcpu-16gb-amd)", style=discord.ButtonStyle.primary, custom_id="resize_high")
    async def resize_high(self, interaction: discord.Interaction, button: discord.ui.Button):
        if await self.check_permissions(interaction):
            await self.ask_for_confirmation(interaction, "resize", PEAK_USAGE)

    @ui.button(label="Resize Low Usage (s-2vcpu-8gb-amd)", style=discord.ButtonStyle.primary, custom_id="resize_low")
    async def resize_low(self, interaction: discord.Interaction, button: discord.ui.Button):
        if await self.check_permissions(interaction):
            await self.ask_for_confirmation(interaction, "resize", LOW_USAGE)

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
            ephemeral=True,
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
        else:
            result = perform_droplet_action(self.action_type)
        await interaction.response.send_message(result, ephemeral=True)
        self.stop()

    @ui.button(label="Cancel", style=discord.ButtonStyle.danger)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("Action canceled.", ephemeral=True)
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

@bot.event
async def on_message(message):
    if message.content.lower() == VINNY_COMMAND:
        await message.delete()
        sent_message = await message.channel.send("Action confirmed! Performing the requested operation...")
        await asyncio.sleep(4)
        await sent_message.delete()
    await bot.process_commands(message)

@bot.event
async def on_ready():
    print(f'{bot.user} has connected to Discord!')
    await bot.change_presence(activity=discord.Activity(type=discord.ActivityType.watching, name="FX Systems"))
    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} commands")
    except Exception as e:
        print(e)

@bot.command(name='create_embed')
async def create_embed_command(ctx):
    await create_embed(ctx)

@bot.command(name='embed')
async def embed_command(ctx):
    await create_embed(ctx)

@bot.command(name="reload")
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
    ip_address = ""
    
    try:
        # Use aioping to ping the server
        delay = await aioping.ping(ip_address)
        await interaction.response.send_message(f"Ping successful! Time: {delay * 1000:.2f} ms")
    except asyncio.TimeoutError:
        await interaction.response.send_message("Ping failed: Request timed out. Please check the server status.")
    except Exception as e:
        await interaction.response.send_message(f"An unexpected error occurred while pinging: {str(e)}")

bot.run(discord_api_secret)
