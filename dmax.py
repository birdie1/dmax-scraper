#!/usr/bin/env python3
import argparse
import logging
import os
import sys
import time
import youtube_dl
import xlsxwriter
import shutil
import re
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

API_BASE = "https://eu1-prod.disco-api.com"
SHOW_INFO_URL = API_BASE + "/content/videos//?include=primaryChannel,primaryChannel.images,show,show.images," \
                           "genres,tags,images,contentPackages&sort=-seasonNumber,-episodeNumber" \
                           "&filter[show.alternateId]={0}&filter[videoType]=EPISODE&page[number]={1}&page[size]=100"
API_URL_ALL_SHOWS = API_BASE + "/content/shows?page[number]={0}&page[size]=100"
PLAYER_URL = "https://sonic-eu1-prod.disco-api.com/playback/videoPlaybackInfo/"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:68.0) Gecko/20100101 Firefox/68.0"
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


def get_videos_api_request(showid, token, page):
    try:
        req = get(SHOW_INFO_URL.format(showid, page), headers={"Authorization": "Bearer " + token})
    except Exception as e:
        logger.critical("Connection error: {0}".format(str(e)))
        return False

    if req.status_code != 200:
        logger.error("This show does not exist.")
        return False

    data = req.json()
    if "errors" in data:
        logger.error("This show does not exist.")
        return False

    return data


def get_episodes(showid, token, chosen_season=0, chosen_episode=0):
    episodes = []
    data = get_videos_api_request(showid, token, 1)
    if not data:
        logger.error("Can't fetch data on page 1 on show {}".format(showid))

    if data["meta"]["totalPages"] > 1:
        logger.info("More than 100 videos, need to get more pages")
        for i in range(1, data["meta"]["totalPages"]):
            more_data = get_videos_api_request(showid, token, i+1)
            if not more_data:
                logger.error("Can't fetch data on page {} on show {}".format(i+1, showid))
            else:
                data["data"].extend(more_data["data"])

    if len(data["data"]) == 0:
        logger.warning("No episodes found in {}".format(showid))
        return episodes
    show = formats.DMAX(data)

    if chosen_season == 0 and chosen_episode == 0:  # Get EVERYTHING
        episodes = show.episodes
    elif chosen_season > 0 and chosen_episode == 0:  # Get whole season
        for episode in show.episodes:
            if episode.seasonNumber == chosen_season:
                episodes.append(episode)
        if not episodes:
            logger.error("This season does not exist.")
            return
    else:  # Get single episode
        for episode in show.episodes:
            if episode.seasonNumber == chosen_season and episode.episodeNumber == chosen_episode:
                episodes.append(episode)
        if not episodes:
            logger.error("Episode not found.")
            return

    if not episodes:
        logger.info("No Episodes to download.")
        return

    return_dict = []
    logger.info("Found {} episodes, getting video links...".format(len(episodes)))

    for num, episode in enumerate(episodes):
        if episode.season == "" and episode.episode == "":
            filename = "{show_name} - {episode_name}".format(
                show_name=show.show.name,
                episode_name=episode.name.strip()
            )
        elif episode.season == "" and episode.episode != "":
            filename = "{show_name} - S{season}E{episode} - {episode_name}".format(
                show_name=show.show.name,
                season="{:02d}".format(episode.season),
                episode="{:02d}".format(episode.episode),
                episode_name=episode.name.strip()
            )
        else:
            filename = "{show_name} - S{season}E{episode} - {episode_name}".format(
                show_name=show.show.name,
                season="{:02d}".format(episode.season),
                episode="{:02d}".format(episode.episode),
                episode_name=episode.name.strip()
            )

        filename = filename.replace("/", "-")

        return_dict.append({'name': episode.name, 'id': episode.id, 'description': episode.description, 'filename': filename,
                            'dir': "{}/{} Staffel {}".format(
                                show.show.name.replace("/", "-"),
                                show.show.name.replace("/", "-"), "{:02d}".format(episode.season)
                            )})
    return return_dict


