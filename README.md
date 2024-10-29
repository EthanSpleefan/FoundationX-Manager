# FX Manager

FoundationX Manager Discord Bot.

## Features

* **Resize droplet:** Easily resize your droplet to different sizes for optimal performance during low usage and high usage.
* **Power management:** Power on/off or reboot your droplet.
* **Role-based authorization:** Control who can access the bot's features using roles.

## Installation

1. **Create a DigitalOcean API token:** [https://cloud.digitalocean.com/account/api/tokens](https://cloud.digitalocean.com/account/api/tokens)
2. **Create a Discord bot:** [https://discord.com/developers/applications](https://discord.com/developers/applications)
3. **Create a `keys.json` file and add the following info:**
    **See example/keys.json**
    * `digital ocean api`: Your DigitalOcean API token
    * `discord token`: Your Discord bot token
    * `confirm command`: A unique command to trigger the bot (optional)
4. **Install the required packages:**
    ```bash
    pip install -r requirements.txt
    ```
5. **Run the bot:**
    ```bash
    python app.py
    ```

## Contributing

Contributions are welcome! Please open an issue or submit a pull request.

## License

This project is licensed under the MIT License.
