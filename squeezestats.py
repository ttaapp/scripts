import os
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from datetime import datetime, timedelta
import re
import statistics
from tabulate import tabulate
import argparse
import matplotlib.pyplot as plt
from pathlib import Path
import numpy as np

def parse_duration(duration_str):
    """Converts 'm:ss' or 'h:mm:ss' duration to seconds. Returns None if invalid."""
    if not duration_str or duration_str == "0":
        return None  # Invalid duration
    try:
        # Handle different time formats
        if duration_str.count(':') == 1:
            minutes, seconds = map(int, duration_str.split(':'))
            return minutes * 60 + seconds
        elif duration_str.count(':') == 2:
            hours, minutes, seconds = map(int, duration_str.split(':'))
            return hours * 3600 + minutes * 60 + seconds
        else:
            return None
    except ValueError:
        return None  # Invalid format or non-integer values
    except TypeError: #catch type errors in case duration string is not a string.
        return None

def format_duration(seconds):
    """Converts seconds to minutes:seconds format or hours:minutes:seconds if needed."""
    if seconds >= 3600:
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        remaining_seconds = seconds % 60
        return f"{hours}:{minutes:02d}:{remaining_seconds:02d}"
    else:
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

def extract_file_format(path):
    """Extract file format from path"""
    if not path:
        return "unknown"
    
    ext = Path(path).suffix.lower()
    if ext:
        return ext[1:]  # Remove the dot
    return "unknown"

def extract_year_from_comment(comment):
    """Extract year from comment field if it contains a date"""
    if not comment:
        return None
        
    # Look for patterns like "download 2011-03-18"
    match = re.search(r'\b(19|20)\d{2}\b', comment)
    if match:
        return int(match.group())
    return None

