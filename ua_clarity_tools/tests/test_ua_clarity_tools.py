# TODO: We need to refactor this to no longer use nose.
import os
import re
import unittest
import string
import random
import json
from collections import namedtuple
from datetime import datetime

# from nose.tools import raises
from jinja2 import Template
from bs4 import BeautifulSoup
from ua_clarity_tools import ua_clarity_tools
from ua_clarity_tools import api_types


CLARITY_TOOLS = None


def setUpModule():
    creds_path = os.path.join(os.path.split(__file__)[0], "lims_dev_creds.json")
    with open(creds_path, "r") as file:
        contents = file.read()

    creds = json.loads(contents)

    global CLARITY_TOOLS

    CLARITY_TOOLS = ua_clarity_tools.ClarityTools(
        host=creds["host"], username=creds["username"], password=creds["password"]
    )


class TestClarityTools(unittest.TestCase):
    def test_get_samples(self):
        sample_soups = BeautifulSoup(
            CLARITY_TOOLS.api.get("samples", get_all=False), "xml"
        )

        sample_uris = [soup["uri"] for soup in sample_soups.find_all("sample")]

        samples = CLARITY_TOOLS.get_samples(sample_uris)

        for sample in samples:
            assert sample.uri in sample_uris
            assert sample.name
            assert sample.date_received
            if sample.project_uri:
                assert sample.project_name

    def test_get_arts_from_samples(self):
        sample_uris_soups = BeautifulSoup(
            CLARITY_TOOLS.api.get("samples", get_all=False), "xml"
        )
        sample_uris = [sample["uri"] for sample in sample_uris_soups.find_all("sample")]

        smp_art_uris = CLARITY_TOOLS.get_arts_from_samples(sample_uris)
        for uri in smp_art_uris.values():
            assert CLARITY_TOOLS.api.host in uri

    def test_get_udfs(self):
        # NOTE: To test this method, make sure you have at least 1 'Analyte'
        # udf type in your environment.
        assert len(CLARITY_TOOLS.get_udfs("Analyte")) > 1

    def test_set_reagent_label_with_none_and_reagent(self):
        art_uris_soups = BeautifulSoup(
            CLARITY_TOOLS.api.get("artifacts", get_all=False), "xml"
        )

        limsid_none_label = dict()
        limsid_reagent_label = dict()
        art_uris = list()

        for art in art_uris_soups.find_all("artifact"):
            art_uris.append(art["uri"])
            reagent_name = f"Reagent {string.ascii_uppercase[random.randint(0, 25)]}"

            limsid_none_label[art["limsid"]] = None
            limsid_reagent_label[art["limsid"]] = reagent_name

        CLARITY_TOOLS.set_reagent_label(limsid_none_label)

        art_soups = BeautifulSoup(CLARITY_TOOLS.api.get(art_uris), "xml")
        for soup in art_soups.find_all("art:artifact"):
            assert soup.find("reagent-label") is None

        CLARITY_TOOLS.set_reagent_label(limsid_reagent_label)

        art_soups = BeautifulSoup(CLARITY_TOOLS.api.get(art_uris), "xml")
        for soup in art_soups.find_all("art:artifact"):
            reagent_soup = soup.find("reagent-label")["name"]
            assert limsid_reagent_label[soup["limsid"]] == reagent_soup

        CLARITY_TOOLS.set_reagent_label(limsid_none_label)

    def test_step_router(self):
        arts_url = f"{CLARITY_TOOLS.api.host}artifacts"
        art_uris_soups = BeautifulSoup(
            CLARITY_TOOLS.api.get(arts_url, get_all=False), "xml"
        )
        artifact_uris = [art["uri"] for art in art_uris_soups.find_all("artifact")]

        workflows_url = f"{CLARITY_TOOLS.api.host}configuration/workflows"
        workflows_soup = BeautifulSoup(CLARITY_TOOLS.api.get(workflows_url), "xml")

        for workflow in workflows_soup.find_all("workflow"):
            if workflow["status"] == "ACTIVE" and "CS-" not in workflow["name"]:
                stages_response = CLARITY_TOOLS.api.get(workflow["uri"])
                workflow_name = workflow["name"]
                workflow_soup = BeautifulSoup(stages_response, "xml")
                stage_soup = workflow_soup.find("stage")
                stage_name = stage_soup["name"]
                break

        # Don't worry about testing the soup tag -- is a PAIN to make sure that
        # the queue was changed. If this doesn't error, the queue has already
        # been checked.
        CLARITY_TOOLS.step_router(workflow_name, stage_name, artifact_uris)
        CLARITY_TOOLS.step_router(
            workflow_name, stage_name, artifact_uris, action="unassign"
        )

    @raises(ua_clarity_tools.ClarityExceptions.CallError)
    def test_step_router_wf_does_not_exist(self):
        CLARITY_TOOLS.step_router("Doesn't exist", "", [])

    @raises(ua_clarity_tools.ClarityExceptions.CallError)
    def test_step_router_step_does_not_exist(self):
        workflows_url = f"{CLARITY_TOOLS.api.host}configuration/workflows"
        workflows_soup = BeautifulSoup(CLARITY_TOOLS.api.get(workflows_url), "xml")

        for workflow in workflows_soup.find_all("workflow"):
            if workflow["status"] == "ACTIVE" and "CS-" not in workflow["name"]:
                workflow_soup = BeautifulSoup(
                    CLARITY_TOOLS.api.get(workflow["uri"]), "xml"
                )
                stage_soup = workflow_soup.find("stage")
                stage_name = stage_soup["name"]
                break

        CLARITY_TOOLS.step_router(stage_name, "Doesn't exist", [])


