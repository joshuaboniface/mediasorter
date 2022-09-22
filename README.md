# mediasorter

mediasorter is a tool to automatically "sort" media files from a source naming format  into something nicer for humans to read/organize, and for tools like Jellyfin to parse and collect metadata for. It uses The Movie DB for movie metadata and TVMaze for TV metadata to obtain additional information, then performs the "sort" via a user-selectable mechanism. In this aspect it seeks to be a replacement for FileBot and other similar tools.

Most aspects of mediasorter can be configured, either inside the main configuration file, or via command-line arguments; it hopes to remain simple yet flexible, doing exactly what the administrator wants and nothing more.

mediasorter is free software, released under the GNU GPL version 3 (or later). It is written as a single Python 3 script and makes use of Click (`python3-click`) and YAML (`python3-yaml`).

## Usage

1. Install the required Python 3 dependencies: `click` and `yaml`.

1. Create the directory `/etc/mediasorter`.

1. Copy the `mediasorter.yml.sample` file to `/etc/mediasorter/mediasorter.yml` and edit it to suit your needs.

1. Install `mediasorter.py` somewhere useful, for instance at `/usr/local/bin/mediasorter.py`.

1. Run `mediasorter.py --help` for detailed help.

1. Profit!

## Metainfo Tagging

With the `-tm`/`--tag-metainfo` option, additional info can be added to the destination filename to leverage Jellyfin's ["multiple movie versions"](https://jellyfin.org/docs/general/server/media/movies.html#multiple-versions-of-a-movie) feature. Currently, this only works with Movies (not TV episodes) in Jellyfin, and thus in mediasorter as well.

When this option is specified, the information found in the `metainfo_map` in the configuration file which is present in the source filename will be appended, using the square-brackets format, to the end of the destination filename.

When parsing, the list is iterated through in the order specified, and then for each item, the source filename is searched for the relevant regex match. If found, the value will be appended (once) to the metainfo string. The entries are grouped by type, for example cuts/editions first, then resolutions, then media types, etc. to produce a coherent and consistent string.

A large sample of possible match values is included in the `mediasorter.yml.sample` file, but more can be added or some removed as desired.

As an example, the following might be a destination filename with metainfo tagging using the default map:

```
Lord of the Rings: The Return of the King, The (2003) - [Extended Edition 2160p BD Remux 7.x Atmos TrueHD].mkv
```

## Replacement

By default, `mediasorter` will replace an existing destination file, if one exists, with a new one during a run. This is useful if new media comes in which should replace the existing media (e.g. an upgraded quality version). To disable this behaviour, use `--no-upgrade`.

This behaviour is redundent when metainfo tagging is enabled for Movies, since the differenting quality profile would trigger a new file to be created anyways; it is thus mostly useful for TV which does not support this feature.

## Search Overrides

Sometimes, the name of a piece of media, as extracted from the file, will not return proper results from the upstream metadata providers. If this happens, `mediasorter` includes an option in the configuration file to specify search overrides. For example, the TV show "S.W.A.T." does not return sensible results, so it can be overridden like so:

```
search_overrides:
  "s w a t": "swat"
```

This is currently the only *provided* example for demonstration purposes, but it can happen to many different titles. If you find a title that returns no results consider adding it to this list on your local system.

## Name Overrides

Soemtimes, the name returned by the metadata providers might not match what you want to sort as. Thus `mediasorter` can override titles based on a list provided in the configuration file. For example, if you want the TV show "Star Trek" to be named "Star Trek: The Original Series" instead, it can be overridden like so:

```
name_overrides:
  tv:
    "Star Trek": "Star Trek: The Original Series"
```

These overrides are specific to media type (`tv` or `movie`) to avoid conflicts, e.g. in this example, with the 2009 film "Star Trek" which would also be changed (erroneously) if this were global.

Name overrides are handled *before* adjusting a suffixed "The", so entries containing "The" should be written normally, e.g. "The Series" instead of "Series, The" even if the latter is what is ultimately written.

## fix-episodes.sh

mediasorter isn't that smart. For instance, if a show has inconsistent episode numbers between, say, airdate and a DVD, it can give episodes the wrong numbering.

Fixing this manually is quite cumbersome, and after having to deal with it more than once, I created this quick-and-dirty script that will quickly rename such files, especially for ranges of episodes that are incorrectly numbered.

Run it with no arguments for usage information.
