#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
validate-keiba-json.py - 競馬ダッシュボードJSONバリデーター

使用例:
    python scripts/validate-keiba-json.py data_2026.json
    python scripts/validate-keiba-json.py data_2026.json --fix
"""

import json
import re
import sys
from pathlib import Path
from typing import List, Dict, Any, Tuple

# バリデーションルール
VALID_TYPES = {
    '単勝', '複勝', '馬連', '馬単', 'ワイド', '枠連', '3連複', '3連単', '単複'
}

# selection の正規表現パターン
# OK: "5", "05", "03-15", "03-06-15", "枠5-5"
SELECTION_PATTERN = re.compile(r'^(\d{1,2}(-\d{1,2}){0,2}|枠\d{1,2}-\d{1,2})$')


class ValidationError:
    """バリデーションエラー"""
    def __init__(self, race_key: str, field: str, value: str, reason: str):
        self.race_key = race_key
        self.field = field
        self.value = value
        self.reason = reason

    def __str__(self):
        return f'{self.field}: "{self.value}" ({self.reason})'


def validate_type(bet_type: str) -> Tuple[bool, str]:
    """typeフィールドをバリデーション"""
    if bet_type in VALID_TYPES:
        return True, ""

    # 番号が含まれているか（3連複、3連単は除外）
    if bet_type not in {'3連複', '3連単'} and re.search(r'\d+-\d+', bet_type):
        return False, "番号が含まれている"

    return False, f"許可されていないtype（許可: {', '.join(sorted(VALID_TYPES))}）"


def validate_selection(selection: str, bet_type: str) -> Tuple[bool, str]:
    """selectionフィールドをバリデーション"""
    sel_str = str(selection)

    # 空、"-"、"0" は不正
    if sel_str in ['', '-', '0']:
        return False, "空または不正な値"

    # カンマ、「番」が含まれていたら不正
    if ',' in sel_str or '番' in sel_str:
        return False, "不正な形式（カンマや「番」を含む）"

    # 枠連の場合は「枠X-X」形式を許可
    if bet_type == '枠連':
        if sel_str.startswith('枠') or SELECTION_PATTERN.match(sel_str):
            return True, ""
        return False, "枠連の形式が不正"

    # 通常のパターンチェック
    if SELECTION_PATTERN.match(sel_str):
        return True, ""

    return False, "形式が不正（期待: 数字 or 数字-数字 or 数字-数字-数字）"


def validate_json(data: Dict[str, Any]) -> List[ValidationError]:
    """JSONデータ全体をバリデーション"""
    errors = []

    races = data.get('races', {})

    for race_key, race in races.items():
        bets = race.get('bets', [])

        for i, bet in enumerate(bets):
            bet_type = bet.get('type', '')
            selection = bet.get('selection', '')

            # type バリデーション
            valid, reason = validate_type(bet_type)
            if not valid:
                errors.append(ValidationError(race_key, 'type', bet_type, reason))

            # selection バリデーション
            valid, reason = validate_selection(selection, bet_type)
            if not valid:
                errors.append(ValidationError(race_key, 'selection', selection, reason))

    return errors


def print_results(errors: List[ValidationError], total_bets: int):
    """結果を出力"""
    print("=" * 50)
    print("=== バリデーション結果 ===")
    print("=" * 50)

    if not errors:
        print("\n✅ エラーなし！")
    else:
        print(f"\n❌ エラー: {len(errors)}件\n")

        # レース別にグループ化
        by_race: Dict[str, List[ValidationError]] = {}
        for err in errors:
            if err.race_key not in by_race:
                by_race[err.race_key] = []
            by_race[err.race_key].append(err)

        for i, (race_key, race_errors) in enumerate(sorted(by_race.items()), 1):
            print(f"{i}. {race_key}")
            for err in race_errors:
                print(f"   - {err}")
            print()

    print("=" * 50)
    print(f"=== 全{total_bets}件中、{len(errors)}件のエラー ===")
    print("=" * 50)


def count_total_bets(data: Dict[str, Any]) -> int:
    """全ベット数をカウント"""
    total = 0
    for race in data.get('races', {}).values():
        total += len(race.get('bets', []))
    return total


def main():
    if len(sys.argv) < 2:
        print("使用法: python validate-keiba-json.py <json_file>")
        print("例: python validate-keiba-json.py data_2026.json")
        sys.exit(1)

    json_path = Path(sys.argv[1])

    # 相対パスの場合、カレントディレクトリからの相対パスとして解決
    if not json_path.is_absolute():
        # scriptsディレクトリから実行された場合を考慮
        if not json_path.exists():
            json_path = Path(__file__).parent.parent / json_path

    if not json_path.exists():
        print(f"エラー: ファイルが見つかりません: {json_path}")
        sys.exit(1)

    # JSON読み込み
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        print(f"エラー: JSONパースエラー: {e}")
        sys.exit(1)

    # バリデーション実行
    errors = validate_json(data)
    total_bets = count_total_bets(data)

    # 結果出力
    print_results(errors, total_bets)

    # エラーがあれば終了コード1
    sys.exit(1 if errors else 0)


if __name__ == '__main__':
    main()
