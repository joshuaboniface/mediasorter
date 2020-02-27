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
import sys
import re
import urllib.request
import json
import subprocess
import hashlib
import click
import yaml
from datetime import datetime

def logger(config, msg, nl=True):
    click.echo(msg, nl=nl)

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

    # Get the series title and SXXEYY identifier, then end; we get the rest from TVMaze
    end_idx = len(split_filename)
    sxxeyy_idx = 0
    season_id = 0
    episode_id = 0
    for idx, element in enumerate(split_filename):
        if re.match('[Ss][0-9]+[Ee][0-9]+', element):
            sxxeyy_idx = idx
            seid = re.match('[Ss]([0-9]+)[Ee]([0-9]+)', element)
            season_id = int(seid.group(1))
            episode_id = int(seid.group(2))
            break

    # Series title: start to sxxeyy_idx
    raw_series_title_unfixed = split_filename[0:sxxeyy_idx]
    raw_series_title = list()
    for word in raw_series_title_unfixed:
        # Skip years in the title, because of The Grand Tour
        if re.match('^[0-9]{4}$', word):
            continue
        raw_series_title.append(word)
    search_series_title = '+'.join([x.lower() for x in raw_series_title])
    logger(config, "Raw file info:    series='{}' S={} E={}".format(search_series_title, season_id, episode_id))

    # Fetch series information from TVMaze
    show_path = config['tvmaze_api_path'].format(show=search_series_title)
    show_url = '{}/{}'.format(config['tvmaze_api_base'], show_path)
    logger(config, "TVMaze API URL:   {}".format(show_url))
    request = urllib.request.Request(show_url)
    response = urllib.request.urlopen(request)
    data = response.read()
    series_data = json.loads(data)
    
    # Get the series and episode titles
    series_title = series_data.get('name')
    episode_list = series_data.get('_embedded').get('episodes')
    episode_title = 'unnamed'
    for episode in episode_list:
        if episode.get('season') == season_id and episode.get('number') == episode_id:
            episode_title = episode.get('name')

    if config['suffix_the']:
        # Fix leading The's in the series title
        if re.match('[Tt]he\s(.*)', series_title):
            series_title = re.match('[Tt]he\s(.*)', series_title).group(1) + ', The'

    # Build the final path+filename
    dst_path = '{dst}/{series}/Season {sid}'.format(
        dst=dstpath,
        series=series_title,
        sid=season_id,
    )
    dst_file = '{series} - S{sid:02d}E{eid:02d} - {title}{ext}'.format(
        series=series_title,
        sid=season_id,
        eid=episode_id,
        title=episode_title,
        ext=fileext
    )
    logger(config, "Sorted filename:  {}/{}".format(dst_path, dst_file))

    return dst_path, dst_file

def sort_movie_file(config, srcpath, dstpath):
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
        # A year is an element exactly matching 4 numerals; it has to do
        if re.match('^[0-9]{4}$', element):
            year_idx = idx
            search_movie_year = element
            # Don't break here, since we always want the last year (e.g. in "2001 A Space Odyssey")

    # Series title: start to year_idx
    raw_movie_title = split_filename[0:year_idx]
    search_movie_title = '+'.join([x.lower() for x in raw_movie_title])
    logger(config, "Raw file info:    movie='{}' year={}".format(search_movie_title, search_movie_year))

    # Fetch series information from TVMaze
    movie_path = config['tmdb_api_path'].format(key=config['tmdb_api_key'], title=search_movie_title)
    movie_url = '{}/{}'.format(config['tmdb_api_base'], movie_path)
    logger(config, "TMDB API URL:     {}".format(movie_url))
    request = urllib.request.Request(movie_url)
    response = urllib.request.urlopen(request)
    data = response.read()
    movie_data = json.loads(data)
    
    # List all movies and find the one matching the year
    movie_list = movie_data.get('results')
    movie_title = 'unnamed'
    movie_year = '0000'
    for movie in movie_list:
        release_year = movie.get('release_date').split('-')[0]
        if search_movie_year == '0000' or release_year == search_movie_year:
            movie_title = movie.get('title')
            movie_year = release_year
            break

    if movie_title == 'unnamed':
        logger(config, "Error: No movie was found in the database for filename '{}'.".format(filename))
        return False, False

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
    dst_file = '{movie} ({year}){ext}'.format(
        dst=dstpath,
        movie=movie_title,
        year=movie_year,
        ext=fileext
    )
    logger(config, "Sorted filename:  {}/{}".format(dst_path, dst_file))

    return dst_path, dst_file

