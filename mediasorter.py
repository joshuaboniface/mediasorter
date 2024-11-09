#!/usr/bin/env python3

# mediasorter.py - Sort a media file into an organized library
#
#    Copyright (C) 2020  Joshua M. Boniface <joshua@boniface.me>
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation, either version 3 of the License, or
#    (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with this program.  If not, see <https://www.gnu.org/licenses/>.
#
###############################################################################

import os
import pwd
import grp
import re
import requests
import json
import subprocess
import click
import yaml
from pathlib import Path
from datetime import datetime

def logger(config, msg, nl=True, stderr=True):
    click.echo(msg, nl=nl, err=stderr)

    log_to_file = config.get('log_to_file', False)
    logfile  = config.get('logfile', False)

    if log_to_file and logfile:
        with open(logfile, 'a') as logfhd:
            logfhd.write(str(datetime.now()) + ' ' + str(msg) + '\n')

# TV file/directory sorting
def sort_tv_file(config, srcpath, dstpath):
    """
    TV handling
    """

    # Get basename from the path
    basename = os.path.basename(srcpath)
    # Discard the extension to get the filename
    filename = os.path.splitext(basename)[0]
    fileext = os.path.splitext(basename)[-1]

    if not fileext in config['valid_extensions']:
        return False, False

    # Try splitting the filename
    for split_character in config['split_characters']:
        split_filename = filename.split(split_character)
        if len(split_filename) >= config['min_split_length']:
            break
    if len(split_filename) < config['min_split_length']:
        logger(config, "Error: Filename '{}' could not be split into sufficient parts to be parsed.".format(filename))
        return False, False

    # Get the series title and SXXEYY identifier, then end; we get the rest from TVDB
    end_idx = len(split_filename)
    sxxeyy_idx = 0
    season_id = 0
    episode_id = 0
    next_match_flag_episode = False
    for idx, element in enumerate(split_filename):
        if re.search('[Ss][0-9]+[Ee][0-9]+', element):
            sxxeyy_idx = idx
            seid = re.findall('[Ss]([0-9]+)[Ee]([0-9]+)', element)[0]
            season_id = int(seid[0])
            episode_id = int(seid[1])
            break
        if re.search('[Ss][0-9]+', element):
            if sxxeyy_idx < 1:
                sxxeyy_idx = idx
            seid = re.findall('[Ss]([0-9]+)', element)[0]
            season_id = int(seid[0])
        if re.search('[Ee][0-9]+', element):
            if sxxeyy_idx < 1:
                sxxeyy_idx = idx
            seid = re.findall('[Ee]([0-9]+)', element)[0]
            episode_id = int(seid[0])
        if re.search('[Ee]pisode', element):
            if sxxeyy_idx < 1:
                sxxeyy_idx = idx
                if not re.findall(r'[0-9]+', element)[0]:
                    next_match_flag_episode = True
                    continue
                else:
                    seid = re.findall('([0-9]+)', element)[0]
                    episode_id = int(seid[0])
        if next_match_flag_episode:
            seid = re.findall('([0-9]+)', element)[0]
            episode_id = int(seid[0])
        if episode_id > 0:
            if season_id == 0:
                season_id = 1
            break

    # Series title: start to sxxeyy_idx
    raw_series_title_unfixed = split_filename[0:sxxeyy_idx]
    if not raw_series_title_unfixed:
        # Handle cases where the filename is like DexterS01E03 or similar stupid naming
        raw_series_title_unfixed = split_filename[0:sxxeyy_idx+1]
    raw_series_title = list()
    for word in raw_series_title_unfixed:
        # Remove SXXEYY from the word
        if re.search(r'[Ss][0-9]+[Ee][0-9]+', word):
            word = re.sub(r'[Ss][0-9]+[Ee][0-9]+', '', word)
        # Only remove years that are in parentheses
        if re.search(r'^\(([0-9]{4})\)$', word):
            continue
        raw_series_title.append(word)
    search_series_title = ' '.join([x.lower() for x in raw_series_title])
    if search_series_title in config['search_overrides']:
        search_series_title = config['search_overrides'][search_series_title]
    logger(config, "Raw file info:    series='{}' S={} E={}".format(search_series_title, season_id, episode_id))

    # Log in to TVDB
    tvdb_login_url = "{}/login".format(config['tvdb_api_base'])
    try:
        data = {"apikey": config['tvdb_api_key'], "pin": ""}
        response = requests.post(
            tvdb_login_url,
            data=json.dumps(data),
            headers={"Content-Type": "application/json"}
        )
        tvdb_token = response.json()['data']['token']
    except Exception:
        logger(config, "Failed to log in to TVDB")
        return False, False

    tvdb_headers = {"Authorization": "Bearer {}".format(tvdb_token)}

    # Fetch series information from TVDB
    show_path = config['tvdb_api_search_path'].format(show=requests.utils.quote(search_series_title))
    show_url = '{}/{}'.format(config['tvdb_api_base'], show_path)
    logger(config, "TVDB API Search URL:   {}".format(show_url))
    try:
        response = requests.get(show_url, headers=tvdb_headers)
        show_data = response.json()
        if show_data["status"] != "success":
            raise ValueError
    except Exception:
        logger(config, "Failed to find results for {}".format(show_url))
        return False, False

    found_episode = None
    for series in show_data['data']:
        series_id = series['tvdb_id']

        # Get episodes list from TVDB
        series_path = config['tvdb_api_series_path'].format(id=series_id, season=season_id, episode=episode_id)
        series_url = '{}/{}'.format(config['tvdb_api_base'], series_path)
        logger(config, "TVDB API Series URL:   {}".format(series_url))
        try:
            response = requests.get(series_url, headers=tvdb_headers)
            series_data = response.json()
            if series_data["status"] != "success" or not series_data["data"]["episodes"]:
                continue
            found_episode = series_data
            break
        except Exception:
            continue

    if found_episode is None:
        logger(config, "Failed to find results for {}".format(show_url))
        return False, False
    
    # Get the series title
    series_title = found_episode["data"]["series"]['name']
    for title in config['tv_name_overrides']:
        if title == series_title:
            series_title = config['tv_name_overrides'][title]
            break

    # Get the episode details
    episode_title = found_episode["data"]["episodes"][0].get('name')
    # Sometimes, we get a slash; only invalid char on *NIX so replace it
    episode_title = episode_title.replace('/', '-')
    # Remove double-quotes because they can cause a lot of headaches
    episode_title = episode_title.replace('"', '')

    if config['suffix_the']:
        # Fix leading The's in the series title
        if re.match('[Tt]he\s(.*)', series_title):
            series_title = re.match('[Tt]he\s(.*)', series_title).group(1) + ', The'

    # Build the final path+filename
    dst_path = '{dst}/{series}/Season {sid}'.format(
        dst=dstpath,
        series=series_title.replace('/', '-'),
        sid=season_id,
    )
    dst_name = '{series} - S{sid:02d}E{eid:02d} - {title}'.format(
        series=series_title.replace('/', '-'),
        sid=season_id,
        eid=episode_id,
        title=episode_title,
    )
    dst_file = '{dst_name}{ext}'.format(
        dst_name=dst_name,
        ext=fileext
    )

    logger(config, "Sorted full filepath:  {}/{}".format(dst_path, dst_file))
    logger(config, "Sorted full filepath:  {}/{}".format(dst_path, dst_file), stderr=False)
    logger(config, "Sorted media:  {}".format(dst_name))
    logger(config, "Sorted media:  {}".format(dst_name), stderr=False)

    return dst_path, dst_file

