import ipdb
import requests
import json
import re
import copy
import random
import time
from shared.common_func import *
from chunithm.paths import *
from datetime import datetime
from bs4 import BeautifulSoup, NavigableString, Tag

wiki_url = 'https://silentblue.remywiki.com/CHUNITHM:VERSE_(Asia)'

request_headers = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:121.0) Gecko/20100101 Firefox/121.0',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8'
}

# Copy over data from JP ver to INTL
def sync_json_data():
    print_message(f"Syncing song data from JP to INTL", 'H2', log=True)

    # Read JP data
    with open(LOCAL_MUSIC_EX_JSON_PATH, 'r', encoding='utf-8') as f:
        src_music_data = json.load(f)

    # If the current INTL and JP ver are not the same, load previous version archive as well
    if game.CURRENT_INTL_VER != game.CURRENT_JP_VER:
        with open(LOCAL_MUSIC_EX_PREV_VER_JSON_PATH, 'r', encoding='utf-8') as f:
            src_prev_ver_music_data = json.load(f)

    # Read INTL data
    with open(LOCAL_INTL_MUSIC_EX_JSON_PATH, 'r', encoding='utf-8') as f:
        dest_music_data = json.load(f)

    src_music_map = json_to_hash_value_map(src_music_data)

    if game.CURRENT_INTL_VER != game.CURRENT_JP_VER:
        src_prev_ver_music_map = json_to_hash_value_map(src_prev_ver_music_data)

    dest_music_map = json_to_hash_value_map(dest_music_data)
    dest_music_data_pre_update = copy.deepcopy(dest_music_data)

    added_songs = []
    removed_songs = []

    # Compare sets of IDs to identify added and removed songs
    added_ids = set(src_music_map.keys()) - set(dest_music_map.keys())
    removed_ids = set(dest_music_map.keys()) - set(src_music_map.keys())

    if game.CURRENT_INTL_VER != game.CURRENT_JP_VER:
        removed_ids_against_prev_ver = set(dest_music_map.keys()) - set(src_prev_ver_music_map.keys())

    updated_songs = []
    unchanged_songs = []
    for id, src_song in src_music_map.items():
        if id in dest_music_map:
            local_song = dest_music_map[id]
            # Remove the "sort" key from both server_song and local_song
            src_song_without_sort = {k: v for k, v in src_song.items() if k != "sort"}
            local_song_without_sort = {k: v for k, v in local_song.items() if k != "sort"}

            if src_song_without_sort != local_song_without_sort:
                # Song has been updated (excluding the "sort" key), include it in the updated_songs list
                updated_songs.append(src_song)
            else:
                # Maimai always updates the "sort" value so let's keep it updated...
                unchanged_songs.append(src_song)

    # check if any song doesn't exist in JP but is in INTL
    if removed_ids:
        removed_songs = [dest_music_map[id] for id in removed_ids]

    # If INTL ver is behind JP, check with previous ver archive data first
    if game.CURRENT_INTL_VER != game.CURRENT_JP_VER:
        if removed_ids_against_prev_ver:
            removed_songs_prev_ver = [dest_music_map[id] for id in removed_ids_against_prev_ver]

            for song in removed_songs_prev_ver:
                song_diffs = [0]
                song_hash = generate_hash_from_keys(song)
                existing_song = next((s for s in dest_music_data if generate_hash_from_keys(s) == song_hash), None)

                if existing_song:
                    title_print = f"[{song['we_kanji']}] {song['title']}" if song["we_kanji"] else song["title"]
                    lazy_print_song_header(title_print, song_diffs, log=True)

                    # INTL song exists in latest JP version, skip
                    if existing_song not in removed_songs:
                        print_message(f"- Song does not exist in JP ({game.CURRENT_INTL_VER}) final data but is found in current JP version", bcolors.WARNING)
                    else:
                        print_message(f"- Warning: Song does not exist in JP ({game.CURRENT_INTL_VER}) final data. Perhaps this song was deleted?", bcolors.FAIL)
    else:
        if removed_ids:
            for song in removed_songs:
                song_diffs = [0]
                song_hash = generate_hash_from_keys(song)
                existing_song = next((s for s in dest_music_data if generate_hash_from_keys(s) == song_hash), None)

                if existing_song:
                    title_print = f"[{song['we_kanji']}] {song['title']}" if song["we_kanji"] else song["title"]
                    lazy_print_song_header(title_print, song_diffs, log=True)
                    print_message(f"- Warning: Song does not exist in JP data. Perhaps this song was deleted?", bcolors.FAIL)


    # Iterate through updated songs
    # For the list of updated songs, go through each of them in older song list
    # Find the same song in ex_data list then update any changed keys
    for song in updated_songs:
        song_diffs = [0]
        title_print = f"[{song['we_kanji']}] {song['title']}" if song["we_kanji"] else song["title"]
        song_hash = generate_hash_from_keys(song)
        song_pre_update = next((s for s in dest_music_data_pre_update if generate_hash_from_keys(s) == song_hash), None)
        dest_song = next((s for s in dest_music_data if generate_hash_from_keys(s) == song_hash), None)

        # Song can't be found in music-ex.json
        if not dest_song:
            lazy_print_song_header(title_print, song_diffs, log=True)
            print_message(f"- Couldn't find matching song in INTL", bcolors.WARNING)
            continue

        if song_pre_update == song:
            continue

        if song_pre_update and dest_song:
            # Check for changes, additions, or removals
            for key, value in song.items():
                # Don't update these keys
                if key in ['date', 'version', 'intl', 'release', 'date_intl_added', 'date_intl_updated']:
                    continue

                # Also, if INTL and JP ver are different
                # never update non-chart detail data (e.g. Title, Artist etc)
                if (game.CURRENT_JP_VER != game.CURRENT_INTL_VER):
                    all_required_keys = {key for keys in game.REQUIRED_KEYS_PER_CHART.values() for key in keys}
                    if key not in all_required_keys:
                        continue

                # If key doesn't exist
                if key not in song_pre_update:
                    # Chart Constant
                    if "_i" in key:
                        # Check if relevant chart already exists in INTL
                        if parent_key_exists(key, dest_song):
                            # If INTL and JP version are same, copy key and value from JP
                            if (game.CURRENT_JP_VER == game.CURRENT_INTL_VER):
                                dest_song[key] = value
                                lazy_print_song_header(title_print, song_diffs, log=True)
                                print_message(f"- Copied {key}: {song[key]}", bcolors.OKBLUE)
                    # Other notes data keys
                    elif "_notes" in key:
                        # Don't copy if ULTIMA level actually doesn't exist
                        if key.startswith("lev_ult") and dest_song["lev_ult"] == "":
                            continue

                        # Check if relevant chart already exists in INTL
                        if parent_key_exists(key, dest_song):
                            if value != "":
                                dest_song[key] = value
                                lazy_print_song_header(title_print, song_diffs, log=True)
                                print_message(f"- Copied {key}: {song[key]}", bcolors.OKBLUE)

                # If key exists, but value is empty
                elif song_pre_update[key] != value and value != "":
                    if song_pre_update[key] == "":
                        # For chart constant, skip overwrite if current INTL and JP ver are different
                        if "_i" in key and (game.CURRENT_JP_VER != game.CURRENT_INTL_VER):
                            continue

                        lazy_print_song_header(title_print, song_diffs, log=True)
                        print_message(f"- Added value for {key}: {song[key]}", bcolors.OKBLUE)
                        dest_song[key] = value
                        print_message(f"- (Synced JP archive data)", bcolors.OKBLUE)
                        song_pre_update[key] = value
                    else:
                        # For chart constant, skip overwrite if current INTL and JP ver are different
                        if "_i" in key and (game.CURRENT_JP_VER != game.CURRENT_INTL_VER):
                            continue

                        lazy_print_song_header(title_print, song_diffs, log=True)
                        print_message(f"- Overwrote {key}: {song_pre_update[key]} → {song[key]}", bcolors.OKBLUE)
                        dest_song[key] = value
                        print_message(f"- (Synced JP archive data)", bcolors.OKBLUE)
                        song_pre_update[key] = value


    # Iterate through unchanged songs
    for song in unchanged_songs:
        song_diffs = [0]
        title_print = f"[{song['we_kanji']}] {song['title']}" if song["we_kanji"] else song["title"]
        song_hash = generate_hash_from_keys(song)
        song_pre_update = next((s for s in dest_music_data_pre_update if generate_hash_from_keys(s) == song_hash), None)
        dest_song = next((s for s in dest_music_data if generate_hash_from_keys(s) == song_hash), None)

        # Song can't be found in music-ex.json
        if not dest_song:
            lazy_print_song_header(title_print, song_diffs, log=True)
            print_message(f"- Couldn't find matching song in {LOCAL_INTL_MUSIC_EX_JSON_PATH}", bcolors.WARNING)
            continue

        if song_pre_update and dest_song:
            # Check for changes, additions, or removals
            for key, value in song.items():
                 # overwrite "sort" value silently (only if INTL and JP version are same)
                if key == 'sort':
                    if (game.CURRENT_JP_VER != game.CURRENT_INTL_VER):
                        continue
                    else:
                        dest_song[key] = value
                        continue

                # maimai uses 'date' key for recording NEW markers... ignore them
                if key == 'date':
                    continue
                if key not in song_pre_update or song_pre_update[key] != value:
                    dest_song[key] = value

            # Check for removed keys
            for key in song_pre_update.copy():
                # maimai uses 'date' key for recording NEW markers... ignore them
                if key == 'date':
                    continue
                if key not in song:
                    del dest_song[key]

    if song_diffs[0] == 0:
        print_message("(Nothing updated)", bcolors.ENDC, log=True)
    else:
        sort_and_save_json(dest_music_data, LOCAL_INTL_MUSIC_EX_JSON_PATH)

        if game.CURRENT_INTL_VER != game.CURRENT_JP_VER:
            sort_and_save_json(dest_music_data_pre_update, LOCAL_MUSIC_EX_PREV_VER_JSON_PATH)


