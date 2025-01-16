import sys

from gsuid_core.data_store import get_res_path

MAIN_PATH = get_res_path() / "BeyondUID"
sys.path.append(str(MAIN_PATH))

CU_BG_PATH = MAIN_PATH / "bg"
CONFIG_PATH = MAIN_PATH / "config.json"
RESOURCE_PATH = MAIN_PATH / "resource"

GAMEDATA_PATH = RESOURCE_PATH / "gamedata"


def init_dir():
    for i in [
        MAIN_PATH,
        CU_BG_PATH,
        RESOURCE_PATH,
        GAMEDATA_PATH,
    ]:
        i.mkdir(parents=True, exist_ok=True)


init_dir()
