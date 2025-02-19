# Copyright 2020-2023 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

import os
import yaml
import logging

import tests.end_to_end.utils.constants as constants
import tests.end_to_end.utils.subprocess_helper as sh

log = logging.getLogger(__name__)


# Define the ModelOwner class
class ModelOwner:
    """
    ModelOwner class to handle the model related operations.
    Note: Aggregator can also act as a model owner.
    This includes (non-exhaustive list):
    1. Creating the workspace - to create a workspace using given workspace and model names.
    2. Modifying based on input params provided and initializing the plan.
    3. Certifying the workspace and setting up the PKI.
    4. Importing and exporting the workspace etc.
    """

    def __init__(self, workspace_name, model_name, log_memory_usage):
        """
        Initialize the ModelOwner class
        Args:
            workspace_name (str): Workspace name
            model_name (str): Model name
            log_memory_usage (bool): Memory Log flag
        """
        self.workspace_name = workspace_name
        self.model_name = model_name
        self.aggregator = None
        self.collaborators = []
        self.workspace_path = None
        self.plan_path = None
        self.num_collaborators = constants.NUM_COLLABORATORS
        self.rounds_to_train = constants.NUM_ROUNDS
        self.log_memory_usage = log_memory_usage

    def create_workspace(self, results_dir=None):
        """
        Create the workspace for the model
        Args:
            results_dir (str): Results directory path
        Returns:
            str: Path to the workspace
        """
        try:
            results_dir = results_dir if results_dir else os.getcwd()
            return_code, _, error = sh.run_command(
                f"fx workspace create --prefix {self.workspace_name} --template {self.model_name}",
                work_dir=results_dir,
            )
            if return_code != 0:
                log.error(f"Failed to create the workspace: {error}")
                raise Exception(f"Failed to create the workspace: {error}")

            log.info(f"Created the workspace {self.workspace_name} for the {self.model_name} model")
            self.workspace_path = os.path.join(results_dir, self.workspace_name)
            log.info(f"Workspace path: {self.workspace_path}")
        except Exception as e:
            log.error(f"Failed to create the workspace: {e}")
            raise e
        return self.workspace_path

    def get_workspace_path(self, results_dir, workspace_name):
        """
        Get the workspace path
        Args:
            results_dir (str): Results directory path
            workspace_name (str): Workspace name
        Returns:
            str: Path to the workspace
        """
        workspace_path = os.path.join(results_dir, workspace_name)
        log.info(f"Workspace path: {workspace_path}")
        if os.path.exists(workspace_path):
            self.workspace_path = workspace_path
            log.info(f"Workspace path: {self.workspace_path}")
        else:
            log.error(f"Workspace {workspace_name} does not exist in {results_dir}")
            raise FileNotFoundError(f"Workspace {workspace_name} does not exist in {results_dir}")
        return self.workspace_path

    def certify_collaborator(self, collaborator_name):
        """
        Sign the CSR for the collaborator
        Args:
            collaborator_name (str): Name of the collaborator
        Returns:
            bool: True if successful, else False
        """
        try:
            zip_name = f"col_{collaborator_name}_to_agg_cert_request.zip"
            col_zip = os.path.join(os.getcwd(), self.workspace_path, zip_name)
            return_code, output, error = sh.run_command(
                f"fx collaborator certify --request-pkg {col_zip} -s", work_dir=self.workspace_path
            )
            msg_received = [line for line in output if constants.SUCCESS_MARKER in line]
            log.info(f"Message received: {msg_received}")
            if return_code == 0 and len(msg_received):
                log.info(
                    f"Successfully signed the CSR for the collaborator {collaborator_name} with zip path {col_zip}"
                )
            else:
                log.error(f"Failed to sign the CSR for collaborator {collaborator_name}: {error}")

        except Exception as e:
            log.error(f"Failed to sign the CSR: {e}")
            raise e
        return True

    def modify_plan(self, new_rounds=None, num_collaborators=None, require_client_auth=True, use_tls=True):
        """
        Modify the plan to train the model
        Args:
            new_rounds (int): Number of rounds to train
            num_collaborators (int): Number of collaborators
            require_client_auth (bool): Enable client authentication
            use_tls (bool): Enable TLS communication
        Returns:
            bool: True if successful, else False
        """
        self.plan_path = os.path.join(self.workspace_path, "plan", "plan.yaml")
        # Open the file and modify the entries
        self.rounds_to_train = new_rounds if new_rounds else self.rounds_to_train
        self.num_collaborators = num_collaborators if num_collaborators else self.num_collaborators

        with open(self.plan_path) as fp:
            data = yaml.load(fp, Loader=yaml.FullLoader)

        data["aggregator"]["settings"]["rounds_to_train"] = int(self.rounds_to_train)
        # Memory Leak related
        data["aggregator"]["settings"]["log_memory_usage"] = self.log_memory_usage
        data["collaborator"]["settings"]["log_memory_usage"] = self.log_memory_usage

        data["data_loader"]["settings"]["collaborator_count"] = int(self.num_collaborators)
        data["network"]["settings"]["require_client_auth"] = require_client_auth
        data["network"]["settings"]["use_tls"] = use_tls


        with open(self.plan_path, "w+") as write_file:
            yaml.dump(data, write_file)

        log.info(f"Modified the plan at {self.plan_path} with provided parameters.")
        return True

    def initialize_plan(self, agg_domain_name):
        """
        Initialize the plan
        Args:
            agg_domain_name (str): Aggregator domain name
        Returns:
            bool: True if successful, else False
        """
        try:
            log.info("Initializing the plan. It will take some time to complete..")
            return_code, _, error = sh.run_command(f"fx plan initialize -a {agg_domain_name}", work_dir=self.workspace_path)
            if return_code != 0:
                log.error(f"Failed to initialize the plan: {error}")
                raise Exception(f"Failed to initialize the plan: {error}")

            log.info(f"Initialized the plan for the workspace {self.workspace_name}")
        except Exception as e:
            log.error(f"Failed to initialize the plan: {e}")
            raise e
        return True

    def certify_workspace(self):
        """
        Certify the workspace
        Returns:
            bool: True if successful, else False
        """
        try:
            return_code, _, error = sh.run_command("fx workspace certify", work_dir=self.workspace_path)
            if return_code != 0:
                log.error(f"Failed to certify the workspace: {error}")
                raise Exception(f"Failed to certify the workspace: {error}")

            log.info(f"Certified the workspace {self.workspace_name}")
        except Exception as e:
            log.error(f"Failed to certify the workspace: {e}")
            raise e
        return True

    def register_collaborators(self, num_collaborators=None):
        """
        Register the collaborators
        Args:
            num_collaborators (int, Optional): Number of collaborators
        Returns:
            bool: True if successful, else False
        """
        self.cols_path = os.path.join(self.workspace_path, "plan", "cols.yaml")
        log.info(f"Registering the collaborators..")
        self.num_collaborators = num_collaborators if num_collaborators else self.num_collaborators

        try:
            # Straightforward writing to the yaml file is not recommended here
            # As the file might contain spaces and tabs which can cause issues
            with open(self.cols_path, "r", encoding="utf-8") as f:
                doc = yaml.load(f, Loader=yaml.FullLoader)

            if "collaborators" not in doc.keys() or not doc["collaborators"]:
                doc["collaborators"] = []  # Create empty list

            for i in range(num_collaborators):
                col_name = "collaborator" + str(i+1)
                doc["collaborators"].append(col_name)
                with open(self.cols_path, "w", encoding="utf-8") as f:
                    yaml.dump(doc, f)

            log.info(
                f"Successfully registered collaborators in {self.cols_path}"
            )
        except Exception as e:
            log.error(f"Failed to register the collaborators: {e}")
            raise e
        return True

    def certify_aggregator(self, agg_domain_name):
        """
        Certify the aggregator request
        Args:
            agg_domain_name (str): Aggregator domain name
        Returns:
            bool: True if successful, else False
        """
        log.info(f"CA should sign the aggregator request")
        try:
            return_code, _, error = sh.run_command(
                f"fx aggregator certify --silent --fqdn {agg_domain_name}",
                work_dir=self.workspace_path,
            )
            if return_code != 0:
                log.error(f"Failed to certify the aggregator request: {error}")
                raise Exception(f"Failed to certify the aggregator request: {error}")

            log.info(f"CA signed the request from aggregator")
        except Exception as e:
            log.error(f"Failed to certify the aggregator request : {e}")
            raise e
        return True

    def export_workspace(self):
        """
        Export the workspace
        Returns:
            bool: True if successful, else False
        """
        try:
            return_code, _, error = sh.run_command("fx workspace export", work_dir=self.workspace_path)
            if return_code != 0:
                log.error(f"Failed to export the workspace: {error}")
                raise Exception(f"Failed to export the workspace: {error}")

            log.info(f"Exported the workspace")
        except Exception as e:
            log.error(f"Failed to export the workspace: {e}")
            raise e
        return True

    def import_workspace(self, workspace_zip):
        """
        Import the workspace
        Args:
            workspace_zip (str): Path to the workspace zip file
        Returns:
            bool: True if successful, else False
        """
        try:
            return_code, _, error = sh.run_command(
                f"fx workspace import --archive {workspace_zip}", work_dir=self.workspace_path
            )
            if return_code != 0:
                log.error(f"Failed to import the workspace: {error}")
                raise Exception(f"Failed to import the workspace: {error}")

            log.info(f"Imported the workspace")
        except Exception as e:
            log.error(f"Failed to import the workspace: {e}")
            raise e
        return True