# Update on top of existing music-ex
def add_intl_info():
    total_diffs = [0]

    print_message(f"Update International ver. song data from RemyWiki", 'H2', log=True)

    # Load JSON data
    with open(LOCAL_MUSIC_EX_JSON_PATH, 'r', encoding='utf-8') as f:
        local_music_ex_data = json.load(f)

    if game.CURRENT_INTL_VER != game.CURRENT_JP_VER:
        with open(LOCAL_MUSIC_EX_PREV_VER_JSON_PATH, 'r', encoding='utf-8') as f:
            local_music_ex_prev_ver_data = json.load(f)

    with open(LOCAL_INTL_MUSIC_EX_JSON_PATH, 'r', encoding='utf-8') as f:
        local_intl_music_ex_data = json.load(f)

    # Get Wiki page
    print_message(f"Request URL: {wiki_url}", bcolors.ENDC, log=True, is_verbose=True)
    try:
        wiki = requests.get(wiki_url, timeout=5, headers=request_headers, allow_redirects=True)
    except requests.RequestException as e:
        print_message(f"Error while loading wiki page: {e}", bcolors.FAIL, log=True, is_verbose=True)
        return


    # Parse HTML
    soup = BeautifulSoup(wiki.text, 'html.parser')

    # Find all tables with class 'bluetable'
    song_list = soup.find('span', id="New_Songs_/_WORLD'S_END_Charts", class_="mw-headline")
    table = song_list.find_next('table', class_='bluetable')
    rows = table.find_all('tr')

    # Initialize a dictionary to store songs

    # Iterate through each row
    for row in rows:
        wiki_song = {}
        header_printed = [0]

        # If this is empty, it means the song has single chart type
        wiki_chart_type = ''
        # If B/A/E/M fields are empty, it means only ULTIMA is added at this time
        only_ultima = False
        song_details = row.find_all('td')

        # skip header rows
        if len(song_details) <= 1:
            continue

        # Find the closest previous th tag to get the datestamp
        date_stamp = None
        prev_th = row.find_previous('th')
        while prev_th:
            if prev_th.get('id') and re.match(r'\d{8}', prev_th['id']):
                date_stamp = prev_th
                break
            prev_th = prev_th.find_previous('th')

        if date_stamp:
            # Extract the date in yyyymmdd format if the id attribute matches
            date = date_stamp['id']
        else:
            # Skip if no datestamp found
            continue

        # Check if it's a WORLDS END song
        worlds_end_td = row.find('td', style="color:white; background:black;", colspan="5")
        if worlds_end_td:
            title = song_details[0].find('a').text.strip()
            artist = song_details[1].text.strip()

            # Extract kanji and stars from WORLDS END row
            we_content = worlds_end_td.text.strip()
            we_kanji = we_content[0]
            we_star_count = we_content.count('☆')

            # Convert star count to integer value
            if we_star_count == 1:
                we_star = '1'
            elif we_star_count == 2:
                we_star = '3'
            elif we_star_count == 3:
                we_star = '5'
            elif we_star_count == 4:
                we_star = '7'
            elif we_star_count == 5:
                we_star = '9'
            else:
                # Handle unexpected star count
                we_star = None

            if we_star is not None:
                # Add song to dictionary with date
                wiki_song = {
                    'title': title,
                    'title_print': f"[{we_kanji}]{title}",
                    'artist': artist,
                    'date': date,
                    'we_kanji': we_kanji,
                    'we_star': we_star
                }

        # Non-WE song
        else:
            wiki_chart_type = 'std'

            title = song_details[0].find('a').text.strip()
            artist = song_details[1].text.strip()
            lev_bas = song_details[2].text.strip()
            lev_adv = song_details[3].text.strip()
            lev_exp = song_details[4].text.strip()
            lev_mas = song_details[5].text.strip()
            lev_ult = song_details[6].text.strip()

            # Add song to dictionary with date
            wiki_song = {
                'title': title,
                'title_print': title,
                'artist': artist,
                'date': date,
                'lev_bas': lev_bas,
                'lev_adv': lev_adv,
                'lev_exp': lev_exp,
                'lev_mas': lev_mas,
                'lev_ult': lev_ult
            }

            # Set only_ultima and is_update
            if (wiki_song['lev_bas'] == '-' and
                wiki_song['lev_adv'] == '-' and
                wiki_song['lev_exp'] == '-' and
                wiki_song['lev_mas'] == '-' and
                wiki_song['lev_ult'] != '-'):
                only_ultima = True

            # If song needs unlock
            # if 'Unlockable' in row.find_previous('th').text.strip():
            #     wiki_song['key_intl'] = True



        # Match wiki song with song from JP JSON file
        jp_song_matched, matched_jp_song, matched_jp_song_pre_update = _match_jp_song(local_music_ex_data, worlds_end_td, wiki_song, wiki_chart_type, only_ultima, header_printed)

        # If JP version is ahead of INTL, additionally match JP song from prev ver data
        # to source level data from
        if game.CURRENT_INTL_VER != game.CURRENT_JP_VER:
            jp_prev_ver_song_matched, matched_jp_prev_ver_song, matched_jp_prev_ver_song_pre_update = _match_jp_song(local_music_ex_prev_ver_data, worlds_end_td, wiki_song, wiki_chart_type, only_ultima, header_printed, legacy=True)


        # Match wiki song with song from INTL JSON file
        intl_song_matched, matched_intl_song, matched_intl_song_pre_update = _match_intl_song(local_intl_music_ex_data, worlds_end_td, wiki_song, header_printed)

        # if 'Campus mode!!' in wiki_song['title']:
        #     ipdb.set_trace()

        # If song is not yet in INTL data
        # Copying entire song from JP->INTL
        if intl_song_matched is False:
            # If current JP ver is ahead of INTL, first look in the prev ver data
            if game.CURRENT_INTL_VER != game.CURRENT_JP_VER:
                # cross check if JP song (latest ver. data) says the song is not yet in INTL
                if jp_prev_ver_song_matched:
                    local_intl_music_ex_data.append(matched_jp_song)
                    matched_intl_song = local_intl_music_ex_data[-1]
                    intl_song_matched = True
                    _sync_jp_to_intl_song('full_copy', matched_jp_prev_ver_song, matched_intl_song, matched_intl_song_pre_update, title, header_printed, only_ultima, wiki_song)

                    # Update INTL marker in current ver JP data as well
                    if jp_song_matched:
                        matched_jp_song['intl'] = "1"

                        if ('date_intl_added' not in matched_jp_song or matched_jp_song['date_intl_added'] == '000000'):
                            matched_jp_song['date_intl_added'] = wiki_song['date']
                            print_message(f"- Marked INTL added date (JP data)", bcolors.OKGREEN, log=True)

                # Fallback: fetch from current ver jp song
                # (Song is not of this version)
                else:
                    if jp_song_matched:
                        local_intl_music_ex_data.append(matched_jp_song)
                        matched_intl_song = local_intl_music_ex_data[-1]
                        intl_song_matched = True
                        _sync_jp_to_intl_song('full_copy', matched_jp_song, matched_intl_song, matched_intl_song_pre_update, title, header_printed, only_ultima, wiki_song)

            # If current JP ver = INTL ver
            else:
                if jp_song_matched:
                    # Copy song from JP data (prev ver)
                    local_intl_music_ex_data.append(matched_jp_song)
                    matched_intl_song = local_intl_music_ex_data[-1]
                    intl_song_matched = True
                    _sync_jp_to_intl_song('full_copy', matched_jp_song, matched_intl_song, matched_intl_song_pre_update, title, header_printed, only_ultima, wiki_song)


        # If song is already in INTL data
        # Partial copy (chart) from JP->INTL
        elif intl_song_matched is True:
            # If current JP ver is ahead of INTL, first look in the prev ver data
            if game.CURRENT_INTL_VER != game.CURRENT_JP_VER:
                if jp_prev_ver_song_matched:
                    _sync_jp_to_intl_song('partial_copy', matched_jp_prev_ver_song, matched_intl_song, matched_intl_song_pre_update, title, header_printed, only_ultima, wiki_song)

            # If current JP ver = INTL ver
            else:
                if jp_song_matched:
                    _sync_jp_to_intl_song('partial_copy',matched_jp_song, matched_intl_song, matched_intl_song_pre_update, title, header_printed, only_ultima, wiki_song)

            # Write unlockable info
            # if 'key_intl' in wiki_song and ('key_intl' not in matched_jp_song or matched_jp_song['key_intl'] == ''):
            #     matched_intl_song['key_intl'] = "○"
            #     matched_jp_song['key_intl'] = "○"

            #     # If JP version is ahead of INTL, also update PREV VER JP data
            #     if game.CURRENT_INTL_VER != game.CURRENT_JP_VER:
            #         matched_jp_prev_ver_song['key_intl'] = "○"

            #     lazy_print_song_header(wiki_song['title_print'], header_printed, log=True)
            #     print_message(f"- Marked as unlockable in Intl ver", bcolors.OKBLUE, log=True)



        # Check if anything has actually changed
        if matched_intl_song_pre_update is not None and matched_intl_song_pre_update == matched_intl_song:
            lazy_print_song_header(wiki_song['title_print'], header_printed, log=True, is_verbose=True)
            print_message("- Done (Nothing updated)", bcolors.ENDC, is_verbose=True)
        else:
            total_diffs[0] += 1


        # if song was not matched, not copied from any JP data after all (if break was not triggered)
        if intl_song_matched is False:
            lazy_print_song_header(wiki_song['title_print'], header_printed, log=True)

            if jp_song_matched is False:
                print_message(f"- Song not matched with any song in JP data", bcolors.FAIL, log=True)
            else:
                print_message(f"- Song not matched with any song in INTL data", bcolors.FAIL, log=True)

    if total_diffs[0] == 0:
        print_message("(Nothing updated)", bcolors.ENDC, log=True)
    else:
        sort_and_save_json(local_intl_music_ex_data, LOCAL_INTL_MUSIC_EX_JSON_PATH)

        if game.CURRENT_INTL_VER != game.CURRENT_JP_VER:
            sort_and_save_json(local_music_ex_prev_ver_data, LOCAL_MUSIC_EX_PREV_VER_JSON_PATH)

        sort_and_save_json(local_music_ex_data, LOCAL_MUSIC_EX_JSON_PATH)



