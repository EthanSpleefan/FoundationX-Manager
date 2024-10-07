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

with open('keys/vinnycommand.key', 'r') as file:
    discord_api_secret = file.read().strip() 



API_TOKEN = do_api_secret
DROPLET_ID = '2' #'3164450'  

# Define the sizes for low and peak usage
#i need to change this but i cant be fucked rn
LOW_USAGE = '512mb'
PEAK_USAGE = '1gb'


intents = discord.Intents.default()
intents.message_content = True  # Enable message content intents
#i hate line 28 this took me like 45 min to fix
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

# Function to resize the droplet
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
        await self.ask_for_confirmation(interaction, "resize", PEAK_USAGE)

    @ui.button(label="Resize (512MB)", style=discord.ButtonStyle.primary, custom_id="resize_512mb")
    async def resize_512mb(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.ask_for_confirmation(interaction, "resize", LOW_USAGE)

    @ui.button(label="Power On", style=discord.ButtonStyle.success, custom_id="poweron")
    async def power_on(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.ask_for_confirmation(interaction, "power_on")

    @ui.button(label="Power Off", style=discord.ButtonStyle.danger, custom_id="poweroff")
    async def power_off(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.ask_for_confirmation(interaction, "power_off")

    @ui.button(label="Reboot", style=discord.ButtonStyle.secondary, custom_id="reboot")
    async def reboot(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.ask_for_confirmation(interaction, "reboot")

    async def ask_for_confirmation(self, interaction, action_type, size=None):
        view = ConfirmationView(action_type, size)
        # Send a confirmation message
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
        title="🔧 Droplet Management", 
        description="Easily manage your DigitalOcean droplet using the buttons below.",
        color=discord.Color.blue()
    )
    embed.set_thumbnail(url="https://example.com/droplet_icon.png")  # Replace with actual icon URL
    embed.add_field(name="🔄 Resize", value="Use buttons to resize the droplet.", inline=False)
    embed.add_field(name="⚡ Power", value="Power on/off your droplet or reboot it.", inline=False)
    embed.set_footer(text="Manage your DigitalOcean resources efficiently.")

    view = DropletManagementView()
    
    # Check if it's an interaction or a normal command
    if isinstance(ctx_or_interaction, discord.Interaction):
        await ctx_or_interaction.response.send_message(embed=embed, view=view)
    else:
        await ctx_or_interaction.send(embed=embed, view=view)


@bot.event
async def on_message(message):
    if message.content.lower() == vinnycommand: #dont ask

        await message.channel.send("Action confirmed! Performing the requested operation...")

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


@bot.tree.command(name="create_embed", description="Create an improved embed for droplet management")
async def slash_create_embed(interaction: discord.Interaction):
    await create_embed(interaction)


bot.run(discord_api_secret)
