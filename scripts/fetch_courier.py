"""Download the independent public Courier 0.1.0 wheel, checking its pinned digest."""
import argparse
import hashlib
from pathlib import Path
import urllib.request

NAME = "octave_courier-0.1.0-py3-none-any.whl"
URL = "https://github.com/chatgptopenaiagi/octave-courier/releases/download/v0.1.0/" + NAME
SHA256 = "9b58369949f22f72fe519a341ff3caaeb4f1da51b41d12e19dc2264f18eec8dc"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, required=True)
    args = parser.parse_args()
    args.directory.mkdir(parents=True, exist_ok=True)
    target = args.directory / NAME
    if target.exists():
        content = target.read_bytes()
    else:
        with urllib.request.urlopen(URL, timeout=60) as response:
            content = response.read(1024 * 1024)
    if hashlib.sha256(content).hexdigest() != SHA256:
        raise ValueError("Public Courier release wheel checksum mismatch; file not installed or overwritten")
    if not target.exists():
        with target.open("xb") as stream:
            stream.write(content)
    print(target)


if __name__ == "__main__":
    main()
