# Changelog

All notable changes to this project can be found here.
The format of this changelog is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/) and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

### 2022/02/23 [1.1.8](https://github.com/UACoreFacilitiesIT/UA-Clarity-Tools)

Updated the "get_artifacts_previous_step()" method so that it can handle input samples that traveled through the previous step at different times (different process ids). The function will now travel down all the paths in the step history, not just the first path.

### 2022/11/14 [1.1.7](https://github.com/UACoreFacilitiesIT/UA-Clarity-Tools)

Updated the step router so it won't timeout when routing to steps with many queued samples.

#### 2021/7/12 [1.1.4](https://github.com/UACoreFacilitiesIT/UA-Clarity-Tools)

Added a command-line argument to get_samples to facilitate skipping project data.

#### 2021/1/20 [1.1.3](https://github.com/UACoreFacilitiesIT/UA-Clarity-Tools/commit/72c70ac33b36b990f63c3de27aa78fc77241de70)

Updated setup.py dependencies to be more explicit and contain every dependency.

- Previously some dependencies were not listed, but were assumed to be installed through other packages.

#### 2019/11/26 [1.1.0](https://github.com/UACoreFacilitiesIT/UA-Clarity-Tools)

- Removed hardcoded Api hosts
- If no uri's are found for a combination of arguments, get_artifacts returns an empty list. Prior it would error.

#### 2019/10/28 [1.0.0](https://github.com/UACoreFacilitiesIT/UA-Clarity-Tools/commit/3c10f9bbc8125b68b1d118ad9be2f1a9c264adf1)

Get_artifacts now returns an empty list if it can't find arts with the given arguments.

##### Changed

- In get_artifacts, if no specified uris are found, get_artifacts will now return an empty list instead of erroring.

#### 2019/10/19 [0.0.2](https://github.com/UACoreFacilitiesIT/UA-Clarity-Tools/commit/0295910650d296d2ca2cb49a12f70c8943a32264)

While making more mature tests, a couple of small bugs cropped up that were fixed. A lot of the testing code now is a little cleaner, without as much commented-out code.

##### Fixed

- Routing file_uri's to step_router will no longer throw an error. Now, if a file uri is passed it will be ignored, as files can't be routed.
- Now get_samples runs far quicker; before it would perform number of samples + 1 gets. Now, it will perform as many gets as there are projects + 1. During normal use, that is usually only a handful of gets.

##### Deprecated

- Removed get_assays method. The code is too specific for our own environment to keep as an API method.

#### 2019/10/03 [0.0.1](https://github.com/UACoreFacilitiesIT/UA-Clarity-Tools/commit/db749e06683367528f9365603bde84cf6da2cc49)

This is the initial start point for a University of Arizona Illumina Clarity Tools.

- Moved repo from private repo to public.
- The code will be moved next release, while we finish writing unit tests for the StepTools class.
