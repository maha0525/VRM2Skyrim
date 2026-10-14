"""Build isolated browser fixtures from read-only local game records."""
from dataclasses import asdict
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from environment import find_game  # noqa: E402
from game_catalog import GameCatalog  # noqa: E402
from settings import FollowerSettings  # noqa: E402


if __name__ == '__main__':
    game = find_game()
    if not game:
        raise SystemExit('A local Skyrim.esm is required for this read-only fixture')
    target = ROOT / 'build/ui-roles'
    target.mkdir(parents=True, exist_ok=True)
    target.joinpath('defaults.json').write_text(json.dumps(asdict(FollowerSettings())), encoding='utf8')
    target.joinpath('roles.json').write_text(json.dumps(GameCatalog(game / 'Data').json_choices(),
                                                      ensure_ascii=False), encoding='utf8')
    print(f'Browser fixtures: {target}')
