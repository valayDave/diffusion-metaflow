import random
from metaflow import Task, Flow, Step, namespace, Run
import os
from utils import create_prompt
from typing import Iterable
from model_store import ModelStore
import tempfile
import glob
import os

try:
    import matplotlib.pyplot as plt
    import numpy as np
except ImportError as e:
    pass


def img_reshape(img, width=300, height=300):
    img = img.resize((width, height))
    img = np.asarray(img)
    return img


def create_image_grid(
    run_metadata,
    prompt,
    style,
    rows=4,
    cols=4,
    width=150,
    height=150,
    randomly_selected=False,
):
    selected_values = []

    for val in run_metadata:
        if prompt is not None:
            if prompt.lower() in val["prompt"].lower():
                selected_values.append(val)
        if style is not None:
            if style.lower() in val["style"].lower():
                selected_values.append(val)

    if len(selected_values) == 0:
        print("No Images could be filtered for prompt:%s style:%s" % (prompt, style))
        return
    img_count = 0
    if randomly_selected:
        selected_values = random.choices(
            selected_values, k=min(len(selected_values), rows * cols)
        )

    fig, axes = plt.subplots(nrows=rows, ncols=cols, figsize=(15, 15))
    for i in range(rows):
        for j in range(cols):
            task_obj = Task(selected_values[img_count]["task_pathspec"])
            image = task_obj[selected_values[img_count]["img_val"]].data
            if img_count < rows * cols or img_count < len(selected_values):
                axes[i, j].set_title(
                    create_prompt(
                        selected_values[img_count]["prompt"],
                        selected_values[img_count]["style"],
                    )
                )
                axes[i, j].axis("off")
                axes[i, j].imshow(img_reshape(image, width=width, height=height))
                img_count += 1


def get_successful_run_prompts(max_runs=None):
    namespace(None)
    flow = Flow("DynamicPromptsToImages")
    success_runs = []
    _idx = 0
    for r in flow.runs():
        if max_runs is not None and _idx >= max_runs:
            break
        if r.successful:
            success_runs.append(r)
        _idx += 1

    # extract all unique runs
    core_step_pathspecs = []
    for r in success_runs:
        if "None" in r["generate_images"].origin_pathspec:
            core_step_pathspecs.append(r["generate_images"].pathspec)
        else:
            if r["generate_images"].origin_pathspec not in core_step_pathspecs:
                core_step_pathspecs.append(r["generate_images"].origin_pathspec)

    # Extract all the prompt values into a json list.
    prompt_values = []
    for steptsp in list(set(core_step_pathspecs)):
        mf_step = Step(steptsp)
        seed_value = None
        for task in mf_step:
            if seed_value is None:
                seed_value = task.data.seed
            run_id = task.pathspec.split("/")[1]
            image_indx = task.data.image_index
            prompt_values.extend(
                [
                    dict(
                        prompt=prompt,
                        style=style,
                        img_val=img_val,
                        task_pathspec=task.pathspec,
                        run_id=run_id,
                        seed=seed_value,
                    )
                    for prompt, style, img_val in image_indx
                ]
            )

    return prompt_values


def get_runs_by_id(flow_name, run_id):
    namespace(None)
    flow = Flow(flow_name)
    return flow[run_id]


def get_runs_by_tag(flow_name, tags):
    namespace(None)
    flow = Flow(flow_name)
    return flow.runs(*tags)


def get_runs_by_branch(flow_name, project, branch):
    namespace(None)
    flow = Flow(flow_name)
    tags = [f"project:{project}", f"project_branch:{branch}"]
    return flow.runs(*tags)


def get_runs(
    flow_name, run_id=None, tags=None, branch=None, project=None
) -> Iterable[Run]:
    if run_id is not None:
        return [get_runs_by_id(flow_name, run_id)]
    elif tags is not None:
        return get_runs_by_tag(flow_name, tags)
    elif branch is not None and project is not None:
        return get_runs_by_branch(flow_name, project, branch)


def export_image_to_video_conversions(
    run_id=None, tags=None, branch=None, project=None, max_runs=None, save_folder=None
):
    if all([run_id, tags, branch, project]):
        raise ValueError("Only one of run_id, tag, branch, project can be specified.")
    if (branch or project) and (all([branch, project]) is False):
        raise ValueError("Both branch and project must be specified.")
    if save_folder is None:
        print(
            "No save folder specified. Using 'final_render' folder in current working directory."
        )
        save_folder = os.path.join(os.getcwd(), "final_render")
    kwags = dict(run_id=run_id, tags=tags, branch=branch, project=project)
    run_videos = []
    for idx, run in enumerate(get_runs("TextToVideo", **kwags)):
        if max_runs is not None and idx >= max_runs:
            break
        if not run.successful:
            continue
        store = ModelStore.from_path(run["generate_video_from_images"].task.pathspec)
        save_pth = os.path.join(
            save_folder,
            run.id,
        )
        store.download("final_render", save_pth)
        run_videos.append((run, save_pth))
    return run_videos


def add_fade_animation(clip, fade_duration=1):
    return clip.fadein(fade_duration).fadeout(fade_duration)


def stitch_videos(video_paths, output_path, fade_duration=1, film_fps=24):
    from moviepy.editor import VideoFileClip, concatenate_videoclips

    clips = [
        add_fade_animation(VideoFileClip(path), fade_duration) for path in video_paths
    ]
    final_clip = concatenate_videoclips(clips)
    final_clip.write_videofile(output_path, fps=film_fps)


def make_movie_from_runs(
    run_id=None,
    tags=None,
    branch=None,
    project=None,
    max_runs=None,
    save_folder=None,
    max_video_in_film=20,
    film_fps=24,
    final_video_path=None,
):
    if max_video_in_film is not None and max_video_in_film < 1:
        raise ValueError("max_video_in_film must be greater than 1.")

    if final_video_path is None:
        print(
            "No final video path specified. Using 'final_video.mp4' in current working directory."
        )
        final_video_path = os.path.join(os.getcwd(), "final_video.mp4")
    exported_runs = export_image_to_video_conversions(
        run_id=run_id,
        tags=tags,
        branch=branch,
        project=project,
        max_runs=max_runs,
        save_folder=save_folder,
    )
    video_paths = []
    for run, folp in exported_runs:
        video_paths.extend(glob.glob(os.path.join(folp, "**", "*.mp4")))

    if max_video_in_film is not None:
        video_paths = random.sample(video_paths, max_video_in_film)
    stitch_videos(video_paths, final_video_path, film_fps=film_fps)
    return final_video_path
