#!/usr/bin/env python3
"""Append a config fragment to the shared wild fragment, one entry per symbol.

Every step that wants to contribute kernel options appends to the same file
(common/wild_defconfig.fragment by default), which the build then applies as a defconfig
fragment. Doing it through this script instead of `cat >>` means:

  * only real config lines land - comments and blank lines are dropped, and anything
    that is not a CONFIG_ line is reported rather than silently copied
  * the file never holds the same symbol twice: appending a symbol that is already
    there replaces the earlier value, and the change is printed
  * the appending step is named in the output, so a fragment's contents can be traced
    back to the steps that put them there

Usage:
    append_fragment.py <source-fragment> [--dest common/wild_defconfig.fragment] [--label NAME]
"""

import argparse
import os
import re
import sys

SYMBOL = re.compile(r"^(?:# )?(CONFIG_[A-Za-z0-9_]+)(?:=.*| is not set)$")
NOT_SET = re.compile(r"^(?:# CONFIG_[A-Za-z0-9_]+ is not set|CONFIG_[A-Za-z0-9_]+=n)$")


def read_symbols(dest: str) -> dict[str, str]:
    symbols: dict[str, str] = {}
    if not os.path.exists(dest):
        return symbols
    with open(dest, encoding="utf-8") as fh:
        for line in fh:
            item = line.strip()
            match = SYMBOL.match(item)
            if match:
                symbols[match.group(1)] = item
    return symbols


def main() -> None:
    parser = argparse.ArgumentParser(description="Append a config fragment to wild_defconfig.fragment")
    parser.add_argument("source", help="Path to the source fragment file (or '-' for stdin)")
    parser.add_argument("--dest", default="common/wild_defconfig.fragment",
                        help="Destination fragment file (default: common/wild_defconfig.fragment)")
    parser.add_argument("--label", default="fragment", help="Label for trace output")
    args = parser.parse_args()

    if args.source == "-":
        lines = sys.stdin.read().splitlines()
    elif not os.path.exists(args.source):
        sys.exit(f"ERROR: {args.source} not found")
    else:
        with open(args.source, encoding="utf-8") as fh:
            lines = fh.read().splitlines()

    symbols = read_symbols(args.dest)
    before = len(symbols)
    added = overridden = skipped = 0

    for line in lines:
        item = line.strip()
        if not item or (item.startswith("#") and "is not set" not in item):
            continue
        match = SYMBOL.match(item)
        if not match:
            skipped += 1
            continue
        key = match.group(1)
        # Kleaf's own check greps .config for the symbol and blanks the value only
        # for the '# CONFIG_X is not set' spelling, so a literal 'CONFIG_X=n' can
        # never match: .config holds the comment form for a bool that is off.
        if item.endswith("=n"):
            item = f"# {key} is not set"
        if key in symbols:
            if symbols[key] != item:
                print(f"note: {args.label} overrides {key}: {symbols[key]} -> {item}")
                overridden += 1
            symbols[key] = item
        else:
            symbols[key] = item
            added += 1

    os.makedirs(os.path.dirname(os.path.abspath(args.dest)), exist_ok=True)
    with open(args.dest, "w", encoding="utf-8") as fh:
        fh.write("\n".join(symbols.values()) + "\n")

    print(
        f"{args.label} -> {args.dest}: +{added} new, {overridden} overridden, "
        f"{skipped} non-config line(s) skipped, "
        f"{len(symbols)} symbol(s) total (was {before})"
    )


if __name__ == "__main__":
    main()
