# UA-Lims-Tools

Provides 2 sets of tools for use with clarity and it's endpoints: ClarityTools
and StepTools.

## Motivation

To create a set of tools to assist in script writing for Clarity.

## Features

Use ClarityTools as a means of interfacing with Clarity and it's endpoints.

* get_samples will get all samples from a list of uris passed in.

* get_arts_from_samples will get all artifact uris for the list of uris passed.

* get_udfs will find all the udfs that should be attached to target.

* set_reagent_label will set the reagent_label for all artifacts passed.

* step_router will route a list of artifact_uris to a specified step.Use StepTools as a way of interacting with a Clarity step.*

* get_artifacts will return all artifacts from the step.

* get_process_data will retrieve the process data for the current step.

* get_artifact_map creates a mapping of input artifacts to output artifacts.

* set_artifact_udf sets the udfs of all analytes in the step.

* get_artifacts_previous_step will map the current steps artifact uris to an ancestor artifact from the step passed to it.

* get_assays will find the assays within the current protocol.## Code Example

python
from ua_lims_tools import ua_lims_tools
clarity_api = ua_lims_tools.ClarityApi()
step_api = ua_lims_tools.StepTools()

## Installation

bash
pip install ua-lims-tools

## Tests

bash
pip install --update nose
cd ./repo
cd ./tests
nosetests test_lims_tools.py

## How to Use

Examples of syntax for each method

python
clarity_api = ua_lims_tools.ClarityApi()
samples = clarity_api.get_samples(uris)

* get_samples gets the samples from the passed in uris.
* Arguments: uris is a list of sample endpoints to get.
* Returns: a list of Sample dataclass objects with gotten sample's data.

## Credits

[sterns1](https://github.com/sterns1)
[raflopjr](https://github.com/raflopjr)
[RyanJohannesBland](https://github.com/RyanJohannesBland)

## LicenseMIT