def get_episode_video_link(episode_id, filename):
    try:
        req = get(PLAYER_URL + episode_id, headers={
            "Authorization": "Bearer " + token,
            "User-Agent": USER_AGENT
        })
    except Exception as exception:
        logger.error("Connection for video id {0} ({1}) failed: {2}".format(episode_id, filename, str(exception)))
        return False

    if req.status_code == 429:
        logger.error("HTTP error code {0} for video id {1} ({2}): This means RATE LIMITER, you are getting to many Items per second.".format(req.status_code, episode_id, filename))
        logger.error("Exiting")
        #time.sleep(60)
        sys.exit(1)
    elif req.status_code != 200:
        logger.error("HTTP error code {0} for video id {1} ({2})".format(req.status_code, episode_id, filename))
        return False

    data = req.json()
    return data["data"]["attributes"]["streaming"]["hls"]["url"]


def get_token():
    logger.info("Getting Authorization token...")
    try:
        token = get(API_BASE + "/token?realm=dmaxde").json()["data"]["attributes"]["token"]
    except Exception as e:
        logger.critical("Connection error: {0}".format(str(e)))
        return False
    return token


def request_dmax_api_all_shows(token):
    count = 0
    return_list = []

    while True:
        count += 1
        response = get(API_URL_ALL_SHOWS.format(count), headers={"Authorization": "Bearer " + token})
        data = response.json()
        if len(data["data"]) == 0:
            break
        for i in data["data"]:
            return_list.append(i["attributes"]["alternateId"])

    logger.info("Found {} shows on {} pages with 100 entries".format(len(return_list), count-1))
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
    xlsx = arguments.xls
    out_links = arguments.links
    out_commands = arguments.commands
    downloaded_count = 0

    token = get_token()
    if not token:
        sys.exit(1)

    if showid is None:
        alternate_id_list = request_dmax_api_all_shows(token)
        logger.info("Found following shows (Count: {}): {}".format(len(alternate_id_list), alternate_id_list))
    else:
        if chosen_episode < 0 or chosen_season < 0:
            print("ERROR: Episode/Season must be > 0.")

        if chosen_episode > 0 and chosen_season == 0:
            print("ERROR: Season must be set.")

        alternate_id_list = [showid]

    for show in alternate_id_list:
        logger.info("Processing Show: {}".format(show))
        episodes = get_episodes(show, token, chosen_season=chosen_season, chosen_episode=chosen_episode)

        if episodes is None:
            logger.warning("No Episodes in {}".format(show))
            continue

        if xlsx:
            write_to_xls(show, episodes)
        elif out_links:
            logger.warning(
                "Due to rate limiting request from dmax, I will wait 5 seconds between each request, this can take some time!")
            for episode in episodes:
                print(get_episode_video_link(episode['id'], episode.get("filename")))
                # Sleep to prevent dmax api rate limiter
                time.sleep(5)
        elif out_commands:
            logger.warning(
                "Due to rate limiting request from dmax, I will wait 5 seconds between each request, this can take some time!")
            for episode in episodes:
                print(f"youtube-dl \"{get_episode_video_link(episode['id'], episode.get('filename'))}\" -o \"{episode['filename']}.mp4\"")
                # Sleep to prevent dmax api rate limiter
                time.sleep(5)
        else:
            if not os.path.isfile(ALREADY_DOWNLOADED_FILE):
                open(ALREADY_DOWNLOADED_FILE, 'a').close()

            for j in episodes:
                if downloaded_count == MAX_DOWNLOAD:
                    logger.info("Max download count reached. Stopping")
                    sys.exit(0)

                rename = False
                if not already_downloaded(j.get("filename")):
                    ydl_opts = {'quiet': True, 'outtmpl': "downloads/{}/{}".format(j.get("dir"), j.get("filename").replace("%", "PERCENT"))}
                    rename = True
                    link = get_episode_video_link(j['id'], j.get("filename"))
                    if not link:
                        continue
                    logger.info("Downloading file: {}".format(j.get("filename")))
                    with youtube_dl.YoutubeDL(ydl_opts) as ydl:
                        ydl.download([])

                    if rename:
                        shutil.move("downloads/{}/{}.mp4".format(j.get("dir"), j.get("filename").replace("%", "PERCENT")),
                                    "downloads/{}/{}.mp4".format(j.get("dir"), j.get("filename")))

                    if os.path.isfile("downloads/{}/{}.mp4".format(j.get("dir"), j.get("filename"))):
                        logger.info("Downloading file finished: {}".format(j.get("filename")))
                        set_downloaded(j.get("filename"))
                    else:
                        logger.warning("Downloading file failed: {}".format(j.get("filename")))

                downloaded_count += 1
