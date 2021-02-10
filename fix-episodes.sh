#!/bin/bash

usage() {
    echo "Increment/decrement episode numbers in TV shows"
    echo
    echo -e "Usage: $0 [-d/--dry-run] <directory> <extension> <increment/decrement> [<start_episode>] [<end_episode>]"
    echo
    echo -e "  -d/--dry-run: Do not perform the action, just print the change."
    echo -e "  directory: A directory containing TV episodes with SXXEYY naming format to"
    echo -e "             modify episode numbers for."
    echo -e "  extension: the .xyz file extension (usable by the basename utility) of the"
    echo -e "             media file type, e.g. .mkv, .avi, etc. within the directory."
    echo -e "             Used to determine the list of episodes to work on while"
    echo -e "             supporting the renaming of arbitrary files, e.g. shasums, nfos, etc."
    echo -e "  increment/decrement: An integer number (either positive or negative) to change"
    echo -e "                       episode IDs by, e.g. -1 turns E04 into E03."
    echo -e "  start_episode: Optional, a (current) episode number to start on."
    echo -e "  end_episode: Optional, a (current) episode number to end on, inclusive."
    exit 0
}

if [[ ${1} == '-d' || ${1} == '--dry-run' ]]; then
    shift
    dryrun="y"
else
    dryrun=""
fi

if [[ -z ${1} || -z ${2} || -z ${3} ]]; then
    usage
fi

pushd "${1}" &>/dev/null

extension="${2}"
increment="${3}"
start_episode="${4}"
end_episode="${5}"

if [[ -z ${start_episode} ]]; then
    start_episode=01
fi

if [[ -n ${dryrun} ]]; then
    echo "Dryrun mode active - no changes will be made to files."
fi

for file in *${extension}; do
    cur_episode="$( basename "${file}" ${extension} )"
    cur_episode_num="$( grep -o 'E[0-9]*' <<<"${cur_episode}" | sed 's/E//g' )"

    if [[ -n ${start_episode} ]]; then
        if [[ ${cur_episode_num#0} -lt ${start_episode#0} ]]; then
            continue
        fi
    fi
    if [[ -n ${end_episode} ]]; then
        if [[ ${cur_episode_num#0} -gt ${end_episode#0} ]]; then
            continue
        fi
    fi

    new_episode_num=$( printf "%02d\n" $(( ${cur_episode_num#0} + ${increment#0} )) )
    new_episode="$( sed "s/E${cur_episode_num}/E${new_episode_num}/g" <<<"${cur_episode}" )"

    echo "Renaming '${cur_episode}' -> '${new_episode}'"
    if [[ -n ${dryrun} ]]; then
        continue
    fi

    mmv "${cur_episode}*" "${new_episode}#1"
done

popd &>/dev/null
