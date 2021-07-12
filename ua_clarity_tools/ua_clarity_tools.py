"""Tools that interact with Clarity's REST database."""
import os
import re
import argparse
from dataclasses import dataclass, field, astuple
from collections import namedtuple
import requests
from bs4 import BeautifulSoup, Tag
from jinja2 import Template
from ua_clarity_api import ua_clarity_api


__author__ = (
    "Stephen Stern, Archer Morgan, Rafael Lopez,",
    "Ryan Johannes-Bland, Etienne Thompson")
__maintainer__ = "Ryan Johannes-Bland"
__email__ = "rjjohannesbland@email.arizona.edu"


class ClarityExceptions:
    """Holds custom Clarity Exceptions."""
    class TechnicianError(Exception):
        """A Clarity user technician has made a mistake."""

    class EPPError(Exception):
        """The EPP script provided is not correct."""

    class CallError(Exception):
        """This method call wasn't well-formed."""


PreviousStepArtifact = namedtuple(
    "PreviousStepArtifact", ["uri", "art_type", "generation_type"])


@dataclass
class Sample:
    """Stores the fields of a Sample."""
    name: str = ""
    uri: str = None
    date_received: str = None
    project_uri: str = None
    project_name: str = None
    artifact_uri: str = None
    udf: dict = field(default_factory=dict)


@dataclass
class Artifact:
    """Stores the fields of an Artifact."""
    name: str = None
    uri: str = None
    art_type: str = None
    sample_uri: str = None
    container_uri: str = None
    container_name: str = None
    container_type: str = None
    location: str = None
    parent_process: str = None
    reagent_label: str = None
    udf: dict = field(default_factory=dict)


@dataclass
class Process:
    """Stores the fields of a Process."""
    uri: str = None
    technician: str = "None"
    udf: dict = field(default_factory=dict)


