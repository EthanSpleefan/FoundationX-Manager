# AutoResizer-DigitalOcean

This repository contains a Discord bot that allows you to easily resize your DigitalOcean droplet using the DigitalOcean API.

## Features

* **Resize droplet:** Easily resize your droplet to different sizes for optimal performance during low usage and high usage.
* **Power management:** Power on/off or reboot your droplet.
* **Role-based authorization:** Control who can access the bot's features using roles.

## Installation

1. **Create a DigitalOcean API token:** [https://cloud.digitalocean.com/account/api/tokens](https://cloud.digitalocean.com/account/api/tokens)
2. **Create a Discord bot:** [https://discord.com/developers/applications](https://discord.com/developers/applications)
3. **Create a `keys` folder and add the following files:**
    * `digitaloceanapi.key`: Your DigitalOcean API token
    * `discordapi.key`: Your Discord bot token
    * `vinnycommand.key`: A unique command to trigger the bot (optional)
4. **Install the required packages:**
    ```bash
    pip install -r requirements.txt
    ```
5. **Run the bot:**
    ```bash
    python app.py
    ```

## Usage

1. **Invite the bot to your Discord server:** [https://discord.com/api/oauth2/authorize?client_id=YOUR_BOT_ID&permissions=8&scope=bot](https://discord.com/api/oauth2/authorize?client_id=YOUR_BOT_ID&permissions=8&scope=bot)
2. **Use the following commands:**
    * `!create_embed`: Create the embed for droplet management.
    * `!add_role <role_id>`: Add a role to the list of authorized roles.
    * `!add_user <user_id>`: Add a user to the list of authorized users.
    * `!reload`: Reload the settings from `settings.json`.

## Contributing

Contributions are welcome! Please open an issue or submit a pull request.

## License

This project is licensed under the MIT License.
