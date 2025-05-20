import os
from interactions import *
from interactions.api.events import Startup
import logging
from dotenv import load_dotenv

load_dotenv()

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("rpa_script.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

bot = Client(intents=Intents.DEFAULT, logger=logger)


@listen(event_name=Startup)
async def on_ready():
    logger.info("Launching Book Sailor!")


if __name__ == '__main__':
    DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
    logger.info("Loading Commands...")
    bot.load_extension('default_commands')
    bot.start(DISCORD_TOKEN)
