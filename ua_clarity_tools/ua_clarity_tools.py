"""Tools that interact with Clarity's REST database."""
import os
import re
import argparse
import logging
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

LOGGER = logging.getLogger(f"__main__.{__name__}")
class ClarityExceptions:
    """Holds custom Clarity Exceptions."""
    class TechnicianError(Exception):
        """A Clarity user technician has made a mistake."""

    class EPPError(Exception):
        """The EPP script provided is not correct."""

    class CallError(Exception):
        """This method call wasn't well-formed."""

    class POSTNameCollision(Exception):
        """You tried to POST something with a name that is already in Clarity."""

    class POSTException(Exception):
        """The POST failed."""

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
        if prj_info and project_uris:
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

        # Check that the artifact was queued (if not a qc protocol step, as those all have different queues).
        if qc_step is False and action == "assign":
            for uri in artifact_uris:
                file_uri = uri.split('/')[-1].startswith("92-")
                if not file_uri:
                    artifact_queued = False

                    artifact_soup = BeautifulSoup(self.api.get(uri), "xml")
                    workflow_stages = artifact_soup.find_all("workflow-stage")
                    for workflow_stage in workflow_stages:
                        if workflow_stage["name"] == dest_stage_name:
                            if workflow_stage["status"] == "QUEUED":
                                artifact_queued = True

                    if not artifact_queued:
                        raise RuntimeError(f"The artifact: {uri} was not queued.")

    def get_researcher_uri(self, res):
        """Get the uri's of all researchers in Clarity with the given name.

        Arguments:
            res (dataclass):
                A dataclass called Researcher defined in api_types, with the
                fields: "first_name", "last_name", "lab_type", "email", and
                "uri", where all of these are strings and lab_type is either
                'internal' or 'external'.

        Returns:
            res_uris (list of strings):
                A list that of all the uris with names
                that match the given res.first_name and res.last_name, case
                insensitive.

        Notes:
            The onus of responsibility for checking the size of this list is
                on the caller.
        """
        parameters = {"firstname": res.first_name, "lastname": res.last_name}
        res_soup = BeautifulSoup(self.api.get(
            "researchers", parameters=parameters), "xml")

        res_uris = list()
        for researcher in res_soup.find_all("researcher"):
            res_uris.append(researcher["uri"])

        return res_uris

    def post_researcher(self, res):
        """Add a new researcher to Clarity.

        Arguments:
            res (dataclass):
                A dataclass called Researcher defined in api_types, with the
                fields: "first_name", "last_name", "lab_type", "email", and
                "uri", where all of these are strings and lab_type is either
                'internal' or 'external'.

        Returns:
            (string):
                The uri of the newly posted researcher.

        Side Effects:
            If successful, this function will post the researcher to the
                Clarity REST DB.

        Raises:
            POSTNameCollision
            POSTException
        """
        # Check for collision.
        current_uri = self.get_researcher_uri(res)
        if current_uri != []:
            raise ClarityExceptions.POSTNameCollision(
                "There is already a researcher with that name. Choose a"
                " different one and try again.")

        # Hardcoded for the default Administrative Lab.
        lab_uri = f"{self.api.host}labs/1"

        # Build and submit the xml request. Pass in the directory that this
        # module is in, by finding the folder relative to the __file__
        # attribute of this module.
        research_template_path = os.path.join(
            os.path.split(__file__)[0],
            "post_researcher_template.xml")

        with open(research_template_path, 'r') as file:
            template = Template(file.read())
            res_xml = template.render(
                first_name=res.first_name,
                last_name=res.last_name,
                lab_uri=lab_uri,
                email=res.email)

        res_post = self.api.post("researchers", res_xml)

        res_post_soup = BeautifulSoup(res_post, "xml")
        new_researcher_uri = res_post_soup.find("res:researcher")["uri"]
        return new_researcher_uri

    def post_project(self, prj_info):
        """Add a new project to Clarity.
        Arguments:
            prj_info (dataclass):
                A dataclass called Project, defined in api_types, with the
                fields: "name", "res", "open_date", "files", "uri", where all
                of these are strings.

        Returns:
            (string):
                The uri of the posted project.

        Side Effects:
            If successful, this function will post the project to the
                Clarity REST DB.

        Raises:
            POSTNameCollision
            POSTException
        """
        # Get will return xml, but only have the project tag if a project was
        # found.
        prjs_soup = BeautifulSoup(self.api.get(
            "projects", parameters={"name": prj_info.name}), "xml")
        if prjs_soup.find("project"):
            raise(ClarityExceptions.POSTNameCollision(
                "There is already a project with that name. Choose a"
                " different one and try again."))

        # Build and submit the xml request.
        project_template_path = os.path.join(
            os.path.split(__file__)[0],
            "post_project_template.xml")

        with open(project_template_path, 'r') as file:
            template = Template(file.read())
            project_xml = template.render(
                name=prj_info.name,
                open_date=prj_info.open_date,
                researcher_uri=prj_info.res.uri)

        prj_post = self.api.post("projects", project_xml)

        prj_post_soup = BeautifulSoup(prj_post, "xml")
        new_project_uri = prj_post_soup.find("prj:project")["uri"]
        return new_project_uri

    def batch_post_containers(self, samples, prj_name):
        """Add new containers to Clarity.

        Arguments:
            samples (list of samples): The samples that contain a
                fully-formed Container in their .con value, where fully-formed
                here means having a con.name and con.con_type.
            prj_name (string): The name of the project where the samples in
                these containers are going to be posted.

        Returns:
            list_art_uris (list of  strings): The uri's of the containers that
                were just created.

        Side Effects:
            If successful, this function will post all of the containers in
                to the Clarity REST DB.

        Raises:
            POSTException
        """
        parameters = {"name": {sample.con.name for sample in samples}}
        exist_con_soup = BeautifulSoup(self.api.get(
            "containers", parameters=parameters), "xml")
        found_cons = [con.name for con in exist_con_soup.find_all("container")]

        container_types_soup = BeautifulSoup(
            self.api.get("containertypes"), "xml")
        contypes_uris = dict()
        for con_type in container_types_soup.find_all("container-type"):
            contypes_uris[con_type["name"]] = con_type["uri"]

        # Renaming container name if container name exists.
        con_post_collisions = set()
        for sample in samples:
            if sample.con.name in found_cons:
                con_post_collisions.add(sample.con.name)
                sample.con.name = f"{sample.con.name}-{prj_name}"

            # Check that the container type has been implemented.
            if sample.con.con_type in contypes_uris.keys():
                sample.con.con_type_uri = contypes_uris[sample.con.con_type]
            else:
                raise NotImplementedError(
                    f"The container type '{sample.con.con_type}' does not"
                    f" exist in this Clarity environment.")

        # Warn of any collisions.
        if con_post_collisions:
            LOGGER.warning({
                "template": os.path.join("general", "warning.html"),
                "content": (
                    f"The containers: {con_post_collisions} have the same name"
                    f" as another container in Clarity. These containers have"
                    f" been added to Clarity with their prj_names appended to"
                    f" their names.")
            })

        # Constructing various paths for use.
        con_template_path = os.path.join(
            os.path.split(__file__)[0], "post_containers_template.xml")
        batch_con_template_path = os.path.join(
            os.path.split(__file__)[0], "post_containers_batch_template.xml")

        # Constructing the xml objects for each artifact.
        con_xmls = list()
        con_infos = {
            (sample.con.name, sample.con.con_type_uri) for sample in samples}
        for name, uri in con_infos:
            with open(con_template_path, 'r') as file:
                template = Template(file.read())
                con_xml = template.render(con_name=name, con_type_uri=uri)
            con_xmls.append(con_xml)

        # Build the list that will be rendered by the Jinja template.
        with open(batch_con_template_path, 'r') as file:
            template = Template(file.read())
            container_xml = template.render(con_list='\n'.join(con_xmls))

        # Attempt to post.
        con_post = self.api.post(
            "containers/batch/create", container_xml)

        # Get return info out of post.
        con_post_soup = BeautifulSoup(con_post, "xml")
        new_container_uris = [
            link["uri"] for link in con_post_soup.find_all("link")]

        # Check that the uris are gettable.
        BeautifulSoup(self.api.get(new_container_uris), "xml")

        return new_container_uris

    def batch_post_samples(self, samples, prj_info):
        """Add samples to a project in Clarity.

        Arguments:
            samples (list of samples):
                Sample is a class defined in data_types. These objects must
                have the requisite info to post a sample: a container_uri,
                location, name, and a udf name: udf value dictionary.
            prj_info (dataclass):
                A dataclass called Project,  with the fields: "name", "res",
                "open_date", "files", "uri", where all of these are strings.

        Returns:
            (list of strings):
                The uri's of the samples that were just created.

        Side Effects:
            If successful, this function will post all of the samples in
                samples to the Clarity REST DB.

        Raises:
            requests.exceptions.HTTPError
        """

        sample_template_path = os.path.join(
            os.path.split(__file__)[0], "post_samples_template.xml")
        batch_sample_template_path = os.path.join(
            os.path.split(__file__)[0], "post_samples_batch_template.xml")
        sample_xmls = list()

        # Construct each of the sample xml objects.
        for sample in samples:
            with open(sample_template_path, 'r') as file:
                template = Template(file.read())
                smp_xml = template.render(
                    name=sample.name,
                    prj_limsid=prj_info.uri.split('/')[-1],
                    prj_uri=prj_info.uri,
                    con_uri=sample.con.uri,
                    location=sample.location,
                    udf_dict=sample.udf_to_value)
            smp_xml = smp_xml.replace('&', "&amp;")
            sample_xmls.append(smp_xml)

        # Compile all of the sample xmls into a batch sample xml object.
        with open(batch_sample_template_path, 'r') as file:
            template = Template(file.read())
            batch_xml = template.render(
                samples='\n'.join(sample_xmls))

        # If the sample has a UDF that is unknown to Clarity, remove it from
        # the xml for all samples, and try to post again.
            valid_udfs = self.get_udfs("Sample")
            batch_soup = BeautifulSoup(batch_xml, "xml")
            for udf_tag in batch_soup.find_all("udf:field"):
                if udf_tag["name"] not in valid_udfs:
                    udf_tag.decompose()

        response = self.api.post("samples/batch/create", batch_soup)
        samples_post_soup = BeautifulSoup(response, "xml")

        sample_uris = [x["uri"] for x in samples_post_soup.find_all("link")]

        # Add adapter info to sample's artifacts in Clarity if provided.
        if [sample.adapter for sample in samples if sample.adapter]:
            # Map created artifacts to samples, as I am not comfortable relying
            # on the sample_uri links being in the same order as samples.
            smp_art_uris = self.get_arts_from_samples(sample_uris)
            arts_soup = BeautifulSoup(
                self.api.get(list(smp_art_uris.values())), "xml")

            art_limsid_label = dict()
            for art in arts_soup.find_all("art:artifact"):
                for sample in samples:
                    # If location and con_uri are ==, they map to each other.
                    if (art.find("container")["uri"] == sample.con.uri
                            and art.find("value").text == sample.location):
                        art_limsid_label[art["limsid"]] = sample.adapter
            self.set_reagent_label(art_limsid_label)

        return sample_uris

    def get_workflow(self, workflow_name):
        """Return the active workflow soup for a workflow name."""
        workflow_response = self.api.get(
            "configuration/workflows",
            parameters={"name": workflow_name}
        )
        workflow_list_soup = BeautifulSoup(workflow_response, "xml")
        workflow_tag = workflow_list_soup.find("workflow")

        if not workflow_tag:
            raise ClarityExceptions.CallError(
                f"The workflow {workflow_name} does not exist."
            )

        if workflow_tag.get("status") != "ACTIVE":
            raise ClarityExceptions.CallError(
                f"The workflow {workflow_name} is not active."
            )

        workflow_soup = BeautifulSoup(self.api.get(workflow_tag["uri"]), "xml")
        return workflow_soup


    def get_stage(self, workflow_name, stage_name):
        """Return the stage tag for a stage in a workflow."""
        workflow_soup = self.get_workflow(workflow_name)
        stage = workflow_soup.find("stage", attrs={"name": stage_name})

        if not stage:
            raise ClarityExceptions.CallError(
                f"There is no {stage_name} stage in workflow {workflow_name}."
            )

        return stage

    def get_stage_uri(self, workflow_name, stage_name):
        """Return the URI for a stage in a workflow."""
        return self.get_stage(workflow_name, stage_name)["uri"]

    def get_queue_uri(self, workflow_name, stage_name):
        """Return the queue URI for a workflow stage."""
        stage_uri = self.get_stage_uri(workflow_name, stage_name)
        stage_soup = BeautifulSoup(self.api.get(stage_uri), "xml")

        queue = stage_soup.find("queue")
        if queue:
            return queue["uri"]

        step = stage_soup.find("step")
        if step and step.get("uri"):
            step_soup = BeautifulSoup(self.api.get(step["uri"]), "xml")
            queue = step_soup.find("queue")
            if queue:
                return queue["uri"]

        raise ClarityExceptions.CallError(
            f"Could not find queue for stage {stage_name} in workflow {workflow_name}."
        )

    def get_queued_artifacts(self, workflow_name, stage_name, uri_only=False):
        """Return artifacts currently queued for a workflow stage."""
        queue_uri = self.get_queue_uri(workflow_name, stage_name)
        queue_soup = BeautifulSoup(self.api.get(queue_uri), "xml")

        artifact_uris = []
        for artifact in queue_soup.find_all("artifact"):
            artifact_uris.append(artifact["uri"].split("?")[0])

        if uri_only:
            return artifact_uris

        if not artifact_uris:
            return []

        artifacts_soup = BeautifulSoup(self.api.get(artifact_uris), "xml")
        artifacts = []

        for artifact_data in artifacts_soup.find_all("art:artifact"):
            artifact = Artifact()
            artifact.name = artifact_data.find("name").text
            artifact.uri = artifact_data["uri"].split("?")[0]
            artifact.art_type = artifact_data.find("type").text
            artifact.sample_uri = artifact_data.find("sample")["uri"]

            container = artifact_data.find("container")
            if container:
                artifact.container_uri = container["uri"]

            location = artifact_data.find("location")
            if location:
                value = location.find("value")
                if value:
                    artifact.location = value.text

            parent_process = artifact_data.find("parent-process")
            if parent_process:
                artifact.parent_process = parent_process["uri"]

            reagent_label = artifact_data.find("reagent-label")
            if reagent_label:
                artifact.reagent_label = reagent_label["name"]

            for udf_data in artifact_data.find_all("udf:field"):
                artifact.udf[udf_data["name"]] = udf_data.text

            artifacts.append(artifact)

        return artifacts

    def filter_artifacts_by_samples(self, artifacts, sample_uris, uri_only=False):
        """Filter artifacts to only artifacts whose sample URI is in sample_uris."""
        sample_uri_set = set(sample_uris)

        filtered = [
            artifact for artifact in artifacts
            if artifact.sample_uri in sample_uri_set
        ]

        if uri_only:
            return [artifact.uri for artifact in filtered]

        return filtered

    def create_step_from_queue(self, workflow_name, stage_name, artifact_uris, container_type="96 well plate"):
        """Start a step from queued artifacts and return the new step URI."""
        stage = self.get_stage(workflow_name, stage_name)
        stage_soup = BeautifulSoup(self.api.get(stage["uri"]), "xml")
        step_config_uri = stage_soup.find("step")["uri"]

        artifact_uris = [uri.split("?")[0] for uri in artifact_uris]

        template_path = os.path.join(
            os.path.split(__file__)[0],
            "create_step_from_queue_template.xml"
        )

        with open(template_path, "r") as file:
            template = Template(file.read())
            step_xml = template.render(
                step_config_uri=step_config_uri,
                artifact_uris=artifact_uris,
                container_type=container_type,
            )

        response = self.api.post("steps", step_xml)

        step_soup = BeautifulSoup(response, "xml")
        step = step_soup.find("stp:step") or step_soup.find("step")

        if not step or not step.get("uri"):
            raise ClarityExceptions.CallError(
                f"Could not create step for stage {stage_name} in workflow {workflow_name}."
            )

        return step["uri"]

    def place_step_outputs(self, step_uri):
        """Place all output artifacts in the step into the output container."""

        placements_uri = f"{step_uri}/placements"

        placements_soup = BeautifulSoup(
            self.api.get(placements_uri),
            "xml",
        )

        configuration_uri = placements_soup.find("configuration")["uri"]
        step_name = placements_soup.find("configuration").text.strip()
        container_uri = placements_soup.find("container")["uri"]
        container_limsid = container_uri.split("/")[-1]

        placements = []

        row = "A"
        col = 1

        for output in placements_soup.find_all("output-placement"):
            placements.append({
                "artifact_uri": output["uri"],
                "location": f"{row}:{col}",
            })
            col += 1

        template_path = os.path.join(
            os.path.split(__file__)[0],
            "post_step_placements_template.xml",
        )

        with open(template_path, "r") as file:
            template = Template(file.read())
            placement_xml = template.render(
                placements_uri=placements_uri,
                step_uri=step_uri,
                configuration_uri=configuration_uri,
                step_name=step_name,
                container_uri=container_uri,
                container_limsid=container_limsid,
                placements=placements,
            )

        try:
            self.api.post(placements_uri, placement_xml)
        except requests.exceptions.HTTPError as e:
            print("===== PLACEMENT XML SENT =====")
            print(placement_xml)
            print("==============================")

            if e.response is not None:
                print("===== RESPONSE =====")
                print(e.response.text)
                print("====================")

            raise