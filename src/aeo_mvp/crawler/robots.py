"""Minimal robots.txt parser for AEOBot / wildcard rules."""

from __future__ import annotations

from dataclasses import dataclass, field
from urllib.parse import urlparse


@dataclass
class RobotsRules:
    """Parsed allow/disallow for a user-agent group."""

    allows: list[str] = field(default_factory=list)
    disallows: list[str] = field(default_factory=list)
    fetched: bool = False
    raw: str = ""

    def is_allowed(self, path: str) -> bool | None:
        """Return True/False if a rule matches; None if no matching rule (default allow)."""
        if not path.startswith("/"):
            path = "/" + path
        best_match = ""
        best_allowed: bool | None = None
        for rule_path in self.disallows:
            if path.startswith(rule_path) and len(rule_path) >= len(best_match):
                best_match = rule_path
                best_allowed = False
        for rule_path in self.allows:
            if path.startswith(rule_path) and len(rule_path) >= len(best_match):
                best_match = rule_path
                best_allowed = True
        return best_allowed


def parse_robots(text: str, user_agent: str = "AEOBot") -> RobotsRules:
    """Parse robots.txt preferring the named UA group, else *."""
    ua_target = user_agent.split("/")[0].lower()
    groups: dict[str, RobotsRules] = {}
    current_agents: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.split("#", 1)[0].strip()
        if not line:
            continue
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip().lower()
        value = value.strip()
        if key == "user-agent":
            agent = value.lower()
            if not current_agents or current_agents[-1] != "__pending__":
                current_agents = [agent]
            else:
                current_agents.append(agent)
            # Start fresh group markers
            for a in current_agents:
                groups.setdefault(a, RobotsRules(fetched=True, raw=text))
        elif key in ("allow", "disallow"):
            if not current_agents:
                continue
            for a in current_agents:
                rules = groups.setdefault(a, RobotsRules(fetched=True, raw=text))
                if key == "allow":
                    if value == "":
                        continue
                    rules.allows.append(value)
                else:
                    # Empty disallow means allow all
                    if value == "":
                        continue
                    rules.disallows.append(value)
            current_agents = current_agents  # keep applying to same agents
        else:
            current_agents = []

    # Prefer exact UA, then *
    if ua_target in groups:
        rules = groups[ua_target]
    elif "*" in groups:
        rules = groups["*"]
    else:
        rules = RobotsRules(fetched=True, raw=text)
    rules.fetched = True
    rules.raw = text
    return rules


def path_from_url(url: str) -> str:
    return urlparse(url).path or "/"


def robots_pass_value(rules: RobotsRules | None, path: str = "/") -> float:
    """T2 scoring: 1 allow, 0.5 missing robots, 0 disallow."""
    if rules is None or not rules.fetched:
        return 0.5
    allowed = rules.is_allowed(path)
    if allowed is False:
        return 0.0
    return 1.0