def sort_movie_file(config, srcpath, dstpath, metainfo_tag):
    """
    Movie handling
    """

    # Get basename from the path
    basename = os.path.basename(srcpath)
    # Discard the extension to get the filename
    filename = os.path.splitext(basename)[0]
    fileext = os.path.splitext(basename)[-1]

    if not fileext in config['valid_extensions']:
        return False, False

    # Try splitting the filename
    for split_character in config['split_characters']:
        split_filename = filename.split(split_character)
        if len(split_filename) >= config['min_split_length']:
            break
    if len(split_filename) < config['min_split_length']:
        logger(config, "Error: Filename '{}' could not be split into sufficient parts to be parsed.".format(filename))
        return False, False

    # Get the year identifier, then end; we get the rest from TVDB
    year_idx = len(split_filename)
    search_movie_year = "0000"
    for idx, element in enumerate(split_filename):
        # A year is an element exactly matching 4 numerals optionally wrapped in parens
        match = re.match('^\(?([0-9]{4})\)?$', element)
        if match:
            year_idx = idx
            search_movie_year = match.group(1)
            # Don't break here, since we always want the last year (e.g. in "2001 A Space Odyssey")

    # Series title: start to year_idx
    raw_movie_title = split_filename[0:year_idx]
    search_movie_title = '+'.join([x.lower() for x in raw_movie_title])
    # Remove the first "The" from the title when searching to avoid weird conflicts
    search_movie_title = re.sub('[Tt]he\+', '', search_movie_title, 1)
    # Apply overrides
    if search_movie_title in config['search_overrides']:
        search_movie_title = config['search_overrides'][search_movie_title]
    logger(config, "Raw file info:    movie='{}' year={}".format(search_movie_title, search_movie_year))

    # Fetch movie information from TMDB
    movie_path = config['tmdb_api_path'].format(key=config['tmdb_api_key'], title=requests.utils.quote(search_movie_title))
    movie_url = '{}/{}'.format(config['tmdb_api_base'], movie_path)
    logger(config, "TMDB API URL:     {}".format(movie_url))
    try:
        response = requests.get(movie_url)
        movie_data = response.json()
    except Exception:
        logger(config, "Failed to find results for {}".format(show_url))
        return False, False
    
    # List all movies and find the one matching the year (within on year either side)
    movie_list = movie_data.get('results')
    movie_title = 'unnamed'
    movie_year = '0000'
    if len(movie_list) == 1:
        # If there's exactly one result, then we just use that
        movie_title = movie_list[0].get('title')
        movie_year = movie_list[0].get('release_date', '0000-00-00').split('-')[0]
    else:
        # Otherwise, loop through the results and select the movie with the closest year
        for movie in movie_list:
            release_year = movie.get('release_date', '0000-00-00').split('-')[0]
            if not release_year:
                release_year = '0000'
            if not search_movie_year:
                search_movie_year = '0000'
    
            if search_movie_year == '0000' or release_year == search_movie_year:
                movie_title = movie.get('title')
                movie_year = release_year
                break
            elif int(release_year) == int(search_movie_year) + 1 or int(release_year) == int(search_movie_year) - 1:
                movie_title = movie.get('title')
                movie_year = release_year
                # Candidate, but don't break

    if movie_title == 'unnamed':
        logger(config, "Error: No movie was found in the database for filename '{}'.".format(filename))
        return False, False

    for title in config['movie_name_overrides']:
        if title == movie_title:
            movie_title = config['movie_name_overrides'][title]
            break

    if config['suffix_the']:
        # Fix leading The's in the movie title
        if re.match('[Tt]he\s(.*)', movie_title):
            movie_title = re.match('[Tt]he\s(.*)', movie_title).group(1) + ', The'

    # Build the final path+filename
    dst_path = '{dst}/{movie} ({year})'.format(
        dst=dstpath,
        movie=movie_title,
        year=movie_year
    )
    if metainfo_tag:
        # Pull metainfo from filename if it is in the map
        metainfo = list()
        for item in config['metainfo_map']:
            for idx, element in enumerate(split_filename):
                key, value = list(item.items())[0]
                if re.fullmatch(key, element) and value not in metainfo:
                    metainfo.append(value)

        dst_name = '{movie} ({year}) - [{metainfo}]'.format(
            dst=dstpath,
            movie=movie_title,
            year=movie_year,
            metainfo=' '.join(metainfo)
        )
    else:
        dst_name = '{movie} ({year})'.format(
            dst=dstpath,
            movie=movie_title,
            year=movie_year
        )
    dst_file = '{dst_name}{ext}'.format(
        dst_name=dst_name,
        ext=fileext
    )

    logger(config, "Sorted full filepath:  {}/{}".format(dst_path, dst_file))
    logger(config, "Sorted full filepath:  {}/{}".format(dst_path, dst_file), stderr=False)
    logger(config, "Sorted media:  {}".format(dst_name))
    logger(config, "Sorted media:  {}".format(dst_name), stderr=False)

    return dst_path, dst_file