# Define the Aggregator class
class Aggregator:
    """
    Aggregator class to handle the aggregator operations.
    This includes (non-exhaustive list):
    1. Generating the sign request
    2. Starting the aggregator
    """

    def __init__(self, agg_domain_name=None, workspace_path=None):
        """
        Initialize the Aggregator class
        """
        self.name = "aggregator"
        self.agg_domain_name = agg_domain_name
        self.workspace_path = workspace_path

    def generate_sign_request(self):
        """
        Generate a sign request for the aggregator
        Returns:
            bool: True if successful, else False
        """
        try:
            return_code, _, error = sh.run_command(
                f"fx aggregator generate-cert-request --fqdn {self.agg_domain_name}",
                work_dir=self.workspace_path,
            )
            if return_code != 0:
                log.error(f"Failed to generate the sign request: {error}")
                raise Exception(f"Failed to generate the sign request: {error}")

            log.info(f"Generated a sign request for {self.name}")
        except Exception as e:
            log.error(f"Failed to generate the sign request: {e}")
            raise e
        return True

    def start(self):
        """
        Start the aggregator
        Returns:
            str: Path to the log file
        """
        try:
            log.info(f"Starting {self.name}")
            filename = f"{self.name}.log"
            res_file = os.path.join(os.getcwd(), self.workspace_path, filename)
            bg_file = open(res_file, "w", buffering=1)

            sh.run_command_background(
                "fx aggregator start",
                work_dir=self.workspace_path,
                redirect_to_file=bg_file,
                check_sleep=60,
            )
            log.info(
                f"Started {self.name} and tracking the logs at {os.path.join(self.workspace_path, filename)}"
            )
        except Exception as e:
            log.error(f"Failed to start the aggregator: {e}")
            res_file.close()
            raise e
        return res_file