# File sorting main function
def sort_file(config, srcpath, dstpath, mediatype, action, infofile, shasum, chown, user, group, file_mode, directory_mode, dryrun):
    # Get UID and GID for chowning
    uid = pwd.getpwnam(user)[2]
    gid = grp.getgrnam(group)[2]

    logger(config, ">>> Parsing {}".format(srcpath))
    # Determine if srcpath is a directory, then act recursively
    if os.path.isdir(srcpath):
        for filename in sorted(os.listdir(srcpath)):
            child_filename = '{}/{}'.format(srcpath, filename)
            sort_file(config, child_filename, dstpath, mediatype, action, infofile, shasum, chown, user, group, file_mode, directory_mode, dryrun)
        return 0

    logger(config, "Sorting action:   {}".format(action))

    # Get our destination path and filename (media-specific)
    if mediatype == 'tv':
        file_dst_path, file_dst_filename = sort_tv_file(config, srcpath, dstpath)
    if mediatype == 'movie':
        file_dst_path, file_dst_filename = sort_movie_file(config, srcpath, dstpath)

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
        shasum_cmdout = subprocess.run(['sha256sum', '{}'.format(file_dst)], capture_output=True, encoding='utf8')
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
    help="Create/don't create information file at target."
)
@click.option(
    '-s/-S', '--shasum/--no-shasum', 'shasum',
    is_flag=True, default=False, show_default=True,
    help="Create/don't create SHA256sum file at target."
)
@click.option(
    '-o/-O', '--chown/--no-chown', 'chown',
    is_flag=True, default=False, show_default=True,
    help="Change/don't change ownership and permissions of destfile to match user/group and mode."
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
def cli_root(srcpath, dstpath, mediatype, action, infofile, shasum, chown, user, group, file_mode, directory_mode, dryrun, config_file):
    """
    Sort the file or directory SRCPATH.
    """

    config = {}
    # Parse the configuration file
    with open(config_file, 'r') as cfgfile:
        try:
            o_config = yaml.load(cfgfile)
        except Exception as e:
            logger(config, 'ERROR: Failed to parse configuration file: {}'.format(e))
            exit(1)
    
    try:
        config = {
            'tvmaze_api_base':  o_config['mediasorter']['api']['tvmaze']['url'],
            'tvmaze_api_path':  o_config['mediasorter']['api']['tvmaze']['path'],
            'tmdb_api_base':    o_config['mediasorter']['api']['tmdb']['url'],
            'tmdb_api_path':    o_config['mediasorter']['api']['tmdb']['path'],
            'tmdb_api_key':     o_config['mediasorter']['api']['tmdb']['key'],
            'valid_extensions': o_config['mediasorter']['parameters']['valid_extensions'],
            'split_characters': o_config['mediasorter']['parameters']['split_characters'],
            'min_split_length': o_config['mediasorter']['parameters']['min_split_length'],
            'suffix_the':       o_config['mediasorter']['parameters']['suffix_the'],
            'log_to_file':      o_config['mediasorter']['logging']['file'],
            'logfile':          o_config['mediasorter']['logging']['logfile'],
        }
    except Exception as e:
        logger(config, 'ERROR: Failed to load configuration: {}'.format(e))
        exit(1)
    
    srcpath = os.path.abspath(os.path.expanduser(srcpath))
    dstpath = os.path.abspath(os.path.expanduser(dstpath))

    # Sort the media file
    returncode = sort_file(config, srcpath, dstpath, mediatype, action, infofile, shasum, chown, user, group, file_mode, directory_mode, dryrun)
    exit(returncode)

# Entry point
def main():
    return cli_root(obj={})

if __name__ == '__main__':
    main()
