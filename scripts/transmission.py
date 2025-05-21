from transmission_rpc import Client, error
from dotenv import load_dotenv
import logging
import os

load_dotenv()

logger = logging.getLogger(__name__)


# Transmission Client
class TransmissionClient:
    def __init__(self):
        self.host = os.getenv('TRANSMISSION_HOST', 'localhost')
        self.port = int(os.getenv('TRANSMISSION_PORT', '9091'))
        self.username = os.getenv('TRANSMISSION_USERNAME', 'user')
        self.password = os.getenv('TRANSMISSION_PASS')
        self.client = Client(host=self.host, port=self.port,
                             username=self.username, password=self.password)

    def get_torrents(self):
        try:
            logger.info("Retrieving Torrents...")
            torrents = self.client.get_torrents()
            return torrents

        except Exception as e:
            logger.error(f"Could not retrieve the list of torrents. {e}")

    def load_torrent(self, file_path: str):
        logger.info(f"Attempting to add torrent with path {file_path}")
        try:
            session = self.client.get_session()
            if session:
                torrent = self.client.add_torrent(torrent=file_path,
                                                  download_dir=os.getenv('TRANSMISSION_DOWNLOAD', '/downloads'))
                logger.info(f'Name: {torrent.name}, Status: {torrent.status}')

                return torrent

        except error.TransmissionError as e:
            logger.error(f"Failed to add torrent: {e}")
