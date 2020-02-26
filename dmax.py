#!/usr/bin/env python3
import argparse
import logging
import os
import sys
import youtube_dl
import xlsxwriter
import shutil
from requests import get

import formats

logging.getLogger('requests.packages.urllib3.connectionpool').setLevel('WARNING')
logging.basicConfig(level=logging.INFO,
                    format='[%(levelname)-7s] (%(asctime)s) %(filename)s::%(lineno)d %(message)s',
                    datefmt='%Y-%m-%d %H:%M:%S',
                    filename='main.log')
logger = logging.getLogger("DMAX")

handler = logging.StreamHandler(sys.stdout)
handler.setLevel(logging.INFO)
formatter = logging.Formatter('[%(levelname)-7s] (%(asctime)s) %(filename)s::%(lineno)d %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)


BASE_URL = "https://www.dmax.de/"
API_URL = BASE_URL + "api/show-detail/{0}"
API_URL_ALL_SHOWS = BASE_URL + "api/shows-az/"
PLAYER_URL = "https://sonic-eu1-prod.disco-api.com/playback/videoPlaybackInfo/"
USER_AGENT = "Mozilla/5.0 (Windows NT 6.1; Win64; x64; rv:66.0) Gecko/20100101 Firefox/66.0"
MAX_DOWNLOAD = 500
ALREADY_DOWNLOADED_FILE = "downloaded.txt"


class WorkbookWriter:
    """Wrapper around xlswriter."""

    def __init__(self, filename):
        """
        Initializes the WorkookWriter class
        :param filename: Name of XLS file
        """
        self.workbook = xlsxwriter.Workbook(filename)
        self.worksheet = self.workbook.add_worksheet()
        self.bold = self.workbook.add_format({'bold': True})
        self.row = 0
        self._col = 0
        self.write_header()

    def col(self, start=False):
        """Returns the current column and moves to the next.
           If start is True, it will move back to 0.
        """
        curcol = self._col
        if start:
            self._col = 0
        else:
            self._col += 1
        return curcol

    def write_header(self):
        self.worksheet.write(self.row, self.col(), "Name", self.bold)
        self.worksheet.write(self.row, self.col(), "Description", self.bold)
        self.worksheet.write(self.row, self.col(), "File name", self.bold)
        self.worksheet.write(self.row, self.col(), "Link", self.bold)
        self.worksheet.write(self.row, self.col(start=True), "Command", self.bold)
        self.row += 1

    def __del__(self):
        self.workbook.close()

def get_episodes(showid, chosen_season=0, chosen_episode=0, includespecials=True):
    try:
        req = get(API_URL.format(showid))
    except Exception as e:
        logger.critical("Connection error: {0}".format(str(e)))
        return

    if req.status_code != 200:
        logger.error("This show does not exist.")
        return

    data = req.json()
    if "errors" in data:
        logger.error("This show does not exist.")
        return

    cookies = req.cookies.get_dict()
    if "sonicToken" not in cookies:
        logger.error("No sonicToken found, can not proceed")
        return
    token = cookies["sonicToken"]
    show = formats.DMAX(data)

    episodes = []
    if includespecials:
        for special in show.specials:
            episodes.append(special)

    if chosen_season == 0 and chosen_episode == 0:  # Get EVERYTHING
        for season in show.seasons:
            for episode in season.episodes:
                episodes.append(episode)
    elif chosen_season > 0 and chosen_episode == 0:  # Get whole season
        for season in show.seasons:
            if season.number == chosen_season:
                for episode in season.episodes:
                    episodes.append(episode)
        if not episodes:
            logger.error("This season does not exist.")
            return
    else:  # Get single episode
        for season in show.seasons:
            if season.number == chosen_season:
                for episode in season.episodes:
                    if episode.episodeNumber == chosen_episode:
                        episodes.append(episode)
        if not episodes:
            logger.error("Episode not found.")
            return

    if not episodes:
        logger.info("No Episodes to download.")
        return

    return_dict = []
    logger.info("Get {} links".format(len(episodes)))

    for num, episode in enumerate(episodes):
        if episode.season == "" and episode.episode == "":
            filename = "{show_name} - {episode_name}".format(
                show_name=show.show.name,
                episode_name=episode.name
            )
        elif episode.season == "" and episode.episode != "":
            filename = "{show_name} - S{season}E{episode} - {episode_name}".format(
                show_name=show.show.name,
                season=episode.season,
                episode=episode.episode,
                episode_name=episode.name
            )
        else:
            filename = "{show_name} - S{season}E{episode} - {episode_name}".format(
                show_name=show.show.name,
                season=episode.season,
                episode=episode.episode,
                episode_name=episode.name
            )

        try:
            req = get(PLAYER_URL + episode.id, headers={
                "Authorization": "Bearer " + token,
                "User-Agent": USER_AGENT
            })
        except Exception as exception:
            logger.error("Connection for video id {0} failed: {1}".format(episode.id, str(exception)))
            continue

        if req.status_code != 200:
            logger.error("HTTP error code {0} for video id {1]".format(req.status_code, episode.id))
            continue

        data = req.json()
        video_link = data["data"]["attributes"]["streaming"]["hls"]["url"]
        filename = filename.replace("/", "-")

        return_dict.append({'name': episode.name, 'description': episode.description, 'filename': filename, 'video_link': video_link, 'dir': "{}/{} Staffel {}".format(show.show.name.replace("/", "-"), show.show.name.replace("/", "-"), episode.season)})
    return return_dict


def request_dmax_api_all_shows():
    response = get(API_URL_ALL_SHOWS)
    return response.json()


def extract_alternate_id(data):
    return_list = []
    for i in data["items"]:
        ##this is sort by A, B, C...
        for j in i["items"]:
            return_list.append(j["url"][11:])
    return return_list


def already_downloaded(episode_filename):
    found = False
    with open(ALREADY_DOWNLOADED_FILE, "r") as f:
        line = f.readline()
        while line:
            if episode_filename == line.strip():
                found = True
                break
            line = f.readline()
    return found


def set_downloaded(episode_filename):
    with open(ALREADY_DOWNLOADED_FILE, "a") as f:
        f.write("{}\n".format(episode_filename))


def write_to_xls(show, episodes):
    xlsname = "{}.xlsx".format(show)
    file_num = 0
    while os.path.isfile(xlsname):
        file_num += 1
        xlsname = "{0}-{1}.xlsx".format(showid, file_num)
    xls = WorkbookWriter(xlsname)

    for episode in episodes:
        xls.worksheet.write(xls.row, xls.col(), episode['name'])
        xls.worksheet.write(xls.row, xls.col(), episode['description'])
        xls.worksheet.write(xls.row, xls.col(), episode['filename'])

        xls.worksheet.write(xls.row, xls.col(), episode['video_link'])
        xls.worksheet.write(xls.row, xls.col(start=True),
                            "youtube-dl \"{0}\" -o \"{1}.mp4\"".format(episode['video_link'], episode['filename'])
                            )

        xls.row += 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Gets direct links for DMAX series and download them or save to xlsx file")
    parser.add_argument(
        "-i",
        metavar="Show ID",
        dest="id",
        type=str,
        help="alternateId of the series (last part of URL), e.g. american-chopper"
    )
    parser.add_argument(
        "-s",
        metavar="Season",
        type=int,
        default=0,
        dest="season",
        help="Season to get (default: 0 = all)"
    )
    parser.add_argument(
        "-e",
        metavar="Episode",
        type=int,
        default=0,
        dest="episode",
        help="Episode of season to get (default: 0 = all) - season MUST be set!"
    )
    parser.add_argument(
        '--specials',
        action='store_true',
        default=False,
        dest='includespecials',
        help='Download specials'
    )
    parser.add_argument(
        '--xls',
        action='store_true',
        default=False,
        dest='xls',
        help='Instead of downloading files, save links into xslx file'
    )
    parser.add_argument(
        '--links',
        action='store_true',
        default=False,
        dest='links',
        help='Output links directly'
    )
    parser.add_argument(
        '--commands',
        action='store_true',
        default=False,
        dest='commands',
        help='Output youtube download commands directly'
    )
    arguments = parser.parse_args()

    showid = arguments.id,
    showid = showid[0]
    chosen_season = arguments.season,
    chosen_season = chosen_season[0]
    chosen_episode = arguments.episode,
    chosen_episode = chosen_episode[0]
    includespecials = arguments.includespecials
    xlsx = arguments.xls
    out_links = arguments.links
    out_commands = arguments.commands
    downloaded_count = 0

    if showid is None:
        json_data = request_dmax_api_all_shows()
        alternate_id_list = extract_alternate_id(json_data)
        logger.info("Found following shows: {}".format(alternate_id_list))
    else:
        if chosen_episode < 0 or chosen_season < 0:
            print("ERROR: Episode/Season must be > 0.")

        if chosen_episode > 0 and chosen_season == 0:
            print("ERROR: Season must be set.")

        alternate_id_list = [showid]


    for show in alternate_id_list:
        logger.info("Processing Show: {}".format(show))
        episodes = get_episodes(show, chosen_season=chosen_season, chosen_episode=chosen_episode, includespecials=includespecials)

        if episodes is None:
            logger.warning("No Episodes in {}".format(show))
            continue

        if xlsx:
            write_to_xls(show, episodes)
        elif out_links:
            for episode in episodes:
                print(episode['video_link'])
        elif out_commands:
            for episode in episodes:
                print("youtube-dl \"{0}\" -o \"{1}.mp4\"".format(episode['video_link'], episode['filename']))
        else:
            if not os.path.isfile(ALREADY_DOWNLOADED_FILE):
                open(ALREADY_DOWNLOADED_FILE, 'a').close()

            for j in episodes:
                if downloaded_count == MAX_DOWNLOAD:
                    logger.info("Max download count reached. Stopping")
                    sys.exit(0)

                rename = False
                if not already_downloaded(j.get("filename")):
                    logger.info("Downloading file: {}".format(j.get("filename")))
                    ydl_opts = {'quiet': True, 'outtmpl': "downloads/{}/{}".format(j.get("dir"), j.get("filename").replace("%", "PERCENT"))}
                    rename = True
                    with youtube_dl.YoutubeDL(ydl_opts) as ydl:
                        ydl.download([j.get("video_link")])

                    if rename:
                        shutil.move("downloads/{}/{}.mp4".format(j.get("dir"), j.get("filename").replace("%", "PERCENT")),
                                    "downloads/{}/{}.mp4".format(j.get("dir"), j.get("filename")))

                    if os.path.isfile("downloads/{}/{}.mp4".format(j.get("dir"), j.get("filename"))):
                        logger.info("Downloading file finished: {}".format(j.get("filename")))
                        set_downloaded(j.get("filename"))
                    else:
                        logger.warning("Downloading file failed: {}".format(j.get("filename")))

                downloaded_count += 1
