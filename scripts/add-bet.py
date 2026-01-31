#!/usr/bin/env python3
"""
add-bet.py - ベット情報追加CLIツール
"""
import json
import re
import sqlite3
import sys
from pathlib import Path
from datetime import datetime

# パス設定
DATA_DIR = Path(__file__).parent.parent
DATA_FILE = DATA_DIR / "data_2026.json"
# DBパス（Windows/WSL両対応）
DB_PATH_WIN = Path(r"C:\tools\bookmap_like\data\jvlink.db")
DB_PATH_WSL = Path("/mnt/c/tools/bookmap_like/data/jvlink.db")
DB_PATH = DB_PATH_WSL if DB_PATH_WSL.exists() else DB_PATH_WIN

# 会場コード対応表
JYO_CODE = {
    "札幌": "01", "函館": "02", "福島": "03", "新潟": "04", "東京": "05",
    "中山": "06", "中京": "07", "京都": "08", "阪神": "09", "小倉": "10"
}

# 有効な券種
VALID_TYPES = ["単勝", "複勝", "馬連", "ワイド", "枠連", "馬単", "3連複", "3連単"]

# 曜日
WEEKDAYS = ["月", "火", "水", "木", "金", "土", "日"]


def get_horse_names(race_date: str, jyo_code: str, race_num: int) -> dict:
    """JV-Link DBから馬名を取得"""
    if not DB_PATH.exists():
        print(f"  ⚠️ DB未接続: {DB_PATH}")
        return {}

    try:
        conn = sqlite3.connect(str(DB_PATH))
        cursor = conn.cursor()
        cursor.execute("""
            SELECT umaban, bamei FROM race_horses
            WHERE race_date = ? AND jyo_code = ? AND race_num = ?
            ORDER BY CAST(umaban AS INTEGER)
        """, (race_date, jyo_code, race_num))
        result = {row[0].zfill(2): row[1] for row in cursor.fetchall()}
        conn.close()
        return result
    except Exception as e:
        print(f"  ⚠️ DB照会エラー: {e}")
        return {}


def validate_date(date_str: str) -> bool:
    """日付バリデーション"""
    try:
        datetime.strptime(date_str, "%Y-%m-%d")
        return True
    except ValueError:
        return False


def validate_selection(selection: str, bet_type: str) -> bool:
    """馬番バリデーション"""
    # 枠連は枠番（1-8）
    if bet_type == "枠連":
        pattern = r"^\d(-\d)?$"
    else:
        # 通常の馬番
        pattern = r"^\d{1,2}(-\d{1,2}){0,2}$"
    return bool(re.match(pattern, selection))


def get_day_of_week(date_str: str) -> str:
    """曜日を取得"""
    dt = datetime.strptime(date_str, "%Y-%m-%d")
    return WEEKDAYS[dt.weekday()]