# File sorting main function
def sort_file(config, srcpath, dstpath, mediatype, action, infofile, shasum, chown, user, group, file_mode, directory_mode, metainfo_tag, upgrade, dryrun):
    # Get UID and GID for chowning
    uid = pwd.getpwnam(user)[2]
    gid = grp.getgrnam(group)[2]

    logger(config, ">>> Parsing {}".format(srcpath))
    # Determine if srcpath is a directory, then act recursively
    if os.path.isdir(srcpath):
        for filename in sorted(os.listdir(srcpath)):
            child_filename = '{}/{}'.format(srcpath, filename)
            returncode = sort_file(config, child_filename, dstpath, mediatype, action, infofile, shasum, chown, user, group, file_mode, directory_mode, metainfo_tag, upgrade, dryrun)
            if returncode > 0:
                logger(config, "Failed to sort file {}".format(srcpath))
        return 0

    logger(config, "Sorting action:   {}".format(action))

    # Get our destination path and filename (media-specific)
    if mediatype == 'tv':
        file_dst_path, file_dst_filename = sort_tv_file(config, srcpath, dstpath)
    if mediatype == 'movie':
        file_dst_path, file_dst_filename = sort_movie_file(config, srcpath, dstpath, metainfo_tag)

    if not file_dst_filename:
        return 1

    # Ensure our dst_path exists or create it
    if not os.path.isdir(file_dst_path) and not dryrun:
        logger(config, "Creating target directory '{}'".format(file_dst_path))
        os.makedirs(file_dst_path)
        if chown:
            os.chown(file_dst_path, uid, gid)
            os.chmod(file_dst_path, int(directory_mode, 8))

    file_dst = '{}/{}'.format(file_dst_path, file_dst_filename)

    if dryrun:
        # Make the output quoted
        srcpath = '"{}"'.format(srcpath)
        file_dst = '"{}"'.format(file_dst)

    # Perform our action
    if action == 'symlink':
        action_cmd = ['ln', '-s', '{}'.format(srcpath), '{}'.format(file_dst)]
    if action == 'hardlink':
        action_cmd = ['ln', '{}'.format(srcpath), '{}'.format(file_dst)]
    if action == 'copy':
        action_cmd = ['cp', '{}'.format(srcpath), '{}'.format(file_dst)]
    if action == 'move':
        action_cmd = ['mv', '{}'.format(srcpath), '{}'.format(file_dst)]
 
    if dryrun:
        logger(config, "Sort command: {}".format(' '.join(action_cmd)))
        return 0

    # Handle upgrading by removing existing dest file
    dst_path = Path(file_dst)
    if dst_path.exists():
        if upgrade:
            logger(config, "Removing existing destination file for upgrade... ", nl=False)
            os.remove(file_dst)
            logger(config, "done.")
        else:
            logger(config, "Destination file exists; skipping.")
            return 1

    # Run the action
    logger(config, "Running sort action... ", nl=False)
    process = subprocess.run(action_cmd)
    retcode = process.returncode
    logger(config, "done.")

    if retcode != 0:
        return retcode

    # Create info file
    if infofile:
        logger(config, "Creating info file... ", nl=False)
        infofile_name = '{}.txt'.format(file_dst)
        infofile_contents = [
            "Source filename:  {}".format(os.path.basename(srcpath)),
            "Source directory: {}".format(os.path.dirname(srcpath))
        ]
        with open(infofile_name, 'w') as fh:
            fh.write('\n'.join(infofile_contents))
            fh.write('\n')
        logger(config, "done.")

    # Create sha256sum file
    if shasum:
        logger(config, "Generating shasum file... ", nl=False)
        shasum_name = '{}.sha256sum'.format(file_dst)
        shasum_cmdout = subprocess.run(['sha256sum', '-b', '{}'.format(file_dst)], capture_output=True, encoding='utf8')
        shasum_data = shasum_cmdout.stdout
        if shasum_data:
            shasum_data = shasum_data.strip()
        with open(shasum_name, 'w') as fh:
            fh.write(shasum_data)
            fh.write('\n')
        logger(config, "done.")

    if chown:
        logger(config, "Correcting ownership and permissions... ", nl=False)
        os.chown(file_dst, uid, gid)
        os.chmod(file_dst, int(file_mode, 8))
        if infofile:
            os.chown(infofile_name, uid, gid)
            os.chmod(infofile_name, int(file_mode, 8))
        if shasum:
            os.chown(shasum_name, uid, gid)
            os.chmod(shasum_name, int(file_mode, 8))
        logger(config, "done.")

    return retcode

