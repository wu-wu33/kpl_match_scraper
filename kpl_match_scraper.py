import time
import re
import os
import io
import requests
from collections import Counter
from PIL import Image
import pandas as pd
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.action_chains import ActionChains
from webdriver_manager.chrome import ChromeDriverManager
from pypinyin import pinyin, Style


# ================= Helper Functions =================
def chinese_to_english(text):
    """Convert Chinese text to English (first letter uppercase, rest lowercase)."""
    if not text or not isinstance(text, str):
        return text
    result = ''.join([p[0].capitalize() for p in pinyin(text, style=Style.NORMAL)])
    return result[0].upper() + result[1:].lower() if result else result


def parse_number(value):
    """Convert '42.1k' or '15.13%' to numeric values (42100 or 15.13)."""
    if not value or value == '0':
        return 0
    value = str(value).strip().lower()
    try:
        if 'k' in value:
            return int(float(value.replace('k', '')) * 1000)
        elif '%' in value:
            return float(value.replace('%', ''))
        else:
            return float(value) if '.' in value else int(value)
    except:
        return 0


def match_team_name(team_name, team_df):
    """Match Chinese team name to English abbreviation."""
    if not team_name:
        return team_name

    matched = team_df[team_df['team_name'] == team_name]
    if not matched.empty:
        return matched.iloc[0]['team']

    matched = team_df[team_df['team_name'].str.startswith(team_name, na=False)]
    if not matched.empty:
        return matched.iloc[0]['team']

    matched = team_df[team_df['team_name'].str.contains(team_name, na=False)]
    if not matched.empty:
        return matched.iloc[0]['team']

    matched = team_df[team_df['team'] == team_name]
    if not matched.empty:
        return matched.iloc[0]['team']

    return team_name


def extract_team_and_player(full_name, team_df):
    """Parse 'BeijingJDG.Qingyu' into team and player name."""
    if not full_name or '.' not in full_name:
        return None, chinese_to_english(full_name) if full_name else (None, '')

    last_dot = full_name.rfind('.')
    team_part = full_name[:last_dot]
    player_part = full_name[last_dot + 1:]

    team_full_name = team_part
    player_en = chinese_to_english(player_part)
    return team_full_name, player_en


def extract_duration(driver):
    """Extract match duration."""
    try:
        selectors = ['.center1', '.time-text', '.match-duration']
        for sel in selectors:
            try:
                elem = driver.find_element(By.CSS_SELECTOR, sel)
                text = elem.text.strip()
                if ':' in text and len(text) <= 8:
                    return text
            except:
                continue
        page_text = driver.find_element(By.TAG_NAME, 'body').text
        match = re.search(r'(\d{1,2}:\d{2})', page_text)
        if match:
            return match.group(1)
    except:
        pass
    return 'N/A'


# ================= Image Color Analysis =================
def get_dominant_color(image_url):
    """Download image and detect dominant color ('red' or 'blue')."""
    try:
        response = requests.get(image_url, timeout=10)
        img = Image.open(io.BytesIO(response.content))
        img = img.convert('RGB')
        img.thumbnail((50, 50))
        pixels = list(img.getdata())

        red_pixels = 0
        blue_pixels = 0
        for r, g, b in pixels:
            if r > g + 30 and r > b + 30:
                red_pixels += 1
            elif b > r + 30 and b > g + 30:
                blue_pixels += 1

        total = len(pixels)
        red_ratio = red_pixels / total
        blue_ratio = blue_pixels / total

        print(f"        Color analysis: red {red_ratio:.2%}, blue {blue_ratio:.2%}")
        if red_ratio > 0.3:
            return 'red'
        elif blue_ratio > 0.3:
            return 'blue'
        return 'unknown'
    except Exception as e:
        print(f"        Color analysis failed: {e}")
        return 'unknown'


# ================= Hero Duplicate Detection =================
def check_hero_duplicates(game_records, game_id):
    """Check if any hero appears more than once in a game."""
    heroes = []
    for record in game_records:
        hero = record.get('champion_used', '')
        if hero and hero != '':
            heroes.append(hero)

    hero_counts = Counter(heroes)
    duplicates = {h: count for h, count in hero_counts.items() if count > 1}

    if duplicates:
        print(f"      WARNING: Duplicate heroes detected! game_id={game_id}")
        print(f"        Duplicates: {duplicates}")
        return True, duplicates, heroes
    return False, {}, heroes


