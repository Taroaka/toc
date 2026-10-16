#!/usr/bin/env python3
"""Record user-authorized reuse of an existing generated image in the same run."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from toc.image_adoption import adopt_generated_image


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-dir', required=True, type=Path)
    for field in ('kind', 'source-kind'):
        parser.add_argument('--' + field, required=True, choices=('scene', 'asset'))
    for field in ('item-id', 'source-item-id', 'expected-revision', 'expected-request-digest',
                  'expected-source-sha256', 'authorization', 'reason'):
        parser.add_argument('--' + field, required=True)
    result = adopt_generated_image(**vars(parser.parse_args()))
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
