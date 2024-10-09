import os
import json
import requests
import discord
from discord.ext import commands
from discord import ui
import pytz
import time
import asyncio
from datetime import datetime

with open('keys/digitaloceanapi.key', 'r') as file:
    do_api_secret = file.read().strip()

with open('keys/discordapi.key', 'r') as file:
    discord_api_secret = file.read().strip()

with open('keys/vinnycommand.key', 'r') as file:
    VINNY_COMMAND = file.read().strip()

API_TOKEN = do_api_secret
DROPLET_ID = '449984469'
LOW_USAGE = 's-2vcpu-8gb-amd'
PEAK_USAGE = 's-4vcpu-16gb-amd'

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)

# Load or initialize settings
def load_settings():
    if os.path.exists('settings.json'):
        with open('settings.json', 'r') as f:
            return json.load(f)
    return {'authorized_roles': [], 'authorized_user_ids': [], 'response_channel_id': None}

settings = load_settings()
authorized_roles = settings.get('authorized_roles', [])
authorized_user_ids = settings.get('authorized_user_ids', [])
response_channel_id = settings.get('response_channel_id')

def save_settings():
    with open('settings.json', 'w') as f:
        json.dump({'authorized_roles': authorized_roles, 'authorized_user_ids': authorized_user_ids, 'response_channel_id': response_channel_id}, f)

def perform_droplet_action(action_type):
    url = f'https://api.digitalocean.com/v2/droplets/{DROPLET_ID}/actions'
    headers = {'Content-Type': 'application/json', 'Authorization': f'Bearer {API_TOKEN}'}
    data = {'type': action_type}
    response = requests.post(url, headers=headers, json=data)
    return "Action initiated successfully." if response.status_code == 201 else f"❌ Failed to perform action: {response.content}"

def resize_droplet(new_size):
    url = f'https://api.digitalocean.com/v2/droplets/{DROPLET_ID}/actions'
    headers = {'Content-Type': 'application/json', 'Authorization': f'Bearer {API_TOKEN}'}
    data = {'type': 'resize', 'size': new_size}
    response = requests.post(url, headers=headers, json=data)
    return "Droplet resizing initiated successfully." if response.status_code == 201 else f"❌ Failed to resize droplet: {response.content}"

class DropletManagementView(ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    async def check_permissions(self, interaction):
        if not authorized_roles:
            return True
        if any(role.id in authorized_roles for role in interaction.user.roles):
            return True
        await interaction.response.send_message("You do not have permission to use this.", ephemeral=True)
        return False

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
    #embed.set_thumbnail("/droplet_icon.png")
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
    if response_channel_id and message.channel.id != response_channel_id:
        return

    if message.content.lower() == VINNY_COMMAND:
        await message.delete()
        sent_message = await message.channel.send("Action confirmed! Performing the requested operation...")
        await asyncio.sleep(4)
        await sent_message.delete()
    await bot.process_commands(message)

@bot.event
async def on_ready():
    print(f'{bot.user} has connected to Discord!')
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

@bot.tree.command(name='set_roles', description="Set the authorized roles for the bot")
async def slash_set_roles(interaction: discord.Interaction, *role_ids: int):
    if not authorized_roles and not authorized_user_ids:
        await interaction.response.send_message("No authorized roles or user IDs set. Please contact the administrator.", ephemeral=True)
        return

    if not any(role.id in authorized_roles for role in interaction.user.roles) and interaction.user.id not in authorized_user_ids:
        await interaction.response.send_message("You do not have permission to use this command.", ephemeral=True)
        return
    
    authorized_roles = list(role_ids)
    save_settings()
    await interaction.response.send_message("Authorized roles updated successfully.", ephemeral=True)

@bot.tree.command(name='set_channel', description="Set the response channel for the bot")
async def slash_set_channel(interaction: discord.Interaction, channel_id: int):
    if not authorized_roles and not authorized_user_ids:
        await interaction.response.send_message("No authorized roles or user IDs set. Please contact the administrator.", ephemeral=True)
        return

    if not any(role.id in authorized_roles for role in interaction.user.roles) and interaction.user.id not in authorized_user_ids:
        await interaction.response.send_message("You do not have permission to use this command.", ephemeral=True)
        return

    global response_channel_id
    response_channel_id = channel_id
    save_settings()
    await interaction.response.send_message(f"Response channel set to <#{channel_id}> successfully.", ephemeral=True)

@bot.tree.command(name="create_embed", description="Create the embed for FoundationX droplet management")
async def slash_create_embed(interaction: discord.Interaction):
    await create_embed(interaction)

bot.run(discord_api_secret)