# Match wiki song with song from JP JSON file
def _match_jp_song(json_data, worlds_end_td, wiki_song, wiki_chart_type, only_ultima, header_printed, legacy=False):
    jp_song_title_matched = False
    jp_song_artist_matched = False
    jp_song_matched = False
    matched_jp_song = None
    matched_jp_song_pre_update = None

    for song in json_data:
        if worlds_end_td:
            if 'we_kanji' in song and 'we_kanji' in wiki_song:
                # Match kanji
                if (song['we_kanji'] != wiki_song['we_kanji']):
                    continue

                # Match title
                jp_song_title_matched = _smart_match('jp', 'title', song, wiki_song, header_printed)
                if jp_song_title_matched is False:
                    continue

                # Match artist
                jp_song_artist_matched = _smart_match('jp', 'artist', song, wiki_song, header_printed)
                if jp_song_artist_matched is False:
                    continue


                if ('we_star' in song and song['we_star'] != wiki_song['we_star']):
                    lazy_print_song_header(wiki_song['title_print'], header_printed, log=True)

                    if game.ARGS.strict:
                        print_message(f"- JP song match: WORLDS END level (stars) mismatch. (JSON: {song['we_star']} vs Wiki: {wiki_song['we_star']})", bcolors.FAIL, log=True)
                        continue
                    else:
                        print_message(f"- JP song match: WORLDS END level (stars) mismatch. (JSON: {song['we_star']} vs Wiki: {wiki_song['we_star']})", bcolors.WARNING, log=True)

                if ('we_kanji' in song and song['we_kanji'] == wiki_song['we_kanji']):
                    jp_song_matched = True
                    matched_jp_song = song
                    matched_jp_song_pre_update = copy.copy(song)
                    break
        else:
            # Match title
            jp_song_title_matched = _smart_match('jp', 'title', song, wiki_song, header_printed)
            if jp_song_title_matched is False:
                continue

            # Match artist
            jp_song_artist_matched = _smart_match('jp', 'artist', song, wiki_song, header_printed)
            if jp_song_artist_matched is False:
                continue

            # if song only has ult added
            if only_ultima:
                if song['lev_ult'] != wiki_song['lev_ult']:
                    lazy_print_song_header(wiki_song['title_print'], header_printed, log=True, is_verbose=True)

                    if game.ARGS.strict:
                        print_message(f"- JP song matched but rejected due to chart levels mismatch (JSON{ " (Prev.ver)" if legacy else "" }: {song['lev_ult']} vs Wiki: {wiki_song['lev_ult']})", bcolors.FAIL, log=True, is_verbose=True)
                        continue
                    else:
                        print_message(f"- JP song matched but chart levels differ partially (JSON{ " (Prev.ver)" if legacy else "" }: {song['lev_ult']} vs Wiki: {wiki_song['lev_ult']})", bcolors.WARNING, log=True, is_verbose=True)

            # Song has other charts added but levels mismatch
            else:
                if ((song['lev_bas'] != wiki_song['lev_bas'] or
                    song['lev_adv'] != wiki_song['lev_adv'] or
                    song['lev_exp'] != wiki_song['lev_exp'] or
                    song['lev_mas'] != wiki_song['lev_mas'])):

                    lazy_print_song_header(wiki_song['title_print'], header_printed, log=True, is_verbose=True)

                    if game.ARGS.strict:
                        print_message(f"- JP song matched but rejected due to chart levels mismatch (JSON{ " (Prev.ver)" if legacy else "" }: {song['lev_bas']}/{song['lev_adv']}/{song['lev_exp']}/{song['lev_mas']} vs Wiki: {wiki_song['lev_bas']}/{wiki_song['lev_adv']}/{wiki_song['lev_exp']}/{wiki_song['lev_mas']})", bcolors.FAIL, log=True, is_verbose=True)
                        continue
                    else:
                        print_message(f"- JP song matched but chart levels differ partially (JSON{ " (Prev.ver)" if legacy else "" }: {song['lev_bas']}/{song['lev_adv']}/{song['lev_exp']}/{song['lev_mas']} vs Wiki: {wiki_song['lev_bas']}/{wiki_song['lev_adv']}/{wiki_song['lev_exp']}/{wiki_song['lev_mas']})", bcolors.WARNING, log=True, is_verbose=True)

            matched_jp_song = song
            matched_jp_song_pre_update = copy.copy(song)
            jp_song_matched = True
            break

    return jp_song_matched, matched_jp_song, matched_jp_song_pre_update



