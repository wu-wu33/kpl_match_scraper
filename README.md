# KPL Match Data Scraper

A Selenium-based Python scraper for King Pro League (KPL) match data, including player statistics, champion picks, and match outcomes.

## Overview

This tool uses Selenium to crawl KPL match data from the official Honor of Kings esports website. It extracts player KDA, gold, damage, and other performance metrics for both teams in each game.

## Features

- Scrape multi-game matches (BO5, BO7)
- Extract player-level statistics: KDA, gold, damage dealt, damage taken, kill participation
- Determine winning team by analyzing victory image color
- Convert Chinese player/hero/team names to English
- Automatic checkpoint system for resume on interruption
- Detect duplicate heroes (data quality check)
- Export to Excel

## Requirements

    pip install -r requirements.txt

## Setup

### Input Files

You need two Excel files in the same directory:

1. **match_metadata.xlsx**: Match information with columns:
   - `match_id`
   - `league_id`
   - `match_stage_desc`
   - `match_address`

2. **team_list.xlsx**: Team mapping with columns:
   - `team_name` (Chinese name)
   - `team` (English abbreviation)

### Chrome Driver

ChromeDriver is automatically managed by `webdriver-manager`. No manual setup required.

## Usage

    python kpl_match_scraper.py

### Test Mode

To test with only 2 matches, set at the top of the script:

    TEST_MODE = True
    TEST_LIMIT = 2

## Output

- `kpl_spring_2026.xlsx`: Main output file with all match data
- `crawled_matches.txt`: Checkpoint file (tracks completed matches)
- `unknown_winners.txt`: Log of games where winner couldn't be determined
- `hero_duplicate_warnings.txt`: Log of games with duplicate heroes

## Output Format

| Column | Description |
|--------|-------------|
| league_id | League identifier |
| match_stage_desc | Match stage (Regular Season, Playoffs, etc.) |
| match_id | Match identifier |
| game_id | Individual game identifier |
| duration | Game duration |
| player | Player English name |
| position | Top / Jungle / Mid / ADC / Support |
| team | Team abbreviation |
| side | blue / red |
| rivalry | Opponent team |
| result | Win / Lose |
| champion_used | Champion name |
| kill / death / assist | KDA statistics |
| gold | Gold earned |
| damage_dealt | Damage dealt |
| damage_share | Damage share (%) |
| damage_taken | Damage taken |
| damage_taken_share | Damage taken share (%) |
| kill_participation | Kill participation (%) |
| match_address | Match location |

## How It Works

1. Load match metadata and team list from Excel.
2. Open each match page using Selenium.
3. Iterate through each game in the match.
4. Extract KDA overview, matchup data, and player statistics.
5. Determine the winning team by analyzing the victory image color.
6. Convert Chinese names to English using pypinyin.
7. Save results and update checkpoint.

## Technical Details

**Winner detection**: The winning team is identified by analyzing the dominant color (red or blue) of the victory banner image on the matchup page. Pixels are classified by RGB thresholds; games with ambiguous colors are logged and skipped.

**Blue/Red identification**: The website uses a fixed layout — the left panel (`.dhil`) is the blue team and the right panel (`.dhir`) is the red team. Team names are matched against `team_list.xlsx` for English abbreviations.

**Player ID extraction**: Player names follow the format `TeamName.PlayerName`. The script splits at the last dot (`rfind('.')`) to handle team names that contain dots (e.g., `RNG.M`), then converts Chinese player names to English using `pypinyin`.

**KDA extraction**: KDA data is read from the Overview tab (`.tsboxl` container). Each player's KDA is in the format `kills/deaths/assists` and parsed into three integers. The champion name is read from the `alt` or `title` attribute of the image in `.c-icon`.

**Hero duplicate detection**: After extracting all ten players' champions, the script counts occurrences. Duplicates are logged to `hero_duplicate_warnings.txt` as a data quality check.

**Checkpoint and resume**: Progress is saved after each match. If interrupted, re-running the script will skip completed matches and resume.

## Notes

- The script requires Chrome/Chromium installed.
- Headless mode is available (uncomment in the code).
- For large datasets, crawling may take several hours.
- Website structure may change; update selectors if needed.
- Please respect the website's terms of service and use this tool only for academic research.

## Disclaimer

This tool is intended for academic research purposes only. Users are responsible for complying with the website's terms of service and applicable data protection laws.

## Contact

florencewu103@gmail.com