###############################################################################
# CLICK
###############################################################################

# Global Click options
CONTEXT_SETTINGS = dict(help_option_names=['-h', '--help'], max_content_width=120)

@click.command(context_settings=CONTEXT_SETTINGS)
@click.option(
    '-d', '--destination', 'dstpath',
    type=click.Path(),
    default='~/Media', show_default=True,
    help='The target directory to sort to.'
)
@click.option(
    '-t', '--type', 'mediatype',
    type=click.Choice(['tv', 'movie']),
    required=True,
    help='The type of media to aid the sorter.'
)
@click.option(
    '-a', '--action', 'action',
    type=click.Choice(['symlink', 'hardlink', 'copy', 'move']),
    default='symlink', show_default=True,
    help='How to get the media to the destination.'
)
@click.option(
    '-i/-I', '--infofile/--no-infofile', 'infofile',
    is_flag=True, default=False, show_default=True,
    help="Create information file at target."
)
@click.option(
    '-s/-S', '--shasum/--no-shasum', 'shasum',
    is_flag=True, default=False, show_default=True,
    help="Create SHA256sum file at target."
)
@click.option(
    '-o/-O', '--chown/--no-chown', 'chown',
    is_flag=True, default=False, show_default=True,
    help="Change ownership and permissions of destfile to match user/group and mode."
)
@click.option(
    '-u', '--user', 'user',
    default='root', show_default=True,
    help='The user that should own the sorted files if --chown.'
)
@click.option(
    '-g', '--group', 'group',
    default='media', show_default=True,
    help='The group that should own the sorted files if --chown.'
)
@click.option(
    '-mf', '--file-mode', 'file_mode',
    default='0o644', show_default=True,
    help='The Python-octal-format permissions for the target files if --chown.'
)
@click.option(
    '-md', '--directory-mode', 'directory_mode',
    default='0o755', show_default=True,
    help='The Python-octal-format permissions for the created file parent directory if --chown.'
)
@click.option(
    '-tm', '--tag-metainfo', 'metainfo_tag',
    is_flag=True, default=False, show_default=True,
    help="Add metainfo tagging to target filenames (see README)."
)
@click.option(
    '-p/-P', '--upgrade/--no-upgrade', 'upgrade',
    is_flag=True, default=True, show_default=True,
    help='Upgrade (replace) files at the destination.'
)
@click.option(
    '-x', '--dryrun', 'dryrun',
    is_flag=True, default=False,
    help="Don't perform actual sorting."
)
@click.option(
	'-c', '--config', 'config_file',
	envvar='MEDIASORTER_CONFIG',
    type=click.Path(),
	default='/etc/mediasorter/mediasorter.yml', show_default=False,
	help="Override default configuration file path."
)
@click.argument(
    'srcpath'
)
def cli_root(srcpath, dstpath, mediatype, action, infofile, shasum, chown, user, group, file_mode, directory_mode, metainfo_tag, upgrade, dryrun, config_file):
    """
    Sort the file or directory SRCPATH.
    """

    config = {}
    # Parse the configuration file
    with open(config_file, 'r') as cfgfile:
        try:
            o_config = yaml.load(cfgfile, Loader=yaml.SafeLoader)
        except Exception as e:
            logger(config, 'ERROR: Failed to parse configuration file: {}'.format(e))
            exit(1)
    
    try:
        config = {
            'tvdb_api_base':    o_config['mediasorter']['api']['tvdb']['url'],
            'tvdb_api_search_path':    o_config['mediasorter']['api']['tvdb']['search_path'],
            'tvdb_api_series_path':    o_config['mediasorter']['api']['tvdb']['series_path'],
            'tvdb_api_key':     o_config['mediasorter']['api']['tvdb']['key'],
            'tmdb_api_base':    o_config['mediasorter']['api']['tmdb']['url'],
            'tmdb_api_path':    o_config['mediasorter']['api']['tmdb']['path'],
            'tmdb_api_key':     o_config['mediasorter']['api']['tmdb']['key'],
            'valid_extensions': o_config['mediasorter']['parameters']['valid_extensions'],
            'split_characters': o_config['mediasorter']['parameters']['split_characters'],
            'min_split_length': int(o_config['mediasorter']['parameters']['min_split_length']),
            'suffix_the':       o_config['mediasorter']['parameters']['suffix_the'],
            'metainfo_map':     o_config['mediasorter']['parameters'].get('metainfo_map', []),
            'search_overrides': o_config['mediasorter'].get('search_overrides', {}),
            'tv_name_overrides':   o_config['mediasorter'].get('name_overrides', {}).get('tv', {}),
            'movie_name_overrides':   o_config['mediasorter'].get('name_overrides', {}).get('movie', {}),
            'log_to_file':      o_config['mediasorter']['logging']['file'],
            'logfile':          o_config['mediasorter']['logging']['logfile'],
        }
    except Exception as e:
        logger(config, 'ERROR: Failed to load configuration: {}'.format(e))
        exit(1)

    srcpath = os.path.abspath(os.path.expanduser(srcpath))
    dstpath = os.path.abspath(os.path.expanduser(dstpath))

    # Sort the media file
    returncode = sort_file(config, srcpath, dstpath, mediatype, action, infofile, shasum, chown, user, group, file_mode, directory_mode, metainfo_tag, upgrade, dryrun)
    if returncode > 0:
        logger(config, "Failed to sort file {}".format(srcpath))
    exit(returncode)

# Entry point
def main():
    return cli_root(obj={})

if __name__ == '__main__':
    main()