class TestStepTools(unittest.TestCase):
    def setUp(self):
        creds_path = os.path.join(os.path.split(__file__)[0], "lims_dev_creds.json")
        with open(creds_path, "r") as file:
            contents = file.read()

        creds = json.loads(contents)

        # NOTE: For now, add a standard step type by hand in the web interface,
        # then add that step uri to your creds file.
        self.step_tools = ua_clarity_tools.StepTools(
            creds["username"], creds["password"], creds["step_uri"]
        )

        # TODO: Programmatically create a step.

    def test_get_artifacts_input_stream(self):
        return_value = self.step_tools.get_artifacts("input")

        art_uris = self._harvest_art_uris("input")
        batch_artifacts = BeautifulSoup(self.step_tools.api.get(art_uris), "xml")

        uri_artifacts = dict()
        for artifact_data in batch_artifacts.find_all("artifact"):
            artifact = ua_clarity_tools.Artifact()
            artifact.name = artifact_data.find("name").text
            artifact.container_uri = artifact_data.find("container")["uri"]
            artifact.location = artifact_data.find("location").find("value").text
            uri_artifacts[artifact_data["uri"].split("?")[0]] = artifact

        assert len(uri_artifacts) == len(return_value)
        for found in return_value:
            expected = uri_artifacts[found.uri]
            assert expected.name == found.name
            assert expected.container_uri == found.container_uri
            assert expected.location == found.location

    def test_get_artifacts_output_stream(self):
        return_value = self.step_tools.get_artifacts("output")

        art_uris = self._harvest_art_uris("output")
        batch_artifacts = BeautifulSoup(self.step_tools.api.get(art_uris), "xml")

        uri_artifacts = dict()
        for artifact_data in batch_artifacts.find_all("artifact"):
            artifact = ua_clarity_tools.Artifact()
            artifact.name = artifact_data.find("name").text
            artifact.container_uri = artifact_data.find("container")["uri"]
            artifact.location = artifact_data.find("location").find("value").text
            uri_artifacts[artifact_data["uri"].split("?")[0]] = artifact

        assert len(uri_artifacts) == len(return_value)
        for found in return_value:
            expected = uri_artifacts[found.uri]
            assert expected.name == found.name
            assert expected.container_uri == found.container_uri
            assert expected.location == found.location

    def test_get_artifacts_both_streams_uri_only(self):
        input_return = self.step_tools.get_artifacts("input", uri_only=True)
        output_return = self.step_tools.get_artifacts("output", uri_only=True)

        in_art_uris = self._harvest_art_uris("input")
        out_art_uris = self._harvest_art_uris("output")
        batch_in_artifacts = BeautifulSoup(self.step_tools.api.get(in_art_uris), "xml")
        batch_out_artifacts = BeautifulSoup(
            self.step_tools.api.get(out_art_uris), "xml"
        )

        input_uris = [
            art["uri"].split("?")[0] for art in batch_in_artifacts.find_all("artifact")
        ]
        output_uris = [
            art["uri"].split("?")[0] for art in batch_out_artifacts.find_all("artifact")
        ]

        assert len(input_uris) == len(input_return)
        assert len(output_uris) == len(output_return)

        for expected in input_uris:
            assert expected in input_return

        for expected in output_uris:
            assert expected in output_return

    def test_get_artifacts_output_container_info(self):
        return_value = self.step_tools.get_artifacts("output", container_info=True)

        art_uris = self._harvest_art_uris("output")
        batch_artifacts = BeautifulSoup(self.step_tools.api.get(art_uris), "xml")

        artifacts = list()
        con_uris = list()
        for artifact_data in batch_artifacts.find_all("artifact"):
            artifact = ua_clarity_tools.Artifact()
            artifact.name = artifact_data.find("name").text
            artifact.container_uri = artifact_data.find("container")
            if artifact.container_uri:
                artifact.container_uri = artifact.container_uri["uri"]
            artifact.location = artifact_data.find("location")
            if artifact.location:
                artifact.location = artifact.location.find("value").text
            artifacts.append(artifact)
            con_uris.append(artifact.container_uri)

        con_soups = BeautifulSoup(self.step_tools.api.get(con_uris), "xml")
        ConInfo = namedtuple("ConInfo", ["name", "con_type"])
        con_uri_info = dict()
        for soup in con_soups.find_all("con:container"):
            con_uri_info[soup["uri"]] = ConInfo(
                soup.find("name").text, soup.find("type")["name"]
            )
        for art in artifacts:
            art.container_name = con_uri_info.get(art.container_uri).name

        assert len(artifacts) == len(return_value)

        for expected, found in zip(artifacts, return_value):
            assert expected.name == found.name
            assert expected.container_uri == found.container_uri
            assert expected.location == found.location

    def test_get_artifacts_output_per_all_inputs(self):
        # TODO: Find or make step that only has shared outputs.
        pass

    def test_get_process_data(self):
        test_process = self.step_tools.get_process_data()

        step_limsid = self.step_tools.args.step_uri.split("/")[-1]
        process_uri = f"{self.step_tools.api.host}processes/{step_limsid}"
        soup = BeautifulSoup(self.step_tools.api.get(process_uri), "xml")

        first_name = soup.find("first-name").text.strip()
        last_name = soup.find("last-name").text.strip()
        expected_technician = f"{first_name} {last_name}"
        udfs = {udf["name"]: udf.text for udf in soup.find_all("udf:field")}

        assert test_process.technician == expected_technician
        for udf in udfs.keys():
            assert test_process.udf[udf] == udfs[udf]

    def test_get_artifact_map_one_input_one_output(self):
        test_map = self.step_tools.get_artifact_map()
        in_out_uris = self._harvest_art_uris("map")

        all_uris = list(in_out_uris.keys())
        all_uris.extend(list(in_out_uris.values()))

        arts_soup = BeautifulSoup(self.step_tools.api.get(all_uris), "xml")

        for in_art, out_arts in test_map.items():
            expected_input = arts_soup.find(
                attrs={"uri": re.compile(f"{in_art.uri}.*")}
            )
            expected_output = arts_soup.find(
                attrs={"uri": re.compile(f"{out_arts[0].uri}.*")}
            )

            assert in_out_uris[in_art.uri] == expected_output["uri"].split("?")[0]

            assert in_art.name == expected_input.find("name").text
            assert in_art.container_uri == expected_input.find("container")["uri"]
            assert in_art.location == expected_input.find("location").find("value").text

            assert out_arts[0].name == expected_output.find("name").text
            assert out_arts[0].container_uri == expected_output.find("container")["uri"]
            assert (
                out_arts[0].location
                == expected_output.find("location").find("value").text
            )

    def test_get_artifact_map_container_info_one_input_one_output(self):
        test_map = self.step_tools.get_artifact_map(container_info=True)
        in_out_uris = self._harvest_art_uris("map")

        all_uris = list(in_out_uris.keys())
        for value in in_out_uris.values():
            if type(value) == list:
                all_uris.extend(value)
            else:
                all_uris.append(value)

        arts_soup = BeautifulSoup(self.step_tools.api.get(all_uris), "xml")

        for in_art, out_arts in test_map.items():
            expected_input = arts_soup.find(
                attrs={"uri": re.compile(f"{in_art.uri}.*")}
            )
            expected_output = arts_soup.find(
                attrs={"uri": re.compile(f"{out_arts[0].uri}.*")}
            )

            assert in_out_uris[in_art.uri] == expected_output["uri"].split("?")[0]

            assert in_art.name == expected_input.find("name").text
            input_con_uri = expected_input.find("container")["uri"]
            assert in_art.container_uri == input_con_uri

            input_con_soup = BeautifulSoup(
                self.step_tools.api.get(input_con_uri), "xml"
            )
            assert in_art.container_name == input_con_soup.find("name").text
            assert in_art.container_type == input_con_soup.find("type")["name"]

            assert in_art.location == expected_input.find("location").find("value").text

            assert out_arts[0].name == expected_output.find("name").text
            output_con_uri = expected_output.find("container")["uri"]
            assert out_arts[0].container_uri == output_con_uri
            output_con_soup = BeautifulSoup(
                self.step_tools.api.get(output_con_uri), "xml"
            )
            assert out_arts[0].container_name == output_con_soup.find("name").text
            assert out_arts[0].container_type == output_con_soup.find("type")["name"]

            assert (
                out_arts[0].location
                == expected_output.find("location").find("value").text
            )

    def test_get_artifact_map_uri_only_one_input_one_output(self):
        test_map = self.step_tools.get_artifact_map(uri_only=True)
        in_out_uris = self._harvest_art_uris("map")

        all_uris = list(in_out_uris.keys())
        all_uris.extend(list(in_out_uris.values()))

        arts_soup = BeautifulSoup(self.step_tools.api.get(all_uris), "xml")

        for in_art, out_arts in test_map.items():
            expected_output = arts_soup.find(
                attrs={"uri": re.compile(f"{out_arts[0]}.*")}
            )

            assert in_out_uris[in_art] == expected_output["uri"].split("?")[0]

    def test_get_artifact_map_per_all_input(self):
        # TODO: Find or make step that only has shared outputs.
        pass

    def test_set_artifact_udf_input_all_data_types(self):
        udfs_url = f"{CLARITY_TOOLS.api.host}configuration/udfs"
        udfs_soup = BeautifulSoup(self.step_tools.api.get(udfs_url), "xml")
        art_udfs = [
            udf["uri"]
            for udf in udfs_soup.find_all("udfconfig")
            if udf["attach-to-name"] == "Analyte"
        ]
        art_udfs_soup = BeautifulSoup(self.step_tools.api.get(art_udfs), "xml")
        boolean_udf_soup = art_udfs_soup.find(attrs={"type": "Boolean"})
        string_udf_soup = art_udfs_soup.find(attrs={"type": "String"})
        numeric_udf_soup = art_udfs_soup.find(attrs={"type": "Numeric"})
        if not boolean_udf_soup or not string_udf_soup or not numeric_udf_soup:
            raise RuntimeError(
                "There must be at least 1 Analyte boolean, string, and numeric"
                " UDF configured to run this test."
            )

        Udf = namedtuple("Udf", ["name", "type", "value"])

        boolean_udf = Udf(boolean_udf_soup.find("name").text, "Boolean", "true")
        string_udf = Udf(string_udf_soup.find("name").text, "String", "Test")
        numeric_udf = Udf(numeric_udf_soup.find("name").text, "Numeric", "5")

        art_uris = self._harvest_art_uris("input")
        art_limsids = [art.split("/")[-1] for art in art_uris]
        udf_tests = [boolean_udf, string_udf, numeric_udf]
        sample_values = {art: udf_tests for art in art_limsids}

        self.step_tools.set_artifact_udf(sample_values, "input")

        updated_soup = BeautifulSoup(self.step_tools.api.get(art_uris), "xml")
        limsid_udfs = dict()
        for artifact in updated_soup.find_all("art:artifact"):
            limsid_udfs.setdefault(artifact["limsid"], list())
            for tag in artifact.find_all("udf:field"):
                limsid_udfs[artifact["limsid"]].append(
                    Udf(tag["name"], tag["type"], tag.text)
                )

            verified_udfs = 0
            for posted_udf in sample_values[artifact["limsid"]]:
                for found_udf in limsid_udfs[artifact["limsid"]]:
                    if posted_udf.name == found_udf.name:
                        assert found_udf.type == posted_udf.type
                        assert found_udf.value == posted_udf.value
                        verified_udfs += 1
                        break

            assert verified_udfs == len(sample_values[artifact["limsid"]])

    def _harvest_art_uris(self, stream):
        in_out_uris = dict()

        step_soup = BeautifulSoup(
            self.step_tools.api.get(f"{self.step_tools.args.step_uri}/details"), "xml"
        )

        for io_map in step_soup.find_all("input-output-map"):
            output_soup = io_map.find("output")
            input_soup = io_map.find("input")
            input_uri = input_soup["uri"].split("?")[0]
            output_uri = output_soup["uri"].split("?")[0]
            if output_soup["output-generation-type"] == "PerInput":
                in_out_uris[input_uri] = output_uri

        if stream == "input":
            return list(in_out_uris.keys())
        if stream == "output":
            return list(in_out_uris.values())
        if stream == "map":
            return in_out_uris


