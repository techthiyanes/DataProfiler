"""Contains space and time analysis tests for the Dataprofiler"""

import json
import random
import time
from collections import defaultdict
from typing import Dict, List, Optional

import memray
import numpy as np
import pandas as pd
import tensorflow as tf

try:
    import sys

    sys.path.insert(0, "../../..")
    import dataprofiler as dp
except ImportError:
    import dataprofiler as dp

from dataset_generation import generate_dataset_by_class

from dataprofiler import StructuredProfiler

# suppress TF warnings
tf.compat.v1.logging.set_verbosity(tf.compat.v1.logging.ERROR)


def dp_profile_space_analysis(
    data: pd.DataFrame,
    path: str,
    options: Optional[Dict] = None,
    percent_to_nan: float = 0.0,
) -> StructuredProfiler:
    """
    Generate memray bin file of the space analysis of dp.Profiler function

    :param data: DataFrame that is to be profiled
    :type data: pandas.DataFrame
    :param path: Path to output the memray bin file generated for space analysis
    :type path: string
    :param options: options for the dataprofiler intialization
    :type options: Dict, None, optional
    :param percent_to_nan: Percentage of dataset that needs to be nan values
    :type percent_to_nan: float, optional

    :return: The StructuredProfile generated by dp.Profiler
    """
    if percent_to_nan:
        nan_injection(df, percent_to_nan)
    with memray.Tracker(path):
        profile = dp.Profiler(data, options=options, samples_per_update=len(data))
    return profile


def dp_merge_space_analysis(profile: StructuredProfiler, path: str):
    """
    Generate memray bin file of the space analysis of merge profile functionality

    :param profile: Profile that is to be merged with itself
    :type profile: StructuredProfile
    :param path: Path to output the memray bin file generated for space analysis
    :type path: string
    """

    with memray.Tracker(path):
        _ = profile + profile


def dp_time_analysis(
    sample_sizes: List,
    data: pd.DataFrame,
    path: str = "structured_profiler_times.json",
    percent_to_nan: float = 0.0,
    allow_subsampling: bool = True,
    options: Optional[Dict] = None,
):
    """
    Run time analysis for profile and merge functionality

    :param sample_sizes: List of sample sizes of dataset to be analyzed
    :type sample_sizes: list
    :param data: DataFrame to be used for time analysis
    :type data: pandas DataFrame
    :param path: Path to output json file with all time analysis info
    :type path: string, optional
    :param percent_to_nan: Percentage of dataset that needs to be nan values
    :type percent_to_nan: float, optional
    :param allow_subsampling: boolean to allow subsampling when running time analysis
    :type allow_subsampling: bool, optional
    :param options: options for the dataprofiler intialization
    :type options: Dict, None, optional

    """
    # [0] allows model to be initialized and added to labeler
    sample_sizes = [0] + sample_sizes
    profile_times = []
    for sample_size in sample_sizes:
        # setup time dict

        print(f"Evaluating sample size: {sample_size}")
        replace = False
        if sample_size > len(data):
            replace = True

        df = (
            data.sample(sample_size, replace=replace)
            .sort_index()
            .reset_index(drop=True)
        )

        if percent_to_nan:
            df = nan_injection(df)

        # time profiling
        start_time = time.time()
        if allow_subsampling:
            profiler = dp.Profiler(df, options=options)
        else:
            profiler = dp.Profiler(df, samples_per_update=len(df), options=options)
        total_time = time.time() - start_time

        # get overall time for merging profiles
        start_time = time.time()
        try:
            merged_profile = profiler + profiler
        except ValueError:
            pass  # empty profile merge if 0 data
        merge_time = time.time() - start_time

        # get times for each profile in the columns
        for profile in profiler.profile:
            compiler_times = defaultdict(list)

            for compiler_name in profile.profiles:
                compiler = profile.profiles[compiler_name]
                inspector_times = dict()
                for inspector_name in compiler._profiles:
                    inspector = compiler._profiles[inspector_name]
                    inspector_times[inspector_name] = inspector.times
                compiler_times[compiler_name] = inspector_times
            column_profile_time = {
                "name": profile.name,
                "sample_size": sample_size,
                "total_time": total_time,
                "column": compiler_times,
                "merge": merge_time,
                "percent_to_nan": percent_to_nan,
                "allow_subsampling": allow_subsampling,
                "is_data_labeler": options.structured_options.data_labeler.is_enabled,
                "is_multiprocessing": options.structured_options.multiprocess.is_enabled,
            }
            profile_times += [column_profile_time]

        # add time for for Top-level
        if sample_size:
            profile_times += [
                {
                    "name": "StructuredProfiler",
                    "sample_size": sample_size,
                    "total_time": total_time,
                    "column": profiler.times,
                    "merge": merge_time,
                    "percent_to_nan": percent_to_nan,
                    "allow_subsampling": allow_subsampling,
                    "is_data_labeler": options.structured_options.data_labeler.is_enabled,
                    "is_multiprocessing": options.structured_options.multiprocess.is_enabled,
                }
            ]

        print(f"COMPLETE sample size: {sample_size}")
        print(f"Profiled in {total_time} seconds")
        print(f"Merge in {merge_time} seconds")
        print()

    # Print dictionary with profile times
    print("Results Saved")
    # print(json.dumps(profile_times, indent=4))

    # only works if columns all have unique names
    times_table = (
        pd.json_normalize(profile_times).set_index(["name", "sample_size"]).sort_index()
    )

    # save json and times table
    with open(path, "w") as fp:
        json.dump(profile_times, fp, indent=4)
    times_table.to_csv(path)


if __name__ == "__main__":
    ################################################################################
    ######################## set any optional changes here #########################
    ################################################################################
    options = dp.ProfilerOptions()

    # these two options default to True if commented out
    options.structured_options.multiprocess.is_enabled = False
    options.structured_options.data_labeler.is_enabled = False

    # parameter alteration
    ALLOW_SUBSAMPLING = True  # profiler to subsample the dataset if large
    PERCENT_TO_NAN = 0.0  # Value must be between 0 and 100

    # If set to None new dataset is generated.
    DATASET_PATH = "./data/time_structured_profiler.csv"

    TIME_ANALYSIS = True
    SPACE_ANALYSIS = True
    sample_sizes = [100, 1000, 5000, 7500, int(1e5)]

    # set seed
    random_seed = 0
    ################################################################################

    random.seed(random_seed)
    np.random.seed(random_seed)
    dp.set_seed(random_seed)
    rng = np.random.default_rng(seed=random_seed)
    # load data]
    if not DATASET_PATH:
        data = generate_dataset_by_class(rng, dataset_length=max(sample_sizes))
    else:
        data = dp.Data(DATASET_PATH)

    if TIME_ANALYSIS:
        dp_time_analysis(
            sample_sizes,
            data,
            path="structured_profiler_times.json",
            percent_to_nan=PERCENT_TO_NAN,
            options=options,
        )
    if SPACE_ANALYSIS:
        profile = dp_profile_space_analysis(
            data=data,
            path="profile_space_analysis.bin",
            percent_to_nan=PERCENT_TO_NAN,
            options=options,
        )
        dp_merge_space_analysis(profile=profile, path="merge_space_analysis.bin")