def load_data() -> dict:
    """JSONデータを読み込み"""
    if not DATA_FILE.exists():
        return {
            "lastUpdated": "",
            "summary": {"totalInvest": 0, "totalPayout": 0, "totalProfit": 0, "roi": 0},
            "monthly": [],
            "daily": [],
            "races": {},
            "weaponStats": {},
            "weaponBreakdown": []
        }

    with open(DATA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_data(data: dict):
    """JSONデータを保存"""
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def update_summary(data: dict):
    """サマリーを再計算"""
    total_invest = 0
    total_payout = 0

    for race_key, race in data.get("races", {}).items():
        for bet in race.get("bets", []):
            total_invest += bet.get("amount", 0)
            total_payout += bet.get("payout", 0)

    data["summary"]["totalInvest"] = total_invest
    data["summary"]["totalPayout"] = total_payout
    data["summary"]["totalProfit"] = total_payout - total_invest
    data["summary"]["roi"] = round(total_payout / total_invest * 100) if total_invest > 0 else 0


def update_daily(data: dict, date: str, dow: str):
    """日別データを更新"""
    # 該当日のレースを集計
    invest = 0
    payout = 0
    note = ""

    for race_key, race in data.get("races", {}).items():
        if race_key.startswith(date):
            for bet in race.get("bets", []):
                invest += bet.get("amount", 0)
                payout += bet.get("payout", 0)
            if race.get("title"):
                note = race["title"]

    profit = payout - invest

    # 既存のdailyエントリを探す
    daily_entry = None
    for d in data["daily"]:
        if d["date"] == date:
            daily_entry = d
            break

    if daily_entry:
        daily_entry["invest"] = invest
        daily_entry["payout"] = payout
        daily_entry["profit"] = profit
        if note:
            daily_entry["note"] = note
    else:
        data["daily"].append({
            "date": date,
            "dayOfWeek": dow,
            "invest": invest,
            "payout": payout,
            "profit": profit,
            "cumulative": 0,
            "note": note
        })
        data["daily"].sort(key=lambda x: x["date"])

    # cumulative再計算
    cumulative = 0
    for d in data["daily"]:
        cumulative += d["profit"]
        d["cumulative"] = cumulative


def update_monthly(data: dict):
    """月別データを更新"""
    monthly_data = {}

    for d in data["daily"]:
        month = d["date"][:7]  # "YYYY-MM"
        if month not in monthly_data:
            monthly_data[month] = {"invest": 0, "payout": 0}
        monthly_data[month]["invest"] += d["invest"]
        monthly_data[month]["payout"] += d["payout"]

    data["monthly"] = []
    for month, m_data in sorted(monthly_data.items()):
        profit = m_data["payout"] - m_data["invest"]
        roi = round(m_data["payout"] / m_data["invest"] * 100) if m_data["invest"] > 0 else 0
        data["monthly"].append({
            "month": month,
            "invest": m_data["invest"],
            "payout": m_data["payout"],
            "profit": profit,
            "roi": roi
        })


def main():
    print("\n" + "="*50)
    print("  ベット追加ツール")
    print("="*50 + "\n")

    # 1. 日付入力
    while True:
        date = input("日付 (YYYY-MM-DD): ").strip()
        if validate_date(date):
            break
        print("  ❌ 無効な形式です。例: 2026-02-01")

    dow = get_day_of_week(date)
    print(f"  → {date} ({dow})")

    # 2. 会場入力
    while True:
        venue = input("会場 (東京/中山/京都/阪神...): ").strip()
        if venue in JYO_CODE:
            jyo_code = JYO_CODE[venue]
            break
        print(f"  ❌ 無効な会場です。選択肢: {', '.join(JYO_CODE.keys())}")

    # 3. レース番号入力
    while True:
        try:
            race_num = int(input("レース番号 (1-12): ").strip())
            if 1 <= race_num <= 12:
                break
        except ValueError:
            pass
        print("  ❌ 1-12の数字を入力してください")

    race_name = f"{venue}{race_num}R"
    race_key = f"{date}_{race_name}"
    race_date = date.replace("-", "")

    print(f"\n  📍 {race_key}")

    # DBから馬名取得
    horses = get_horse_names(race_date, jyo_code, race_num)
    if horses:
        print("  出走馬:")
        for num, name in sorted(horses.items(), key=lambda x: int(x[0])):
            print(f"    {num}: {name}")

    # 4. 券種入力
    while True:
        bet_type = input(f"\n券種 ({'/'.join(VALID_TYPES)}): ").strip()
        if bet_type in VALID_TYPES:
            break
        print(f"  ❌ 無効な券種です")

    # 5. 馬番入力
    while True:
        selection = input("馬番 (例: 05 or 05-11 or 05-11-13): ").strip()
        if validate_selection(selection, bet_type):
            break
        print("  ❌ 無効な形式です")

    # 馬名表示
    sel_nums = selection.split("-")
    sel_names = []
    for num in sel_nums:
        padded = num.zfill(2)
        name = horses.get(padded, horses.get(num, "?"))
        sel_names.append(name)

    print(f"  → {' / '.join(sel_names)}")

    # 6. 金額入力
    while True:
        try:
            amount = int(input("金額 (円): ").strip())
            if amount > 0:
                break
        except ValueError:
            pass
        print("  ❌ 正の整数を入力してください")

    # 7. 武器入力
    weapon = input("武器 (なければ Enter): ").strip() or "-"

    # 8. 結果入力
    while True:
        result = input("結果 (的中/不的中): ").strip()
        if result in ["的中", "不的中"]:
            break
        print("  ❌ 的中 または 不的中 を入力してください")

    # 9. 払戻金入力
    payout = 0
    if result == "的中":
        while True:
            try:
                payout = int(input("払戻金 (円): ").strip())
                if payout >= 0:
                    break
            except ValueError:
                pass
            print("  ❌ 0以上の整数を入力してください")

    # 確認
    print("\n" + "-"*50)
    print("  確認:")
    print(f"    レース: {race_key}")
    print(f"    券種: {bet_type}")
    print(f"    馬番: {selection} ({' / '.join(sel_names)})")
    print(f"    金額: {amount}円")
    print(f"    武器: {weapon}")
    print(f"    結果: {result}")
    if payout > 0:
        print(f"    払戻: {payout}円 (収支: {payout - amount:+}円)")
    print("-"*50)

    confirm = input("\n追加しますか? (y/n): ").strip().lower()
    if confirm != "y":
        print("  キャンセルしました")
        return

    # データ読み込み・更新
    data = load_data()

    # racesに追加
    if "races" not in data:
        data["races"] = {}

    if race_key not in data["races"]:
        data["races"][race_key] = {
            "date": date,
            "name": race_name,
            "title": "",
            "horses": {},
            "bets": []
        }

    # horsesに追加
    for num in sel_nums:
        padded = num.zfill(2)
        if padded not in data["races"][race_key]["horses"]:
            name = horses.get(padded, horses.get(num, ""))
            if name:
                data["races"][race_key]["horses"][padded] = name

    # ベット追加
    data["races"][race_key]["bets"].append({
        "type": bet_type,
        "selection": selection,
        "amount": amount,
        "payout": payout,
        "weapon": weapon,
        "result": "的中" if payout > 0 else "-"
    })

    # サマリー更新
    data["lastUpdated"] = date
    update_daily(data, date, dow)
    update_monthly(data)
    update_summary(data)

    # 保存
    save_data(data)

    print("\n  ✅ 追加完了!")
    print(f"     ファイル: {DATA_FILE}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n  中断しました")
        sys.exit(1)
