import os
import requests
import json
import discord
from discord.ext import commands
from discord import app_commands
from discord import ui
import asyncio

with open('keys/digitaloceanapi.key', 'r') as file:
    do_api_secret = file.read().strip()

with open('keys/discordapi.key', 'r') as file:
    discord_api_secret = file.read().strip()   

API_TOKEN = do_api_secret
DROPLET_ID = '3164450'  

# Define the sizes for low and peak usage
LOW_USAGE = '512mb'
PEAK_USAGE = '1gb'

intents = discord.Intents.default()
intents.message_content = True  
bot = commands.Bot(command_prefix='!', intents=intents)


def perform_droplet_action(action_type):
    url = f'https://api.digitalocean.com/v2/droplets/{DROPLET_ID}/actions'
    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {API_TOKEN}',
    }
    data = {
        'type': action_type,
    }
    
    response = requests.post(url, headers=headers, data=json.dumps(data))
    
    if response.status_code == 201:
        return "Action initiated successfully."
    else:
        return f"Failed to perform action: {response.content}"


def resize_droplet(new_size):
    url = f'https://api.digitalocean.com/v2/droplets/{DROPLET_ID}/actions'
    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {API_TOKEN}',
    }
    data = {
        'type': 'resize',
        'size': new_size,
    }
    
    response = requests.post(url, headers=headers, data=json.dumps(data))
    
    if response.status_code == 201:
        return "Droplet resizing initiated successfully."
    else:
        return f"Failed to resize droplet: {response.content}"


class DropletManagementView(ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @ui.button(label="Resize (1GB)", style=discord.ButtonStyle.primary, custom_id="resize_1gb")
    async def resize_1gb(self, interaction: discord.Interaction, button: discord.ui.Button):
        result = resize_droplet(PEAK_USAGE)
        await interaction.response.send_message(result, ephemeral=True)

    @ui.button(label="Resize (512MB)", style=discord.ButtonStyle.primary, custom_id="resize_512mb")
    async def resize_512mb(self, interaction: discord.Interaction, button: discord.ui.Button):
        result = resize_droplet(LOW_USAGE)
        await interaction.response.send_message(result, ephemeral=True)

    @ui.button(label="Power On", style=discord.ButtonStyle.success, custom_id="poweron")
    async def power_on(self, interaction: discord.Interaction, button: discord.ui.Button):
        result = perform_droplet_action('power_on')
        await interaction.response.send_message(result, ephemeral=True)

    @ui.button(label="Power Off", style=discord.ButtonStyle.danger, custom_id="poweroff")
    async def power_off(self, interaction: discord.Interaction, button: discord.ui.Button):
        result = perform_droplet_action('power_off')
        await interaction.response.send_message(result, ephemeral=True)

    @ui.button(label="Reboot", style=discord.ButtonStyle.secondary, custom_id="reboot")
    async def reboot(self, interaction: discord.Interaction, button: discord.ui.Button):
        result = perform_droplet_action('reboot')
        await interaction.response.send_message(result, ephemeral=True)


async def create_embed(ctx_or_interaction):
    embed = discord.Embed(title="Droplet Management", description="Manage your DigitalOcean droplet with ease.", color=0x00ff00)
    embed.add_field(name="Resize", value="Use the buttons below to resize your droplet.", inline=False)
    embed.add_field(name="Power On", value="Power on your droplet.", inline=False)
    embed.add_field(name="Power Off", value="Power off your droplet.", inline=False)
    embed.add_field(name="Reboot", value="Reboot your droplet.", inline=False)
    

    view = DropletManagementView()
    

    if isinstance(ctx_or_interaction, discord.Interaction):
        await ctx_or_interaction.response.send_message(embed=embed, view=view)
    else:
        await ctx_or_interaction.send(embed=embed, view=view)


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


@bot.tree.command(name="create_embed", description="Create an embed for droplet management")
async def slash_create_embed(interaction: discord.Interaction):
    await create_embed(interaction)

# Run the bot
bot.run(discord_api_secret)