def _post_project(prj=None):
    """Method that will post a project and return an api_types.Project."""
    template_path = os.path.join(
        os.path.split(__file__)[0], "post_project_template.xml"
    )
    with open(template_path, "r") as file:
        template = Template(file.read())
        response_xml = template.render(
            name=f"Project_TEST_{datetime.now()}",
            open_date=str(datetime.today().date()),
            res_uri=f"{CLARITY_TOOLS.api.host}researchers/1",
        )

    res = api_types.Researcher(
        "System",
        "Administrator",
        "internal",
        "",
        f"{CLARITY_TOOLS.api.host}researchers/1",
    )

    prj_response = CLARITY_TOOLS.api.post(
        f"{CLARITY_TOOLS.api.host}projects", response_xml
    )

    prj_response_soup = BeautifulSoup(prj_response, "xml").find("prj:project")
    prj = api_types.Project(
        prj_response_soup.find("name"),
        res,
        datetime.today().date(),
        [],
        prj_response_soup["uri"],
    )

    return prj


def _post_con(name):
    """Method that will post a container and return a request."""
    template_path = os.path.join(
        os.path.split(__file__)[0], "post_container_template.xml"
    )
    with open(template_path, "r") as file:
        template = Template(file.read())
        response_xml = template.render(
            con_name=name, type_ur=f"{CLARITY_TOOLS.api.host}containertypes/1"
        )

    return CLARITY_TOOLS.api.post(f"{CLARITY_TOOLS.api.host}containers", response_xml)


