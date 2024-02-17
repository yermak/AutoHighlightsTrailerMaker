import os
import sys
import random
import time

scene_distance = 10
max_scene_distance = 60
scene_difference = 0.15
hardware = "-hwaccel nvdec -hwaccel_output_format cuda"
# hardware = ""
vc = "-c:v libx265 -crf 0 -preset superfast"
# vc = "-c:v libsvtav1 -crf 25 -preset 10 -svtav1-params fast-decode=1 -g 300"
vc_final = "-c:v hevc_nvenc -profile:v main10 -pix_fmt p010le -rc:v vbr -tune hq -preset p5 -multipass 2 -bf 4 -b_ref_mode 1 -nonref_p 1 -rc-lookahead 75 -spatial-aq 1 -aq-strength 8 -temporal-aq 1 -cq 25 -qmin 23 -qmax 30 -b:v 1M -maxrate:v 3M"
vf = """-vf "hwdownload,format=nv12" """
# vf = ""
# ac = "-c:a aac -b:a 192k -ac 2 -ar 44100"
ac = "-c:a libopus -b:a 96k -ac 2"
filter_complex = """-filter_complex "[0:a]asplit=2[sc][mix];[1:a][sc]sidechaincompress=threshold=0.006:ratio=19:attack=1000:release=3000:link=maximum:detection=peak[bg];[bg][mix]amerge[final]" """


# accept array of strings and print them
def print_files(files):
    # Use a breakpoint in the code line below to debug your script.
    for file in files:
        print(f'File, {file}')


# recursively collect files in the directory passed as parameter and return the array of files as result of method
def collect_files(directory, extensions):
    # Create an empty list to store the files
    found_files = []

    # Get the list of files in the directory using their full path
    directory_content = [os.path.join(directory, file) for file in os.listdir(directory)]

    # Go through the list and print the file name and size
    for file in directory_content:
        # If the file is a directory, call the method recursively.
        if os.path.isdir(file):
            print(f'Searching recursively in, {file}')
            found_files += collect_files(file, extensions)
        # If the file is a file, add it to the list
        else:
            # Check if the file has the right extension
            if os.path.splitext(file)[1] in extensions:
                found_files.append(file)
    return found_files


def mk_tmp_dir(file):
    # create unique directory for the file in tmp directory from env viriable, using just parent dir name and file name replacing spaces and slashes with underscores
    tmp_dir = (os.path.join(os.environ['TMP'],
                            (os.path.basename(os.path.dirname(file)) + "_" + os.path.basename(file))
                            .replace(" ", "_")
                            .replace("/", "_")
                            .replace("'", ""))
               )
    # tmp_dir exist remove all contents of it and recreate it
    if os.path.exists(tmp_dir):
        for root, dirs, files in os.walk(tmp_dir):
            for file in files:
                os.remove(os.path.join(root, file))
            for dir in dirs:
                os.rmdir(os.path.join(root, dir))
    else:
        os.mkdir(tmp_dir)
    print(tmp_dir)
    return tmp_dir


# read the time.txt file in tmp_dir and collect a list of timestamps for the trailer, time.txt has following format: 1st line: "frame:4    pts:8883875 pts_time:296.129", each 2nd line should be ignored
def collect_pts_timestamps(time_file, skip):
    timestamps = []
    with open(time_file, 'r') as file:
        lines = file.readlines()
        for i in range(0, len(lines), 1):
            # extract timestamp from line and append it to timestamps list
            split = lines[i].split("pts_time:")
            if (len(split) == 2):
                pts_time = split[1]
                ts = float(pts_time)
                if ts > skip:
                    timestamps.append(ts)
                # pts.append(int(lines[i].split("pts:")[1].split(" ")[0]))
    return timestamps


# format time in seconds to HH:MM:SS.miliseconds, miliseconds should be rounded to 3 decimal places
def format_time(seconds):
    return time.strftime('%H:%M:%S', time.gmtime(seconds)) + f".{int((seconds * 1000) % 1000):03d}"


def write_file(list_file, scenes):
    with open(list_file, 'w') as file:
        for scene in scenes:
            file.write(f"file '{scene}'\n")


