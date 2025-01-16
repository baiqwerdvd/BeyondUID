from typing import cast

from ..beyonduid_config.byd_config import BydConfig

PREFIX = cast(str, BydConfig.get_config("BydPrefix").data)