# ================= Crawl One Match =================
def crawl_one_match_safe(match_meta_row, team_df):
    """Crawl a single match and return list of records."""
    match_id = match_meta_row['match_id']
    league_id = match_meta_row['league_id']
    match_stage = match_meta_row['match_stage_desc']
    match_address = match_meta_row['match_address']
    match_url = f"https://pvp.qq.com/matchdata/scheduleDetails.html?league_id={league_id}&match_id={match_id}"

    print(f"\n>>> Crawling: {match_id} ({match_stage}, {match_address})")

    options = webdriver.ChromeOptions()
    # options.add_argument('--headless')
    options.add_argument('--disable-blink-features=AutomationControlled')
    options.add_argument('user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)

    all_game_records = []

    try:
        driver.get(match_url)
        WebDriverWait(driver, 20).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "#every-game-list li"))
        )
        time.sleep(5)

        game_tabs = driver.find_elements(By.CSS_SELECTOR, "#every-game-list li")
        print(f"  Found {len(game_tabs)} games")

        for game_idx, tab in enumerate(game_tabs, start=1):
            print(f"    Crawling game {game_idx}...")
            game_id = f"{match_id}{game_idx:02d}"

            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", tab)
            time.sleep(1)
            ActionChains(driver).move_to_element(tab).perform()
            time.sleep(0.5)
            driver.execute_script("arguments[0].click();", tab)
            time.sleep(5)

            duration = extract_duration(driver)

            # ========== Step 1: Extract KDA Overview ==========
            print(f"      Extracting KDA overview...")
            overview_tab = driver.find_element(By.XPATH, "//li[contains(text(), 'Overview')]")
            if 'active' not in overview_tab.get_attribute('class'):
                overview_tab.click()
                time.sleep(3)

            kda_map = {}
            player_rows = driver.find_elements(By.CSS_SELECTOR, "#tb-box0 .tsboxl")
            print(f"      Found {len(player_rows)} matchup groups")

            for row in player_rows:
                for side in ['.tsboxl:first-child', '.tsboxright']:
                    try:
                        name_elem = row.find_element(By.CSS_SELECTOR, f"{side} .c-rbox .zs1")
                        full_name = name_elem.text.strip()
                        if not full_name:
                            continue

                        if '.' in full_name:
                            chinese_name = full_name.split('.')[-1]
                        else:
                            chinese_name = full_name

                        kda_text = row.find_element(By.CSS_SELECTOR, f"{side} .c-rbox .zs2").text.strip()

                        hero = ""
                        try:
                            hero_img = row.find_element(By.CSS_SELECTOR, f"{side} .c-icon img")
                            hero = hero_img.get_attribute("alt")
                            if not hero:
                                hero = hero_img.get_attribute("title")
                        except:
                            try:
                                hero_text = row.find_element(By.CSS_SELECTOR, f"{side} .c-icon").text
                                if hero_text:
                                    hero = hero_text
                            except:
                                pass

                        kda_parts = kda_text.split('/')
                        if len(kda_parts) >= 3:
                            kda_map[chinese_name] = {
                                'hero': hero,
                                'kill': int(kda_parts[0]),
                                'death': int(kda_parts[1]),
                                'assist': int(kda_parts[2])
                            }
                            print(f"        KDA: {chinese_name} -> {kda_text} (hero: {hero})")
                    except:
                        continue

            print(f"      Extracted KDA for {len(kda_map)} players")

            if len(kda_map) == 0:
                print(f"      WARNING: No KDA data found, game may be invalid")
                continue

            # ========== Step 2: Click Matchup Tab ==========
            matchup_tab = driver.find_element(By.XPATH, "//li[contains(text(), 'Matchup')]")
            driver.execute_script("arguments[0].click();", matchup_tab)
            time.sleep(5)

            # ========== Step 3: Determine Winning Side ==========
            victory_imgs = driver.find_elements(By.XPATH, "//img[contains(@src, 'victory')]")
            visible_imgs = [img for img in victory_imgs if img.is_displayed()]

            winner_team_abbr = None
            if visible_imgs:
                img_src = visible_imgs[0].get_attribute('src')
                print(f"        Victory image URL: {img_src}")
                color = get_dominant_color(img_src)
                print(f"        Image color: {color}")
            else:
                color = None
                print(f"        No victory image found")

            try:
                blue_team_elem = driver.find_element(By.CSS_SELECTOR, ".dw-hero-info .dhil .dhlname")
                red_team_elem = driver.find_element(By.CSS_SELECTOR, ".dw-hero-info .dhir .dhlname")

                blue_full = blue_team_elem.text.strip()
                red_full = red_team_elem.text.strip()

                blue_name = blue_full.rsplit('.', 1)[0] if '.' in blue_full else blue_full
                red_name = red_full.rsplit('.', 1)[0] if '.' in red_full else red_full

                print(f"        Matchup -> Blue: {blue_name}, Red: {red_name}")

                blue_abbr = match_team_name(blue_name, team_df)
                red_abbr = match_team_name(red_name, team_df)

                if color == 'red':
                    winner_team_abbr = red_abbr
                    print(f"        Image is red -> Red team wins: {winner_team_abbr}")
                elif color == 'blue':
                    winner_team_abbr = blue_abbr
                    print(f"        Image is blue -> Blue team wins: {winner_team_abbr}")
                else:
                    print(f"        Cannot determine color")

            except Exception as e:
                print(f"        Failed to get blue/red sides: {e}")
                winner_team_abbr = None

            if not winner_team_abbr:
                print(f"      WARNING: Cannot determine winner for game {game_idx}")
                with open("unknown_winners.txt", "a", encoding="utf-8") as f:
                    f.write(f"{match_id}|{game_idx}\n")
                continue
            else:
                print(f"      Winner of game {game_idx}: {winner_team_abbr}")

            # ========== Step 4: Extract Detailed Matchup Data ==========
            positions_cn = ['Top', 'Jungle', 'Mid', 'ADC', 'Support']
            pos_en_map = {'Top': 'Top', 'Jungle': 'Jungle', 'Mid': 'Mid', 'ADC': 'ADC', 'Support': 'Support'}

            game_records = []

            for pos_idx, pos_cn in enumerate(positions_cn, 1):
                try:
                    print(f"        Processing position {pos_idx}/5: {pos_cn}...")

                    pos_tab = driver.find_element(By.XPATH, f"//div[contains(@class, 'dw-wrap-item') and contains(., '{pos_cn}')]")
                    driver.execute_script("arguments[0].scrollIntoView(true);", pos_tab)
                    time.sleep(0.5)
                    driver.execute_script("arguments[0].click();", pos_tab)
                    time.sleep(3)

                    left_name = driver.find_element(By.CSS_SELECTOR, ".dw-hero-info .dhil .dhlname").text.strip()
                    left_hero = driver.find_element(By.CSS_SELECTOR, ".dw-hero-info .dhil .dhlhero").text.strip()
                    right_name = driver.find_element(By.CSS_SELECTOR, ".dw-hero-info .dhir .dhlname").text.strip()
                    right_hero = driver.find_element(By.CSS_SELECTOR, ".dw-hero-info .dhir .dhlhero").text.strip()

                    print(f"          Left: {left_name}({left_hero}) | Right: {right_name}({right_hero})")

                    metric_rows = driver.find_elements(By.CSS_SELECTOR, ".re-data-li")
                    left_stats = {}
                    right_stats = {}

                    for mrow in metric_rows:
                        try:
                            mname = mrow.find_element(By.CSS_SELECTOR, ".rdc").text.strip()
                            left_val = mrow.find_element(By.CSS_SELECTOR, ".rdl .rdl1-count").text.strip()
                            right_val = mrow.find_element(By.CSS_SELECTOR, ".rdr .rdl1-count").text.strip()

                            col_map = {
                                'Gold': 'gold',
                                'Damage Dealt': 'damage_dealt',
                                'Damage Share': 'damage_share',
                                'Damage Taken': 'damage_taken',
                                'Damage Taken Share': 'damage_taken_share',
                                'Kill Participation': 'kill_participation'
                            }
                            if mname in col_map:
                                left_stats[col_map[mname]] = parse_number(left_val)
                                right_stats[col_map[mname]] = parse_number(right_val)
                        except:
                            continue

                    left_chinese = left_name.split('.')[-1] if '.' in left_name else left_name
                    right_chinese = right_name.split('.')[-1] if '.' in right_name else right_name

                    kda_left = kda_map.get(left_chinese, {})
                    kda_right = kda_map.get(right_chinese, {})

                    team_left_name, player_left = extract_team_and_player(left_name, team_df)
                    team_right_name, player_right = extract_team_and_player(right_name, team_df)

                    team_left_abbr = match_team_name(team_left_name, team_df) if team_left_name else ''
                    team_right_abbr = match_team_name(team_right_name, team_df) if team_right_name else ''

                    side_left = "blue"
                    side_right = "red"

                    result_left = 'Win' if winner_team_abbr and team_left_abbr == winner_team_abbr else 'Lose'
                    result_right = 'Win' if winner_team_abbr and team_right_abbr == winner_team_abbr else 'Lose'

                    hero_left = kda_left.get('hero', '')
                    if not hero_left:
                        hero_left = left_hero
                    hero_right = kda_right.get('hero', '')
                    if not hero_right:
                        hero_right = right_hero

                    record_left = {
                        'league_id': league_id,
                        'match_stage_desc': match_stage,
                        'match_id': match_id,
                        'game_id': game_id,
                        'duration': duration,
                        'player': player_left if player_left else '',
                        'position': pos_en_map[pos_cn],
                        'team': team_left_abbr,
                        'side': side_left,
                        'rivalry': team_right_abbr,
                        'result': result_left,
                        'champion_used': chinese_to_english(hero_left) if hero_left else '',
                        'kill': kda_left.get('kill', 0),
                        'death': kda_left.get('death', 0),
                        'assist': kda_left.get('assist', 0),
                        'gold': left_stats.get('gold', 0),
                        'damage_dealt': left_stats.get('damage_dealt', 0),
                        'damage_share': left_stats.get('damage_share', 0),
                        'damage_taken': left_stats.get('damage_taken', 0),
                        'damage_taken_share': left_stats.get('damage_taken_share', 0),
                        'kill_participation': left_stats.get('kill_participation', 0),
                        'match_address': match_address
                    }
                    game_records.append(record_left)

                    record_right = {
                        'league_id': league_id,
                        'match_stage_desc': match_stage,
                        'match_id': match_id,
                        'game_id': game_id,
                        'duration': duration,
                        'player': player_right if player_right else '',
                        'position': pos_en_map[pos_cn],
                        'team': team_right_abbr,
                        'side': side_right,
                        'rivalry': team_left_abbr,
                        'result': result_right,
                        'champion_used': chinese_to_english(hero_right) if hero_right else '',
                        'kill': kda_right.get('kill', 0),
                        'death': kda_right.get('death', 0),
                        'assist': kda_right.get('assist', 0),
                        'gold': right_stats.get('gold', 0),
                        'damage_dealt': right_stats.get('damage_dealt', 0),
                        'damage_share': right_stats.get('damage_share', 0),
                        'damage_taken': right_stats.get('damage_taken', 0),
                        'damage_taken_share': right_stats.get('damage_taken_share', 0),
                        'kill_participation': right_stats.get('kill_participation', 0),
                        'match_address': match_address
                    }
                    game_records.append(record_right)

                except Exception as e:
                    print(f"        Error processing position {pos_cn}: {e}")
                    continue

            # ========== Step 5: Check Hero Duplicates ==========
            has_duplicate, duplicates, heroes = check_hero_duplicates(game_records, game_id)

            if has_duplicate:
                with open("hero_duplicate_warnings.txt", "a", encoding="utf-8") as f:
                    f.write(f"{match_id}|{game_id}|{duplicates}\n")
                print(f"      Logged to hero_duplicate_warnings.txt")
            else:
                print(f"      Hero check passed ({len(set(heroes))} unique heroes)")

            all_game_records.extend(game_records)

    except Exception as e:
        print(f"  Failed to crawl match {match_id}: {e}")
        return []
    finally:
        driver.quit()

    return all_game_records