def make_trailer(video, music, skip):
    # run ffprobe to get the duration of the music file into the variable, reading directly from the output
    # ffprobe -i "input.mp3" -show_entries format=duration -v quiet -of csv="p=0"
    music_duration = get_media_duration(music)

    # video_duration = getMediaDuration(video)

    # ffprobe_video = f"""ffprobe -i "{video}" -v error -select_streams v:0 -show_entries stream=r_frame_rate -of default=noprint_wrappers=1:nokey=1 """
    # video_fps = os.popen(ffprobe_video).read().split("/")
    # print("Video FPS:", video_fps)

    # call ffmpeg with the file as input and store the result in the tmp directory
    tmp_dir = mk_tmp_dir(video)

    # escape backslashes in the file path (for windows) and filters (for ffmpeg)
    time_file = os.path.join(tmp_dir, 'time.txt')
    time_file_fixed = time_file.replace('\\', '\\\\').replace(':', '\\:')

    print("Time file:", time_file_fixed)
    detect_scenes(video, time_file_fixed)

    timestamps = collect_pts_timestamps(time_file, skip)

    # print(pts)
    print(timestamps)

    # generate random number from 5 to 10
    random.seed()

    scenes = cut_by_timestamp(music_duration, timestamps, tmp_dir, video, skip)

    list_file = os.path.join(tmp_dir, 'list.txt')
    write_file(list_file, scenes)
    result_file = os.path.join(tmp_dir, f"{os.path.basename(video)}_trailer.mkv")
    print(f"Result file: {result_file}")

    # concatenate all scenes into one file and mux it with the music file
    ffmpeg_concat = f"""ffmpeg.exe -f concat -safe 0 -i "{list_file}" -c:v copy -c:a copy "{result_file}" """
    print(ffmpeg_concat)

    if os.system(ffmpeg_concat) != 0:
        print(f"Error in ffmpeg command, {ffmpeg_concat}")
        exit(1)

    trailer_file = os.path.join(os.path.dirname(video), f"{os.path.basename(video)}_trailer.mkv")
    print(f"Result file: {trailer_file}")

    # concatenate all scenes into one file and mux it with the music file
    ffmpeg_mux = f"""ffmpeg.exe -i  "{result_file}" -i "{music}" {filter_complex} -map 0:v {vc_final} -map [final] {ac} -movflags +faststart -y "{trailer_file}" """
    print(ffmpeg_mux)
    os.system(f"{ffmpeg_mux}")

    print(f'trailer created for {video}')

    return 0


def detect_scenes(video, time_file):
    if skip != 0:
        skip_time = format_time(skip)
    ffmpeg_scenes = f"""ffmpeg.exe -i "{video}" -filter:v "select='isnan(prev_selected_t)+gte(t-prev_selected_t\\,{max_scene_distance})*eq(pict_type\\,PICT_TYPE_I)+gte(t-prev_selected_t\\,{scene_distance})*gt(scene,{scene_difference})*eq(pict_type\\,PICT_TYPE_I)',showinfo,metadata=print:file='{time_file}'" -fps_mode vfr -f null NULL"""
    print(ffmpeg_scenes)
    # measure time of execution
    start_time = time.time()

    # run the command and check exit code if it is not 0, check std and err of the process and print it
    if os.system(ffmpeg_scenes) != 0:
        print(f"Error in ffmpeg command:\n {ffmpeg_scenes}")
        exit(1)

    print(f"ffmpeg scenes took {time.time() - start_time} seconds")


def get_media_duration(media_file):
    ffprobe = f"""ffprobe.exe -i "{media_file}" -show_entries format=duration -v quiet -of csv="p=0" """
    print(ffprobe)
    # read media duration from the output to float
    music_duration = float(os.popen(ffprobe).read())
    print(f"Duration of {media_file}: {music_duration}")
    return music_duration


def cut_by_timestamp(music_duration, timestamps, tmp_dir, video, skip):
    remaining_duration = music_duration
    total_segments = len(timestamps)
    default_duration = music_duration / total_segments
    scenes = []
    last_position = timestamps[0]
    for i in range(1, total_segments, 1):
        segment_duration = remaining_duration * 0.8 / (total_segments - i + 1)

        if timestamps[i] < skip:
            last_position = timestamps[i]
            continue
        if segment_duration < (default_duration / 2):
            last_position = timestamps[i]
            continue
        if (last_position + segment_duration) > timestamps[i]:
            last_position = timestamps[i]
            continue

        start = format_time(timestamps[i])
        print(f"start: {start}, duration: {segment_duration}")
        duration = format_time(segment_duration)
        output_file = os.path.join(tmp_dir, f"scene_{i:04d}.ts")
        # ffmpeg_cut = f"""ffmpeg.exe {hardware} -ss {start} -i "{video}" -t {duration} {vf} -map 0:v {vc} -map 0:a  -c:a copy {output_file}"""
        ffmpeg_cut = f"""ffmpeg.exe {hardware} -ss {start} -i "{video}" -t {duration} -map 0:v -map 0:a -c:v copy -avoid_negative_ts 1 -c:a copy "{output_file}" """
        print(ffmpeg_cut)
        if os.system(ffmpeg_cut) != 0:
            print(f"Error in ffmpeg command:\n {ffmpeg_cut}")
            exit(1)

        real_duration = get_media_duration(output_file)
        last_position = timestamps[i] + real_duration
        remaining_duration = remaining_duration - real_duration
        print(f"Real duration of {output_file}: {real_duration}")
        scenes.append(output_file)

    return scenes


# Accept directory as parameter and collect all files in the directory into list with extension stored in array of strings
if __name__ == '__main__':
    # Get the directory name from the command line
    extensions = {".mp4", ".mkv", ".avi", ".wmv", ".mov",
                  ".mpg", ".mpeg", ".flv", ".webm", ".vob",
                  ".qt", ".swf", ".avchd", ".m4v", ".3gp",
                  ".3g2", ".mxf", ".ts", ".m2ts", ".m2t", ".mts", ".m2ts"}
    if len(sys.argv) < 2:
        print("Usage: ", sys.argv[0], " <video file>", "<music file> (optional)", "<skip seconds> (optional)")
        sys.exit(1)

    video = sys.argv[1]
    if len(sys.argv) > 2:
        music = sys.argv[2]
    if len(sys.argv) > 3:
        skip = (int)(sys.argv[3])

    # Go through the list and print the file name and size
    # files = collect_files(directory, extensions)

    # for file in files:
    make_trailer(video, music, skip)

    # print_files(files)
