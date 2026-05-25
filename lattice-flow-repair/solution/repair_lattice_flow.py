"""Repair script for the temporal constraint propagation scheduler."""

import re


def patch_intervals():
    path = "/app/runtime/intervals.py"
    with open(path, "r") as f:
        content = f.read()

    content = content.replace(
        "return end_a >= start_b",
        "return end_a > start_b"
    )

    with open(path, "w") as f:
        f.write(content)


def patch_propagator():
    path = "/app/runtime/propagator.py"
    with open(path, "r") as f:
        content = f.read()

    old_backward = (
        'new_latest_end = tighten_end_bound(\n'
        '                        bounds[pred]["latest_end"],\n'
        '                        bounds[succ]["earliest_start"]\n'
        '                    )'
    )
    new_backward = (
        'new_latest_end = tighten_end_bound(\n'
        '                        bounds[pred]["latest_end"],\n'
        '                        bounds[succ]["latest_start"]\n'
        '                    )'
    )
    content = content.replace(old_backward, new_backward)

    old_forward = (
        'new_earliest_start = tighten_start_bound(\n'
        '                        bounds[succ]["earliest_start"],\n'
        '                        bounds[pred]["latest_end"]\n'
        '                    )'
    )
    new_forward = (
        'new_earliest_start = tighten_start_bound(\n'
        '                        bounds[succ]["earliest_start"],\n'
        '                        bounds[pred]["earliest_end"]\n'
        '                    )'
    )
    content = content.replace(old_forward, new_forward)

    with open(path, "w") as f:
        f.write(content)


def patch_config():
    path = "/app/runtime/config.ini"
    with open(path, "r") as f:
        content = f.read()

    content = re.sub(
        r"max_propagation_passes\s*=\s*\d+",
        "max_propagation_passes = 20",
        content
    )

    with open(path, "w") as f:
        f.write(content)


if __name__ == "__main__":
    patch_intervals()
    patch_propagator()
    patch_config()
    print("All patches applied successfully.")