class ClarityTools():
    """Tools that interact with Clarity without a step. These tools are general
    use functions for when caller is not attached to a step and knows the
    endpoints they want to perform work on. These methods are not limited by
    the requirement to have a step uri.
    """
    def __init__(self, host, username, password):
        """Initializes a ClarityAPI object for use within method calls.

        username and password should be strings representing your creds in the
            clarity environment.
        host should be a string representing the url of your clarity api
            endpoint.
        """
        self.api = ua_clarity_api.ClarityApi(host, username, password)

    def get_samples(self, uris, prj_info=True):
        """Returns a list of Sample data classes with data populated from the
        get responses of given clarity sample URIs.

        Arguments:
            uris (list): List of Sample URIs harvested from the clarity env.

        Returns:
            samples (list): Returns a list of Sample data classes.
        """
        samples = list()
        samples_soup = BeautifulSoup(self.api.get(uris), "xml")
        project_uris = set()
        for sample_data in samples_soup.find_all("smp:sample"):
            sample = Sample()

            sample.name = sample_data.find("name").text
            sample.uri = sample_data["uri"]
            sample.date_received = sample_data.find("date-received").text

            # Find the project uri if the sample is not a control sample.
            if prj_info:
                if sample_data.find("control-type"):
                    sample.project_uri = None
                    sample.project_name = None

                else:
                    project = sample_data.find("project")
                    sample.project_uri = project["uri"]
                    project_uris.add(project["uri"])

            # Find 0th-artifact tag and extract data.
            artifact = sample_data.find("artifact")
            sample.artifact_uri = artifact["uri"].split('?')[0]

            # Extract all UDF names and values.
            for udf_data in sample_data.find_all("udf:field"):
                sample.udf[udf_data["name"]] = udf_data.text

            samples.append(sample)

        # Map the projects to their names.
        if prj_info:
            projects_soup = BeautifulSoup(
                self.api.get(list(project_uris)), "xml")
            project_uri_name = dict()
            for soup in projects_soup.find_all("prj:project"):
                project_uri_name[soup["uri"]] = soup.find("name").text.strip()

            # Assign project names to each sample.
            for sample in samples:
                sample.project_name = project_uri_name.get(sample.project_uri)

        return samples

    def get_arts_from_samples(self, sample_uris):
        """Map sample uris to their respective artifact uris from clarity.

        Arguments:
            sample_uris (list): A list of sample uris. All sample uris given
                must have at least one artifact uri in clarity.

        Returns:
            smp_art_uris (dict): The sample uri mapped to the artifact uri.
        """
        batch_soup = BeautifulSoup(self.api.get(sample_uris), "xml")

        smp_art_uris = dict()
        for sample_soup in batch_soup.find_all("smp:sample"):
            smp_art_uris[sample_soup["uri"]] = sample_soup.find(
                "artifact")["uri"].split('?')[0]

        return smp_art_uris

    def get_udfs(self, target):
        """Find all of the udfs with attach-to-name: target attributes.

        Arguments:
            target (str): A string representation of what attach-to-name
                attributes to harvest.

        Returns:
            target_udfs (list): A list of all udf names for specified target.

        Raises:
            ClarityExceptions.CallError: If there are no target udfs found.
        """
        udfs = self.api.get(
            "configuration/udfs", parameters={"attach-to-name": target})
        udf_soup = BeautifulSoup(udfs, "xml")

        target_udfs = [tag["name"] for tag in udf_soup.find_all("udfconfig")]

        if not target_udfs:
            raise ClarityExceptions.CallError(
                f"There are no UDFs for {target}. Either that target"
                f" doesn't exist, or you forgot that this argument is"
                f" case sensitive.")

        return target_udfs

    def set_reagent_label(self, limsid_label):
        """Set reagent-label of all artifact limsid keys to their mapped value.

        Arguments:
            limsid_label (dict {str: str}): maps limsid's to
                reagent-label information. If a value is Falsey, then all
                labels will be removed.

        Side Effects:
            If successful, this method will add a reagent-label to each
                artifact.
            Overwrites the original reagent-label if it existed.

        Raises:
            RuntimeError: If there was an exception raised while POSTing.
        """
        art_uris = [f"artifacts/{key}" for key in limsid_label.keys()]
        art_soup = BeautifulSoup(self.api.get(art_uris), "xml")

        for art in art_soup.find_all("art:artifact"):
            art_limsid = art["limsid"]
            reagent_label = limsid_label.get(art_limsid)
            if reagent_label:
                label_tag = f'<reagent-label name="{reagent_label}"/>'
                label_tag = BeautifulSoup(label_tag, "xml")
                art.find("sample").insert_after(label_tag)
            else:
                [tag.decompose() for tag in art.find_all("reagent-label")]

        # Use Jinja to create the batch update xml.
        template_path = (os.path.join(
            os.path.split(__file__)[0], "batch_artifact_update_template.xml"))

        with open(template_path, "r") as file:
            template = Template(file.read())
            update_xml = template.render(artifacts=[
                str(tag) for tag in art_soup.find_all("art:artifact")])

        self.api.post(f"{self.api.host}artifacts/batch/update", update_xml)

    def step_router(self, wf_name, dest_stage_name, art_uris, action="assign"):
        """Assign/unassign artifacts from current step to a destination step.
            Assigning will move the artifacts to the given destination step.
            Unassigning will remove the artifact from the step/queue, but does
            not remove the artifact from the clarity environment

        Arguments:
            wf_name (string): The workflow name in which the destination
                step is.
            dest_stage_name (string): The step name that is the destination
                for the artifacts.
            art_uris (list): The list of artifact_uris to route to the
                destination step.
            action (string): Either 'assign' or 'unassign', determining which
                action to perform.

        Side Effects:
            If successful, assigns or unassigns the artifacts to the
                destination step in Clarity.

        Raises:
            ClarityExceptions.CallError: If that workflow or stage isn't found.
            RuntimeError: If there was an exception raised while POSTing.
            RuntimeError: If for some other, unknown reason the artifact was
                not routed.
        """
        # Remove the ?state information from the artifacts.
        artifact_uris = [uri.split('?')[0] for uri in art_uris]

        # Extract all of the workflow names from Clarity.
        workflows_url = f"{self.api.host}configuration/workflows"
        workflow_cnf_response = (self.api.get(
            workflows_url, parameters={"name": wf_name}))
        workflow_cnf_soup = BeautifulSoup(workflow_cnf_response, "xml")
        workflow_cnf_soup = workflow_cnf_soup.find("workflow")

        # If the workflow passed in doesn't exist or isn't active.
        if not workflow_cnf_soup:
            raise ClarityExceptions.CallError(
                f"The workflow {wf_name} doesn't exist.")
        else:
            if not workflow_cnf_soup["status"] == "ACTIVE":
                raise ClarityExceptions.CallError(
                    f"The worklow {wf_name} is not active.")

        # Find all of the stage names.
        workflow_soup = BeautifulSoup(
            self.api.get(workflow_cnf_soup["uri"]), "xml")
        wf_stages = workflow_soup.find_all("stage")
        stage_names = [stage["name"] for stage in wf_stages]

        # If that stage name isn't in that workflow, throw an error.
        if dest_stage_name not in stage_names:
            raise ClarityExceptions.CallError(
                f"There is no {dest_stage_name} stage(step) in the {wf_name}"
                f" format.")

        stage_uri = workflow_soup.find(
            "stage", attrs={"name": dest_stage_name})["uri"]
        stage_soup = BeautifulSoup(self.api.get(stage_uri), "xml")

        # Find the step uri which will provide the location of the queue.
        try:
            step_uri = stage_soup.find("step")["uri"].split('/')[-1]
            qc_step = False
        except TypeError:
            qc_step = True

        # Build and submit the routing message.
        routing_template_path = os.path.join(
            os.path.split(__file__)[0],
            "routing_template.xml")
        with open(routing_template_path, "r") as file:
            template = Template(file.read())
            routing_xml = template.render(
                stage_uri=stage_uri,
                artifact_uris=artifact_uris,
                action=action)

        try:
            self.api.post(f"{self.api.host}route/artifacts", routing_xml)
        except requests.exceptions.HTTPError:
            raise RuntimeError(f"The post for \n\n{routing_xml}\n\n failed.")

        # Check the queue for this stagename to make sure the artifacts were
        # actually added to it if the queue is easily accessible (not a qc
        # protocol step, as those all have different queues).
        if qc_step is False and action == "assign":
            queue_uri = f"{self.api.host}queues/{step_uri}"
            queue_soup = BeautifulSoup(self.api.get(queue_uri), "xml")
            queue_art_uris = [
                soup["uri"] for soup in queue_soup.find_all("artifact")]
            for uri in artifact_uris:
                file_uri = uri.split('/')[-1].startswith("92-")
                if uri not in queue_art_uris and not file_uri:
                    raise RuntimeError(f"The artifact: {uri} was not queued.")


