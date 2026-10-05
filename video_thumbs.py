#!/usr/bin/env python3

import argparse
import math
import os
import shutil
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


def run(cmd):
    return subprocess.check_output(cmd, text=True).strip()


def get_font(size):
    candidates = [
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/System/Library/Fonts/Supplemental/Helvetica.ttc",
        "/System/Library/Fonts/Supplemental/Times New Roman.ttf",
    ]

    for font_path in candidates:
        if Path(font_path).exists():
            try:
                return ImageFont.truetype(font_path, size)
            except Exception:
                pass

    return ImageFont.load_default()


def format_size(num_bytes):
    return f"{num_bytes / (1024 ** 3):.2f} GB"


def seconds_to_hms(seconds):
    total = int(seconds)

    hours = total // 3600
    minutes = (total % 3600) // 60
    secs = total % 60

    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def get_metadata(video_path):
    filesize = format_size(video_path.stat().st_size)

    resolution = run([
        "mediainfo",
        "--Inform=Video;%Width%x%Height%",
        str(video_path)
    ])

    framerate = run([
        "mediainfo",
        "--Inform=Video;%FrameRate/String%",
        str(video_path)
    ])

    duration_text = run([
        "mediainfo",
        "--Inform=General;%Duration/String3%",
        str(video_path)
    ])

    duration_seconds = float(run([
        "ffprobe",
        "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(video_path)
    ]))

    return {
        "filesize": filesize,
        "resolution": resolution,
        "framerate": framerate,
        "duration_text": duration_text,
        "duration_seconds": duration_seconds
    }


def generate_screenshots(video_path, temp_dir, count, duration_seconds):
    screenshots = []

    for i in range(count):

        percent = (i + 1) / (count + 1)

        timestamp_seconds = duration_seconds * percent

        timestamp_label = seconds_to_hms(timestamp_seconds)

        output_file = temp_dir / f"shot_{i:03d}.jpg"

        subprocess.run(
            [
                "ffmpeg",
                "-loglevel",
                "error",
                "-y",
                "-ss",
                str(timestamp_seconds),
                "-i",
                str(video_path),
                "-frames:v",
                "1",
                str(output_file)
            ],
            check=True
        )

        screenshots.append(
            {
                "file": output_file,
                "timestamp": timestamp_label
            }
        )

    return screenshots


def create_contact_sheet(
    screenshots,
    video_path,
    output_path,
    mediainfo_path,
    metadata,
    filename,
    columns,
    thumb_width,
    header_font_size,
    timestamp_font_size
):
    font_header = get_font(header_font_size)
    font_stamp = get_font(timestamp_font_size)

    images = []

    thumb_height = None

    for shot in screenshots:

        img = Image.open(shot["file"])

        thumb_height = int(
            img.height * thumb_width / img.width
        )

        img = img.resize(
            (thumb_width, thumb_height),
            Image.Resampling.LANCZOS
        )

        draw = ImageDraw.Draw(img)

        label = shot["timestamp"]

        bbox = draw.textbbox(
            (0, 0),
            label,
            font=font_stamp
        )

        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]

        x = 10
        y = thumb_height - text_height - 20

        draw.rectangle(
            (
                x - 6,
                y - 4,
                x + text_width + 6,
                y + text_height + 4
            ),
            fill=(0, 0, 0)
        )

        draw.text(
            (x, y),
            label,
            fill="white",
            font=font_stamp
        )

        images.append(img)

    rows = math.ceil(len(images) / columns)

    grid_width = thumb_width * columns
    grid_height = thumb_height * rows

    header_text = "\n".join([
        f"Filename   : {filename}",
        f"Size       : {metadata['filesize']}",
        f"Resolution : {metadata['resolution']}",
        f"Framerate  : {metadata['framerate']}",
        f"Duration   : {metadata['duration_text']}"
    ])

    header_height = 220

    sheet = Image.new(
        "RGB",
        (grid_width, header_height + grid_height),
        (30, 30, 30)
    )

    draw = ImageDraw.Draw(sheet)

    draw.multiline_text(
        (20, 20),
        header_text,
        fill="white",
        font=font_header,
        spacing=10
    )

    for index, img in enumerate(images):

        x = (index % columns) * thumb_width
        y = header_height + (index // columns) * thumb_height

        sheet.paste(img, (x, y))

    sheet.save(
        output_path,
        quality=95
    )

    mediainfo_output = subprocess.check_output(
        [
            "mediainfo",
            str(video_path)
        ],
        text=True
    )

    with open(
        mediainfo_path,
        "w",
        encoding="utf-8"
    ) as fh:
        fh.write(mediainfo_output)


def main():
    parser = argparse.ArgumentParser(
        description="Generate tracker-style thumbnail sheet"
    )

    parser.add_argument(
        "video_file",
        help="Video file to process"
    )

    parser.add_argument(
        "--output",
        help="Output folder (default: same folder as video)"
    )

    parser.add_argument(
        "--count",
        type=int,
        default=12,
        help="Number of screenshots (default: 12)"
    )

    parser.add_argument(
        "--columns",
        type=int,
        default=4,
        help="Number of columns (default: 4)"
    )

    parser.add_argument(
        "--width",
        type=int,
        default=400,
        help="Thumbnail width (default: 400)"
    )

    parser.add_argument(
        "--header-font-size",
        type=int,
        default=28,
        help="Header font size"
    )

    parser.add_argument(
        "--timestamp-font-size",
        type=int,
        default=22,
        help="Timestamp font size"
    )

    parser.add_argument(
        "--keep-temp",
        action="store_true",
        help="Keep temporary screenshots"
    )

    args = parser.parse_args()

    video_path = Path(args.video_file).expanduser().resolve()

    if not video_path.exists():
        raise SystemExit(f"File not found: {video_path}")

    if args.output:
        output_dir = Path(args.output).expanduser().resolve()
    else:
        output_dir = video_path.parent

    output_dir.mkdir(
        parents=True,
        exist_ok=True
    )

    temp_dir = output_dir / "screenshots"

    if temp_dir.exists():
        shutil.rmtree(temp_dir)

    temp_dir.mkdir()

    try:

        metadata = get_metadata(video_path)

        print("Generating screenshots...")

        screenshots = generate_screenshots(
            video_path=video_path,
            temp_dir=temp_dir,
            count=args.count,
            duration_seconds=metadata["duration_seconds"]
        )

        output_file = output_dir / f"{video_path.stem}.jpg"
        mediainfo_file = output_dir / f"{video_path.stem}_MediaInfo.txt"

        create_contact_sheet(
            screenshots=screenshots,
            video_path=video_path,
            output_path=output_file,
            mediainfo_path=mediainfo_file,
            metadata=metadata,
            filename=video_path.name,
            columns=args.columns,
            thumb_width=args.width,
            header_font_size=args.header_font_size,
            timestamp_font_size=args.timestamp_font_size
        )

        print(f"Created: {output_file}")
        print(f"Created MediaInfo : {mediainfo_file}")

    finally:

        if not args.keep_temp and temp_dir.exists():
            shutil.rmtree(temp_dir)


if __name__ == "__main__":
    main()