def analyze_music_logs(log_dir="./logs", year_filter=None, search_pattern=None, html_output=None, top_count=None, 
                      plot_graphs=False, output_dir="./stats"):
    """Analyzes XML music log files and generates statistics."""

    if not os.path.exists(log_dir):
        print(f"Error: Directory '{log_dir}' not found.")
        return

    # Create output directory if it doesn't exist
    if plot_graphs and not os.path.exists(output_dir):
        os.makedirs(output_dir)
    
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
                            "stitle": song_element.findtext("stitle"),  # Short title
                            "date": song_element.findtext("date"),
                            "duration": parsed_duration,
                            "player_name": song_element.findtext("playerName"),
                            "player_id": song_element.findtext("playerId"),
                            "path": song_element.findtext("path"),
                            "comment": song_element.findtext("comment"),
                            "time": song_element.findtext("time"),
                            "guid": song_element.findtext("guid"),
                        }
                        
                        # Extract file format from path
                        song["file_format"] = extract_file_format(song["path"])
                        
                        # Extract year from comment if available
                        song["comment_year"] = extract_year_from_comment(song["comment"])
                        
                        # Check if song date is valid
                        try:
                            song_date = datetime.strptime(song["date"], "%Y/%m/%d %H:%M:%S")
                            song_year = song_date.year
                            song["datetime"] = song_date  # Store the parsed datetime
                            
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
    
    # Sort songs by datetime for chronological analysis
    songs.sort(key=lambda x: x["datetime"])
    
    # Statistics calculations
    total_songs = len(songs)
    unique_albums = len(set(song["album"] for song in songs if song["album"]))
    unique_titles = len(set(song["title"] for song in songs if song["title"]))
    unique_artists = len(set(song["artist"] for song in songs if song["artist"]))

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

    # File format statistics
    format_counts = Counter(song["file_format"] for song in songs)
    top_formats = format_counts.most_common()

    # Time-based statistics
    month_counts = Counter(song["datetime"].strftime("%Y-%m") for song in songs)
    sorted_months = sorted(month_counts.items(), key=lambda item: datetime.strptime(item[0], "%Y-%m"), reverse=True)

    year_counts = Counter(song["datetime"].strftime("%Y") for song in songs)
    sorted_years = sorted(year_counts.items(), key=lambda item: datetime.strptime(item[0], "%Y"), reverse=True)

    # Day of week and hour of day statistics
    day_of_week_counts = Counter(song["datetime"].strftime("%A") for song in songs)
    # Sort by day of week (Monday first)
    day_order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    sorted_days = [(day, day_of_week_counts.get(day, 0)) for day in day_order]
    
    hour_counts = Counter(song["datetime"].hour for song in songs)
    sorted_hours = sorted(hour_counts.items())

    # Calculate listening patterns
    player_counts = Counter(song["player_name"] for song in songs if song["player_name"])
    sorted_players = sorted(player_counts.items(), key=lambda item: item[1], reverse=True)

    # Duration statistics
    durations = [song["duration"] for song in songs]
    avg_duration = sum(durations) / len(durations) if durations else 0
    median_duration = statistics.median(durations) if durations else 0
    min_duration = min(durations) if durations else 0
    max_duration = max(durations) if durations else 0
    
    # Calculate total listening time
    total_duration = sum(durations)
    
    # Calculate listening sessions
    # A new session starts if there's more than 30 minutes between songs
    session_gap = 30 * 60  # 30 minutes in seconds
    sessions = []
    current_session = {"start": None, "end": None, "songs": [], "duration": 0}
    
    for i, song in enumerate(songs):
        if i == 0 or (song["datetime"] - songs[i-1]["datetime"]).total_seconds() > session_gap:
            # End previous session if exists
            if current_session["start"] is not None:
                sessions.append(current_session)
            
            # Start new session
            current_session = {
                "start": song["datetime"],
                "end": song["datetime"] + timedelta(seconds=song["duration"]),
                "songs": [song],
                "duration": song["duration"]
            }
        else:
            # Continue current session
            current_session["songs"].append(song)
            current_session["end"] = song["datetime"] + timedelta(seconds=song["duration"])
            current_session["duration"] += song["duration"]
    
    # Add the last session
    if current_session["start"] is not None:
        sessions.append(current_session)
    
    # Calculate session statistics
    session_count = len(sessions)
    session_durations = [session["duration"] for session in sessions]
    avg_session_duration = sum(session_durations) / len(session_durations) if session_durations else 0
    median_session_duration = statistics.median(session_durations) if session_durations else 0
    max_session_duration = max(session_durations) if session_durations else 0
    
    session_song_counts = [len(session["songs"]) for session in sessions]
    avg_songs_per_session = sum(session_song_counts) / len(session_song_counts) if session_song_counts else 0
    
    # Calculate most common session starting hours
    session_start_hours = Counter(session["start"].hour for session in sessions)
    top_session_hours = session_start_hours.most_common(5)
    
    # Comment year statistics (when music was added/downloaded)
    comment_years = [song["comment_year"] for song in songs if song["comment_year"] is not None]
    comment_year_counts = Counter(comment_years)
    sorted_comment_years = sorted(comment_year_counts.items(), reverse=True)
    
    # Output generation
    year_range_str = f" ({year_filter})" if year_filter else ""
    output = f"SqueezeCenter Play Statistics{year_range_str}\n\n"
    
    # ===== SUMMARY SECTION =====
    output += "=== SUMMARY ===\n"
    output += f"Total songs played: {total_songs}\n"
    output += f"Unique albums: {unique_albums}\n"
    output += f"Unique titles: {unique_titles}\n"
    output += f"Unique artists: {unique_artists}\n"
    output += f"Total listening time: {format_duration(total_duration)} ({total_duration/3600:.1f} hours)\n"
    output += f"Average song duration: {format_duration(int(avg_duration))}\n"
    output += f"Median song duration: {format_duration(int(median_duration))}\n"
    output += f"Shortest song: {format_duration(int(min_duration))}\n"
    output += f"Longest song: {format_duration(int(max_duration))}\n\n"
    
    # ===== TOP LISTS SECTION =====
    output += "=== TOP ARTISTS, ALBUMS & SONGS ===\n"
    output += f"Top {top_count or 10} artists:\n" + tabulate([(artist, count) for artist, count in top_artists], headers=["Artist", "Count"]) + "\n\n"
    output += f"Top {top_count or 10} albums:\n" + tabulate([(album, artist, count) for (album, artist), count in top_albums], headers=["Album", "Artist", "Count"]) + "\n\n"
    output += f"Top {top_count or 10} songs:\n" + tabulate([(title, artist, count) for (title, artist), count in top_titles], headers=["Song", "Artist", "Count"]) + "\n\n"
    
    # ===== LISTENING PATTERNS SECTION =====
    output += "=== LISTENING PATTERNS ===\n"
    output += f"Total listening sessions: {session_count}\n"
    output += f"Average session duration: {format_duration(int(avg_session_duration))} ({avg_session_duration/3600:.1f} hours)\n"
    output += f"Median session duration: {format_duration(int(median_session_duration))}\n"
    output += f"Longest session: {format_duration(int(max_session_duration))} ({max_session_duration/3600:.1f} hours)\n"
    output += f"Average songs per session: {avg_songs_per_session:.1f}\n\n"
    
    output += "Top session starting hours:\n"
    for hour, count in top_session_hours:
        output += f"  {hour:02d}:00 - {hour:02d}:59: {count} sessions\n"
    output += "\n"
    
    output += "Songs by day of week:\n"
    for day, count in sorted_days:
        percentage = count / total_songs * 100
        output += f"  {day}: {count} ({percentage:.1f}%)\n"
    output += "\n"
    
    # ===== TECHNICAL DETAILS SECTION =====
    output += "=== TECHNICAL DETAILS ===\n"
    output += "Music file formats:\n"
    for format_name, count in top_formats:
        percentage = count / total_songs * 100
        output += f"  {format_name}: {count} ({percentage:.1f}%)\n"
    output += "\n"
    
    output += "Songs per player:\n"
    for player, count in sorted_players:
        percentage = count / total_songs * 100
        output += f"  {player}: {count} ({percentage:.1f}%)\n"
    output += "\n"
    
    # ===== TIME STATISTICS SECTION =====
    output += "=== CHRONOLOGICAL STATISTICS ===\n"
    if sorted_comment_years:
        output += "Music added by year (from comments):\n"
        for year, count in sorted_comment_years:
            output += f"  {year}: {count}\n"
        output += "\n"
    
    output += "Songs per year:\n"
    for year, count in sorted_years:
        output += f"  {year}: {count}\n"
    output += "\n"
    
    output += "Songs per month:\n"
    month_data = [(month, count) for month, count in sorted_months]
    month_table = []
    for i in range(0, len(month_data), 3):
        row = month_data[i:i + 3]
        month_table.append([f"{month}: {count}" for month, count in row])
    output += tabulate(month_table, tablefmt="plain") + "\n\n"
    
    # ===== PARALLEL PLAY SECTION =====
    output += "=== PARALLEL PLAY STATISTICS ===\n"
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
    
    # Generate plots if requested
    if plot_graphs:
        # Plot 1: Listening by month
        plt.figure(figsize=(12, 6))
        months = [m[0] for m in sorted_months][-12:]  # Last 12 months
        counts = [m[1] for m in sorted_months][-12:]  # Last 12 months
        plt.bar(months, counts)
        plt.title('Songs Played by Month (Last 12 Months)')
        plt.xlabel('Month')
        plt.ylabel('Songs Played')
        plt.xticks(rotation=45)
        plt.tight_layout()
        plt.savefig(os.path.join(output_dir, 'songs_by_month.png'))
        plt.close()
        
        # Plot 2: Listening by hour of day
        plt.figure(figsize=(10, 6))
        hours = [h[0] for h in sorted_hours]
        hour_counts = [h[1] for h in sorted_hours]
        plt.bar(hours, hour_counts)
        plt.title('Songs Played by Hour of Day')
        plt.xlabel('Hour')
        plt.ylabel('Songs Played')
        plt.xticks(range(0, 24))
        plt.tight_layout()
        plt.savefig(os.path.join(output_dir, 'songs_by_hour.png'))
        plt.close()
        
        # Plot 3: Listening by day of week
        plt.figure(figsize=(10, 6))
        days = [d[0] for d in sorted_days]
        day_counts = [d[1] for d in sorted_days]
        plt.bar(days, day_counts)
        plt.title('Songs Played by Day of Week')
        plt.xlabel('Day')
        plt.ylabel('Songs Played')
        plt.tight_layout()
        plt.savefig(os.path.join(output_dir, 'songs_by_day.png'))
        plt.close()
        
        # Plot 4: File formats
        plt.figure(figsize=(10, 6))
        formats = [f[0] for f in top_formats]
        format_counts = [f[1] for f in top_formats]
        plt.pie(format_counts, labels=formats, autopct='%1.1f%%')
        plt.title('Music File Formats')
        plt.tight_layout()
        plt.savefig(os.path.join(output_dir, 'file_formats.png'))
        plt.close()
        
        # Add note about plots to output
        output += "\nGraphs have been generated in the " + output_dir + " directory.\n"

    print(output) # Print to console.

    if html_output:
        html = f"<html><head><title>SqueezeCenter Statistics</title></head><body><pre>{output}</pre>"
        
        # Embed images in HTML if plots were generated
        if plot_graphs:
            html += "<h2>Visualizations</h2>"
            html += "<div><img src='songs_by_month.png' alt='Songs by Month'></div>"
            html += "<div><img src='songs_by_hour.png' alt='Songs by Hour'></div>"
            html += "<div><img src='songs_by_day.png' alt='Songs by Day'></div>"
            html += "<div><img src='file_formats.png' alt='File Formats'></div>"
        
        html += "</body></html>"
        with open(f"{html_output}.html", "w") as f:
            f.write(html)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Analyze SqueezeCenter music log files.")
    parser.add_argument("-o", "--output", help="Output to HTML file")
    parser.add_argument("-y", "--year", help="Filter by year (e.g., 2023) or year range (e.g., 2020-2023)")
    parser.add_argument("-s", "--search", help="Filter by search pattern")
    parser.add_argument("-t", "--top", type=int, help="Number of top results to display")
    parser.add_argument("-p", "--plot", action="store_true", help="Generate visualization plots")
    parser.add_argument("-d", "--output-dir", default="./stats", help="Directory for output files (default: ./stats)")
    args = parser.parse_args()

    analyze_music_logs(log_dir="./logs", year_filter=args.year, search_pattern=args.search, 
                      html_output=args.output, top_count=args.top, plot_graphs=args.plot, 
                      output_dir=args.output_dir)