class StepTools():
    """Defines step specific methods which act upon a given step uri in
        Clarity. This class can be instantiated directly or from a Clarity EPP
        script.
    """

    def __init__(self, username=None, password=None, step_uri=None):
        """Initialize LimsTools with information to access step details.

        username and password should be strings representing your creds in the
            clarity environment.
        step_uri should be a string representing the step endpoint in your
            clarity environment that you wish to perform work on.
        """
        if username and password and step_uri:
            UserData = namedtuple(
                "UserData", ["username", "password", "step_uri"])
            self.args = UserData(username, password, step_uri)
        else:
            self.args = self.setup_arguments()

        self.host = re.sub("v2/.*", "v2/", self.args.step_uri)
        self.api = ua_clarity_api.ClarityApi(
            self.host, self.args.username, self.args.password)
        self.step_soup = BeautifulSoup(self.api.get(
            f"{self.args.step_uri}/details"), "xml")

    def setup_arguments(self):
        """Incorporate EPP arguments into your StepTools object.

        Returns:
            (arguments): The object that holds all of the arguments that
                were parsed (at object.{dest}).
        """
        parser = argparse.ArgumentParser()
        parser.add_argument(
            "-u", dest="username", required=True)
        parser.add_argument(
            "-p", dest="password", required=True)
        parser.add_argument(
            "-s", dest="step_uri", required=True)
        parser.add_argument(
            "-r", dest="input_files", nargs='+')
        parser.add_argument(
            "-o", dest="output_files", nargs='+')
        parser.add_argument(
            "--log", dest="log")
        parser.add_argument(
            "nargs", nargs=argparse.REMAINDER)

        return parser.parse_args()

    def get_artifacts(self, stream, uri_only=False, container_info=False):
        """Return the artifact information as a list of Artifact data classes.

        Arguments:
            stream (str): The source of the samples, either "input" or
                "output".

        Returns:
            artifacts (list): Returns a list of Artifact data classes.

        Notes:
            Does not include 'PerAllInputs' shared output files.
        """

        art_uris = list()

        # Get URI for target artifacts.
        for iomap in self.step_soup.find_all("input-output-map"):
            target = iomap.find(stream)
            # If there are no {stream}s, skip this iomap soup.
            if target is None:
                continue
            # Only add perInput output uri's.
            if stream == "output":
                if target["output-generation-type"] == "PerInput":
                    art_uris.append(target["uri"])
            # Add input uri's.
            else:
                art_uris.append(target["uri"])

        if art_uris:
            batch_artifacts = BeautifulSoup(self.api.get(art_uris), "xml")
        else:
            return art_uris

        # Store all artifact data.
        artifacts = list()
        con_uris = set()
        for artifact_data in batch_artifacts.find_all("artifact"):
            artifact = Artifact()
            artifact.name = artifact_data.find("name").text
            artifact.uri = artifact_data["uri"].split("?")[0]
            artifact.art_type = artifact_data.find("type").text
            artifact.sample_uri = artifact_data.find("sample")["uri"]

            reagent_label = artifact_data.find("reagent-label")
            if reagent_label:
                artifact.reagent_label = reagent_label["name"]

            # If the artifact has no location or container, set as None.
            artifact.container_uri = artifact_data.find("container")
            artifact.location = artifact_data.find("location")
            if artifact.location:
                artifact.location = artifact_data.location.find("value").text

            if artifact.container_uri:
                con_uris.add(artifact.container_uri["uri"])
                artifact.container_uri = artifact.container_uri["uri"]

            # Find Parent Process.
            parent_process = artifact_data.find("parent-process")
            if parent_process:
                parent_process = parent_process["uri"]

            # Construct UDF Map.
            for udf_data in artifact_data.find_all("udf:field"):
                artifact.udf[udf_data["name"]] = udf_data.text

            # Add link only.
            if uri_only:
                artifacts.append(artifact.uri)
            # Store all artifact data.
            else:
                artifacts.append(artifact)

        # Setting the Artifact's con info if desired, by using a batch get.
        ConInfo = namedtuple("ConInfo", ["name", "con_type"])
        con_uri_info = dict()
        if not uri_only and container_info and con_uris:
            con_soups = BeautifulSoup(self.api.get(list(con_uris)), "xml")
            for soup in con_soups.find_all("con:container"):
                con_uri_info[soup["uri"]] = ConInfo(
                    soup.find("name").text, soup.find("type")["name"])

            for art in artifacts:
                art.container_name = con_uri_info.get(art.container_uri).name
                art.container_type = con_uri_info.get(
                    art.container_uri).con_type

        return artifacts

    def get_process_data(self):
        """Retrieves Process data for the current step, including technician,
            uri, and udfs.

        Returns:
            process: a Process dataclass representing the process of the
                current step.
        """
        step_limsid = self.args.step_uri.split("/")[-1]
        process_uri = (f"{self.api.host}processes/{step_limsid}")

        # Get Process URI to extract data.
        soup = BeautifulSoup(self.api.get(process_uri), "xml")

        # Construct Process data class.
        process = Process()
        process.uri = process_uri
        first_name = soup.find("first-name").text.strip()
        last_name = soup.find("last-name").text.strip()
        process.technician = f"{first_name} {last_name}"

        # Extract all UDF names and values.
        for udf_data in soup.find_all("udf:field"):
            process.udf[udf_data["name"]] = udf_data.text

        return process

    def get_artifact_map(self, uri_only=False, container_info=False):
        """Returns a map of input artifacts to output artifacts, either as uris
            or as Artifact dataclasses. One input artifact can be mapped to a
            list of their multiple output artifacts.

        Arguments:
            uri_only (boolean): This denotes whether to harvest this mapping as
                uris or as namedtuples.

        Returns:
            artifact_map (dict {input artifact: [output_artifact]}):
                Returns a dict of input artifact : all output artifacts.
        """
        if not uri_only:
            # Make a dict with input_uri: input_artifact.
            input_uri_art = {
                art.uri: art for art in self.get_artifacts("input")}
            # Make a dict with output_uri: output_artifact.
            output_uri_art = {
                art.uri: art for art in self.get_artifacts("output")}

        # The container_name and container_type fields will always be None,
        # because it is not always necessary. They exist so that
        # the data_class can be run through the 'astuple' method.
        Hashable_Artifact = namedtuple("HashableArtifact", [
            "name",
            "uri",
            "art_type",
            "sample_uri",
            "container_uri",
            "container_name",
            "container_type",
            "location",
            "parent_process",
            "reagent_label"
        ])

        artifact_map = dict()
        for io_map in self.step_soup.find_all("input-output-map"):
            output_soup = io_map.find("output")
            if output_soup["output-generation-type"] == "PerInput":
                input_uri = io_map.find("input")["uri"]
                output_uri = output_soup["uri"]

                if uri_only and not container_info:
                    artifact_map.setdefault(input_uri, list())
                    artifact_map[input_uri].append(output_uri)

                else:
                    if container_info:
                        input_con_soup = BeautifulSoup(
                            self.api.get(
                                input_uri_art[input_uri].container_uri),
                            "xml")
                        input_con_name = input_con_soup.find("name").text
                        input_con_type = input_con_soup.find("type")["name"]
                        input_uri_art[
                            input_uri].container_name = input_con_name
                        input_uri_art[
                            input_uri].container_type = input_con_type

                        output_con_soup = BeautifulSoup(
                            self.api.get(
                                output_uri_art[output_uri].container_uri),
                            "xml")
                        output_con_name = output_con_soup.find("name").text
                        output_con_type = output_con_soup.find("type")["name"]
                        output_uri_art[
                            output_uri].container_name = output_con_name
                        output_uri_art[
                            output_uri].container_type = output_con_type

                    # Convert to hashable namedtuples excluding the UDF map.
                    input_art = Hashable_Artifact(
                        *(astuple(input_uri_art[input_uri])[:-1]))
                    output_art = Hashable_Artifact(
                        *(astuple(output_uri_art[output_uri])[:-1]))

                    artifact_map.setdefault(input_art, list())
                    artifact_map[input_art].append(output_art)

        return artifact_map

    def set_artifact_udf(self, sample_values, stream):
        """Set UDF values for analytes in the current step based on given
            mapping.

        Arguments:
            sample_values (dict {str: [namedtuple]}): Maps sample limsid's to
                a list of namedtuples called 'UDF' with the fields 'name',
                'value'.

            stream (str): The source of the samples, either "input" or
                "output".

        Side Effects:
            Sets the samples' UDFs that were passed into the REST database.
                Overwrites the value that was in that UDF if it existed.

        Raises:
            RuntimeError: If there was an exception raised while POSTing.

        Requirements:
            The UDF Value's type must be in line with Clarity's
                initialization of that type.
        """
        art_uris = list()
        for iomap in self.step_soup.find_all("input-output-map"):
            art_soup = iomap.find(stream)
            art_uris.append(art_soup["uri"])

        art_soups = BeautifulSoup(self.api.get(art_uris), "xml")
        art_queue = list()

        for art in art_soups.find_all("art:artifact"):
            if art["limsid"] in sample_values:
                udfs = sample_values[art["limsid"]]
                for udf in udfs:
                    target_udf = art.find(attrs={"name": udf.name})
                    # If the UDF exists as a value, replace it.
                    if target_udf:
                        target_udf.string = str(udf.value)
                    # If it does not exist, find out the UDF type for Clarity.
                    else:
                        if isinstance(udf.value, bool):
                            udf_type = "Boolean"
                        elif (isinstance(udf.value, int)
                                or isinstance(udf.value, float)):
                            udf_type = "Numeric"
                        else:
                            udf_type = "String"

                        # Build a new UDF tag and add it to the art:artifact.
                        udf_tag = Tag(
                            builder=art.builder,
                            name="udf:field",
                            attrs={"name": udf.name, "type": udf_type})

                        udf_tag.string = str(udf.value)
                        art.find("sample").insert_after(udf_tag)
                # Build the list that will be rendered by the Jinja template.
                art_queue.append(str(art))

        # Use Jinja to create the batch update xml.
        template_path = (os.path.join(
            os.path.split(__file__)[0], "batch_artifact_update_template.xml"))
        with open(template_path, "r") as file:
            template = Template(file.read())
            update_xml = template.render(artifacts=art_queue)

        self.api.post(f"{self.api.host}artifacts/batch/update", update_xml)

    def get_artifacts_previous_step(
            self, dest_step, stream, art_smp_uris, step_soup, results=dict()):
        """Return artifact uris mapped to ancestor artifacts from a target
            step.

        Arguments:
            dest_step (str): The name of the step where the ancestor
                artifacts were created.
            stream (str): The source of the samples, either "input" or
                "output" in the dest_step.
            art_smp_uris (dict {str: str}): A dict that maps smp_uris to
                passed in art_uris.
            step_soup: The step details soup for initial step.
            results (dict): The empty dict that will eventually be returned
                with the desired artifacts from the dest_step.

        Returns:
            results (dict {str: Artifact}): The dictionary that
                maps the art_uri to the artifact namedtuple. All of the
                'PerAllInputs' are stored in the results dict at
                results['shared']. If the art_uri does not have ancestors at
                that target, the art_uri will not be in the dictionary.

        Exceptions:
            RuntimeError: If that target_step is not in any of the provided
                art_uri histories.
            RuntimeError: If there are targets that ran through the step at
                two or more different times. (The dest_step process id is not
                the same for all of the passed-in samples.)

        Requirements:
            The targets to reroute must all have the same endpoint; if a sample
                went through the step separately from its fellows, this
                will not work.
        """
        try:
            step_name = step_soup.find("configuration").text
        except AttributeError:
            step_name = step_soup.find("type").text

        if step_name != dest_step:
            # Harvest all of the input uri's of the current step.
            input_uris = [art["uri"].split(
                '?')[0]for art in step_soup.find_all("input")]
            all_input_soup = BeautifulSoup(self.api.get(input_uris), "xml")

            try:
                # Harvest all of the previous steps of the current step.
                prev_steps = {
                    tag["uri"] for tag in all_input_soup.find_all(
                        "parent-process")}

            # If there is no parent-process tag, the step isn't in at least
            # one of the initial artifact's history.
            except AttributeError:
                raise RuntimeError(
                    f"The target_step is not in one or more of your "
                    f"art_smp_uris histories. The earliest step is "
                    f"{step_name}")

            # for every prev_step, you need to recurse (where all of the
            # stored result values are in results).
            else:
                for step_uri in prev_steps:
                    step_soup = BeautifulSoup(self.api.get(step_uri), "xml")
                    return self.get_artifacts_previous_step(
                        dest_step, stream, art_smp_uris, step_soup, results)

        else:
            # Get all of the inputs or outputs as PreviousStepArtifacts.
            target_arts = list()
            for iomap in step_soup.find_all("input-output-map"):
                art_uri = iomap.find(stream)["uri"].split('?')[0]
                out_art = iomap.find("output")
                art_type = out_art["output-type"]
                art_generation_type = out_art["output-generation-type"]

                # Skip PerInput ResultFiles, because there is not a way to map
                # them to the originally passed in artifacts (they don't have
                # a sample tag to match).
                if (art_generation_type == "PerInput"
                        and art_type == "ResultFile"):
                    continue

                # Add Analytes and shared ResultFiles to be matched to its
                # originally passed in analyte.
                target_arts.append(PreviousStepArtifact(
                    art_uri, art_type, art_generation_type))

            target_art_uris = [art.uri for art in target_arts]
            all_target_soup = BeautifulSoup(
                self.api.get(target_art_uris), "xml")

            target_smp_arts = dict()
            # Map the input or output sample_uri : list of
            # Previous_Step_Analytes.
            for art in all_target_soup.find_all("art:artifact"):
                for target_art in target_arts:
                    if art["uri"].split('?')[0] == target_art.uri:
                        target_smp_arts.setdefault(
                            art.find("sample")["uri"], []).append(target_art)

            # Add as a result the original uri: list of Artifacts.
            for initial_art_uri, initial_smp_uri in art_smp_uris.items():
                try:
                    results[initial_art_uri] = target_smp_arts[initial_smp_uri]
                except KeyError:
                    raise RuntimeError(
                        f"The artifact {initial_art_uri} did not run at the"
                        f" same time as the other samples passed in.")

            # Add the PerAllInputs ResultFiles to the results with the key
            # of 'shared'.
            for art in target_arts:
                if art.art_type == "ResultFile":
                    results.setdefault("shared", []).append(art)
            return results
