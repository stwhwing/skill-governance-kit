"""Shared QA-independent constants (Edward).

Kept in a uniquely-named module (not ``conftest``) to avoid pytest's classic
duplicate-``conftest`` import collision with ``tests/conftest.py``.
"""

from __future__ import annotations

# Sensitive shapes, assembled from fragments so this file is not itself a hit.
IPV4 = "111." + "229." + "70." + "191"
MARK_A = "light" + "make.site"
MARK_B = "api." + "skill" + "hub.cn"
CHAN = "wr" + "K" + "AQISgAA" + "EAXxxxxxxxxxxxx"
NICK_OC = "\u541e\u5c0f\u54e5"
NICK_HM = "\u541e\u5c0f\u59b9"
ROOT_HM = "/root" + "/.hermes" + "/skills/x"
SECRET = "sk-" + "A" * 30
CONFIGFILE = "open" + "claw.json"

ALL_SENSITIVE = {
    "ipv4": IPV4,
    "market_a": MARK_A,
    "market_b": MARK_B,
    "channel": CHAN,
    "nick_oc": NICK_OC,
    "nick_hm": NICK_HM,
    "root_hermes": ROOT_HM,
    "secret": SECRET,
    "config_file": CONFIGFILE,
}
