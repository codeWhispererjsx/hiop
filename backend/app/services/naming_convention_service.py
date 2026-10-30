import re
from collections.abc import Mapping


DEFAULT_NAMING_CONVENTION = {
    "template": "{COMPANY}-{NUM:06}",
    "variables": ["COMPANY", "NUM:06"],
    "separator": "-",
}

NAMING_TOKENS = (
    "COMPANY",
    "LOCATION",
    "FLOOR",
    "BUILDING",
    "DEPT",
    "TYPE",
    "USER",
    "NUM",
    "YEAR",
    "ASSET",
)
TOKEN_PATTERN = re.compile(r"\{([A-Z]+(?::\d{2})?)\}")


def variables_in_template(template: str) -> list[str]:
    return list(dict.fromkeys(TOKEN_PATTERN.findall(template)))


def render_asset_number(template: str, values: Mapping[str, str], number: int) -> str:
    def replace(match: re.Match[str]) -> str:
        token = match.group(1)
        if token.startswith("NUM"):
            width = int(token.partition(":")[2] or 0)
            return str(number).zfill(width)
        value = values.get(token)
        if value is None or not value.strip():
            raise ValueError(f"A value is required for {{{token}}} to generate the asset number.")
        normalized = re.sub(r"[^A-Za-z0-9]+", "", value).upper()
        if not normalized:
            raise ValueError(f"A usable value is required for {{{token}}} to generate the asset number.")
        return normalized

    return TOKEN_PATTERN.sub(replace, template)