def _match_intl_song(json_data, worlds_end_td, wiki_song, header_printed):
    intl_song_title_matched = False
    intl_song_artist_matched = False
    intl_song_matched = False
    matched_intl_song = None
    matched_intl_song_pre_update = None

    for intl_song in json_data:
        # WE
        if worlds_end_td:
            if 'we_kanji' in intl_song and 'we_kanji' in wiki_song:
                # Match kanji
                if (intl_song['we_kanji'] != wiki_song['we_kanji']):
                    continue

                # Match title
                intl_song_title_matched = _smart_match('intl', 'title', intl_song, wiki_song, header_printed)
                if intl_song_title_matched is False:
                    continue

                # Match artist
                intl_song_artist_matched = _smart_match('intl', 'artist', intl_song, wiki_song, header_printed)
                if intl_song_artist_matched is False:
                    continue

                matched_intl_song = intl_song
                matched_intl_song_pre_update = copy.copy(intl_song)
                intl_song_matched = True
                break

        # else
        else:
            # Match title
            intl_song_title_matched = _smart_match('intl', 'title', intl_song, wiki_song, header_printed)
            if intl_song_title_matched is False:
                continue

            # Match artist
            intl_song_artist_matched = _smart_match('intl', 'artist', intl_song, wiki_song, header_printed)
            if intl_song_artist_matched is False:
                continue

            matched_intl_song = intl_song
            matched_intl_song_pre_update = copy.copy(intl_song)
            intl_song_matched = True
            break

    return intl_song_matched, matched_intl_song, matched_intl_song_pre_update


