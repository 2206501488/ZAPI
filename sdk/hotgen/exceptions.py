from sdk.sousaku.exceptions import SousakuAPIError as HotgenAPIError
from sdk.sousaku.exceptions import SousakuAuthError as HotgenAuthError
from sdk.sousaku.exceptions import SousakuError as HotgenError
from sdk.sousaku.exceptions import SousakuTaskFailedError as HotgenTaskFailedError
from sdk.sousaku.exceptions import SousakuTimeoutError as HotgenTimeoutError

__all__ = [
    "HotgenAPIError",
    "HotgenAuthError",
    "HotgenError",
    "HotgenTaskFailedError",
    "HotgenTimeoutError",
]