def _batch_post_samples(samples, prj_info):
    """Takes a list of Samples and projet info and posts the samples."""
    template_path = os.path.join(
        os.path.split(__file__)[0], "post_samples_template.xml"
    )
    sample_xmls = list()

    # Construct each of the sample xml objects.
    for sample in samples:
        with open(template_path, "r") as file:
            template = Template(file.read())
            smp_xml = template.render(
                name=sample.name,
                prj_limsid=prj_info.uri.split("/")[-1],
                prj_uri=prj_info.uri,
                con_uri=sample.con.uri,
                location=sample.location,
                udf_dict=sample.udf_to_value,
            )
        smp_xml = smp_xml.replace("&", "&amp;")
        sample_xmls.append(smp_xml)

    batch_template_path = os.path.join(
        os.path.split(__file__)[0], "post_samples_batch_template.xml"
    )
    # Compile all of the sample xmls into a batch sample xml object.
    with open(batch_template_path, "r") as file:
        template = Template(file.read())
        batch_xml = template.render(samples="\n".join(sample_xmls))

    return CLARITY_TOOLS.api.post("samples/batch/create", batch_xml)


def _generate_samples(samples_data_table=None):
    """Method that will create  samples that can be posted."""
    samples_data_table = samples_data_table or dict()

    con_name = f"Auto_Sample_Test_{datetime.now()}"
    con_result_soup = BeautifulSoup(_post_con(con_name), "xml")
    con_uri = con_result_soup.find("con:container")["uri"]

    sample_list = list()
    for i in range(1, 97, 2):
        well = "ABCDEFGH"[(i - 1) % 8] + ":" + "%01d" % ((i - 1) // 8 + 1,)
        letter = "ABCDEFGH"[i % 8]
        to_add = api_types.Sample(f"test{i}{letter}")
        to_add.location = well
        to_add.con = api_types.Container(con_name, "96 well plate", "", con_uri)

        for data_name, data_value in samples_data_table.items():
            if "udf" in data_name:
                udf_name = data_name.strip("udf_")
                to_add.udf_to_value[udf_name] = data_value
            elif "adapter" in data_name:
                to_add.adapter = data_value
        sample_list.append(to_add)
    return sample_list
