from datetime import timedelta, datetime
from pathlib import Path

import re

regex = re.compile(r'<[^>]+>')


def remove_html(string):
    return str(regex.sub('', string).encode("ascii", "ignore"))


def yoink_subtitles(vtt_path: Path, title: str):
    times = {0: title}

    max_duration = -1
    prev_content = title

    with open(vtt_path, 'rt') as f:
        lines = f.readlines()

        i = 4

        while i < len(lines):
            # timestamp
            time_str = lines[i].split(" ")
            i += 1

            # guaranteed line of content
            content = lines[i].strip()
            i += 1

            # multiline captions
            while lines[i].strip() != "":
                content += ' ' + lines[i].strip()
                i += 1

            # Blank line
            i += 1

            if len(time_str) > 0:
                # We only look at the start time.
                start = datetime.strptime(time_str[0], '%H:%M:%S.%f')
                start_time_seconds = timedelta(hours=start.hour, minutes=start.minute, seconds=start.second,
                                               microseconds=start.microsecond).total_seconds()

                # print(time_str)
                end = datetime.strptime(time_str[2].rstrip(), '%H:%M:%S.%f')
                end_time_seconds = timedelta(hours=end.hour, minutes=end.minute, seconds=end.second,
                                             microseconds=end.microsecond).total_seconds()

                max_duration = end_time_seconds

                times[start_time_seconds] = remove_html(prev_content)
                prev_content = content

        # Last one will sustain.
        times[max_duration] = f"{[*times.values()][-1]}. End."

    return times


def generate_captions(subs: dict(), fps=10):
    seconds_per_frame = 1 / fps
    frame_captions = []

    curr_time = 0

    ind = 0
    times = [*subs]
    final_time = times[-1]

    while curr_time < final_time:
        while times[ind] < curr_time:
            # print("increase", times[ind], curr_time)
            ind += 1

        frame_captions.append(subs[times[ind]])

        curr_time += seconds_per_frame

    return frame_captions

# xd = yoink_subtitles(Path('sampleSubs.vtt'), "The Paper Bag Princess by Robert Munsch")
# print(generate_captions(xd))