def _sync_jp_to_intl_song(method, jp_song, intl_song, intl_song_pre_update, title, header_printed, only_ultima, wiki_song):
    if method == 'full_copy':
        lazy_print_song_header(wiki_song['title_print'], header_printed, log=True)
        print_message(f"- Song copied from JP data to INTL", bcolors.OKGREEN, log=True)
    elif method == 'partial_copy':
        # Define key prefixes
        std_prefixes = ["lev_bas", "lev_adv", "lev_exp", "lev_mas"]
        ult_prefixes = ["lev_ult"]

        # Get wiki chart type
        chart_type = _determine_wiki_chart_type(intl_song)

        # Determine which prefixes to use
        if chart_type == 'std':
            prefixes_to_match = ult_prefixes if only_ultima else std_prefixes
            message = "- Copied ULTIMA chart from JP data to INTL" if only_ultima else "- Copied data from JP data to INTL"
        elif chart_type != 'worlds_end':
            lazy_print_song_header(wiki_song['title_print'], header_printed, log=True)
            print_message("- Could not determine chart type", bcolors.FAIL, log=True)
            return

        # Copy data based on matching prefixes
        updated = False
        if not chart_type == 'worlds_end':
            for key in jp_song:
                if any(key.startswith(prefix) for prefix in prefixes_to_match):
                    intl_song[key] = jp_song[key]

                    if intl_song_pre_update.get(key) != intl_song[key]:
                        updated = True

            if updated:
                lazy_print_song_header(wiki_song['title_print'], header_printed, log=True)
                print_message(message, bcolors.OKGREEN, log=True)

    # Note if JP song has INTL already marked
    if jp_song['intl'] != '0':
        lazy_print_song_header(wiki_song['title_print'], header_printed, log=True, is_verbose=True)
        print_message(f"- (INTL already marked as available in JP data)", bcolors.ENDC, log=True, is_verbose=True)
    else:
        # update INTL markers
        intl_song['intl'] = "1"
        jp_song['intl'] = "1"

        lazy_print_song_header(wiki_song['title_print'], header_printed, log=True)
        print_message(f"- Marked as available in INTL ver.", bcolors.OKGREEN, log=True)

    # Process dates
    def _update_date(date_key, color, message):
        intl_song[date_key] = wiki_song['date']
        jp_song[date_key] = wiki_song['date']
        lazy_print_song_header(wiki_song['title_print'], header_printed, log=True)
        print_message(f"- {message} ({wiki_song['date']})", color, log=True)

    wiki_date = int(wiki_song['date'])
    added_date = int(jp_song.get('date_intl_added', '000000')) if 'date_intl_added' in jp_song else 0
    updated_date = int(jp_song.get('date_intl_updated', '000000')) if 'date_intl_updated' in jp_song else 0

    if 'date_intl_added' not in jp_song or jp_song['date_intl_added'] == '000000':  # If added date doesn't exist or is a placeholder
        _update_date('date_intl_added', bcolors.OKGREEN, "Added Intl added date")
    elif 'date_intl_updated' not in jp_song and wiki_date > added_date:  # If new update is found
        _update_date('date_intl_updated', bcolors.OKBLUE, "Added Intl updated date")
    elif 'date_intl_updated' in jp_song and wiki_date > updated_date:  # If a later update exists
        _update_date('date_intl_updated', bcolors.OKBLUE, "Added Intl updated date")


