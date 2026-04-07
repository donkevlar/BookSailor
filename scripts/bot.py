import os
from interactions import *
from interactions.api.events import Startup
import logging
from dotenv import load_dotenv
import rpa as r

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
    browserless_ok, browserless_message = r.WebsiteNavigationRPA.verify_browserless_connection()
    if not browserless_ok:
        logger.error(f"Browserless startup check failed: {browserless_message}")
        raise SystemExit(1)

    logger.info(browserless_message)
    logger.info("Loading Commands...")
    bot.load_extension('default_commands')
    bot.start(DISCORD_TOKEN)
