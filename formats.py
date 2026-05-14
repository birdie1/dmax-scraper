#!/usr/bin/env python3
import re
from datetime import datetime, timedelta


class Show:
    """Defines information about a DMAX show"""

    def __init__(self, json):
        """
        Initializes the Show class with information for a show
        :param json: String. Raw JSON
        """

        self.showId = json["attributes"]['showId']
        self.slug = json["slug"]
        self.name = json["title"]

        if "description" in json:
            self.description = json["metaDescription"]

        if "episodeCount" in json:
            self.episodeCount = json["episodeCount"]

        if "seasonNumbers" in json:
            self.seasonNumbers = json["seasonNumbers"]

    def __repr__(self):
        return "DMAX-Show: {0}".format(self.name)


class Episode:
    """Defines information about an episode"""

    def __init__(self, json):
        """
        Initializes the Episode class with information for an episode
        :param json: String. Raw JSON
        """

        self.id = json["id"]
        self.alternateId = json["alternateId"]

        if "airDate" in json:
            self.airDate = datetime.strptime(json["airDate"], '%Y-%m-%dT%H:%M:%SZ')

        if "title" in json:
            self.name = json["title"]

        if "description" in json:
            self.description = json["description"]

        if "episodeNumber" in json:
            self.episodeNumber = json["episodeNumber"]
            self.episode = self.episodeNumber
        else:
            self.episodeNumber = None
            self.episode = None

        if self.episode is None:
            m = re.search('season-(\d*)-episode-(\d*)', self.alternateId)
            if m.group(2):
                self.episodeNumber = int(m.group(2))
                self.episode = self.episodeNumber

        if "seasonNumber" in json:
            self.seasonNumber = json["seasonNumber"]
            self.season = self.seasonNumber
        else:
            self.seasonNumber = None
            self.season = None

        if self.season is None:
            m = re.search('season-(\d*)-episode-(\d*)', self.alternateId)
            if m.group(1):
                self.seasonNumber = int(m.group(1))
                self.season = self.seasonNumber

        if "publishStart" in json:
            self.publishStart = datetime.strptime(json["publishStart"], '%Y-%m-%dT%H:%M:%S%z')

        if "publishEnd" in json:
            self.publishEnd = datetime.strptime(json["publishEnd"], '%Y-%m-%dT%H:%M:%S%z')

        if "videoDuration" in json:
            self.videoDuration = timedelta(milliseconds=json["videoDuration"])

        if "drmEnabled" in json:
            self.drmEnabled = json["drmEnabled"]

        if "isNew" in json:
            self.isNew = json["isNew"]

    def __repr__(self):
        return "Episode {0}: {1}".format(
                self.episodeNumber if hasattr(self, "episodeNumber") else "?",
                self.name
        )


class DMAX:
    """Main class for Show and Episode classes"""

    def __init__(self, json):
        """
        Initializes the DMAX class
        :param json: String. Raw JSON
        """

        # if "data" not in json or "included" not in json:
        #     raise Exception("Invalid JSON.")

        self.show = None
        if json["type"] == "showpage":
            self.show = Show(json)

        if not self.show:
            raise Exception("No show data found.")

        self.episodes = []
        for i in json.get('blocks'):
            if i.get('showId') == self.show.showId and 'items' in i:
                for j in i.get('items'):
                    episode = Episode(j)
                    #print(j)
                    #print(f"S{j['seasonNumber']}E{j['episodeNumber']} - {j['title']}")
                    self.episodes.append(episode)
                    #print(f"S{episode.season}E{episode.episode} - {episode.name}")