# ================= Save Data =================
def save_data(all_data, output_file):
    if not all_data:
        return

    output_df = pd.DataFrame(all_data)
    output_df = output_df.sort_values(by=['match_id', 'game_id']).reset_index(drop=True)
    column_order = [
        'league_id', 'match_stage_desc', 'match_id', 'game_id', 'duration',
        'player', 'position', 'team', 'side', 'rivalry', 'result', 'champion_used',
        'kill', 'death', 'assist', 'gold', 'damage_dealt', 'damage_share',
        'damage_taken', 'damage_taken_share', 'kill_participation', 'match_address'
    ]
    column_order = [col for col in column_order if col in output_df.columns]
    output_df = output_df[column_order]
    output_df.to_excel(output_file, index=False)


# ================= Configuration =================
TEST_MODE = False
TEST_LIMIT = 2
# ================================================


# ================= Main =================
if __name__ == "__main__":
    meta_df = pd.read_excel('match_metadata.xlsx')
    team_df = pd.read_excel('team_list.xlsx')
    output_file = 'kpl_spring_2026.xlsx'
    checkpoint_file = 'crawled_matches.txt'

    print(f"Loaded metadata: {len(meta_df)} matches, {len(team_df)} teams")

    if TEST_MODE:
        target_matches = meta_df.head(TEST_LIMIT)
        print(f"\nTest mode: only crawling first {TEST_LIMIT} matches")
        if os.path.exists(checkpoint_file):
            os.remove(checkpoint_file)
            print("  Cleared checkpoint file")
        completed_match_ids = set()
        all_data = []
    else:
        target_matches = meta_df
        print(f"\nFull mode: crawling all unfinished matches")

        completed_match_ids = set()
        if os.path.exists(checkpoint_file):
            with open(checkpoint_file, 'r') as f:
                completed_match_ids = set(line.strip() for line in f)
            print(f"  Loaded {len(completed_match_ids)} completed matches from checkpoint")

        all_data = []
        if os.path.exists(output_file):
            try:
                existing_df = pd.read_excel(output_file)
                if not existing_df.empty and 'match_id' in existing_df.columns:
                    all_data = existing_df.to_dict('records')
                    existing_match_ids = set(existing_df['match_id'].unique())
                    print(f"  Loaded {len(existing_df)} records, {len(existing_match_ids)} matches from existing Excel")
                    completed_match_ids.update(existing_match_ids)
            except Exception as e:
                print(f"  Failed to read existing data: {e}")

        target_matches = meta_df[~meta_df['match_id'].isin(completed_match_ids)]

    print(f"\nMatches to crawl: {len(target_matches)}")

    if len(target_matches) == 0:
        print("No matches to crawl!")
        exit(0)

    print("\nTarget matches:")
    for idx, row in target_matches.head(10).iterrows():
        print(f"  - {row['match_id']}: {row['match_stage_desc']} @ {row['match_address']}")
    if len(target_matches) > 10:
        print(f"  ... total {len(target_matches)}")

    if not TEST_MODE:
        user_input = input(f"\nStart crawling {len(target_matches)} matches? (y/n): ")
        if user_input.lower() != 'y':
            print("Cancelled")
            exit(0)

    for idx, row in target_matches.iterrows():
        match_id = row['match_id']
        if TEST_MODE:
            print(f"\n{'='*60}")
            print(f"Test progress: {idx+1} / {len(target_matches)}")
            print(f"{'='*60}")
        else:
            actual_completed = len(set([r.get('match_id') for r in all_data if r.get('match_id')]))
            print(f"\n{'='*60}")
            print(f"Progress: {actual_completed + 1} / {len(meta_df)}")
            print(f"{'='*60}")

        records = crawl_one_match_safe(row, team_df)

        if len(records) > 0:
            if not TEST_MODE:
                all_data = [r for r in all_data if r.get('match_id') != match_id]
            all_data.extend(records)

            if not TEST_MODE:
                completed_match_ids.add(match_id)
                save_data(all_data, output_file)
                with open(checkpoint_file, 'w') as f:
                    for mid in completed_match_ids:
                        f.write(f"{mid}\n")

                print(f"  Saved. Total records: {len(all_data)}")
            else:
                test_output = f'test_{match_id}.xlsx'
                temp_df = pd.DataFrame(records)
                temp_df.to_excel(test_output, index=False)
                print(f"  Test data saved to {test_output}")
        else:
            print(f"  Crawling failed")
            if not TEST_MODE:
                print("  Stopped. Next run will resume from here.")
                break

        time.sleep(3)

    if not TEST_MODE and len(all_data) > 0:
        save_data(all_data, output_file)
        actual_completed_final = len(set([r.get('match_id') for r in all_data if r.get('match_id')]))
        print(f"\nDone! Crawled {len(all_data)} records, {actual_completed_final} matches, saved to '{output_file}'")

        if actual_completed_final >= len(meta_df):
            if os.path.exists(checkpoint_file):
                os.remove(checkpoint_file)
            print("All matches crawled, cleaned up checkpoint file")
    elif TEST_MODE:
        print(f"\nTest done! Crawled {len(all_data)} records")