def _determine_wiki_chart_type(matched_intl_song):
    if matched_intl_song['we_kanji'] == "":
        return 'std'
    else:
        return 'worlds_end'
    return ''

def parent_key_exists(key_name, song):
    for parent_key, child_keys in game.REQUIRED_KEYS_PER_CHART.items():
        # skip irrelevant key
        if key_name not in child_keys:
            continue
        # matched
        if parent_key in song:
            return True
        else:
            return False
    return False

def _smart_match(region, title_or_artist, target_song, wiki_song, header_printed):
    normalized_target_song_title_or_artist = normalize_title(target_song[title_or_artist])
    normalized_wiki_song_title_or_artist = normalize_title(wiki_song[title_or_artist])

    match_similarity = compare_strings(normalized_target_song_title_or_artist, normalized_wiki_song_title_or_artist)
    if (match_similarity == 100):
        # lazy_print_song_header(wiki_song['title_print'], header_printed, log=True)
        # print_message(f"- {region} song {title_or_artist} matched with {round(match_similarity,2)}% accuracy")
        return True
    elif (match_similarity > 80):
        lazy_print_song_header(wiki_song['title_print'], header_printed, log=True)

        if game.ARGS.strict:
            print_message(f"- Rejected {region} song {title_or_artist} matched with {round(match_similarity,2)}% accuracy (strict mode)", bcolors.FAIL)
            return False

        print_message(f"- {region} song {title_or_artist} matched with {round(match_similarity,2)}% accuracy", bcolors.WARNING)
        return True
    else:
        # Allow cases where wiki artist doesn't include extra info
        # ex. 蓮ノ空女学院スクールアイドルクラブ「Link! Like! ラブライブ!」 vs 蓮ノ空女学院スクールアイドルクラブ
        # ex. UNISON SQUARE GARDEN「ブルーロック」vs UNISON SQUARE GARDEN
        if normalized_wiki_song_title_or_artist in normalized_target_song_title_or_artist:
            trimmed_target = re.sub(r'「.*?」$', '', normalized_target_song_title_or_artist).strip()
            if normalize_title(trimmed_target) == normalized_wiki_song_title_or_artist:
                lazy_print_song_header(wiki_song['title_print'], header_printed, log=True)

                print_message(f"- {region} song {title_or_artist} partially matched (JSON: {target_song[title_or_artist]} vs Wiki: {wiki_song[title_or_artist]})", bcolors.WARNING)
                return True

        return False
