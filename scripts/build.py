#!/usr/bin/env python3
"""
build.py - data_2026_source.json から horses を自動付与して data_2026.json を生成

使用方法:
  python build.py

フロー:
  1. data_2026_source.json を読み込み（horses無し版）
  2. 各レースのbets[].selectionから馬番を抽出
  3. JV-Link DBから馬名を取得
  4. horsesマスタを自動生成
  5. data_2026.json に出力（horses付き版）
"""

import json
import sqlite3
import re
import os
from pathlib import Path

# 場所コード対応表
JYO_CODE = {
    '札幌': '01', '函館': '02', '福島': '03', '新潟': '04', '東京': '05',
    '中山': '06', '中京': '07', '京都': '08', '阪神': '09', '小倉': '10'
}

# DBパス（Windows/WSL両対応）
DB_PATH_WIN = r'C:\tools\bookmap_like\data\jvlink.db'
DB_PATH_WSL = '/mnt/c/tools/bookmap_like/data/jvlink.db'
DB_PATH = DB_PATH_WSL if os.path.exists(DB_PATH_WSL) else DB_PATH_WIN

# ファイルパス
SCRIPT_DIR = Path(__file__).parent
DASHBOARD_DIR = SCRIPT_DIR.parent
SOURCE_FILE = DASHBOARD_DIR / 'data_2026_source.json'
OUTPUT_FILE = DASHBOARD_DIR / 'data_2026.json'


def parse_race_key(race_key: str) -> tuple:
    """
    レースキーをパースして (race_date, jyo_code, race_num) を返す
    例: "2026-01-05_中山5R" -> ("20260105", "06", 5)
    """
    # 日付部分とレース部分を分割
    match = re.match(r'(\d{4}-\d{2}-\d{2})_(.+?)(\d+)R', race_key)
    if not match:
        return None, None, None

    date_str = match.group(1).replace('-', '')  # 20260105
    place_name = match.group(2)  # 中山
    race_num = match.group(3).zfill(2)  # "5" -> "05" (ゼロパディング)

    jyo_code = JYO_CODE.get(place_name)
    if not jyo_code:
        return None, None, None

    return date_str, jyo_code, race_num


def extract_horse_numbers(bets: list) -> set:
    """
    bets配列からselectionを解析して馬番のセットを返す
    """
    horse_nums = set()
    for bet in bets:
        selection = bet.get('selection', '')
        if not selection:
            continue
        # ハイフン区切りで分割（馬連、3連複等）
        nums = str(selection).split('-')
        for num in nums:
            # 数字のみ抽出
            n = re.sub(r'\D', '', num)
            if n:
                horse_nums.add(n.zfill(2))  # ゼロパディング
    return horse_nums


def get_horse_names(conn, race_date: str, jyo_code: str, race_num: str, horse_nums: set) -> dict:
    """
    DBから馬名を取得してhorsesマスタを返す
    """
    if not horse_nums:
        return {}

    cursor = conn.cursor()

    # race_horsesテーブルから取得
    # umaban: 馬番、bamei: 馬名
    placeholders = ','.join('?' * len(horse_nums))
    query = f"""
    SELECT umaban, bamei
    FROM race_horses
    WHERE race_date = ? AND jyo_code = ? AND race_num = ?
      AND umaban IN ({placeholders})
    """

    params = [race_date, jyo_code, race_num] + list(horse_nums)

    try:
        cursor.execute(query, params)
        rows = cursor.fetchall()

        horses = {}
        for umaban, bamei in rows:
            # ゼロパディングして格納
            key = str(umaban).zfill(2)
            horses[key] = bamei

        return horses
    except sqlite3.Error as e:
        print(f"  DB Error: {e}")
        return {}


def build():
    """メイン処理"""
    print(f"=== build.py ===")
    print(f"Source: {SOURCE_FILE}")
    print(f"Output: {OUTPUT_FILE}")
    print()

    # ソースファイル読み込み
    if not SOURCE_FILE.exists():
        print(f"Error: {SOURCE_FILE} not found")
        return False

    with open(SOURCE_FILE, 'r', encoding='utf-8') as f:
        data = json.load(f)

    # DB接続
    if not os.path.exists(DB_PATH):
        print(f"Warning: DB not found at {DB_PATH}")
        print("Horses will not be populated from DB")
        conn = None
    else:
        conn = sqlite3.connect(DB_PATH)

    # racesオブジェクトを処理
    races = data.get('races', {})
    updated_count = 0

    for race_key, race_data in races.items():
        bets = race_data.get('bets', [])

        # 既にhorsesがあればスキップ（手動設定を尊重）
        if race_data.get('horses') and len(race_data['horses']) > 0:
            continue

        # レースキーをパース
        race_date, jyo_code, race_num = parse_race_key(race_key)
        if not race_date:
            print(f"  Skip: {race_key} (parse failed)")
            continue

        # 馬番を抽出
        horse_nums = extract_horse_numbers(bets)
        if not horse_nums:
            continue

        # DBから馬名を取得
        if conn:
            horses = get_horse_names(conn, race_date, jyo_code, race_num, horse_nums)
            if horses:
                race_data['horses'] = horses
                updated_count += 1
                print(f"  Updated: {race_key} ({len(horses)} horses)")

    if conn:
        conn.close()

    # 出力
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print()
    print(f"=== Complete ===")
    print(f"Updated {updated_count} races")
    print(f"Output: {OUTPUT_FILE}")

    return True


if __name__ == '__main__':
    build()
