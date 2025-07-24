import os
import subprocess
import cv2
import soundfile as sf


def get_video_fps(video_path: str):
    cam = cv2.VideoCapture(video_path)
    fps = cam.get(cv2.CAP_PROP_FPS)
    cam.release()
    return fps


def get_audio_sr(audio_path: str):
    audio, sample_rate = sf.read(audio_path)
    return sample_rate


def resample_video_fps(video_path: str, video_fps: int, output_path: str = None):
    initial_video_fps = get_video_fps(video_path)
    print(f"Initial video fps: {initial_video_fps}")
    
    if initial_video_fps == video_fps:
        return video_path
    else:
        print(f"Resampling video fps from {initial_video_fps} to {video_fps}")

        if output_path is None:
            output_dir = os.path.join(os.path.dirname(video_path), "resampled")
            output_path = os.path.join(output_dir, os.path.basename(video_path))
        else:
            output_dir = os.path.dirname(output_path)
        os.makedirs(output_dir, exist_ok=True)

        command = f"ffmpeg -loglevel error -y -i {video_path} -vf fps={video_fps} {output_path}"
        subprocess.run(command, shell=True)
        print(f"Resampled video saved to: {output_path}")
        return output_path


def resample_audio_sr(audio_path: str, audio_sample_rate: int, output_path: str = None):
    initial_audio_sr = get_audio_sr(audio_path)
    print(f"Initial audio sample rate: {initial_audio_sr}")

    if initial_audio_sr == audio_sample_rate:
        return audio_path
    else:
        print(f"Resampling audio sample rate from {initial_audio_sr} to {audio_sample_rate}")

        if output_path is None:
            output_dir = os.path.join(os.path.dirname(audio_path), "resampled")
            output_path = os.path.join(output_dir, os.path.basename(audio_path))
        else:
            output_dir = os.path.dirname(output_path)
        os.makedirs(output_dir, exist_ok=True)

        command = f"ffmpeg -loglevel error -y -i {audio_path} -ar {audio_sample_rate} -q:a 0 {output_path}"
        subprocess.run(command, shell=True)
        print(f"Resampled audio saved to: {output_path}")
        return output_path
