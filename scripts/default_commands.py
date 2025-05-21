import asyncio
import os
from interactions import *
from interactions.api.events import *
import rpa as r
import logging
from transmission import TransmissionClient
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


class BookSearch(Extension):
    def __init__(self, bot):
        self.rpa = r.WebsiteNavigationRPA(username=os.getenv('USERNAME'), password=os.getenv('PASSWORD'),
                                          base_url="https://audiobookbay.lu", download_dir=os.getenv('DOWNLOAD_DIR'))
        self.book_result = []
        self.latest_torrent = None

    # Functions --------------
    async def book_search_rpa(self, query: str):
        self.rpa.nav_login_page()
        self.rpa.handle_login()
        results = self.rpa.get_search_result_titles(query)
        return results

    # Commands

    @slash_command(name='request-book',
                   description="Find a book. Important! This will do its best, but can still fail.")
    @slash_option(name="book",
                  description="Book Title. Please be as accurate as possible ex: 'HWFWM 11', and not just 'HWFWM'.",
                  opt_type=OptionType.STRING, required=True)
    async def get_book(self, ctx: SlashContext, book: str):
        await ctx.defer()
        options = []

        results = await self.book_search_rpa(book)
        is_valid = False

        if results:
            count = 0
            for title, url in results:
                count += 1
                if len(title) <= 100:
                    options.append(StringSelectOption(label=title, value=str(count)))
                    self.book_result.append({"id": count, "title": title, "url": url})
                    is_valid = True

            # Components
            components: list[ActionRow] = [
                ActionRow(
                    StringSelectMenu(
                        options,  # NOQA
                        min_values=1,
                        max_values=1,
                        placeholder="",
                        custom_id='book_select_menu'
                    )
                ),
                ActionRow(
                    Button(
                        style=ButtonStyle.RED,
                        label="Cancel",
                        custom_id="cancel_button"
                    )
                )

            ]

            if is_valid:
                await ctx.send(components=components)
            else:
                await ctx.send("Results were inconclusive, please try another title!", ephemeral=True)

        else:
            await ctx.send("No results found! Please try another title.", ephemeral=True)

    # Callbacks ----------------

    @listen(Component)
    async def on_component(self, event: Component):
        ctx = event.ctx

        match ctx.custom_id:
            # Book selector from book search command
            case "book_select_menu":

                selection = ctx.values
                for value in selection:
                    logger.info(f'Book Selected: {selection}')
                    results = self.book_result
                    for result in results:
                        int_id = result.get('id')
                        url = result.get('url')
                        title = result.get('title')

                        if int(int_id) == int(value):
                            # RPA Process
                            outcome = self.rpa.process_post_by_url(title=title, url=url)
                            # Check if using a magnet link
                            if self.rpa.magnet_link or outcome:
                                c = TransmissionClient()
                                torrent = c.load_torrent(file_path=self.rpa.magnet_link)
                                if torrent:
                                    self.latest_torrent = torrent
                                    await ctx.send(content=f"Download has begun for **{title}**")
                                    await self.bot.owner.send(
                                        f"User **{ctx.user.display_name}** has started the download for {title}. Please visit [Transmission]({c.host}:{c.port}.)")
                                    logger.info("Transmission sequence complete!")
                                else:
                                    logger.error("Could not download torrent using magnet link.")
                                    await ctx.edit_origin()
                                    await ctx.delete()

                                    await ctx.send(
                                        f'An error occured while attempting to transfer the book **{title}** to the server, please reach out to the server owner for more details.')
                                    return

                            # Check if file is downloaded
                            elif self.rpa.files_downloaded:
                                logger.info("Attempting to transfer torrent to transmission...")
                                dir_items = os.scandir(self.rpa.download_dir)
                                for entry in dir_items:
                                    c = TransmissionClient()
                                    torrent = c.load_torrent(file_path=entry.path)
                                    if torrent:
                                        self.latest_torrent = torrent
                                        # Give the system a moment to upload the file
                                        await asyncio.sleep(0.5)
                                        logger.info("File uploaded to transmission, removing from directory!")
                                        os.remove(entry.path)
                                        # Send owner a message
                                        await ctx.send(content=f"Download has begun for **{title}**")
                                        await self.bot.owner.send(
                                            f"User **{ctx.user.display_name}** has started the download for {title}. Please visit {c.host}:{c.port}.")
                                        logger.info("Transmission sequence complete!")

                                    else:
                                        logger.warning("Removing file to avoid duplicates.")
                                        os.remove(entry.path)
                                        # Attempt to delete original
                                        await ctx.edit_origin()
                                        await ctx.delete()

                                        await ctx.send(f'An error occured while attempting to transfer the book **{title}** to the server, please reach out to the server owner for more details.')
                                        return

                            else:
                                await ctx.send(
                                    content=f"Could not download: **{title}**. Please visit logs for more information.")

            case "cancel_button":
                await ctx.edit_origin()
                await ctx.delete()
                self.book_result = []
