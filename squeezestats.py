import os
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from datetime import datetime
from tabulate import tabulate
import argparse

def parse_duration(duration_str):
    """Converts 'm:ss' duration to seconds. Returns None if invalid."""
    if not duration_str or duration_str == "0":
        return None  # Invalid duration
    try:
        minutes, seconds = map(int, duration_str.split(':'))
        return minutes * 60 + seconds
    except ValueError:
        return None  # Invalid format or non-integer values
    except TypeError: #catch type errors in case duration string is not a string.
        return None

def format_duration(seconds):
    """Converts seconds to minutes:seconds format."""
    minutes = seconds // 60
    remaining_seconds = seconds % 60
    return f"{minutes:02d}:{remaining_seconds:02d}"

def parse_year_filter(year_filter):
    """Parse year filter string to support single year or year range (e.g. '2020-2023')"""
    if not year_filter:
        return None
        
    if '-' in year_filter:
        try:
            start_year, end_year = map(int, year_filter.split('-'))
            return range(start_year, end_year + 1)  # Include the end year
        except ValueError:
            print(f"Error: Invalid year range format '{year_filter}'. Use format 'YYYY-YYYY'.")
            return None
    else:
        try:
            return [int(year_filter)]  # Return as a list for consistent handling
        except ValueError:
            print(f"Error: Invalid year '{year_filter}'. Use format 'YYYY' or 'YYYY-YYYY'.")
            return None

