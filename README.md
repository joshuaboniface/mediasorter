# mediasorter

mediasorter is a tool to automatically "sort" media files from a source naming format  into something nicer for humans to read/organize, and for tools like Jellyfin to parse and collect metadata for. It uses The Movie DB for movie metadata and TVMaze for TV metadata to obtain additional information, then performs the "sort" via a user-selectable mechanism. In this aspect it seeks to be a replacement for FileBot and other similar tools.

Most aspects of mediasorter can be configured, either inside the main configuration file, or via command-line arguments; it hopes to remain simple yet flexible, doing exactly what the administrator wants and nothing more.

mediasorter is free software, released under the GNU GPL version 3 (or later). It is written as a single Python 3 script and makes use of Click (`python3-click`) and YAML (`python3-yaml`).

## Usage

1. Install the required Python 3 dependencies: `click` and `yaml`.

1. Create the directory `/etc/mediasorter`.

1. Copy the `mediasorter.yml.sample` file to `/etc/mediasorter/mediasorter.yml` and edit it to suit your needs.

1. Install `mediasorter.py` somewhere useful, for instance at `/usr/local/bin/mediasorter.py`.

1. Profit!

## fix-episodes.sh

mediasorter isn't that smart. For instance, if a show has inconsistent episode numbers between, say, airdate and a DVD, it can give episodes the wrong numbering.

Fixing this manually is quite cumbersome, and after having to deal with it more than once, I created this quick-and-dirty script that will quickly rename such files, especially for ranges of episodes that are incorrectly numbered.

Run it with no arguments for usage information.