# Define the Collaborator class
class Collaborator:
    """
    Collaborator class to handle the collaborator operations.
    This includes (non-exhaustive list):
    1. Generating the sign request
    2. Creating the collaborator
    3. Importing and certifying the CSR
    4. Starting the collaborator
    """

    def __init__(self, collaborator_name=None, data_directory_path=None, workspace_path=None):
        """
        Initialize the Collaborator class
        """
        self.name = collaborator_name
        self.collaborator_name = collaborator_name
        self.data_directory_path = data_directory_path
        self.workspace_path = workspace_path

    def generate_sign_request(self):
        """
        Generate a sign request for the collaborator
        Returns:
            bool: True if successful, else False
        """
        try:
            return_code, _, error = sh.run_command(
                f"fx collaborator generate-cert-request -n {self.collaborator_name}",
                work_dir=self.workspace_path,
            )
            if return_code != 0:
                log.error(f"Failed to generate the sign request: {error}")
                raise Exception(f"Failed to generate the sign request: {error}")

            log.info(f"Generated a sign request for {self.collaborator_name}")
        except Exception as e:
            log.error(f"Failed to generate the sign request: {e}")
            raise e
        return True

    def create_collaborator(self):
        """
        Create the collaborator
        Returns:
            bool: True if successful, else False
        """
        try:
            return_code, _, error = sh.run_command(
                f"fx collaborator create -n {self.collaborator_name} -d {self.data_directory_path}",
                work_dir=self.workspace_path,
            )
            if return_code != 0:
                log.error(f"Failed to create the collaborator: {error}")
                raise Exception(f"Failed to create the collaborator: {error}")
            log.info(
                f"Created {self.collaborator_name} with the data directory {self.data_directory_path}"
            )
        except Exception as e:
            log.error(f"Failed to create the collaborator: {e}")
            raise e
        return True

    def import_pki(self):
        """
        Import and certify the CSR for the collaborator
        Returns:
            bool: True if successful, else False
        """
        try:
            zip_name = f"agg_to_col_{self.collaborator_name}_signed_cert.zip"
            col_zip = os.path.join(os.getcwd(), self.workspace_path, zip_name)
            return_code, output, error = sh.run_command(
                f"fx collaborator certify --import {col_zip}", work_dir=self.workspace_path
            )
            msg_received = [line for line in output if constants.SUCCESS_MARKER in line]
            log.info(f"Message received: {msg_received}")
            if return_code == 0 and len(msg_received):
                log.info(
                    f"Successfully imported and certified the CSR for {self.collaborator_name} with zip path {col_zip}"
                )
            else:
                log.error(
                    f"Failed to import and certify the CSR for {self.collaborator_name}: {error}"
                )

        except Exception as e:
            log.error(f"Failed to import and certify the CSR: {e}")
            raise e
        return True

    def start(self):
        """
        Start the collaborator
        Returns:
            str: Path to the log file
        """
        try:
            log.info(f"Starting {self.collaborator_name}")
            filename = f"{self.collaborator_name}.log"
            res_file = os.path.join(os.getcwd(), self.workspace_path, filename)
            bg_file = open(res_file, "w", buffering=1)

            sh.run_command_background(
                f"fx collaborator start -n {self.collaborator_name}",
                work_dir=self.workspace_path,
                redirect_to_file=bg_file,
                check_sleep=60,
            )
            log.info(
                f"Started {self.collaborator_name} and tracking the logs at {os.path.join(self.workspace_path, filename)}"
            )
        except Exception as e:
            log.error(f"Failed to start the collaborator: {e}")
            res_file.close()
            raise e
        return res_file