def analyze_music_logs(log_dir="./logs", year_filter=None, search_pattern=None, html_output=None, top_count=None):
    """Analyzes XML music log files and generates statistics."""

    if not os.path.exists(log_dir):
        print(f"Error: Directory '{log_dir}' not found.")
        return

    # Parse year filter
    years = parse_year_filter(year_filter)
    
    songs = []
    discarded_count = 0  # Initialize discarded count
    
    # Dictionary to track songs played at the exact same time
    parallel_plays = defaultdict(list)
    parallel_play_count = 0  # Counter for parallel plays
    
    for filename in os.listdir(log_dir):
        if filename.endswith(".xml"):
            filepath = os.path.join(log_dir, filename)
            try:
                tree = ET.parse(filepath)
                root = tree.getroot()

                for song_element in root.findall("song"):
                    duration = song_element.findtext("duration")
                    parsed_duration = parse_duration(duration)

                    if parsed_duration is not None:  # Only add songs with valid durations
                        song = {
                            "artist": song_element.findtext("artist"),
                            "album": song_element.findtext("album"),
                            "title": song_element.findtext("title"),
                            "date": song_element.findtext("date"),
                            "duration": parsed_duration,
                            "player_name": song_element.findtext("playerName"),
                        }
                        
                        # Check if song date is valid
                        try:
                            song_date = datetime.strptime(song["date"], "%Y/%m/%d %H:%M:%S")
                            song_year = song_date.year
                            
                            # Apply year filter
                            year_match = years is None or song_year in years
                            
                            if year_match and (search_pattern is None or any(search_pattern.lower() in str(song[key]).lower() for key in song if song[key])):
                                # Create a key to identify parallel playback (same title and date)
                                if song["title"] and song["date"]:
                                    parallel_key = (song["title"], song["date"])
                                    parallel_plays[parallel_key].append(song)
                                songs.append(song)
                            else:
                                discarded_count += 1
                        except (ValueError, TypeError):
                            discarded_count += 1  # Invalid date format
                    else:
                        discarded_count += 1  # Increment discarded count

            except ET.ParseError as e:
                print(f"Error parsing XML file {filepath}: {e}")
            except FileNotFoundError:
                print(f"Error: File '{filepath}' not found.")

    if not songs:
        print("No song data found.")
        return

    # Process parallel plays - keep only one instance of each parallel play group
    deduplicated_songs = []
    parallel_play_info = []  # Store info about parallel plays for reporting
    
    # First, collect songs that don't have parallel plays
    for song in songs:
        if song["title"] and song["date"]:
            parallel_key = (song["title"], song["date"])
            if len(parallel_plays[parallel_key]) <= 1:
                deduplicated_songs.append(song)
        else:
            deduplicated_songs.append(song)
            
    # Then handle parallel plays (only add each group once)
    processed_keys = set()
    for key, group in parallel_plays.items():
        if len(group) > 1 and key not in processed_keys:
            # Add only the first song from each parallel play group
            deduplicated_songs.append(group[0])
            
            # Record information about this parallel play
            title, date = key
            players = [song["player_name"] for song in group]
            parallel_play_info.append({
                "title": title, 
                "date": date,
                "players": players,
                "count": len(group)
            })
            
            # Count parallels (number of duplicates removed)
            parallel_play_count += len(group) - 1
            
            processed_keys.add(key)
    
    # Use deduplicated songs for statistics
    songs = deduplicated_songs
    
    # Statistics calculations
    total_songs = len(songs)
    unique_albums = len(set(song["album"] for song in songs if song["album"]))
    unique_titles = len(set(song["title"] for song in songs if song["title"]))

    # Count albums once per continuous play
    played_albums = []
    last_album = None
    for song in songs:
        if song["album"] and song["album"] != last_album:
            played_albums.append((song["album"], song["artist"]))
            last_album = song["album"]
    album_counts = Counter(played_albums)
    top_albums = album_counts.most_common(top_count or 10)

    title_counts = Counter((song["title"], song["artist"]) for song in songs if song["title"])
    top_titles = title_counts.most_common(top_count or 10)

    artist_counts = Counter(song["artist"] for song in songs if song["artist"])
    top_artists = artist_counts.most_common(top_count or 10)

    month_counts = Counter(datetime.strptime(song["date"], "%Y/%m/%d %H:%M:%S").strftime("%Y-%m") for song in songs if song["date"])
    sorted_months = sorted(month_counts.items(), key=lambda item: datetime.strptime(item[0], "%Y-%m"), reverse=True)

    year_counts = Counter(datetime.strptime(song["date"], "%Y/%m/%d %H:%M:%S").strftime("%Y") for song in songs if song["date"])
    sorted_years = sorted(year_counts.items(), key=lambda item: datetime.strptime(item[0], "%Y"), reverse=True)

    player_counts = Counter(song["player_name"] for song in songs if song["player_name"])
    sorted_players = sorted(player_counts.items(), key=lambda item: item[1], reverse=True) #sort players

    average_duration = sum(song["duration"] for song in songs) / len(songs) if songs else 0

    # Output generation
    year_range_str = f" ({year_filter})" if year_filter else ""
    output = f"SqueezeCenter Play Statistics{year_range_str}\n\n"
    output += f"Top {top_count or 10} artists:\n" + tabulate([(artist, count) for artist, count in top_artists], headers=["Artist", "Count"]) + "\n\n"
    output += f"Top {top_count or 10} albums:\n" + tabulate([(album, artist, count) for (album, artist), count in top_albums], headers=["Album", "Artist", "Count"]) + "\n\n"
    output += f"Top {top_count or 10} songs:\n" + tabulate([(title, artist, count) for (title, artist), count in top_titles], headers=["Song", "Artist", "Count"]) + "\n\n"
    output += f"Unique albums: {unique_albums}\nUnique titles: {unique_titles}\n\n"

    output += "Songs per month:\n"
    month_data = [(month, count) for month, count in sorted_months]
    month_table = []
    for i in range(0, len(month_data), 3):
        row = month_data[i:i + 3]
        month_table.append([f"{month}: {count}" for month, count in row])
    output += tabulate(month_table, tablefmt="plain") + "\n\n"

    output += "Songs per year:\n"
    for year, count in sorted_years:
        output += f"  {year}: {count}\n"
    output += f"\nTotal songs: {total_songs}\n\n"

    output += "Songs per player:\n"
    for player, count in sorted_players:
        output += f"  {player}: {count}\n"
    output += "\n"

    if average_duration:
        output += f"Average song duration: {format_duration(int(average_duration))}\n\n"

    # Add parallel play stats
    output += f"Parallel plays detected: {len(parallel_play_info)}\n"
    output += f"Duplicate entries excluded: {parallel_play_count}\n\n"

    # Show some examples of parallel plays if any found
    if parallel_play_info:
        output += "Examples of parallel plays:\n"
        example_count = min(5, len(parallel_play_info))  # Show up to 5 examples
        for i in range(example_count):
            info = parallel_play_info[i]
            player_list = ", ".join(info["players"])
            output += f"  '{info['title']}' on {info['date']} - played on {info['count']} players: {player_list}\n"
        
        if len(parallel_play_info) > example_count:
            output += f"  ... and {len(parallel_play_info) - example_count} more\n"
        output += "\n"

    output += f"Discarded songs: {discarded_count}\n"

    print(output) # Print to console.

    if html_output:
        html = f"<html><head><title>SqueezeCenter Statistics</title></head><body><pre>{output}</pre></body></html>"
        with open(f"{html_output}.html", "w") as f:
            f.write(html)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Analyze SqueezeCenter music log files.")
    parser.add_argument("-o", "--output", help="Output to HTML file")
    parser.add_argument("-y", "--year", help="Filter by year (e.g., 2023) or year range (e.g., 2020-2023)")
    parser.add_argument("-s", "--search", help="Filter by search pattern")
    parser.add_argument("-t", "--top", type=int, help="Number of top results to display")
    args = parser.parse_args()

    analyze_music_logs(log_dir="./logs", year_filter=args.year, search_pattern=args.search, html_output=args.output, top_count=args.top)