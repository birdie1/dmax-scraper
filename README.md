dmax-scraper
==============

Based on https://github.com/Brawl345/Get-DMAX-Links. But with direct donwload function.

This handy python script gets links of a DMAX show. You can also specify a season with `-s` and an episode with `-e`.

There are 4 options:
- It will download automatic found files and saves filenames into files for tracking already downloaded files. \[DEFAULT\]
- The resulting information will be saved in an Excel file: `--xls`
- Print links directly: `--links`
- Print youtube-dl commands directly: `--commands`

## Usage
The Script is written in Python 3.

1. Clone repo
2. `pip install -U -r requirements.txt`
3. `python dmax.py [-i NAME-OF-SHOW] [-s SEASON] [-e EPISODE] [--specials] [--xlsx] [--links] [--commands]`
4. Check help with `python dmax.py -h`

## How it works
1. Contacts DMAX API and gets video ids plus sonicToken from cookie
2. Sends sonicToken and video id(s) to the player API which returns the link(s)
3. Download files and saves filename into `downloaded.txt`