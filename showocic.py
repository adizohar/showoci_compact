#!/usr/bin/env python3
##########################################################################
# Copyright (c) 2016, 2020, Oracle and/or its affiliates.  All rights reserved.
# This software is dual-licensed to you under the Universal Permissive License (UPL) 1.0 as shown at https://oss.oracle.com/licenses/upl or Apache License 2.0 as shown at http://www.apache.org/licenses/LICENSE-2.0. You may choose either license.
#
# showocic.py
#
# @author: Adi Zohar
#
# Supports Python 3 and above
#
# coding: utf-8
##########################################################################
# OCI Report Tool SHOWOCI:
#
# require OCI read only user with OCI authentication:
#    ALLOW GROUP ReadOnlyUsers to read all-resources IN TENANCY
#
# config file should contain:
#     [TENANT_NAME]
#     user =         user_ocid
#     fingerprint =  fingerprint of the api ssh key
#     key_file =     the path to the private key
#     tenancy =      tenancy ocid
#     region =       region
#
# Recommend to set below for display interactive
# export PYTHONUNBUFFERED=TRUE
##########################################################################
#
# Modules Included:
# - oci.core.VirtualNetworkClient
# - oci.core.ComputeClient
# - oci.core.BlockstorageClient
# - oci.database.DatabaseClient
# - oci.identity.IdentityClient

##########################################################################
from __future__ import print_function

import oci
import json
import sys
import argparse
import datetime
import time
import os
import platform

version = "21.07.13"
oci_compatible_version = "2.40.0"


###########################################################################################################
# class ShowOCIFlags
###########################################################################################################
class ShowOCIFlags(object):
    # Read Flags
    read_identity = False
    read_identity_compartments = False
    read_network = False
    read_compute = False
    read_database = False

    # is_vcn_exist_for_region
    is_vcn_exist_for_region = False

    # filter flags
    filter_by_region = ""
    filter_by_compartment = ""
    filter_by_compartment_recursive = ""
    filter_by_compartment_path = ""
    filter_by_tenancy_id = ""

    # version, config files and proxy
    proxy = ""
    showoci_version = ""
    config_file = oci.config.DEFAULT_LOCATION
    config_section = oci.config.DEFAULT_PROFILE
    use_instance_principals = False
    use_delegation_token = False

    # pyton and host info
    machine = platform.node() + " (" + platform.machine() + ")"
    python = platform.python_version()

    # flag if to run on compartment
    run_on_compartments = False

    ############################################
    # Init
    ############################################
    def __init__(self):
        pass

    ############################################
    # get run on compartments flag
    ############################################
    def is_loop_on_compartments(self):
        return (self.read_network or
                self.read_compute or
                self.read_database
                )

    ############################################
    # check if to load basic network (vcn+subnets)
    ############################################
    def is_load_basic_network(self):
        return (self.read_network or
                self.read_compute or
                self.read_database)


###########################################################################################################
# class ShowOCIService
###########################################################################################################
class ShowOCIService(object):

    # print header options
    print_header_options = {0: 90, 1: 60, 2: 40, 3: 75}

    # Network Identifiers
    C_NETWORK = 'network'
    C_NETWORK_IPS = 'ipsec'
    C_NETWORK_VCN = 'vcn'
    C_NETWORK_SGW = 'sgw'
    C_NETWORK_VLAN = 'vlan'
    C_NETWORK_NAT = 'nat'
    C_NETWORK_DRG = 'drg'
    C_NETWORK_CPE = 'cpe'
    C_NETWORK_DRG_AT = 'drg_attached'
    C_NETWORK_DRG_RT = 'drg_route_tables'
    C_NETWORK_RPC = 'rpc'
    C_NETWORK_IGW = 'igw'
    C_NETWORK_LPG = 'lpg'
    C_NETWORK_SLIST = 'seclist'
    C_NETWORK_NSG = 'secgroups'
    C_NETWORK_NSG_REPTEXT = 'NETWORKSECURITYGR'
    C_NETWORK_ROUTE = 'route'
    C_NETWORK_DHCP = 'dhcp'
    C_NETWORK_SUBNET = 'subnet'
    C_NETWORK_VC = 'virtualcircuit'
    C_NETWORK_PRIVATEIP = 'privateip'
    C_NETWORK_DNS_RESOLVERS = 'dns_resolvers'

    # Identity Identifiers
    C_IDENTITY = 'identity'
    C_IDENTITY_ADS = 'availability_domains'
    C_IDENTITY_USERS = 'users'
    C_IDENTITY_GROUPS = 'groups'
    C_IDENTITY_POLICIES = 'policies'
    C_IDENTITY_TAG_NAMESPACE = 'tag_namespace'
    C_IDENTITY_TENANCY = 'tenancy'
    C_IDENTITY_COMPARTMENTS = 'compartments'
    C_IDENTITY_REGIONS = 'regions'
    C_IDENTITY_PROVIDERS = 'providers'
    C_IDENTITY_DYNAMIC_GROUPS = 'dynamic_groups'
    C_IDENTITY_NETWORK_SOURCES = 'network_sources'
    C_IDENTITY_USERS_GROUPS_MEMBERSHIP = 'users_groups_membership'
    C_IDENTITY_COST_TRACKING_TAGS = 'cost_tracking_tags'

    # Compute Identifiers
    C_COMPUTE = 'compute'
    C_COMPUTE_INST = 'instance'
    C_COMPUTE_INST_CONFIG = 'instance_config'
    C_COMPUTE_INST_POOL = 'instance_pool'
    C_COMPUTE_IMAGES = 'instance_image'
    C_COMPUTE_BOOT_VOL_ATTACH = 'instance_boot_vol_attach'
    C_COMPUTE_VOLUME_ATTACH = 'instance_volume_attach'
    C_COMPUTE_VNIC_ATTACH = 'instance_vnic_attach'
    C_COMPUTE_AUTOSCALING = 'auto_scaling'

    # Block Storage Identifiers
    C_BLOCK = 'blockstorage'
    C_BLOCK_BOOT = 'boot'
    C_BLOCK_BOOTBACK = 'boot_back'
    C_BLOCK_VOL = 'volume'
    C_BLOCK_VOLBACK = 'volume_back'
    C_BLOCK_VOLGRP = 'volume_group'

    # database
    C_DATABASE = "database"
    C_DATABASE_DBSYSTEMS = "dbsystems"
    C_DATABASE_EXADATA = "exadata"
    C_DATABASE_ADB_DATABASE = "autonomous"
    C_DATABASE_ADB_D_INFRA = "autonomous_dedicated_infrastructure"
    C_DATABASE_SOFTWARE_IMAGES = "database_software_images"

    # Error flag and reboot migration
    error = 0
    warning = 0
    reboot_migration_counter = 0
    dbsystem_maintenance = []
    tenancy_home_region = ""

    ##########################################################################
    # Shapes
    ##########################################################################
    shapes_array = [
        {'shape': 'BM.CPU3.8', 'cpu': 52, 'memory': 768, 'storage': 0},
        {'shape': 'BM.DenseIO1.36', 'cpu': 36, 'memory': 512, 'storage': 28.8},
        {'shape': 'BM.DenseIO2.52', 'cpu': 52, 'memory': 768, 'storage': 51.2},
        {'shape': 'BM.GPU2.2', 'cpu': 28, 'memory': 192, 'storage': 0},
        {'shape': 'BM.HPC2.36', 'cpu': 36, 'memory': 384, 'storage': 0},
        {'shape': 'BM.HighIO1.36', 'cpu': 36, 'memory': 512, 'storage': 12.8},
        {'shape': 'BM.RACLocalStorage1.72', 'cpu': 72, 'memory': 1024, 'storage': 64},
        {'shape': 'BM.Standard1.36', 'cpu': 36, 'memory': 256, 'storage': 0},
        {'shape': 'BM.Standard2.52', 'cpu': 52, 'memory': 768, 'storage': 0},
        {'shape': 'BM.StandardE2.64', 'cpu': 64, 'memory': 512, 'storage': 0},
        {'shape': 'BM.Standard.B1.44', 'cpu': 44, 'memory': 512, 'storage': 0},
        {'shape': 'BM.Standard.E2.64', 'cpu': 64, 'memory': 512, 'storage': 0},
        {'shape': 'Exadata.Full1.336', 'cpu': 336, 'memory': 5760, 'storage': 336},
        {'shape': 'Exadata.Half1.168', 'cpu': 168, 'memory': 2880, 'storage': 168},
        {'shape': 'Exadata.Quarter1.84', 'cpu': 84, 'memory': 1440, 'storage': 84},
        {'shape': 'Exadata.Full2.368', 'cpu': 368, 'memory': 5760, 'storage': 424},
        {'shape': 'Exadata.Half2.184', 'cpu': 184, 'memory': 2880, 'storage': 212},
        {'shape': 'Exadata.Quarter2.92', 'cpu': 92, 'memory': 1440, 'storage': 106},
        {'shape': 'Exadata.Full3.400', 'cpu': 400, 'memory': 5760, 'storage': 598},
        {'shape': 'Exadata.Half3.200', 'cpu': 200, 'memory': 2880, 'storage': 298},
        {'shape': 'Exadata.Quarter3.100', 'cpu': 100, 'memory': 1440, 'storage': 149},
        {'shape': 'Exadata.X8M', 'cpu': 100, 'memory': 1440, 'storage': 149},
        {'shape': 'Exadata.Base.48', 'cpu': 48, 'memory': 720, 'storage': 74.8},
        {'shape': 'VM.CPU3.1', 'cpu': 6, 'memory': 90, 'storage': 0},
        {'shape': 'VM.CPU3.2', 'cpu': 12, 'memory': 180, 'storage': 0},
        {'shape': 'VM.CPU3.4', 'cpu': 24, 'memory': 360, 'storage': 0},
        {'shape': 'VM.DenseIO1.16', 'cpu': 16, 'memory': 240, 'storage': 12.8},
        {'shape': 'VM.DenseIO1.4', 'cpu': 4, 'memory': 60, 'storage': 3.2},
        {'shape': 'VM.DenseIO1.8', 'cpu': 8, 'memory': 120, 'storage': 6.4},
        {'shape': 'VM.DenseIO2.16', 'cpu': 16, 'memory': 240, 'storage': 12.8},
        {'shape': 'VM.DenseIO2.24', 'cpu': 24, 'memory': 320, 'storage': 25.6},
        {'shape': 'VM.DenseIO2.8', 'cpu': 8, 'memory': 120, 'storage': 6.4},
        {'shape': 'VM.GPU2.1', 'cpu': 12, 'memory': 104, 'storage': 0},
        {'shape': 'VM.Standard.E2.1.Micro', 'cpu': 1, 'memory': 1, 'storage': 0},
        {'shape': 'VM.Standard.E2.1', 'cpu': 1, 'memory': 8, 'storage': 0},
        {'shape': 'VM.Standard.E2.2', 'cpu': 2, 'memory': 16, 'storage': 0},
        {'shape': 'VM.Standard.E2.4', 'cpu': 4, 'memory': 32, 'storage': 0},
        {'shape': 'VM.Standard.E2.8', 'cpu': 8, 'memory': 64, 'storage': 0},
        {'shape': 'VM.Standard1.1', 'cpu': 1, 'memory': 7, 'storage': 0},
        {'shape': 'VM.Standard1.2', 'cpu': 2, 'memory': 14, 'storage': 0},
        {'shape': 'VM.Standard1.4', 'cpu': 4, 'memory': 28, 'storage': 0},
        {'shape': 'VM.Standard1.8', 'cpu': 8, 'memory': 56, 'storage': 0},
        {'shape': 'VM.Standard1.16', 'cpu': 16, 'memory': 112, 'storage': 0},
        {'shape': 'VM.Standard.B1.1', 'cpu': 1, 'memory': 12, 'storage': 0},
        {'shape': 'VM.Standard.B1.2', 'cpu': 2, 'memory': 24, 'storage': 0},
        {'shape': 'VM.Standard.B1.4', 'cpu': 4, 'memory': 48, 'storage': 0},
        {'shape': 'VM.Standard.B1.8', 'cpu': 8, 'memory': 96, 'storage': 0},
        {'shape': 'VM.Standard.B1.16', 'cpu': 16, 'memory': 192, 'storage': 0},
        {'shape': 'VM.Standard2.1', 'cpu': 1, 'memory': 15, 'storage': 0},
        {'shape': 'VM.Standard2.2', 'cpu': 2, 'memory': 30, 'storage': 0},
        {'shape': 'VM.Standard2.4', 'cpu': 4, 'memory': 60, 'storage': 0},
        {'shape': 'VM.Standard2.8', 'cpu': 8, 'memory': 120, 'storage': 0},
        {'shape': 'VM.Standard2.16', 'cpu': 16, 'memory': 240, 'storage': 0},
        {'shape': 'VM.Standard2.24', 'cpu': 24, 'memory': 320, 'storage': 0}
    ]

    ##########################################################################
    # Local Variables
    # data - hold the data data
    # flags - hold the extract flags
    ##########################################################################
    flags = None
    data = {}

    ##########################################################################
    # init class
    # Creates a new data object
    #
    # required:
    #    flags parameters - Class ShowOCIFlags
    #
    ##########################################################################
    def __init__(self, flags):

        if not isinstance(flags, ShowOCIFlags):
            raise TypeError("flags must be ShowOCIFlags class")

        # check OCI Compatible
        self.check_oci_version_compatible()

        # assign the flags variable
        self.flags = flags

        # if intance pricipals - generate signer from token or config
        if flags.use_instance_principals:
            self.generate_signer_from_instance_principals()

        # if delegation toekn for cloud shell
        elif flags.use_delegation_token:
            self.generate_signer_from_delegation_token()

        # else use config file
        else:
            self.generate_signer_from_config(flags.config_file, flags.config_section)

    ##########################################################################
    # Generate Signer from config
    ###########################################################################
    def generate_signer_from_config(self, config_file, config_section):

        try:
            # create signer from config for authentication
            self.config = oci.config.from_file(config_file, config_section)
            self.signer = oci.signer.Signer(
                tenancy=self.config["tenancy"],
                user=self.config["user"],
                fingerprint=self.config["fingerprint"],
                private_key_file_location=self.config.get("key_file"),
                pass_phrase=oci.config.get_config_value_or_default(self.config, "pass_phrase"),
                private_key_content=self.config.get("key_content")
            )
        except oci.exceptions.ProfileNotFound as e:
            print("*********************************************************************")
            print("* " + str(e))
            print("* Aboting.                                                          *")
            print("*********************************************************************")
            print("")
            raise SystemExit

    ##########################################################################
    # Generate Signer from instance_principals
    ###########################################################################
    def generate_signer_from_instance_principals(self):

        try:
            # get signer from instance principals token
            self.signer = oci.auth.signers.InstancePrincipalsSecurityTokenSigner()

        except Exception:
            print("*********************************************************************")
            print("* Error obtaining instance principals certificate.                  *")
            print("* Aboting.                                                          *")
            print("*********************************************************************")
            print("")
            raise SystemExit

        # generate config info from signer
        self.config = {'region': self.signer.region, 'tenancy': self.signer.tenancy_id}

    ##########################################################################
    # Generate Signer from delegation_token
    # use host variable to point to the OCI Config file and profile
    ###########################################################################
    def generate_signer_from_delegation_token(self):

        # check if env variables OCI_CONFIG_FILE, OCI_CONFIG_PROFILE exist and use them
        env_config_file = os.environ.get('OCI_CONFIG_FILE')
        env_config_section = os.environ.get('OCI_CONFIG_PROFILE')

        # check if file exist
        if env_config_file is not None and env_config_section is not None:
            if os.path.isfile(env_config_file):
                self.flags.config_file = env_config_file
                self.flags.config_section = env_config_section

        try:
            self.config = oci.config.from_file(self.flags.config_file, self.flags.config_section)
            delegation_token_location = self.config["delegation_token_file"]

            with open(delegation_token_location, 'r') as delegation_token_file:
                delegation_token = delegation_token_file.read().strip()
                # get signer from delegation token
                self.signer = oci.auth.signers.InstancePrincipalsDelegationTokenSigner(delegation_token=delegation_token)

        except KeyError:
            print("*********************************************************************")
            print("* Key Error obtaining delegation_token_file")
            print("* Config  File = " + self.flags.config_file)
            print("* Section File = " + self.flags.config_section)
            print("* Aborting.                                                          *")
            print("*********************************************************************")
            print("")
            raise SystemExit

        except Exception:
            print("*********************************************************************")
            print("* Error obtaining instance principals certificate                   *")
            print("* with delegation token                                             *")
            print("* Aborting.                                                          *")
            print("*********************************************************************")
            print("")
            raise SystemExit

        # generate config info from signer
        tenancy_id = self.config["tenancy"]
        self.config = {'region': self.signer.region, 'tenancy': tenancy_id}

    ##########################################################################
    # load_data
    ##########################################################################
    def load_service_data(self):
        return self.__load_data_main()

    ##########################################################################
    # Print header centered
    ##########################################################################
    def print_header(self, name, category):
        chars = int(self.print_header_options[category])
        print("")
        print('#' * chars)
        print("#" + str(name).center(chars - 2, " ") + "#")
        print('#' * chars)

    ##########################################################################
    # return tenancy data
    ##########################################################################
    def get_tenancy(self):
        return self.data[self.C_IDENTITY][self.C_IDENTITY_TENANCY]

    ##########################################################################
    # get tenancy id from file or override
    ##########################################################################
    def get_tenancy_id(self):
        if self.flags.filter_by_tenancy_id:
            return self.flags.filter_by_tenancy_id
        else:
            return self.config["tenancy"]

    ##########################################################################
    # return compartment data
    ##########################################################################
    def get_compartment(self):
        return self.data[self.C_IDENTITY][self.C_IDENTITY_COMPARTMENTS]

    ##########################################################################
    # return availability domains
    ##########################################################################
    def get_availability_domains(self, region_name):
        ads = self.data[self.C_IDENTITY][self.C_IDENTITY_ADS]
        return [e for e in ads if e['region_name'] == region_name]

    ##########################################################################
    # return subnet
    ##########################################################################
    def get_network_subnet(self, subnet_id, detailed=False):
        try:
            result = self.search_unique_item(self.C_NETWORK, self.C_NETWORK_SUBNET, 'id', subnet_id)
            if result:
                if result != "":
                    if detailed:
                        return result['name'] + ",  " + result['cidr_block'] + ", VCN (" + result['vcn_name'] + ")"
                    else:
                        return result['name']
            return ""

        except Exception as e:
            self.__print_error("get_network_subnet", e)

    ##########################################################################
    # return vcn
    ##########################################################################
    def get_network_vcn(self, vcn_id):
        try:
            result = self.search_unique_item(self.C_NETWORK, self.C_NETWORK_VCN, 'id', vcn_id)
            if result:
                if result != "":
                    return result['name']
            return ""

        except Exception as e:
            self.__print_error("get_network_vcn", e)

    ##########################################################################
    # get_network_drg_route_table
    ##########################################################################
    def get_network_drg_route_table(self, drg_route_table_id):
        try:
            route = self.search_unique_item(self.C_NETWORK, self.C_NETWORK_DRG_RT, 'id', drg_route_table_id)
            if route:
                if 'display_name' in route:
                    return route['display_name']
            return ""

        except Exception as e:
            self.__print_error("get_network_drg_route_table", e)

    ##########################################################################
    # return identity data
    ##########################################################################
    def get_identity(self):
        return self.data[self.C_IDENTITY]

    ##########################################################################
    # return oci version
    ##########################################################################
    def get_oci_version(self):
        return oci.version.__version__

    ##########################################################################
    # find shape info
    # returns CPUs, Memory and Local Storage SSD
    ##########################################################################
    def get_shape_details(self, shape_name):
        for array in self.shapes_array:
            if array['shape'] == shape_name:
                return array
        return {}

    ##########################################################################
    # check oci version
    ##########################################################################
    def check_oci_version_compatible(self):

        try:
            # loop on digits
            for i, rl in zip(self.get_oci_version().split("."), oci_compatible_version.split(".")):
                if int(i) > int(rl):
                    return True
                if int(i) < int(rl):
                    print("")
                    print("*********************************************************************")
                    print("Error, OCI SDK version " + oci_compatible_version + " required !")
                    print("OCI SDK Version installed = " + self.get_oci_version())
                    print("Please use below command to upgrade OCI SDK:")
                    print("   python -m pip install --upgrade oci")
                    print("")
                    print("Aboting.")
                    print("*********************************************************************")
                    print("")
                    raise SystemExit

        except Exception as e:
            self.__print_error("check_oci_version_compatible", e)

    ##########################################################################
    # search unique items with multi parameters
    # parameters are
    # MODULE - data Module
    # SECTION - data Sub module
    # P1, v1 - param and value
    # p2, v2 - param and value - optional
    # p3, v3 - param and value - optional
    ##########################################################################

    def search_unique_item(self, module, section, p1, v1, p2=None, v2=None, p3=None, v3=None):
        try:
            result = self.search_multi_items(module, section, p1, v1, p2, v2, p3, v3)

            if not result:
                return None

            return result[0]

        except Exception as e:
            self.__print_error("search_unique_item", e)

    ##########################################################################
    # search multi items with multi parameters
    # parameters are
    # MODULE - data Module
    # SECTION - data Sub module
    # P1, v1 - param and value
    # p2, v2 - param and value - optional
    # p3, v3 - param and value - optional
    ##########################################################################

    def search_multi_items(self, module, section, p1, v1, p2=None, v2=None, p3=None, v3=None):
        try:
            if len(module) == 0 or len(section) == 0:
                return []

            # check if module exists
            if module not in self.data:
                return []

            # check if section exists
            if section not in self.data[module]:
                return []

            # assign data area to array
            array = self.data[module][section]

            # check parameters and search
            if p2 and v2 and p3 and v3:
                return [e for e in array if e[p1] == v1 and e[p2] == v2 and e[p3] == v3]

            # check parameters and search
            if p2 and v2:
                return [e for e in array if e[p1] == v1 and e[p2] == v2]

            return [e for e in array if e[p1] == v1]

        except Exception as e:
            self.__print_error("search_multi_items " + module + ":" + section, e)

    ##########################################################################
    # initialize data key if not exist
    ##########################################################################
    def __initialize_data_key(self, module, section):
        if module not in self.data:
            self.data[module] = {}
        if section not in self.data[module]:
            self.data[module][section] = []

    ##########################################################################
    # print status message
    ##########################################################################
    def __load_print_status(self, msg):
        print("--> " + msg.ljust(25) + "<-- ", end="")

    ##########################################################################
    # print print error
    ##########################################################################
    def __print_error(self, msg, e):
        classname = type(self).__name__

        if 'TooManyRequests' in str(e):
            print(" - TooManyRequests Err in " + msg)
        elif isinstance(e, KeyError):
            print("\nError in " + classname + ":" + msg + ": KeyError " + str(e.args))
        else:
            print("\nError in " + classname + ":" + msg + ": " + str(e))

        self.error += 1

    ##########################################################################
    # check service error to warn instead of error
    ##########################################################################
    def __check_service_error(self, code):
        return 'max retries exceeded' in str(code).lower() or 'auth' in str(code).lower() or 'notfound' in str(code).lower() or code == 'Forbidden' or code == 'TooManyRequests' or code == 'IncorrectState' or code == 'LimitExceeded'

    ##########################################################################
    # check request error if service not exists for region
    ##########################################################################
    def __check_request_error(self, e):

        # service not yet available
        if ('Errno 8' in str(e) and 'NewConnectionError' in str(e)) or 'Max retries exceeded' in str(e) or 'HTTPSConnectionPool' in str(e) or 'not currently available' in str(e):
            print("Service Not Accessible or not yet exist")
            return True
        return False

    ##########################################################################
    # check if managed paas compartment
    ##########################################################################
    def __if_managed_paas_compartment(self, name):
        return name == "ManagedCompartmentForPaaS"

    ##########################################################################
    # print count result
    ##########################################################################
    def __load_print_cnt(self, cnt, start_time):
        et = time.time() - start_time
        print(" (" + str(cnt) + ") - "'{:02d}:{:02d}:{:02d}'.format(round(et // 3600), (round(et % 3600 // 60)), round(et % 60)))

    ##########################################################################
    # print auth warning
    ##########################################################################
    def __load_print_auth_warning(self, special_char="a", increase_warning=True):
        if increase_warning:
            self.warning += 1
        print(special_char, end="")

    ##########################################################################
    # Main procedure to read data to the data
    ##########################################################################
    def __load_data_main(self):
        try:
            print("Guide: '.' Compartment, '+' VCN, '-' Subnets, 'a' - auth/notfound")

            # print filter by
            if self.flags.filter_by_region:
                print("Filtered by Region      = " + self.flags.filter_by_region)

            if self.flags.filter_by_compartment:
                print("Filtered by Compartment like " + self.flags.filter_by_compartment)

            if self.flags.filter_by_compartment_path:
                print("Filtered by Compartment Path = " + self.flags.filter_by_compartment_path)

            if self.flags.filter_by_compartment_recursive:
                print("Filtered by Compartment Recursive = " + self.flags.filter_by_compartment_recursive)

            print("")

            # load identity
            self.__load_identity_main()

            # set tenant home region
            self.config['region'] = self.tenancy_home_region
            self.signer.region = self.tenancy_home_region

            # check if data not loaded, abort
            if self.C_IDENTITY not in self.data:
                return False

            # check if need to loop on compartments
            # if the flags required data from regions
            if self.flags.is_loop_on_compartments():

                # run on each subscribed region
                tenancy = self.data[self.C_IDENTITY][self.C_IDENTITY_TENANCY]
                for region_name in tenancy['list_region_subscriptions']:

                    # if filtered by region skip if not cmd.region
                    if self.flags.filter_by_region and str(self.flags.filter_by_region) not in region_name:
                        continue

                    # load region into data
                    self.__load_oci_region_data(region_name)

            return True

        except Exception as e:
            self.__print_error("__load_data_main: ", e)
            raise

    ##########################################################################
    # run on Region
    ##########################################################################
    def __load_oci_region_data(self, region_name):

        # capture region start time
        region_start_time = time.time()

        # Assign Region to config file
        self.print_header("Region " + region_name, 2)
        self.config['region'] = region_name
        self.signer.region = region_name

        # load ADs
        if self.flags.is_load_basic_network():
            self.__load_identity_availability_domain(region_name)

        # Load Network
        if self.flags.is_load_basic_network():
            self.__load_core_network_main()

        # if load compute
        if self.flags.read_compute:
            self.__load_core_compute_main()

        # database
        if self.flags.read_database:
            self.__load_database_main()

        et = time.time() - region_start_time
        print("*** Elapsed Region '" + region_name + "' - " + '{:02d}:{:02d}:{:02d}'.format(round(et // 3600), (round(et % 3600 // 60)), round(et % 60)) + " ***")

    ##########################################################################
    # Identity Module
    ##########################################################################
    def __load_identity_main(self):
        try:
            print("Identity...")

            # create identity object
            identity = oci.identity.IdentityClient(self.config, signer=self.signer)
            if self.flags.proxy:
                identity.base_client.session.proxies = {'https': self.flags.proxy}

            # get tenancy id from the config file
            tenancy_id = self.get_tenancy_id()
            self.data[self.C_IDENTITY] = {}

            # loading main components - tenancy and compartments
            self.__load_identity_tenancy(identity, tenancy_id)

            # Load single compartment or all
            if 'ocid1.compartment' in self.flags.filter_by_compartment:
                self.__load_identity_single_compartments(identity)
            else:
                self.__load_identity_compartments(identity)

            # if loading the full identity - load the rest
            if self.flags.read_identity:
                self.__load_identity_network_sources(identity, tenancy_id)
                self.__load_identity_users_groups(identity, tenancy_id)
                self.__load_identity_dynamic_groups(identity, tenancy_id)
                self.__load_identity_policies(identity)
                self.__load_identity_providers(identity, tenancy_id)

            print("")
        except oci.exceptions.RequestException:
            raise
        except oci.exceptions.ServiceError:
            raise
        except Exception as e:
            self.__print_error("__load_identity_main: ", e)

    ##########################################################################
    # Load Tenancy
    # Password policy contributed by Josh.
    ##########################################################################

    def __load_identity_tenancy(self, identity, tenancy_id):
        self.__load_print_status("Tenancy")
        start_time = time.time()
        try:
            tenancy = identity.get_tenancy(tenancy_id).data

            # Getting Tenancy Password Policy
            password_policy = {}
            try:
                password_policy_data = identity.get_authentication_policy(tenancy.id).data
                if password_policy_data:
                    ppd = password_policy_data.password_policy
                    password_policy = {
                        'is_lowercase_characters_required': str(ppd.is_lowercase_characters_required),
                        'is_numeric_characters_required': str(ppd.is_numeric_characters_required),
                        'is_special_characters_required': str(ppd.is_special_characters_required),
                        'is_uppercase_characters_required': str(ppd.is_uppercase_characters_required),
                        'is_username_containment_allowed': str(ppd.is_username_containment_allowed),
                        'minimum_password_length': str(ppd.minimum_password_length)
                    }

            except oci.exceptions.ServiceError as e:
                if self.__check_service_error(e.code):
                    self.__load_print_auth_warning()
                else:
                    raise

            # Get sub regions
            data_subs = []
            try:
                sub_regions = identity.list_region_subscriptions(tenancy.id).data
                data_subs = [str(es.region_name) for es in sub_regions]
            except oci.exceptions.ServiceError as e:
                if self.__check_service_error(e.code):
                    self.__load_print_auth_warning()
                else:
                    raise

            # add the data
            data = {
                'id': tenancy.id,
                'name': tenancy.name,
                'home_region_key': tenancy.home_region_key,
                'subscribe_regions': str(', '.join(x for x in data_subs)),
                'list_region_subscriptions': data_subs,
                'password_policy': password_policy
            }

            # home region
            for reg in sub_regions:
                if reg.is_home_region:
                    self.tenancy_home_region = str(reg.region_name)

            self.data[self.C_IDENTITY][self.C_IDENTITY_TENANCY] = data
            self.__load_print_cnt(1, start_time)

        except oci.exceptions.RequestException:
            raise
        except oci.exceptions.ServiceError as e:
            print("\n*********************************************************************")
            print("* Error Authenticating in __load_identity_tenancy:")
            print("* " + str(e.message))
            print("* Aborting.                                                          *")
            print("*********************************************************************")
            print("")
            raise SystemExit
        except Exception as e:
            raise Exception("Error in __load_identity_tenancy: " + str(e.args))

    ##########################################################################
    # Load compartments
    ##########################################################################
    def __load_identity_compartments(self, identity):

        compartments = []
        self.__load_print_status("Compartments")
        start_time = time.time()

        try:
            # point to tenancy
            tenancy = self.data[self.C_IDENTITY][self.C_IDENTITY_TENANCY]

            # read all compartments to variable
            all_compartments = []
            try:
                all_compartments = oci.pagination.list_call_get_all_results(
                    identity.list_compartments,
                    tenancy['id'],
                    compartment_id_in_subtree=True,
                    retry_strategy=oci.retry.DEFAULT_RETRY_STRATEGY
                ).data

            except oci.exceptions.ServiceError as e:
                if self.__check_service_error(e.code):
                    self.__load_print_auth_warning()
                else:
                    raise

            ###################################################
            # Build Compartments
            # return nested compartment list
            ###################################################
            def build_compartments_nested(identity_client, cid, path):
                try:
                    compartment_list = [item for item in all_compartments if str(item.compartment_id) == str(cid)]

                    if path != "":
                        path = path + " / "

                    for c in compartment_list:
                        if c.lifecycle_state == oci.identity.models.Compartment.LIFECYCLE_STATE_ACTIVE:
                            cvalue = {
                                'id': str(c.id),
                                'name': str(c.name),
                                'description': str(c.description),
                                'time_created': str(c.time_created),
                                'is_accessible': str(c.is_accessible),
                                'path': path + str(c.name),
                                'defined_tags': [] if c.defined_tags is None else c.defined_tags,
                                'freeform_tags': [] if c.freeform_tags is None else c.freeform_tags
                            }
                            compartments.append(cvalue)
                            build_compartments_nested(identity_client, c.id, cvalue['path'])

                except Exception as error:
                    raise Exception("Error in build_compartments_nested: " + str(error.args))

            ###################################################
            # Add root compartment
            ###################################################
            try:
                tenc = identity.get_compartment(tenancy['id']).data
                if tenc:
                    cvalue = {
                        'id': str(tenc.id),
                        'name': str(tenc.name),
                        'description': str(tenc.description),
                        'time_created': str(tenc.time_created),
                        'is_accessible': str(tenc.is_accessible),
                        'path': "/ " + str(tenc.name) + " (root)",
                        'defined_tags': [] if tenc.defined_tags is None else tenc.defined_tags,
                        'freeform_tags': [] if tenc.freeform_tags is None else tenc.freeform_tags
                    }
                    compartments.append(cvalue)
            except Exception as error:
                raise Exception("Error in add_tenant_compartment: " + str(error.args))

            # Build the compartments
            build_compartments_nested(identity, tenancy['id'], "")

            # sort the compartment
            sorted_compartments = sorted(compartments, key=lambda k: k['path'])

            # if not filtered by compartment return
            if not (self.flags.filter_by_compartment or self.flags.filter_by_compartment_path or self.flags.filter_by_compartment_recursive):
                self.data[self.C_IDENTITY][self.C_IDENTITY_COMPARTMENTS] = sorted_compartments
                self.__load_print_cnt(len(compartments), start_time)
                return

            filtered_compart = []

            # if filter by compartment, then reduce list and return new list
            if self.flags.filter_by_compartment:
                for x in sorted_compartments:
                    if self.flags.filter_by_compartment in x['name'] or self.flags.filter_by_compartment in x['id']:
                        filtered_compart.append(x)

            # if filter by path compartment, then reduce list and return new list
            if self.flags.filter_by_compartment_path:
                for x in sorted_compartments:
                    if self.flags.filter_by_compartment_path == x['path']:
                        filtered_compart.append(x)            # if filter by path compartment, then reduce list and return new list

            if self.flags.filter_by_compartment_recursive:
                for x in sorted_compartments:
                    if self.flags.filter_by_compartment_recursive in x['path']:
                        filtered_compart.append(x)

            # add to data
            self.data[self.C_IDENTITY][self.C_IDENTITY_COMPARTMENTS] = filtered_compart
            self.__load_print_cnt(len(filtered_compart), start_time)

        except oci.exceptions.RequestException:
            raise
        except Exception as e:
            raise Exception("Error in __load_identity_compartments: " + str(e.args))

    ##########################################################################
    # Load single compartment to support BOAT authentication
    ##########################################################################
    def __load_identity_single_compartments(self, identity):

        self.__load_print_status("Compartments")
        start_time = time.time()

        compartments = []
        try:

            # read compartments to variable
            compartment = ""
            try:
                compartment = identity.get_compartment(self.flags.filter_by_compartment).data
            except oci.exceptions.ServiceError as e:
                if self.__check_service_error(e.code):
                    self.__load_print_auth_warning()
                else:
                    raise

            if compartment:
                cvalue = {
                    'id': str(compartment.id),
                    'name': str(compartment.name),
                    'description': str(compartment.description),
                    'time_created': str(compartment.time_created),
                    'is_accessible': str(compartment.is_accessible),
                    'path': str(compartment.name),
                    'defined_tags': [] if compartment.defined_tags is None else compartment.defined_tags,
                    'freeform_tags': [] if compartment.freeform_tags is None else compartment.freeform_tags
                }
                compartments.append(cvalue)

            self.data[self.C_IDENTITY][self.C_IDENTITY_COMPARTMENTS] = compartments
            self.__load_print_cnt(len(compartments), start_time)

        except oci.exceptions.RequestException:
            raise
        except Exception as e:
            raise Exception("Error in __load_identity_single_compartments: " + str(e.args))

    ##########################################################################
    # Get Identity Users
    ##########################################################################

    def __load_identity_users_groups(self, identity, tenancy_id):
        datauser = []
        datagroup = []

        self.__load_print_status("Groups")
        start_time = time.time()

        try:
            users = []
            groups = []
            identity_providers = []

            try:
                users = oci.pagination.list_call_get_all_results(identity.list_users, tenancy_id, retry_strategy=oci.retry.DEFAULT_RETRY_STRATEGY).data
                groups = oci.pagination.list_call_get_all_results(identity.list_groups, tenancy_id, retry_strategy=oci.retry.DEFAULT_RETRY_STRATEGY).data
                identity_providers = identity.list_identity_providers("SAML2", tenancy_id, retry_strategy=oci.retry.DEFAULT_RETRY_STRATEGY).data
            except oci.exceptions.ServiceError as item:
                if 'auth' in item.code.lower() or item.code == 'Forbidden':
                    self.__load_print_auth_warning()
                else:
                    raise

            members = []

            ##########################
            # add groups
            ##########################
            for group in groups:
                print(".", end="")
                try:
                    user_group_memberships = oci.pagination.list_call_get_all_results(
                        identity.list_user_group_memberships, tenancy_id, group_id=group.id, retry_strategy=oci.retry.DEFAULT_RETRY_STRATEGY).data

                    group_users = []
                    for ugm in user_group_memberships:
                        members.append({'user_id': ugm.user_id, 'group_id': ugm.group_id})
                        for item in [str(item_var.name) for item_var in users if item_var.id == ugm.user_id]:
                            group_users.append(item)

                    datagroup.append({'id': group.id, 'name': group.name, 'users': ', '.join(x for x in group_users)})

                except oci.exceptions.ServiceError as error:
                    if 'auth' in error.code.lower() or error.code == 'Forbidden':
                        self.__load_print_auth_warning()
                        continue
                    raise

            # load to data
            self.data[self.C_IDENTITY][self.C_IDENTITY_GROUPS] = datagroup
            self.__load_print_cnt(len(datagroup), start_time)

            ##########################
            # add users
            ##########################
            self.__load_print_status("Users")
            start_time = time.time()
            for user in users:

                group_users = []
                print(".", end="")

                # find the group users
                for ugm in [e['group_id'] for e in members if user.id == e['user_id']]:
                    group_users.append(next(item for item in groups if item.id == ugm).name)

                # identity provider
                identity_provider_name = ""
                try:
                    if user.identity_provider_id:
                        identity_provider_name = next(
                            item for item in identity_providers if item.id == user.identity_provider_id).name
                except Exception:
                    identity_provider_name = 'unknown'

                # user data
                user_data = {
                    'id': user.id,
                    'name': str(user.name),
                    'description': str(user.description),
                    'is_mfa_activated': str(user.is_mfa_activated),
                    'lifecycle_state': str(user.lifecycle_state),
                    'inactive_status': str(user.inactive_status),
                    'time_created': str(user.time_created),
                    'identity_provider_id': str(user.identity_provider_id),
                    'identity_provider_name': str(identity_provider_name),
                    'email': str(user.email),
                    'email_verified': str(user.email_verified),
                    'external_identifier': str(user.external_identifier),
                    'last_successful_login_time': str(user.last_successful_login_time),
                    'previous_successful_login_time': str(user.previous_successful_login_time),
                    'groups': ', '.join(x for x in group_users),
                    'capabilities': {}
                }

                if user.capabilities:
                    user_data['capabilities'] = {
                        'can_use_console_password': user.capabilities.can_use_console_password,
                        'can_use_api_keys': user.capabilities.can_use_api_keys,
                        'can_use_auth_tokens': user.capabilities.can_use_auth_tokens,
                        'can_use_smtp_credentials': user.capabilities.can_use_smtp_credentials,
                        'can_use_customer_secret_keys': user.capabilities.can_use_customer_secret_keys,
                        'can_use_o_auth2_client_credentials': user.capabilities.can_use_o_auth2_client_credentials
                    }

                datauser.append(user_data)

            # load to data
            self.data[self.C_IDENTITY][self.C_IDENTITY_USERS] = datauser

            self.__load_print_cnt(len(datauser), start_time)

        except oci.exceptions.RequestException:
            raise
        except Exception as e:
            self.__print_error("__load_identity_users_groups", e)

    ##########################################################################
    # Print Identity Policies
    ##########################################################################
    def __load_identity_policies(self, identity):
        data = []
        self.__load_print_status("Policies")
        start_time = time.time()

        try:
            compartments = self.data[self.C_IDENTITY][self.C_IDENTITY_COMPARTMENTS]

            for c in compartments:
                print(".", end="")
                if self.__if_managed_paas_compartment(c['name']) and not self.flags.read_ManagedCompartmentForPaaS:
                    continue

                try:
                    policies = oci.pagination.list_call_get_all_results(identity.list_policies, c['id'], retry_strategy=oci.retry.DEFAULT_RETRY_STRATEGY).data

                    if policies:
                        datapol = []
                        for policy in policies:
                            datapol.append({'name': policy.name, 'statements': [str(e) for e in policy.statements]})

                        dataval = {
                            'compartment_id': str(c['id']),
                            'compartment_name': c['name'],
                            'compartment_path': c['path'],
                            'policies': datapol
                        }
                        data.append(dataval)

                except oci.exceptions.ServiceError as e:
                    if self.__check_service_error(e.code):
                        self.__load_print_auth_warning()
                        continue
                    raise

            # add to data
            self.data[self.C_IDENTITY][self.C_IDENTITY_POLICIES] = data
            self.__load_print_cnt(len(data), start_time)

        except oci.exceptions.RequestException:
            raise
        except Exception as e:
            self.__print_error("__load_identity_policies", e)

    ##########################################################################
    # Print Identity Providers
    ##########################################################################
    def __load_identity_providers(self, identity, tenancy_id):
        data = []
        self.__load_print_status("Providers")
        start_time = time.time()

        try:
            groups = self.data[self.C_IDENTITY][self.C_IDENTITY_GROUPS]

            try:
                identity_providers = identity.list_identity_providers("SAML2", tenancy_id, retry_strategy=oci.retry.DEFAULT_RETRY_STRATEGY).data

                for d in identity_providers:

                    # get identity providers groups
                    try:
                        igm = oci.pagination.list_call_get_all_results(identity.list_idp_group_mappings, d.id, retry_strategy=oci.retry.DEFAULT_RETRY_STRATEGY).data

                        # get the group data
                        groupdata = []
                        for ig in igm:
                            for grp in groups:
                                if grp['id'] == ig.group_id:
                                    groupdata.append(ig.idp_group_name + " <-> " + grp['name'])

                        data.append({
                            'id': str(d.id),
                            'name': str(d.name),
                            'description': str(d.description),
                            'product_type': str(d.product_type),
                            'protocol': str(d.protocol),
                            'redirect_url': str(d.redirect_url),
                            'metadata_url': str(d.metadata_url),
                            'group_map': groupdata
                        })

                    except oci.exceptions.ServiceError as e:
                        if self.__check_service_error(e.code):
                            self.__load_print_auth_warning()
                            continue
                        raise

            except oci.exceptions.ServiceError as e:
                if self.__check_service_error(e.code):
                    self.__load_print_auth_warning()
                else:
                    raise

            # add to data
            self.data[self.C_IDENTITY][self.C_IDENTITY_PROVIDERS] = data
            self.__load_print_cnt(len(data), start_time)

        except oci.exceptions.RequestException:
            raise
        except Exception as e:
            self.__print_error("__load_identity_providers", e)

    ##########################################################################
    # Print Dynamic Groups
    ##########################################################################
    def __load_identity_dynamic_groups(self, identity, tenancy_id):

        data = []
        self.__load_print_status("Dynamic Groups")
        start_time = time.time()

        try:
            dynamic_groups = []
            try:
                dynamic_groups = oci.pagination.list_call_get_all_results(identity.list_dynamic_groups, tenancy_id, retry_strategy=oci.retry.DEFAULT_RETRY_STRATEGY).data
            except oci.exceptions.ServiceError as e:
                if self.__check_service_error(e.code):
                    self.__load_print_auth_warning()
                else:
                    raise

            for dg in dynamic_groups:
                print(".", end="")
                data.append({
                    'id': str(dg.id),
                    'name': str(dg.name),
                    'description': str(dg.description),
                    'matching_rule': str(dg.matching_rule)
                })

            # add to data
            self.data[self.C_IDENTITY][self.C_IDENTITY_DYNAMIC_GROUPS] = data
            self.__load_print_cnt(len(data), start_time)

        except oci.exceptions.RequestException:
            raise
        except Exception as e:
            self.__print_error("__load_identity_dynamic_groups", e)

    ##########################################################################
    # Load Network Sources
    ##########################################################################
    def __load_identity_network_sources(self, identity, tenancy_id):

        data = []
        self.__load_print_status("Network Sources")
        start_time = time.time()

        try:
            network_sources = []
            try:
                network_sources = oci.pagination.list_call_get_all_results(identity.list_network_sources, tenancy_id, retry_strategy=oci.retry.DEFAULT_RETRY_STRATEGY).data
            except oci.exceptions.ServiceError as e:
                if self.__check_service_error(e.code):
                    self.__load_print_auth_warning()
                else:
                    raise

            # oci.identity.models.NetworkSourcesSummary
            for ns in network_sources:
                print(".", end="")

                # compile vcn ip list
                vcn_list = []
                for vcn in ns.virtual_source_list:
                    vcn_list.append({
                        'vcn_id': vcn.vcn_id,
                        'ip_ranges': str(', '.join(x for x in vcn.ip_ranges)),
                    })

                data.append({
                    'id': str(ns.id),
                    'name': str(ns.name),
                    'description': str(ns.description),
                    'virtual_source_list': vcn_list,
                    'public_source_list': ns.public_source_list,
                    'services': ns.services,
                    'time_created': str(ns.time_created)
                })

            # add to data
            self.data[self.C_IDENTITY][self.C_IDENTITY_NETWORK_SOURCES] = data
            self.__load_print_cnt(len(data), start_time)

        except oci.exceptions.RequestException:
            raise
        except Exception as e:
            self.__print_error("__load_identity_network_sources", e)

    ##########################################################################
    # Load Identity Availability Domains
    ##########################################################################
    def __load_identity_availability_domain(self, region_name):

        try:
            print("Identity...")

            # create identity object
            identity = oci.identity.IdentityClient(self.config, signer=self.signer)
            if self.flags.proxy:
                identity.base_client.session.proxies = {'https': self.flags.proxy}

            self.__load_print_status("Availability Domains")
            start_time = time.time()

            # initalize the key
            self.__initialize_data_key(self.C_IDENTITY, self.C_IDENTITY_ADS)

            # get the domains
            availability_domains = []
            try:
                availability_domains = identity.list_availability_domains(self.get_tenancy_id()).data
            except oci.exceptions.ServiceError as e:
                if self.__check_service_error(e.code):
                    self.__load_print_auth_warning()
                else:
                    raise

            data = []
            cnt = 0
            for ad in availability_domains:
                data.append({'region_name': region_name, 'id': str(ad.id), 'name': str(ad.name)})
                cnt += 1

            # add to data
            self.data[self.C_IDENTITY][self.C_IDENTITY_ADS] += data

            # mark count
            self.__load_print_cnt(len(data), start_time)

            print("")

        except oci.exceptions.RequestException:
            raise
        except Exception as e:
            self.__print_error("__load_identity_availability_domains", e)

    ##########################################################################
    # Load all networks to data
    ##########################################################################
    #
    # class oci.core.virtual_network_client.virtual_networkClient(config, **kwargs)
    #
    ##########################################################################
    def __load_core_network_main(self):

        try:
            print("Network...")

            # Open connectivity to OCI
            virtual_network = oci.core.VirtualNetworkClient(self.config, signer=self.signer)
            if self.flags.proxy:
                virtual_network.base_client.session.proxies = {'https': self.flags.proxy}

            # reference to compartments
            compartments = self.data[self.C_IDENTITY][self.C_IDENTITY_COMPARTMENTS]

            # add the key to the network if not exists
            self.__initialize_data_key(self.C_NETWORK, self.C_NETWORK_VCN)
            self.__initialize_data_key(self.C_NETWORK, self.C_NETWORK_SUBNET)
            self.__initialize_data_key(self.C_NETWORK, self.C_NETWORK_NSG)

            # if to load all network resources initialize the keys
            if self.flags.read_network:
                # add the key to the network if not exists
                self.__initialize_data_key(self.C_NETWORK, self.C_NETWORK_VLAN)
                self.__initialize_data_key(self.C_NETWORK, self.C_NETWORK_SGW)
                self.__initialize_data_key(self.C_NETWORK, self.C_NETWORK_NAT)
                self.__initialize_data_key(self.C_NETWORK, self.C_NETWORK_DRG)
                self.__initialize_data_key(self.C_NETWORK, self.C_NETWORK_DRG_AT)
                self.__initialize_data_key(self.C_NETWORK, self.C_NETWORK_DRG_RT)
                self.__initialize_data_key(self.C_NETWORK, self.C_NETWORK_CPE)
                self.__initialize_data_key(self.C_NETWORK, self.C_NETWORK_IPS)
                self.__initialize_data_key(self.C_NETWORK, self.C_NETWORK_RPC)
                self.__initialize_data_key(self.C_NETWORK, self.C_NETWORK_VC)
                self.__initialize_data_key(self.C_NETWORK, self.C_NETWORK_IGW)
                self.__initialize_data_key(self.C_NETWORK, self.C_NETWORK_LPG)
                self.__initialize_data_key(self.C_NETWORK, self.C_NETWORK_ROUTE)
                self.__initialize_data_key(self.C_NETWORK, self.C_NETWORK_SLIST)
                self.__initialize_data_key(self.C_NETWORK, self.C_NETWORK_DHCP)
                self.__initialize_data_key(self.C_NETWORK, self.C_NETWORK_PRIVATEIP)

            # reference to network:
            network = self.data[self.C_NETWORK]

            # append the data for vcns
            vcns = self.__load_core_network_vcn(virtual_network, compartments)
            network[self.C_NETWORK_VCN] += vcns

            # mark if vcn exist for this regiot
            self.is_vcn_exist_for_region = (len(vcns) > 0)

            # read network resources only if there are vcns
            if self.is_vcn_exist_for_region:

                # append the data for subnets
                subnets = self.__load_core_network_subnet(virtual_network, compartments, network[self.C_NETWORK_VCN])
                network[self.C_NETWORK_SUBNET] += subnets
                network[self.C_NETWORK_NSG] += self.__load_core_network_nsg(virtual_network, compartments)

                # if to load all network resources
                if self.flags.read_network:

                    # append the data
                    network[self.C_NETWORK_VLAN] += self.__load_core_network_vlan(virtual_network, compartments, vcns)
                    network[self.C_NETWORK_LPG] += self.__load_core_network_lpg(virtual_network, compartments)
                    network[self.C_NETWORK_SGW] += self.__load_core_network_sgw(virtual_network, compartments)
                    network[self.C_NETWORK_NAT] += self.__load_core_network_nat(virtual_network, compartments)
                    network[self.C_NETWORK_DRG_AT] += self.__load_core_network_dra(virtual_network, compartments)
                    network[self.C_NETWORK_DRG] += self.__load_core_network_drg(virtual_network, compartments)
                    network[self.C_NETWORK_CPE] += self.__load_core_network_cpe(virtual_network, compartments)
                    network[self.C_NETWORK_IPS] += self.__load_core_network_ips(virtual_network, compartments)
                    network[self.C_NETWORK_RPC] += self.__load_core_network_rpc(virtual_network, compartments)
                    network[self.C_NETWORK_VC] += self.__load_core_network_vc(virtual_network, compartments)
                    network[self.C_NETWORK_IGW] += self.__load_core_network_igw(virtual_network, compartments)
                    network[self.C_NETWORK_SLIST] += self.__load_core_network_seclst(virtual_network, compartments)
                    network[self.C_NETWORK_DHCP] += self.__load_core_network_dhcpop(virtual_network, compartments)

                    routes = self.__load_core_network_routet(virtual_network, compartments)
                    network[self.C_NETWORK_ROUTE] += routes
                    network[self.C_NETWORK_PRIVATEIP] += self.__load_core_network_privateip(virtual_network, routes)

            print("")
        except oci.exceptions.RequestException:
            raise
        except oci.exceptions.ServiceError:
            raise
        except Exception as e:
            self.__print_error("__load_core_network_main", e)
            raise

    ##########################################################################
    # data network read vcns
    ##########################################################################
    def __load_core_network_vcn(self, virtual_network, compartments):

        data = []
        cnt = 0
        start_time = time.time()
        try:

            self.__load_print_status("Virtual Cloud Networks")

            # loop on all compartments
            for compartment in compartments:

                vcns = []
                try:
                    vcns = oci.pagination.list_call_get_all_results(
                        virtual_network.list_vcns,
                        compartment['id'],
                        lifecycle_state=oci.core.models.Vcn.LIFECYCLE_STATE_AVAILABLE,
                        sort_by="DISPLAYNAME",
                        retry_strategy=oci.retry.DEFAULT_RETRY_STRATEGY
                    ).data

                except oci.exceptions.ServiceError as e:
                    if self.__check_service_error(e.code):
                        self.__load_print_auth_warning()
                        continue
                    raise

                print(".", end="")

                # loop on the array
                # vcn = oci.core.models.Vcn()
                for vcn in vcns:
                    val = {'id': str(vcn.id), 'name': str(', '.join(x for x in vcn.cidr_blocks)) + " - " + str(vcn.display_name) + " - " + str(vcn.vcn_domain_name),
                           'display_name': str(vcn.display_name),
                           'cidr_block': str(vcn.cidr_block),
                           'cidr_blocks': vcn.cidr_blocks,
                           'time_created': str(vcn.time_created),
                           'vcn_domain_name': str(vcn.vcn_domain_name),
                           'compartment_name': str(compartment['name']),
                           'defined_tags': [] if vcn.defined_tags is None else vcn.defined_tags,
                           'freeform_tags': [] if vcn.freeform_tags is None else vcn.freeform_tags,
                           'compartment_id': str(compartment['id']),
                           'region_name': str(self.config['region'])}
                    data.append(val)
                    cnt += 1

            self.__load_print_cnt(cnt, start_time)
            return data

        except oci.exceptions.RequestException as e:

            if self.__check_request_error(e):
                return data

            raise
        except Exception as e:
            self.__print_error("__load_core_network_vcn", e)
            return data

    ##########################################################################
    # __load_core_network_vlan
    ##########################################################################
    def __load_core_network_vlan(self, virtual_network, compartments, vcns):

        cnt = 0
        data = []
        start_time = time.time()

        try:

            self.__load_print_status("VLANs")

            for compartment in compartments:
                print(".", end="")

                vlans = []
                try:
                    vlans = oci.pagination.list_call_get_all_results(
                        virtual_network.list_vlans,
                        compartment['id'],
                        lifecycle_state=oci.core.models.Vlan.LIFECYCLE_STATE_AVAILABLE,
                        retry_strategy=oci.retry.DEFAULT_RETRY_STRATEGY
                    ).data

                except oci.exceptions.ServiceError as e:
                    if 'not whitelisted' in str(e.message).lower():
                        print(" tenant not enabled for this region, skipped.")
                        return data
                    if self.__check_service_error(e.code):
                        self.__load_print_auth_warning('a', False)
                        continue
                    else:
                        raise

                for vlan in vlans:
                    val = {'id': str(vlan.id),
                           'vlan': str(vlan.vlan_tag) + " - " + str(vlan.cidr_block) + " - " + str(vlan.display_name),
                           'availability_domain': str(vlan.availability_domain),
                           'cidr_block': str(vlan.cidr_block),
                           'vlan_tag': str(vlan.vlan_tag),
                           'display_name': str(vlan.display_name),
                           'time_created': str(vlan.time_created),
                           'lifecycle_state': str(vlan.lifecycle_state),
                           'nsg_ids': vlan.nsg_ids,
                           'route_table_id': str(vlan.route_table_id),
                           'vcn_id': str(vlan.vcn_id),
                           'compartment_name': str(compartment['name']),
                           'compartment_id': str(compartment['id']),
                           'defined_tags': [] if vlan.defined_tags is None else vlan.defined_tags,
                           'freeform_tags': [] if vlan.freeform_tags is None else vlan.freeform_tags,
                           'region_name': str(self.config['region'])
                           }

                    data.append(val)
                    cnt += 1

            self.__load_print_cnt(cnt, start_time)
            return data

        except oci.exceptions.RequestException:
            raise
        except Exception as e:
            if 'NotAuthorizedOrNotFound' in str(e.message):
                return data
            self.__print_error("__load_core_network_vlan", e)
            return data

    ##########################################################################
    # data network read igw
    ##########################################################################
    def __load_core_network_igw(self, virtual_network, compartments):

        cnt = 0
        data = []
        start_time = time.time()

        try:

            self.__load_print_status("Internet Gateways")

            for compartment in compartments:
                print(".", end="")

                igws = []
                try:
                    igws = oci.pagination.list_call_get_all_results(
                        virtual_network.list_internet_gateways,
                        compartment['id'],
                        lifecycle_state=oci.core.models.InternetGateway.LIFECYCLE_STATE_AVAILABLE,
                        retry_strategy=oci.retry.DEFAULT_RETRY_STRATEGY
                    ).data

                except oci.exceptions.ServiceError as e:
                    if self.__check_service_error(e.code):
                        self.__load_print_auth_warning()
                    raise

                for igw in igws:
                    val = {'id': str(igw.id),
                           'vcn_id': str(igw.vcn_id),
                           'name': str(igw.display_name),
                           'time_created': str(igw.time_created),
                           'compartment_name': str(compartment['name']),
                           'compartment_id': str(compartment['id']),
                           'region_name': str(self.config['region'])
                           }

                    data.append(val)
                    cnt += 1

            self.__load_print_cnt(cnt, start_time)
            return data

        except oci.exceptions.RequestException:
            raise
        except Exception as e:
            self.__print_error("__load_core_network_igw", e)
            return data

    ##########################################################################
    # data network lpg
    ##########################################################################
    def __load_core_network_lpg(self, virtual_network, compartments):

        data = []
        cnt = 0
        start_time = time.time()

        try:

            self.__load_print_status("Local Peer GWs")

            # Loop on all compartments
            for compartment in compartments:
                print(".", end="")

                local_peering_gateways = []
                try:
                    local_peering_gateways = virtual_network.list_local_peering_gateways(
                        compartment['id'],
                        retry_strategy=oci.retry.DEFAULT_RETRY_STRATEGY
                    ).data

                except oci.exceptions.ServiceError as e:
                    if self.__check_service_error(e.code):
                        self.__load_print_auth_warning()
                    raise

                # lpg = oci.core.models.LocalPeeringGateway()
                for lpg in local_peering_gateways:
                    if lpg.lifecycle_state != oci.core.models.LocalPeeringGateway.LIFECYCLE_STATE_AVAILABLE:
                        continue

                    # get the cidr block of the peering
                    cidr = "" if lpg.peer_advertised_cidr is None else " - " + str(lpg.peer_advertised_cidr)
                    cidr += "" if not lpg.peer_advertised_cidr_details else " (" + str(', '.join(x for x in lpg.peer_advertised_cidr_details)) + ")"

                    # add lpg info to data
                    val = {'id': str(lpg.id),
                           'vcn_id': str(lpg.vcn_id),
                           'name': str(lpg.peering_status).ljust(8) + " - " + str(lpg.display_name) + str(cidr),
                           'peering_status': str(lpg.peering_status),
                           'time_created': str(lpg.time_created),
                           'display_name': str(lpg.display_name),
                           'peer_advertised_cidr': str(lpg.peer_advertised_cidr),
                           'is_cross_tenancy_peering': str(lpg.is_cross_tenancy_peering),
                           'peer_advertised_cidr_details': lpg.peer_advertised_cidr_details,
                           'route_table_id': str(lpg.route_table_id),
                           'peer_id': str(lpg.peer_id),
                           'peering_status_details': str(lpg.peering_status_details),
                           'compartment_name': str(compartment['name']),
                           'compartment_id': str(compartment['id']),
                           'defined_tags': [] if lpg.defined_tags is None else lpg.defined_tags,
                           'freeform_tags': [] if lpg.freeform_tags is None else lpg.freeform_tags,
                           'region_name': str(self.config['region'])}
                    data.append(val)
                    cnt += 1

            self.__load_print_cnt(cnt, start_time)
            return data

        except oci.exceptions.RequestException as e:

            if self.__check_request_error(e):
                return data

            raise
        except Exception as e:
            self.__print_error("__load_core_network_lpg", e)
            return data

    ##########################################################################
    # data network lpg
    ##########################################################################
    def __load_core_network_rpc(self, virtual_network, compartments):

        data = []
        cnt = 0
        start_time = time.time()

        try:

            self.__load_print_status("Remote Peer Conns")

            # iLoop on all compartments
            for compartment in compartments:

                rpcs = []
                try:
                    rpcs = oci.pagination.list_call_get_all_results(
                        virtual_network.list_remote_peering_connections,
                        compartment['id'],
                        retry_strategy=oci.retry.DEFAULT_RETRY_STRATEGY
                    ).data

                except oci.exceptions.ServiceError as e:
                    if self.__check_service_error(e.code):
                        self.__load_print_auth_warning()
                        continue
                    raise

                print(".", end="")

                # rpc = oci.core.models.RemotePeeringConnection()
                for rpc in rpcs:
                    if rpc.lifecycle_state != oci.core.models.RemotePeeringConnection.LIFECYCLE_STATE_AVAILABLE:
                        continue

                    val = {'id': str(rpc.id), 'peer_id': str(rpc.peer_id), 'drg_id': str(rpc.drg_id),
                           'name': str(rpc.display_name), 'time_created': str(rpc.time_created),
                           'is_cross_tenancy_peering': str(rpc.is_cross_tenancy_peering),
                           'peer_region_name': str(rpc.peer_region_name), 'peer_tenancy_id': str(rpc.peer_tenancy_id),
                           'peering_status': str(rpc.peering_status), 'compartment_name': str(compartment['name']),
                           'compartment_id': str(compartment['id']), 'region_name': str(self.config['region']),
                           'drg_route_table_id': "",
                           'drg_route_table': ""
                           }

                    # find Attachment for the RPC
                    drg_attachment = self.search_unique_item(self.C_NETWORK, self.C_NETWORK_DRG_AT, 'rpc_id', rpc.id)
                    if drg_attachment:
                        val['drg_route_table_id'] = drg_attachment['drg_route_table_id']
                        val['drg_route_table'] = self.get_network_drg_route_table(drg_attachment['drg_route_table_id'])

                    data.append(val)
                    cnt += 1
            self.__load_print_cnt(cnt, start_time)
            return data

        except oci.exceptions.RequestException as e:

            if self.__check_request_error(e):
                return data

            raise
        except Exception as e:
            self.__print_error("__load_core_network_rpc", e)
            return data

    ##########################################################################
    # data network read route
    ##########################################################################
    def __load_core_network_routet(self, virtual_network, compartments):

        data = []
        cnt = 0
        start_time = time.time()

        try:

            self.__load_print_status("Route Tables")

            # Loop on all compartments
            for compartment in compartments:
                print(".", end="")

                route_tables = []
                try:
                    route_tables = oci.pagination.list_call_get_all_results(
                        virtual_network.list_route_tables,
                        compartment['id'],
                        lifecycle_state=oci.core.models.RouteTable.LIFECYCLE_STATE_AVAILABLE,
                        retry_strategy=oci.retry.DEFAULT_RETRY_STRATEGY
                    ).data

                except oci.exceptions.ServiceError as e:
                    if self.__check_service_error(e.code):
                        self.__load_print_auth_warning()
                        continue
                    raise

                # loop on the routes
                # rt = oci.core.models.RouteTable()
                for rt in route_tables:
                    val = {'id': str(rt.id), 'vcn_id': str(rt.vcn_id), 'name': str(rt.display_name),
                           'time_created': str(rt.time_created),
                           'route_rules': [
                               {
                                   'destination': str(es.destination),
                                   'network_entity_id': str(es.network_entity_id),
                                   'cidr_block': "" if str(es.cidr_block) == "None" else str(es.cidr_block),
                                   'description': "" if str(es.description) == "None" else str(es.description),
                                   'destination_type': str(es.destination_type)
                               } for es in rt.route_rules],
                           'compartment_name': str(compartment['name']),
                           'defined_tags': [] if rt.defined_tags is None else rt.defined_tags,
                           'freeform_tags': [] if rt.freeform_tags is None else rt.freeform_tags,
                           'compartment_id': str(compartment['id']), 'region_name': str(self.config['region'])}
                    data.append(val)
                    cnt += 1

            self.__load_print_cnt(cnt, start_time)
            return data

        except oci.exceptions.RequestException as e:

            if self.__check_request_error(e):
                return data

            raise
        except Exception as e:
            self.__print_error("__load_core_network_route", e)
            return data

    ##########################################################################
    # get DHCP options for DHCP_ID
    ##########################################################################
    def __load_core_network_dhcpop_opt(self, dhcp_option):

        retstr = ""
        try:
            opt = dhcp_option

            # if type = oci.core.models.DhcpDnsOption
            if isinstance(opt, oci.core.models.DhcpDnsOption):
                retstr += str(opt.type).ljust(17) + ": " + str(opt.server_type)
                if len(opt.custom_dns_servers) > 0:
                    retstr += " - "
                    for ip in opt.custom_dns_servers:
                        retstr += str(ip) + "  "

            # if type = oci.core.models.DhcpSearchDomainOption
            if isinstance(opt, oci.core.models.DhcpSearchDomainOption):
                if len(opt.search_domain_names) > 0:
                    retstr += str(opt.type).ljust(17) + ": "
                    for ip in opt.search_domain_names:
                        retstr += str(ip) + "  "

            return retstr

        except Exception as e:
            self.__print_error("__load_core_network_dhcpop_opt", e)
            return retstr

    ##########################################################################
    # data network read dhcp options
    ##########################################################################
    def __load_core_network_dhcpop(self, virtual_network, compartments):

        data = []
        cnt = 0
        start_time = time.time()

        try:

            self.__load_print_status("DHCP Options")

            # Loop on all compartments
            for compartment in compartments:
                print(".", end="")

                dhcp_options = []
                try:
                    dhcp_options = oci.pagination.list_call_get_all_results(
                        virtual_network.list_dhcp_options,
                        compartment['id'],
                        lifecycle_state=oci.core.models.DhcpOptions.LIFECYCLE_STATE_AVAILABLE,
                        retry_strategy=oci.retry.DEFAULT_RETRY_STRATEGY).data

                except oci.exceptions.ServiceError as e:
                    if self.__check_service_error(e.code):
                        self.__load_print_auth_warning()
                        continue
                    raise

                # loop on the routes
                # dhcp = oci.core.models.DhcpOptions()
                for dhcp in dhcp_options:

                    # Analyzing DHCP Option
                    dhcp_opt = []
                    if dhcp.options is not None:
                        for opt in dhcp.options:
                            dhcp_opt.append(self.__load_core_network_dhcpop_opt(opt))

                    # add route info to data
                    val = {'id': str(dhcp.id), 'vcn_id': str(dhcp.vcn_id), 'name': str(dhcp.display_name),
                           'time_created': str(dhcp.time_created), 'options': dhcp_opt,
                           'compartment_name': str(compartment['name']), 'compartment_id': str(compartment['id']),
                           'defined_tags': [] if dhcp.defined_tags is None else dhcp.defined_tags,
                           'freeform_tags': [] if dhcp.freeform_tags is None else dhcp.freeform_tags,
                           'region_name': str(self.config['region'])}
                    data.append(val)
                    cnt += 1

            self.__load_print_cnt(cnt, start_time)
            return data

        except oci.exceptions.RequestException as e:

            if self.__check_request_error(e):
                return data

            raise
        except Exception as e:
            self.__print_error("__load_core_network_dhcpop", e)
            return data

    ##########################################################################
    # __load_core_network_port_range
    ##########################################################################
    def __load_core_network_seclst_rule_port_range(self, name, port_range):

        if port_range is None:
            return name + "(ALL) "

        if port_range.min == port_range.max:
            return name + "(" + str(port_range.min) + ") "
        else:
            return name + "(" + str(port_range.min) + "-" + str(port_range.max) + ") "

    ##########################################################################
    # get Network vcn security rule
    ##########################################################################
    def __load_core_network_seclst_rule(self, direction, security_rule):

        protocol_name = self.__load_core_network_seclst_protocl_name(str(security_rule.protocol))
        value = {
            'is_stateless': str(security_rule.is_stateless),
            'protocol': str(security_rule.protocol),
            'protocol_name': protocol_name,
            'source': "",
            'src_port_min': "",
            'src_port_max': "",
            'destination': "",
            'dst_port_min': "",
            'dst_port_max': "",
            'icmp_code': "",
            'icmp_type': "",
            'security_alert': False
        }

        # Process the security rule
        line = str(direction).ljust(7) + " : "

        # process the source or dest
        if isinstance(security_rule, oci.core.models.EgressSecurityRule):
            line += "Dst: " + str(security_rule.destination).ljust(18)
            value['destination'] = str(security_rule.destination)

        if isinstance(security_rule, oci.core.models.IngressSecurityRule):
            line += "Src: " + str(security_rule.source).ljust(18)
            value['source'] = str(security_rule.source)

        # protocol
        line += str(protocol_name).ljust(6)

        # tcp options
        if security_rule.tcp_options is not None:
            line += self.__load_core_network_seclst_rule_port_range("Src", security_rule.tcp_options.source_port_range)
            line += self.__load_core_network_seclst_rule_port_range("Dst", security_rule.tcp_options.destination_port_range)

            # Handle source_port_range
            if security_rule.tcp_options.source_port_range is None:
                value['src_port_min'] = "ALL"
                value['src_port_max'] = "ALL"
            else:
                value['src_port_min'] = str(security_rule.tcp_options.source_port_range.min)
                value['src_port_max'] = str(security_rule.tcp_options.source_port_range.max)

            # Handle destination_port_range
            if security_rule.tcp_options.destination_port_range is None:
                value['dst_port_min'] = "ALL"
                value['dst_port_max'] = "ALL"
            else:
                value['dst_port_min'] = str(security_rule.tcp_options.destination_port_range.min)
                value['dst_port_max'] = str(security_rule.tcp_options.destination_port_range.max)

        # udp options
        if security_rule.udp_options is not None:
            line += self.__load_core_network_seclst_rule_port_range("Src", security_rule.udp_options.source_port_range)
            line += self.__load_core_network_seclst_rule_port_range("Dst", security_rule.udp_options.destination_port_range)

            # Handle source_port_range
            if security_rule.udp_options.source_port_range is None:
                value['src_port_min'] = "ALL"
                value['src_port_max'] = "ALL"
            else:
                value['src_port_min'] = str(security_rule.udp_options.source_port_range.min)
                value['src_port_max'] = str(security_rule.udp_options.source_port_range.max)

            # Handle destination_port_range
            if security_rule.udp_options.destination_port_range is None:
                value['dst_port_min'] = "ALL"
                value['dst_port_max'] = "ALL"
            else:
                value['dst_port_min'] = str(security_rule.udp_options.destination_port_range.min)
                value['dst_port_max'] = str(security_rule.udp_options.destination_port_range.max)

        # icmp options
        if security_rule.icmp_options is None:
            if protocol_name == "ICMP":
                value['icmp_code'] = "ALL"
                value['icmp_type'] = "ALL"
                line += "(ALL)"
        else:
            icmp = security_rule.icmp_options
            line += ""
            if icmp.code is None:
                line += "(ALL),"
                value['icmp_code'] = "ALL"
            else:
                line += str(icmp.code) + ","
                value['icmp_code'] = str(icmp.code)

            if icmp.type is None:
                line += "(ALL),"
                value['icmp_type'] = "ALL"
            else:
                line += str(icmp.type)
                value['icmp_type'] = str(icmp.type)

        # Stateless
        if security_rule.is_stateless:
            line += " (Stateless) "

        # Check security_alert
        value['security_alert'] = self.__load_core_network_check_security_alert(value)
        if value['security_alert']:
            line += " *** Security Alert *** "

        value['desc'] = line
        return value

    ##########################################################################
    # protocol name
    ##########################################################################
    def __load_core_network_seclst_protocl_name(self, protocol):

        try:
            protocol_name = ""
            if str(protocol) == "1":
                protocol_name = "ICMP"
            elif str(protocol) == "6":
                protocol_name = "TCP"
            elif str(protocol) == "17":
                protocol_name = "UDP"
            elif str(protocol) == "all" or str(protocol) == "":
                protocol_name = "ALL"
            else:
                protocol_name = str("Prot(" + str(protocol) + ")")

            return protocol_name

        except Exception as e:
            self.__print_error("__load_core_network_seclst_protocl_name", e)
            return str(protocol)

    ##########################################################################
    # data network read security list
    ##########################################################################
    def __load_core_network_seclst(self, virtual_network, compartments):

        data = []
        cnt = 0
        start_time = time.time()

        try:

            self.__load_print_status("Security Lists")

            # Loop on all compartments
            for compartment in compartments:
                print(".", end="")

                sec_lists = []
                try:
                    sec_lists = oci.pagination.list_call_get_all_results(
                        virtual_network.list_security_lists,
                        compartment['id'],
                        lifecycle_state=oci.core.models.SecurityList.LIFECYCLE_STATE_AVAILABLE,
                        sort_by="DISPLAYNAME",
                        retry_strategy=oci.retry.DEFAULT_RETRY_STRATEGY
                    ).data

                except oci.exceptions.ServiceError as e:
                    if self.__check_service_error(e.code):
                        self.__load_print_auth_warning()
                        continue
                    raise

                # loop on the sec lists
                # sl = oci.core.models.SecurityList
                for sl in sec_lists:

                    # Sec Rules analyzer
                    sec_rules = []

                    for sli in sl.ingress_security_rules:
                        sec_rules.append(self.__load_core_network_seclst_rule("Ingress", sli))

                    for sle in sl.egress_security_rules:
                        sec_rules.append(self.__load_core_network_seclst_rule("Egress", sle))

                    # Add info
                    val = {'id': str(sl.id), 'vcn_id': str(sl.vcn_id), 'name': str(sl.display_name),
                           'time_created': str(sl.time_created),
                           'sec_rules': sec_rules,
                           'compartment_name': str(compartment['name']),
                           'compartment_id': str(compartment['id']),
                           'defined_tags': [] if sl.defined_tags is None else sl.defined_tags,
                           'freeform_tags': [] if sl.freeform_tags is None else sl.freeform_tags,
                           'region_name': str(self.config['region'])}
                    data.append(val)
                    cnt += 1

            self.__load_print_cnt(cnt, start_time)
            return data

        except oci.exceptions.RequestException as e:

            if self.__check_request_error(e):
                return data

            raise
        except Exception as e:
            self.__print_error("__load_core_network_seclst", e)
            return data

    ##########################################################################
    # Return NSG names strings from NSG OCIds
    ##########################################################################
    def __load_core_network_get_nsg_names(self, nsg_ids):

        return_value = ""
        try:

            # search the nsgs, if cannot find specify the ocids instead of name
            for nsg in nsg_ids:
                result = self.search_unique_item(self.C_NETWORK, self.C_NETWORK_NSG, 'id', str(nsg))
                if result:
                    if return_value:
                        return_value += ", "
                    return_value += result['name']
                else:
                    if return_value:
                        return_value += ", "
                    return_value += str(nsg)

            # return the value
            return return_value

        except Exception as e:
            self.__print_error("__load_core_network_get_nsg_names", e)
            return return_value

    ##########################################################################
    # get Network vcn security rule for NSG
    ##########################################################################
    def __load_core_network_nsg_secrule(self, security_rule):

        line = ""
        protocol_name = self.__load_core_network_seclst_protocl_name(str(security_rule.protocol))
        value = {
            'id': str(security_rule.id),
            'description': ("" if security_rule.description is None else str(security_rule.description)),
            'direction': str(security_rule.direction),
            'destination': ("" if security_rule.destination is None else str(security_rule.destination)),
            'destination_name': "",
            'destination_type': ("" if security_rule.destination_type is None else str(security_rule.destination_type)),
            'source': ("" if security_rule.source is None else str(security_rule.source)),
            'source_name': "",
            'source_type': ("" if security_rule.source_type is None else str(security_rule.source_type)),
            'is_stateless': ("False" if security_rule.is_stateless is None else str(security_rule.is_stateless)),
            'is_valid': str(security_rule.is_valid),
            'protocol': str(security_rule.protocol),
            'protocol_name': protocol_name,
            'time_created': str(security_rule.time_created),
            'src_port_min': "",
            'src_port_max': "",
            'dst_port_min': "",
            'dst_port_max': "",
            'icmp_code': "",
            'icmp_type': "",
            'security_alert': False
        }

        # process the source or dest
        if str(security_rule.direction) == oci.core.models.SecurityRule.DIRECTION_EGRESS:
            if security_rule.destination_type == oci.core.models.SecurityRule.DESTINATION_TYPE_NETWORK_SECURITY_GROUP:
                line = "Egress  : NSG: " + self.C_NETWORK_NSG_REPTEXT + " "
            else:
                line = "Egress  : Dst: " + str(security_rule.destination).ljust(17) + " "

        if str(security_rule.direction) == oci.core.models.SecurityRule.DIRECTION_INGRESS:
            if security_rule.source_type == oci.core.models.SecurityRule.SOURCE_TYPE_NETWORK_SECURITY_GROUP:
                line += "Ingress : NSG: " + self.C_NETWORK_NSG_REPTEXT + " "
            else:
                line += "Ingress : Src: " + str(security_rule.source).ljust(17) + " "

        # protocol
        line += str(protocol_name).ljust(6)

        # tcp options
        if security_rule.tcp_options is not None:
            line += self.__load_core_network_seclst_rule_port_range("Src", security_rule.tcp_options.source_port_range)
            line += self.__load_core_network_seclst_rule_port_range("Dst", security_rule.tcp_options.destination_port_range)

            # Handle source_port_range
            if security_rule.tcp_options.source_port_range is None:
                value['src_port_min'] = "ALL"
                value['src_port_max'] = "ALL"
            else:
                value['src_port_min'] = str(security_rule.tcp_options.source_port_range.min)
                value['src_port_max'] = str(security_rule.tcp_options.source_port_range.max)

            # Handle destination_port_range
            if security_rule.tcp_options.destination_port_range is None:
                value['dst_port_min'] = "ALL"
                value['dst_port_max'] = "ALL"
            else:
                value['dst_port_min'] = str(security_rule.tcp_options.destination_port_range.min)
                value['dst_port_max'] = str(security_rule.tcp_options.destination_port_range.max)

        # udp options
        if security_rule.udp_options is not None:
            line += self.__load_core_network_seclst_rule_port_range("Src", security_rule.udp_options.source_port_range)
            line += self.__load_core_network_seclst_rule_port_range("Dst", security_rule.udp_options.destination_port_range)

            # Handle source_port_range
            if security_rule.udp_options.source_port_range is None:
                value['src_port_min'] = "ALL"
                value['src_port_max'] = "ALL"
            else:
                value['src_port_min'] = str(security_rule.udp_options.source_port_range.min)
                value['src_port_max'] = str(security_rule.udp_options.source_port_range.max)

            # Handle destination_port_range
            if security_rule.udp_options.destination_port_range is None:
                value['dst_port_min'] = "ALL"
                value['dst_port_max'] = "ALL"
            else:
                value['dst_port_min'] = str(security_rule.udp_options.destination_port_range.min)
                value['dst_port_max'] = str(security_rule.udp_options.destination_port_range.max)

        # icmp options
        if security_rule.icmp_options is None:
            if protocol_name == "ICMP":
                value['icmp_code'] = "ALL"
                value['icmp_type'] = "ALL"
                line += "(ALL)"
        else:
            icmp = security_rule.icmp_options
            line += ""
            if icmp.code is None:
                line += "(ALL),"
                value['icmp_code'] = "ALL"
            else:
                line += str(icmp.code) + ","
                value['icmp_code'] = str(icmp.code)

            if icmp.type is None:
                line += "(ALL),"
                value['icmp_type'] = "ALL"
            else:
                line += str(icmp.type)
                value['icmp_type'] = str(icmp.type)

        # Stateless
        if security_rule.is_stateless:
            line += " (Stateless) "

        # Check security_alert
        value['security_alert'] = self.__load_core_network_check_security_alert(value)
        if value['security_alert']:
            line += " *** Security Alert *** "

        value['desc'] = line
        return value

    ##########################################################################
    # check Security Alert
    # if source = 0.0.0.0/0 and ports are not 22,443,3389
    ##########################################################################
    def __load_core_network_check_security_alert(self, security_row):
        if (
                security_row['source'] == "0.0.0.0/0" and
                security_row['protocol_name'] == "TCP" and
                not (security_row['dst_port_min'] == "22" and security_row['dst_port_max'] == "22") and
                not (security_row['dst_port_min'] == "443" and security_row['dst_port_max'] == "443") and
                not (security_row['dst_port_min'] == "3389" and security_row['dst_port_max'] == "3389")
        ):
            return True
        else:
            return False

    ##########################################################################
    # data network security groups
    ##########################################################################
    def __load_core_network_nsg(self, virtual_network, compartments):

        data = []
        cnt = 0
        start_time = time.time()

        try:

            self.__load_print_status("Network Security Groups")

            # loop on all compartments
            for compartment in compartments:

                # ngw will throw error if run on Paas compartment
                if self.__if_managed_paas_compartment(compartment['name']):
                    print(".", end="")
                    continue

                arrs = []
                try:
                    arrs = oci.pagination.list_call_get_all_results(
                        virtual_network.list_network_security_groups,
                        compartment_id=compartment['id'],
                        lifecycle_state=oci.core.models.NetworkSecurityGroup.LIFECYCLE_STATE_AVAILABLE,
                        retry_strategy=oci.retry.DEFAULT_RETRY_STRATEGY
                    ).data

                except oci.exceptions.ServiceError as e:
                    if self.__check_service_error(e.code):
                        self.__load_print_auth_warning("n", False)
                        continue
                    raise

                print(".", end="")

                # loop on array
                # arr = oci.core.models.NetworkSecurityGroup
                for arr in arrs:
                    val = {'id': str(arr.id),
                           'name': str(arr.display_name),
                           'vcn_id': str(arr.vcn_id),
                           'time_created': str(arr.time_created),
                           'compartment_name': str(compartment['name']),
                           'defined_tags': [] if arr.defined_tags is None else arr.defined_tags,
                           'freeform_tags': [] if arr.freeform_tags is None else arr.freeform_tags,
                           'compartment_id': str(compartment['id']),
                           'region_name': str(self.config['region']),
                           'sec_rules': []
                           }

                    # loop on NSG
                    arrsecs = []
                    try:
                        arrsecs = oci.pagination.list_call_get_all_results(
                            virtual_network.list_network_security_group_security_rules,
                            arr.id,
                            retry_strategy=oci.retry.DEFAULT_RETRY_STRATEGY
                        ).data

                    except oci.exceptions.ServiceError as e:
                        if self.__check_service_error(e.code):
                            self.__load_print_auth_warning("p", False)
                        else:
                            raise

                    # oci.core.models.SecurityRule
                    for arrsec in arrsecs:
                        val['sec_rules'].append(self.__load_core_network_nsg_secrule(arrsec))

                    data.append(val)
                    cnt += 1

            self.__load_print_cnt(cnt, start_time)
            return data

        except oci.exceptions.RequestException as e:

            if self.__check_request_error(e):
                return data

            raise
        except Exception as e:
            self.__print_error("__load_core_network_nsg", e)
            return data

    ##########################################################################
    # data network read subnets
    ##########################################################################
    def __load_core_network_subnet(self, virtual_network, compartments, vcns):

        data = []
        cnt = 0
        start_time = time.time()

        try:

            self.__load_print_status("Subnets")

            # Loop on all compartments
            for compartment in compartments:
                print(".", end="")

                subnets = []
                try:
                    subnets = oci.pagination.list_call_get_all_results(
                        virtual_network.list_subnets,
                        compartment['id'],
                        lifecycle_state=oci.core.models.Subnet.LIFECYCLE_STATE_AVAILABLE,
                        sort_by="DISPLAYNAME",
                        retry_strategy=oci.retry.DEFAULT_RETRY_STRATEGY
                    ).data

                except oci.exceptions.ServiceError as e:
                    if self.__check_service_error(e.code):
                        self.__load_print_auth_warning()
                        continue
                    raise

                # loop on the subnet
                # subnet = oci.core.models.Subnet.
                for subnet in subnets:
                    availability_domain = (str(subnet.availability_domain) if str(subnet.availability_domain) != "None" else "Regional")

                    val = {'id': str(subnet.id),
                           'vcn_id': str(subnet.vcn_id),
                           'vcn_name': "",
                           'vcn_cidr': "",
                           'vcn_domain_name': "",
                           'dns': "",
                           'name': str(subnet.display_name),
                           'cidr_block': str(subnet.cidr_block),
                           'subnet': (str(subnet.cidr_block) + "  " + availability_domain + (" (Private) " if subnet.prohibit_public_ip_on_vnic else " (Public)")),
                           'availability_domain': availability_domain,
                           'public_private': ("Private" if subnet.prohibit_public_ip_on_vnic else "Public"),
                           'time_created': str(subnet.time_created),
                           'security_list_ids': [str(es) for es in subnet.security_list_ids],
                           'dhcp_options_id': str(subnet.dhcp_options_id),
                           'route_table_id': str(subnet.route_table_id),
                           'dns_label': str(subnet.dns_label),
                           'defined_tags': [] if subnet.defined_tags is None else subnet.defined_tags,
                           'freeform_tags': [] if subnet.freeform_tags is None else subnet.freeform_tags,
                           'compartment_name': str(compartment['name']), 'compartment_id': str(compartment['id']),
                           'region_name': str(self.config['region'])
                           }

                    # find vcn
                    for vcn in vcns:
                        if str(subnet.vcn_id) == vcn['id']:
                            val['dns'] = str(subnet.dns_label) + "." + vcn['vcn_domain_name']
                            val['vcn_name'] = vcn['display_name']
                            val['vcn_domain_name'] = vcn['vcn_domain_name']
                            val['vcn_cidr'] = str(', '.join(x for x in vcn['cidr_blocks']))

                    data.append(val)
                    cnt += 1

            self.__load_print_cnt(cnt, start_time)
            return data

        except oci.exceptions.RequestException as e:

            if self.__check_request_error(e):
                return data

            raise
        except Exception as e:
            self.__print_error("__load_core_network_slist", e)
            return data

    ##########################################################################
    # data network read sgw
    ##########################################################################
    def __load_core_network_sgw(self, virtual_network, compartments):

        data = []
        cnt = 0
        start_time = time.time()

        try:

            self.__load_print_status("Service Gateways")

            # loop on all compartments
            for compartment in compartments:

                sgws = []
                try:
                    sgws = oci.pagination.list_call_get_all_results(
                        virtual_network.list_service_gateways,
                        compartment['id'],
                        lifecycle_state=oci.core.models.ServiceGateway.LIFECYCLE_STATE_AVAILABLE,
                        retry_strategy=oci.retry.DEFAULT_RETRY_STRATEGY
                    ).data

                except oci.exceptions.ServiceError as e:
                    if self.__check_service_error(e.code):
                        self.__load_print_auth_warning()
                        continue
                    raise

                print(".", end="")

                # loop on all sgws
                # sgw = oci.core.models.ServiceGateway
                for sgw in sgws:
                    val = {'id': str(sgw.id),
                           'vcn_id': str(sgw.vcn_id),
                           'name': str(sgw.display_name),
                           'time_created': str(sgw.time_created),
                           'route_table_id': str(sgw.route_table_id),
                           'services': str(', '.join(x.service_name for x in sgw.services)),
                           'compartment_name': str(compartment['name']),
                           'compartment_id': str(compartment['id']),
                           'defined_tags': [] if sgw.defined_tags is None else sgw.defined_tags,
                           'freeform_tags': [] if sgw.freeform_tags is None else sgw.freeform_tags,
                           'region_name': str(self.config['region'])}

                    data.append(val)
                    cnt += 1

            self.__load_print_cnt(cnt, start_time)
            return data

        except oci.exceptions.RequestException as e:

            if self.__check_request_error(e):
                return data

            raise
        except Exception as e:
            self.__print_error("__load_core_network_sgw", e)
            return data

    ##########################################################################
    # data network read sgw
    ##########################################################################
    def __load_core_network_nat(self, virtual_network, compartments):

        data = []
        cnt = 0
        start_time = time.time()

        try:

            self.__load_print_status("NAT Gateways")

            # loop on all compartments
            for compartment in compartments:
                # natgw will throw error if run on Paas compartment
                if self.__if_managed_paas_compartment(compartment['name']):
                    print(".", end="")
                    continue

                natgws = []
                try:
                    natgws = oci.pagination.list_call_get_all_results(
                        virtual_network.list_nat_gateways,
                        compartment['id'],
                        lifecycle_state=oci.core.models.NatGateway.LIFECYCLE_STATE_AVAILABLE,
                        retry_strategy=oci.retry.DEFAULT_RETRY_STRATEGY
                    ).data

                except oci.exceptions.ServiceError as e:
                    if self.__check_service_error(e.code):
                        self.__load_print_auth_warning()
                        continue
                    raise

                print(".", end="")

                # loop on all sgws
                # nat = oci.core.models.NatGateway.
                for nat in natgws:
                    val = {'id': str(nat.id), 'vcn_id': str(nat.vcn_id), 'name': str(nat.display_name) + " - " + str(nat.nat_ip),
                           'time_created': str(nat.time_created),
                           'block_traffic': str(nat.block_traffic),
                           'nat_ip': str(nat.nat_ip),
                           'display_name': str(nat.display_name),
                           'defined_tags': [] if nat.defined_tags is None else nat.defined_tags,
                           'freeform_tags': [] if nat.freeform_tags is None else nat.freeform_tags,
                           'compartment_name': str(compartment['name']), 'compartment_id': str(compartment['id']), 'region_name': str(self.config['region'])}

                    if nat.block_traffic:
                        val['name'] += " - Blocked"
                    data.append(val)
                    cnt += 1

            self.__load_print_cnt(cnt, start_time)
            return data

        except oci.exceptions.RequestException as e:

            if self.__check_request_error(e):
                return data

            raise
        except Exception as e:
            self.__print_error("__load_core_network_nat", e)
            return data

    ##########################################################################
    # data network read drg attachment
    ##########################################################################
    def __load_core_network_dra(self, virtual_network, compartments):

        data = []
        cnt = 0
        start_time = time.time()

        try:

            self.__load_print_status("Dynamic Routing GW Attch")

            # loop on all compartments
            for compartment in compartments:

                arrs = []
                try:
                    arrs = oci.pagination.list_call_get_all_results(
                        virtual_network.list_drg_attachments,
                        compartment['id'],
                        attachment_type="ALL",
                        retry_strategy=oci.retry.DEFAULT_RETRY_STRATEGY
                    ).data

                except oci.exceptions.ServiceError as e:
                    if self.__check_service_error(e.code):
                        self.__load_print_auth_warning()
                        continue
                    raise

                print(".", end="")

                # loop on array
                # arr = oci.core.models.DrgAttachment
                for arr in arrs:
                    if arr.lifecycle_state == oci.core.models.DrgAttachment.LIFECYCLE_STATE_ATTACHED:
                        val = {
                            'id': str(arr.id),
                            'vcn_id': str(arr.vcn_id),
                            'drg_id': str(arr.drg_id),
                            'time_created': str(arr.time_created),
                            'display_name': str(arr.display_name),
                            'is_cross_tenancy': str(arr.is_cross_tenancy),
                            'export_drg_route_distribution_id': str(arr.export_drg_route_distribution_id),
                            'drg_route_table_id': str(arr.drg_route_table_id),
                            'route_table_id': "" if str(arr.route_table_id) == "None" else str(arr.route_table_id),
                            'compartment_name': str(compartment['name']),
                            'compartment_id': str(compartment['id']),
                            'region_name': str(self.config['region']),
                            'ipsec_id': "",
                            'ipsec_connection_id': "",
                            'virtual_cirtcuit_id': "",
                            'rpc_id': ""
                        }

                        # Get attachment id
                        if arr.network_details:
                            if arr.network_details.type == "IPSEC_TUNNEL":
                                val['ipsec_id'] = arr.network_details.id
                                val['ipsec_connection_id'] = arr.network_details.ipsec_connection_id
                            if arr.network_details.type == "VCN":
                                val['vcn_id'] = arr.network_details.id
                                val['route_table_id'] = arr.network_details.route_table_id
                            if arr.network_details.type == "REMOTE_PEERING_CONNECTION":
                                val['rpc_id'] = arr.network_details.id
                            if arr.network_details.type == "VIRTUAL_CIRCUIT":
                                val['virtual_cirtcuit_id'] = arr.network_details.id

                        data.append(val)
                        cnt += 1

            self.__load_print_cnt(cnt, start_time)
            return data

        except oci.exceptions.RequestException as e:

            if self.__check_request_error(e):
                return data

            raise
        except Exception as e:
            self.__print_error("__load_core_network_dra", e)
            return data

    ##########################################################################
    # data network read drg
    ##########################################################################
    def __load_core_network_drg(self, virtual_network, compartments):

        data = []
        cnt = 0
        start_time = time.time()

        try:

            self.__load_print_status("Dynamic Routing GWs")

            # loop on all compartments
            for compartment in compartments:

                arrs = []
                try:
                    arrs = oci.pagination.list_call_get_all_results(
                        virtual_network.list_drgs,
                        compartment['id'],
                        retry_strategy=oci.retry.DEFAULT_RETRY_STRATEGY
                    ).data

                except oci.exceptions.ServiceError as e:
                    if self.__check_service_error(e.code):
                        self.__load_print_auth_warning()
                        continue
                    raise

                print(".", end="")

                # loop on array
                # arr = oci.core.models.Drg
                for arr in arrs:
                    if arr.lifecycle_state == oci.core.models.Drg.LIFECYCLE_STATE_AVAILABLE:
                        val = {'id': str(arr.id),
                               'name': str(arr.display_name),
                               'time_created': str(arr.time_created),
                               'redundancy': "",
                               'drg_route_tables': [],
                               'compartment_name': str(compartment['name']),
                               'compartment_id': str(compartment['id']),
                               'defined_tags': [] if arr.defined_tags is None else arr.defined_tags,
                               'freeform_tags': [] if arr.freeform_tags is None else arr.freeform_tags,
                               'region_name': str(self.config['region'])
                               }

                        # get Redundancy
                        try:
                            # oci.core.models.DrgRedundancyStatus
                            redundancy = virtual_network.get_drg_redundancy_status(arr.id).data
                            if redundancy:
                                val['redundancy'] = str(redundancy.status)
                        except oci.exceptions.ServiceError as e:
                            if self.__check_service_error(e.code):
                                self.__load_print_auth_warning()

                        # DRG Route Tables
                        try:
                            # oci.core.models.DrgRedundancyStatus
                            route_tables = virtual_network.list_drg_route_tables(
                                arr.id,
                                lifecycle_state="AVAILABLE",
                                retry_strategy=oci.retry.DEFAULT_RETRY_STRATEGY
                            ).data

                            for rt in route_tables:
                                rta = {
                                    'id': str(rt.id),
                                    'drg_id': str(arr.id),
                                    'display_name': str(rt.display_name),
                                    'time_created': str(rt.time_created),
                                    'route_rules': self.__load_core_network_drg_route_rules(virtual_network, rt.id),
                                    'import_drg_route_distribution_id': str(rt.import_drg_route_distribution_id),
                                    'is_ecmp_enabled': str(rt.is_ecmp_enabled),
                                    'defined_tags': [] if rt.defined_tags is None else rt.defined_tags,
                                    'freeform_tags': [] if rt.freeform_tags is None else rt.freeform_tags
                                }
                                val['drg_route_tables'].append(rta)
                                network = self.data[self.C_NETWORK]
                                network[self.C_NETWORK_DRG_RT].append(rta)

                        except oci.exceptions.ServiceError as e:
                            if e.code == 'NotAuthorizedOrNotFound':
                                pass
                            if self.__check_service_error(e.code):
                                pass

                        data.append(val)
                        cnt += 1

            self.__load_print_cnt(cnt, start_time)
            return data

        except oci.exceptions.RequestException as e:

            if self.__check_request_error(e):
                return data

            raise
        except Exception as e:
            self.__print_error("__load_core_network_drg", e)
            return data

    ##########################################################################
    # data network read cpes
    ##########################################################################
    def __load_core_network_drg_route_rules(self, virtual_network, drg_route_id):

        data = []
        try:

            arrs = []
            try:
                arrs = oci.pagination.list_call_get_all_results(
                    virtual_network.list_drg_route_rules,
                    drg_route_id,
                    retry_strategy=oci.retry.DEFAULT_RETRY_STRATEGY
                ).data

            except oci.exceptions.ServiceError:
                return data

            # loop on array
            # arr = oci.core.models.DrgRouteRule
            for arr in arrs:
                val = {
                    'name': str(arr.route_type) + " - " + str(arr.destination_type) + " : " + str(arr.destination).ljust(18, ' ') + " -> " + str(arr.route_provenance),
                    'drg_route_id': drg_route_id,
                    'destination': str(arr.destination),
                    'destination_type': str(arr.destination_type),
                    'next_hop_drg_attachment_id': str(arr.next_hop_drg_attachment_id),
                    'route_type': str(arr.route_type),
                    'is_conflict': str(arr.is_conflict),
                    'is_blackhole': str(arr.is_blackhole),
                    'id': str(arr.id),
                    'route_provenance': str(arr.route_provenance)
                }

                # Get vcn name if VCN as destination
                if arr.route_provenance == "VCN":
                    drgatt = self.search_unique_item(self.C_NETWORK, self.C_NETWORK_DRG_AT, 'id', arr.next_hop_drg_attachment_id)
                    if drgatt:
                        vcn_name = self.get_network_vcn(drgatt['vcn_id'])
                        val['name'] += " (" + vcn_name + ")"
                data.append(val)
            return data

        except oci.exceptions.RequestException as e:
            if self.__check_request_error(e):
                return data
            raise
        except Exception as e:
            self.__print_error("__load_core_network_drg_route_rules", e)
            return data

    ##########################################################################
    # data network read cpes
    ##########################################################################
    def __load_core_network_cpe(self, virtual_network, compartments):

        data = []
        cnt = 0
        start_time = time.time()

        try:

            self.__load_print_status("Customer Prem Equipments")

            # loop on all compartments
            for compartment in compartments:

                arrs = []
                try:
                    arrs = oci.pagination.list_call_get_all_results(
                        virtual_network.list_cpes,
                        compartment['id'],
                        retry_strategy=oci.retry.DEFAULT_RETRY_STRATEGY
                    ).data

                except oci.exceptions.ServiceError as e:
                    if self.__check_service_error(e.code):
                        self.__load_print_auth_warning()
                        continue
                    raise

                print(".", end="")

                # loop on array
                # arr = oci.core.models.Cpe
                for arr in arrs:
                    val = {'id': str(arr.id),
                           'name': str(arr.display_name) + " - " + str(arr.ip_address),
                           'display_name': str(arr.display_name),
                           'ip_address': str(arr.ip_address),
                           'time_created': str(arr.time_created),
                           'compartment_name': str(compartment['name']),
                           'defined_tags': [] if arr.defined_tags is None else arr.defined_tags,
                           'freeform_tags': [] if arr.freeform_tags is None else arr.freeform_tags,
                           'compartment_id': str(compartment['id']),
                           'region_name': str(self.config['region'])
                           }
                    data.append(val)
                    cnt += 1

            self.__load_print_cnt(cnt, start_time)
            return data

        except oci.exceptions.RequestException as e:

            if self.__check_request_error(e):
                return data

            raise
        except Exception as e:
            self.__print_error("__load_core_network_cpe", e)
            return data

    ##########################################################################
    # query private ip
    ##########################################################################
    def __load_core_network_single_privateip(self, virtual_network, ip_id, return_name=True):

        try:
            if 'privateip' not in ip_id:
                return ""

            arr = virtual_network.get_private_ip(
                ip_id,
                retry_strategy=oci.retry.DEFAULT_RETRY_STRATEGY
            ).data

            if arr:
                if return_name:
                    return str(arr.ip_address) + " - " + str(arr.display_name)
                else:
                    return str(arr.ip_address)
            return ""

        except oci.exceptions.ServiceError as e:
            if self.__check_service_error(e.code):
                pass
            raise
        except Exception as e:
            self.__print_error("__get_core_network_privateip", e)
            return ""

    ##########################################################################
    # query vlan ip
    ##########################################################################
    def __load_core_network_single_vlan(self, virtual_network, vlan_id):

        try:
            if 'vlan' not in vlan_id:
                return ""

            arr = virtual_network.get_vlan(
                vlan_id,
                retry_strategy=oci.retry.DEFAULT_RETRY_STRATEGY
            ).data

            if arr:
                return "VLAN " + str(arr.vlan_tag) + " - " + str(arr.cidr_block).ljust(20) + " - " + str(arr.display_name)
            return ""

        except oci.exceptions.ServiceError as e:
            if self.__check_service_error(e.code):
                pass
            raise
        except Exception as e:
            self.__print_error("__load_core_network_single_vlan", e)
            return ""

    ##########################################################################
    # __load_core_network_privateip
    ##########################################################################
    def __load_core_network_privateip(self, virtual_network, routes):

        data = []
        cnt = 0
        start_time = time.time()

        try:

            self.__load_print_status("Routed Private IPs")

            # loop on all routes with private ips
            for route in routes:
                for rl in route['route_rules']:
                    if 'privateip' not in rl['network_entity_id']:
                        continue

                    # get the list
                    arr = None
                    try:
                        arr = virtual_network.get_private_ip(
                            rl['network_entity_id'],
                            retry_strategy=oci.retry.DEFAULT_RETRY_STRATEGY
                        ).data
                    except oci.exceptions.ServiceError as e:
                        if str(e.code) == 'NotAuthorizedOrNotFound':
                            continue
                        if self.__check_service_error(e.code):
                            self.__load_print_auth_warning()
                            continue
                        raise

                    print("-", end="")

                    if arr is None:
                        continue

                    val = {'id': str(arr.id), 'name': str(arr.ip_address) + " - " + str(arr.display_name),
                           'time_created': str(arr.time_created), 'availability_domain': str(arr.availability_domain),
                           'hostname_label': str(arr.hostname_label), 'is_primary': str(arr.is_primary),
                           'ip_address': str(arr.ip_address), 'subnet_id': str(arr.subnet_id),
                           'compartment_id': str(arr.compartment_id), 'vnic_id': str(arr.vnic_id),
                           'region_name': str(self.config['region'])}
                    data.append(val)
                    cnt += 1

            self.__load_print_cnt(cnt, start_time)
            return data

        except oci.exceptions.RequestException as e:

            if self.__check_request_error(e):
                return data

            raise
        except Exception as e:
            self.__print_error("__load_core_network_privateip", e)
            return data

    ##########################################################################
    # data network read fastconnect
    ##########################################################################
    def __load_core_network_vc(self, virtual_network, compartments):

        data = []
        cnt = 0
        start_time = time.time()

        try:

            self.__load_print_status("Virtual Circuits")

            # loop on all compartments
            for compartment in compartments:
                arrs = []
                try:
                    arrs = oci.pagination.list_call_get_all_results(
                        virtual_network.list_virtual_circuits,
                        compartment['id'],
                        retry_strategy=oci.retry.DEFAULT_RETRY_STRATEGY
                    ).data

                except oci.exceptions.ServiceError as e:
                    if self.__check_service_error(e.code):
                        self.__load_print_auth_warning()
                        continue
                    raise

                print(".", end="")

                # loop on array
                # arr = oci.core.models.VirtualCircuit
                for arr in arrs:

                    # get the cross connect mapping
                    data_cc = []
                    for cc in arr.cross_connect_mappings:
                        data_cc.append({'customer_bgp_peering_ip': str(cc.customer_bgp_peering_ip),
                                        'oracle_bgp_peering_ip': str(cc.oracle_bgp_peering_ip), 'vlan': str(cc.vlan)})

                    val = {'id': str(arr.id), 'name': str(arr.display_name),
                           'bandwidth_shape_name': str(arr.bandwidth_shape_name),
                           'bgp_management': str(arr.bgp_management), 'bgp_session_state': str(arr.bgp_session_state),
                           'customer_bgp_asn': str(arr.customer_bgp_asn), 'drg_id': str(arr.gateway_id),
                           'lifecycle_state': str(arr.lifecycle_state), 'oracle_bgp_asn': str(arr.oracle_bgp_asn),
                           'provider_name': str(arr.provider_name),
                           'provider_service_name': str(arr.provider_service_name),
                           'provider_state': str(arr.provider_state), 'reference_comment': str(arr.reference_comment),
                           'service_type': str(arr.service_type), 'cross_connect_mappings': data_cc,
                           'type': str(arr.type), 'time_created': str(arr.time_created),
                           'compartment_name': str(compartment['name']), 'compartment_id': str(compartment['id']),
                           'region_name': str(self.config['region']),
                           'drg_route_table_id': "",
                           'drg_route_table': ""
                           }

                    # find Attachment for the VC
                    drg_attachment = self.search_unique_item(self.C_NETWORK, self.C_NETWORK_DRG_AT, 'virtual_cirtcuit_id', arr.id)
                    if drg_attachment:
                        val['drg_route_table_id'] = drg_attachment['drg_route_table_id']
                        val['drg_route_table'] = self.get_network_drg_route_table(drg_attachment['drg_route_table_id'])

                    data.append(val)
                    cnt += 1

            self.__load_print_cnt(cnt, start_time)
            return data

        except oci.exceptions.RequestException as e:

            if self.__check_request_error(e):
                return data

            raise
        except Exception as e:
            self.__print_error("__load_core_network_vc", e)
            return data

    ##########################################################################
    # data network read ipsec
    ##########################################################################
    def __load_core_network_ips(self, virtual_network, compartments):

        data = []
        cnt = 0
        start_time = time.time()

        try:

            self.__load_print_status("IPSEC tunnels")

            # loop on all compartments
            for compartment in compartments:

                arrs = []
                try:
                    arrs = oci.pagination.list_call_get_all_results(
                        virtual_network.list_ip_sec_connections,
                        compartment['id'],
                        retry_strategy=oci.retry.DEFAULT_RETRY_STRATEGY
                    ).data

                except oci.exceptions.ServiceError as e:
                    if self.__check_service_error(e.code):
                        self.__load_print_auth_warning()
                        continue
                    raise

                print(".", end="")

                # loop on array
                # arr = oci.core.models.IPSecConnection.
                for arr in arrs:
                    if arr.lifecycle_state == oci.core.models.IPSecConnection.LIFECYCLE_STATE_AVAILABLE:

                        # get tunnel info
                        # ipss = oci.core.models.IPSecConnectionTunnel
                        data_tun = []
                        try:
                            tunnels = virtual_network.list_ip_sec_connection_tunnels(arr.id).data
                            tunnels_status = ""
                            for tunnel in tunnels:
                                tun_val = {'id': str(tunnel.id),
                                           'status': str(tunnel.status),
                                           'lifecycle_state': str(tunnel.lifecycle_state),
                                           'status_date': tunnel.time_status_updated.strftime("%Y-%m-%d %H:%M"),
                                           'display_name': str(tunnel.display_name),
                                           'routing': str(tunnel.routing),
                                           'cpe_ip': str(tunnel.cpe_ip),
                                           'vpn_ip': str(tunnel.vpn_ip),
                                           'bgp_info': ""
                                           }
                                if tunnels_status:
                                    tunnels_status += " "
                                tunnels_status += str(tunnel.status)

                                if tunnel.bgp_session_info:
                                    bs = tunnel.bgp_session_info
                                    tun_val['bgp_info'] = "BGP Status ".ljust(12) + " - " + str(bs.bgp_state) + ", Cust: " + str(bs.customer_interface_ip) + " (ASN = " + str(bs.customer_bgp_asn) + "), Oracle: " + str(bs.oracle_interface_ip) + " (ASN = " + str(bs.oracle_bgp_asn) + ")"

                                data_tun.append(tun_val)
                        except Exception:
                            pass

                        val = {'id': str(arr.id),
                               'name': str(arr.display_name),
                               'drg_id': str(arr.drg_id),
                               'tunnels_status': tunnels_status,
                               'cpe_id': str(arr.cpe_id), 'time_created': str(arr.time_created),
                               'compartment_name': str(compartment['name']), 'compartment_id': str(compartment['id']),
                               'defined_tags': [] if arr.defined_tags is None else arr.defined_tags,
                               'freeform_tags': [] if arr.freeform_tags is None else arr.freeform_tags,
                               'region_name': str(self.config['region']),
                               'static_routes': [str(es) for es in arr.static_routes], 'tunnels': data_tun,
                               'drg_route_table_id': "",
                               'drg_route_table': ""
                               }

                        # find Attachment for the IPSEC
                        drg_attachment = self.search_unique_item(self.C_NETWORK, self.C_NETWORK_DRG_AT, 'ipsec_connection_id', arr.id)
                        if drg_attachment:
                            val['drg_route_table_id'] = drg_attachment['drg_route_table_id']
                            val['drg_route_table'] = self.get_network_drg_route_table(drg_attachment['drg_route_table_id'])

                        data.append(val)
                        cnt += 1

            self.__load_print_cnt(cnt, start_time)
            return data

        except oci.exceptions.RequestException as e:

            if self.__check_request_error(e):
                return data

            raise
        except Exception as e:
            self.__print_error("__load_core_network_ips", e)
            return data

    ##########################################################################
    # __load_core_compute_block_main
    ##########################################################################
    #
    # OCI Classes used:
    #
    # class oci.core.ComputeClient(config, **kwargs)
    # class oci.core.BlockstorageClient(config, **kwargs)
    # class oci.core.VirtualNetworkClient(config, **kwargs)
    ##########################################################################
    def __load_core_compute_main(self):

        try:
            print("Compute...")

            # BlockstorageClient
            block_storage = oci.core.BlockstorageClient(self.config, signer=self.signer)
            if self.flags.proxy:
                block_storage.base_client.session.proxies = {'https': self.flags.proxy}

            # ComputeClient
            compute_client = oci.core.ComputeClient(self.config, signer=self.signer)
            if self.flags.proxy:
                compute_client.base_client.session.proxies = {'https': self.flags.proxy}

            # virtual_network - for vnics
            virtual_network = oci.core.VirtualNetworkClient(self.config, signer=self.signer)
            if self.flags.proxy:
                virtual_network.base_client.session.proxies = {'https': self.flags.proxy}

            # reference to compartments
            compartments = self.get_compartment()

            # add the key to the network if not exists
            self.__initialize_data_key(self.C_COMPUTE, self.C_COMPUTE_INST)
            self.__initialize_data_key(self.C_COMPUTE, self.C_COMPUTE_IMAGES)
            self.__initialize_data_key(self.C_COMPUTE, self.C_COMPUTE_BOOT_VOL_ATTACH)
            self.__initialize_data_key(self.C_COMPUTE, self.C_COMPUTE_VOLUME_ATTACH)
            self.__initialize_data_key(self.C_COMPUTE, self.C_COMPUTE_VNIC_ATTACH)

            self.__initialize_data_key(self.C_BLOCK, self.C_BLOCK_VOLGRP)
            self.__initialize_data_key(self.C_BLOCK, self.C_BLOCK_BOOT)
            self.__initialize_data_key(self.C_BLOCK, self.C_BLOCK_BOOTBACK)
            self.__initialize_data_key(self.C_BLOCK, self.C_BLOCK_VOL)
            self.__initialize_data_key(self.C_BLOCK, self.C_BLOCK_VOLBACK)

            # reference to compute
            compute = self.data[self.C_COMPUTE]
            block = self.data[self.C_BLOCK]

            # append the data
            compute[self.C_COMPUTE_INST] += self.__load_core_compute_instances(compute_client, compartments)
            compute[self.C_COMPUTE_IMAGES] += self.__load_core_compute_images(compute_client, compartments)
            compute[self.C_COMPUTE_BOOT_VOL_ATTACH] += self.__load_core_compute_boot_vol_attach(compute_client, compartments)
            compute[self.C_COMPUTE_VOLUME_ATTACH] += self.__load_core_compute_vol_attach(compute_client, compartments)
            compute[self.C_COMPUTE_VNIC_ATTACH] += self.__load_core_compute_vnic_attach(compute_client, virtual_network, compartments)

            print("")
            print("Block Storage...")

            block[self.C_BLOCK_VOLGRP] += self.__load_core_block_volume_group(block_storage, compartments)
            block[self.C_BLOCK_BOOT] += self.__load_core_block_boot(block_storage, compartments)
            block[self.C_BLOCK_VOL] += self.__load_core_block_volume(block_storage, compartments)

            print("")

        except oci.exceptions.RequestException:
            raise
        except oci.exceptions.ServiceError as e:
            if self.__check_service_error(e.code):
                print("")
                pass
            raise
        except Exception as e:
            self.__print_error("__load_core_compute_main", e)

    ##########################################################################
    # data compute read instances
    ##########################################################################
    def __load_core_compute_instances(self, compute, compartments):

        data = []
        cnt = 0
        start_time = time.time()

        try:

            self.__load_print_status("Instances")

            # loop on all compartments
            for compartment in compartments:

                # read instances and console connections
                arrs = []
                consoles = []
                try:
                    arrs = oci.pagination.list_call_get_all_results(
                        compute.list_instances,
                        compartment['id'],
                        sort_by="DISPLAYNAME",
                        retry_strategy=oci.retry.DEFAULT_RETRY_STRATEGY
                    ).data

                    consoles = oci.pagination.list_call_get_all_results(
                        compute.list_instance_console_connections,
                        compartment['id'],
                        retry_strategy=oci.retry.DEFAULT_RETRY_STRATEGY
                    ).data

                except oci.exceptions.ServiceError as e:
                    if self.__check_service_error(e.code):
                        self.__load_print_auth_warning()
                        continue
                    raise

                print(".", end="")

                # loop on array
                # arr = oci.core.models.Instance
                for arr in arrs:
                    if (arr.lifecycle_state == oci.core.models.Instance.LIFECYCLE_STATE_TERMINATED or
                            arr.lifecycle_state == oci.core.models.Instance.LIFECYCLE_STATE_PROVISIONING or
                            arr.lifecycle_state == oci.core.models.Instance.LIFECYCLE_STATE_TERMINATING):
                        continue

                    # load data
                    val = {'id': str(arr.id), 'display_name': str(arr.display_name), 'shape': str(arr.shape),
                           'lifecycle_state': str(arr.lifecycle_state),
                           'availability_domain': str(arr.availability_domain), 'fault_domain': str(arr.fault_domain),
                           'time_created': str(arr.time_created),
                           'time_maintenance_reboot_due': str(arr.time_maintenance_reboot_due),
                           'image_id': str(arr.image_id), 'compartment_name': str(compartment['name']),
                           'compartment_id': str(compartment['id']), 'region_name': str(self.config['region']),
                           'console_id': "", 'console': "", 'console_connection_string': "",
                           'defined_tags': [] if arr.defined_tags is None else arr.defined_tags,
                           'freeform_tags': [] if arr.freeform_tags is None else arr.freeform_tags,
                           'shape_ocpu': 0,
                           'shape_memory_gb': 0,
                           'shape_storage_tb': 0,
                           'shape_gpu_description': "",
                           'shape_gpus': 0,
                           'shape_local_disk_description': "",
                           'shape_local_disks': 0,
                           'shape_max_vnic_attachments': 0,
                           'shape_networking_bandwidth_in_gbps': 0,
                           'shape_processor_description': "",
                           'console_vnc_connection_string': "",
                           'image': "Not Found",
                           'image_os': "Oracle Linux",
                           'agent_is_management_disabled ': "",
                           'agent_is_monitoring_disabled': "",
                           'metadata': arr.metadata,
                           'extended_metadata': arr.extended_metadata
                           }

                    # agent_config
                    if arr.agent_config:
                        val["agent_is_management_disabled"] = str(arr.agent_config.is_management_disabled)
                        val["agent_is_monitoring_disabled"] = str(arr.agent_config.is_monitoring_disabled)

                    # check if vm has shape config
                    if arr.shape_config:
                        sc = arr.shape_config
                        val['shape_storage_tb'] = sc.local_disks_total_size_in_gbs / 1000 if sc.local_disks_total_size_in_gbs else 0
                        val['shape_ocpu'] = sc.ocpus
                        val['shape_memory_gb'] = sc.memory_in_gbs
                        val['shape_gpu_description'] = str(sc.gpu_description)
                        val['shape_gpus'] = str(sc.gpus)
                        val['shape_local_disk_description'] = str(sc.local_disk_description)
                        val['shape_local_disks'] = str(sc.local_disks)
                        val['shape_max_vnic_attachments'] = sc.max_vnic_attachments
                        val['shape_networking_bandwidth_in_gbps'] = sc.networking_bandwidth_in_gbps
                        val['shape_processor_description'] = str(sc.processor_description)

                    # if PaaS compartment assign Paas Image
                    if self.__if_managed_paas_compartment(compartment['name']):
                        val['image_os'] = "PaaS Image"
                        val['image'] = "PaaS Image"

                    # mark reboot migration flag
                    if arr.time_maintenance_reboot_due is not None:
                        self.reboot_migration_counter += 1

                    # get image info
                    try:
                        # image = oci.core.models.Image
                        image = compute.get_image(arr.image_id).data
                        if image:
                            val['image'] = str(image.display_name)
                            val['image_os'] = str(image.operating_system)
                    except Exception:
                        pass

                    # check console connections enabled
                    for icc in consoles:
                        if str(icc.instance_id) == str(arr.id) and str(icc.lifecycle_state) == oci.core.models.InstanceConsoleConnection.LIFECYCLE_STATE_ACTIVE:
                            val['console_id'] = str(icc.id)
                            val['console'] = "Console Connection Active"
                            val['console_connection_string'] = icc.connection_string
                            val['console_vnc_connection_string'] = icc.vnc_connection_string

                    # add data to array

                    data.append(val)
                    cnt += 1

            self.__load_print_cnt(cnt, start_time)
            return data

        except oci.exceptions.RequestException as e:

            if self.__check_request_error(e):
                return data

            raise
        except Exception as e:
            self.__print_error("__load_core_compute_instances", e)
            return data

    ##########################################################################
    # data compute read images
    ##########################################################################
    def __load_core_compute_images(self, compute, compartments):

        data = []
        cnt = 0
        start_time = time.time()

        try:

            self.__load_print_status("Images")

            # loop on all compartments
            for compartment in compartments:

                images = []
                try:
                    images = oci.pagination.list_call_get_all_results(
                        compute.list_images,
                        compartment['id'],
                        sort_by="DISPLAYNAME",
                        lifecycle_state=oci.core.models.Image.LIFECYCLE_STATE_AVAILABLE,
                        retry_strategy=oci.retry.DEFAULT_RETRY_STRATEGY
                    ).data

                except oci.exceptions.ServiceError as e:
                    if self.__check_service_error(e.code):
                        self.__load_print_auth_warning()
                        continue
                    raise

                # filter the array to only customer images
                arrs = [i for i in images if i.compartment_id is not None]
                print(".", end="")

                # loop on array
                # arr = oci.core.models.Image.
                for arr in arrs:
                    val = {'id': str(arr.id), 'display_name': str(arr.display_name),
                           'base_image_id': str(arr.base_image_id),
                           'time_created': str(arr.time_created),
                           'operating_system': str(arr.operating_system),
                           'size_in_gbs': str(round(arr.size_in_mbs / 1024)),
                           'compartment_name': str(compartment['name']), 'compartment_id': str(compartment['id']),
                           'region_name': str(self.config['region']),
                           'defined_tags': [] if arr.defined_tags is None else arr.defined_tags,
                           'freeform_tags': [] if arr.freeform_tags is None else arr.freeform_tags,
                           'base_image_name': (str(compute.get_image(arr.base_image_id, retry_strategy=oci.retry.DEFAULT_RETRY_STRATEGY).data.display_name) if arr.base_image_id else "")
                           }
                    data.append(val)
                    cnt += 1

            self.__load_print_cnt(cnt, start_time)
            return data

        except oci.exceptions.RequestException as e:

            if self.__check_request_error(e):
                return data

            raise
        except Exception as e:
            self.__print_error("__load_core_compute_images", e)
            return data

    ##########################################################################
    # data compute read boot volume attached
    ##########################################################################
    def __load_core_compute_boot_vol_attach(self, compute, compartments):

        data = []
        cnt = 0
        start_time = time.time()

        try:

            self.__load_print_status("Boot Volumes Attached")

            # loop on all compartments
            for compartment in compartments:
                print(".", end="")

                # loop on all ads
                ads = self.get_availability_domains(self.config['region'])

                for ad in ads:

                    arrs = []
                    try:
                        arrs = oci.pagination.list_call_get_all_results(
                            compute.list_boot_volume_attachments,
                            ad['name'],
                            compartment['id'],
                            retry_strategy=oci.retry.DEFAULT_RETRY_STRATEGY
                        ).data

                    except oci.exceptions.ServiceError as e:
                        if self.__check_service_error(e.code):
                            self.__load_print_auth_warning()
                            continue
                        raise

                    # loop on array
                    # arr = oci.core.models.BootVolumeAttachment
                    for arr in arrs:
                        val = {'id': str(arr.id), 'display_name': str(arr.display_name),
                               'boot_volume_id': str(arr.boot_volume_id), 'instance_id': str(arr.instance_id),
                               'lifecycle_state': str(arr.lifecycle_state), 'time_created': str(arr.time_created),
                               'compartment_name': str(compartment['name']), 'compartment_id': str(compartment['id']),
                               'region_name': str(self.config['region'])}
                        data.append(val)
                        cnt += 1

            self.__load_print_cnt(cnt, start_time)
            return data

        except oci.exceptions.RequestException as e:

            if self.__check_request_error(e):
                return data

            raise
        except Exception as e:
            self.__print_error("__load_core_compute_boot_vol_attach", e)
            return data

    ##########################################################################
    # data compute read volume attached
    ##########################################################################
    def __load_core_compute_vol_attach(self, compute, compartments):

        data = []
        cnt = 0
        start_time = time.time()

        try:

            self.__load_print_status("Volumes Attached")

            # loop on all compartments
            for compartment in compartments:
                arrs = []
                try:
                    arrs = oci.pagination.list_call_get_all_results(
                        compute.list_volume_attachments,
                        compartment['id'],
                        retry_strategy=oci.retry.DEFAULT_RETRY_STRATEGY
                    ).data

                except oci.exceptions.ServiceError as e:
                    if self.__check_service_error(e.code):
                        self.__load_print_auth_warning()
                        continue
                    raise

                print(".", end="")

                # loop on array
                # arr = oci.core.models.VolumeAttachment
                for arr in arrs:
                    val = {'id': str(arr.id), 'display_name': str(arr.display_name), 'volume_id': str(arr.volume_id),
                           'instance_id': str(arr.instance_id), 'lifecycle_state': str(arr.lifecycle_state),
                           'time_created': str(arr.time_created), 'attachment_type': str(arr.attachment_type),
                           'compartment_name': str(compartment['name']), 'compartment_id': str(compartment['id']),
                           'region_name': str(self.config['region'])}
                    data.append(val)
                    cnt += 1

            self.__load_print_cnt(cnt, start_time)
            return data

        except oci.exceptions.RequestException as e:

            if self.__check_request_error(e):
                return data

            raise
        except Exception as e:
            self.__print_error("__load_core_compute_vol_attach", e)
            return data

    ##########################################################################
    # load Core Network Vnic
    ##########################################################################

    def __load_core_compute_vnic(self, virtual_network, vnic_id):
        data = {}
        try:
            if vnic_id is None:
                return {}

            # get the vnic
            vnic = virtual_network.get_vnic(vnic_id).data

            # add attributes to data
            data['private_ip'] = str(vnic.private_ip)
            data['display_name'] = (str(vnic.private_ip) + " (Prv)")
            data['public_ip'] = ""
            data['skip_source_dest_check'] = vnic.skip_source_dest_check
            data['is_primary'] = vnic.is_primary
            data['subnet'] = ""
            data['hostname_label'] = str(vnic.hostname_label)
            data['internal_fqdn'] = ""
            data['mac_address'] = str(vnic.mac_address)
            data['time_created'] = str(vnic.time_created)
            data['subnet_id'] = ""
            data['nsg_ids'] = [x for x in vnic.nsg_ids]
            data['nsg_names'] = self.__load_core_network_get_nsg_names(vnic.nsg_ids)
            data['vcn'] = ""

            # search the subnet
            subnet_display = ""
            subnet = self.search_unique_item(self.C_NETWORK, self.C_NETWORK_SUBNET, 'id', str(vnic.subnet_id))
            if subnet:
                data['subnet'] = subnet['name'] + " " + subnet['cidr_block']
                data['vcn'] = subnet['vcn_name'] + " " + subnet['vcn_cidr']
                data['subnet_id'] = subnet['id']
                subnet_display = ", Subnet (" + data['subnet'] + "), VCN (" + data['vcn'] + ")"
                data['internal_fqdn'] = str(vnic.hostname_label) + '.' + subnet['dns']

            # check vnic information
            if vnic.public_ip is not None:
                data['display_name'] += ", " + str(vnic.public_ip) + " (Pub)"
                data['public_ip'] = str(vnic.public_ip)

            # if source dest
            if vnic.skip_source_dest_check:
                data['display_name'] += " - Skip=Y"

            # if primary
            if vnic.is_primary:
                data['display_name'] += " - Primary "

            # subnet
            data['dbdesc'] = data['display_name']
            data['display_name'] += subnet_display

            # get all private_ip_addresses for vnic
            data['ip_addresses'] = []
            private_ip_addresses = virtual_network.list_private_ips(vnic_id=vnic_id).data
            for pip in private_ip_addresses:
                data['ip_addresses'].append({'ip_address': str(pip.ip_address), 'id': str(pip.id), 'type': "Private"})

                # get public ip assigned to the private ip
                try:
                    privdetails = oci.core.models.GetPublicIpByPrivateIpIdDetails()
                    privdetails.private_ip_id = pip.id
                    pub_ip = virtual_network.get_public_ip_by_private_ip_id(privdetails)
                    if pub_ip.status == 200:
                        data['ip_addresses'].append({'ip_address': str(pub_ip.data.ip_address), 'id': str(pub_ip.data.id), 'type': "Public"})
                except Exception:
                    pass

            return data

        except oci.exceptions.RequestException as e:

            if self.__check_request_error(e):
                return data

            raise
        except oci.exceptions.ServiceError as e:
            if self.__check_service_error(e.code):
                return data
            raise
        except Exception as e:
            self.__print_error("__load_core_compute_vnic", e)

    ##########################################################################
    # data compute read volume attached
    ##########################################################################
    def __load_core_compute_vnic_attach(self, compute, virtual_network, compartments):

        data = []
        cnt = 0
        start_time = time.time()

        try:

            self.__load_print_status("Vnics Attached")

            # loop on all compartments
            for compartment in compartments:

                arrs = []
                try:
                    arrs = oci.pagination.list_call_get_all_results(
                        compute.list_vnic_attachments,
                        compartment['id'],
                        retry_strategy=oci.retry.DEFAULT_RETRY_STRATEGY
                    ).data
                except oci.exceptions.ServiceError as e:
                    if self.__check_service_error(e.code):
                        self.__load_print_auth_warning()
                        continue
                    raise

                print(".", end="")

                # loop on array
                # arr = oci.core.models.VnicAttachment
                for arr in arrs:
                    if str(arr.lifecycle_state) != oci.core.models.VnicAttachment.LIFECYCLE_STATE_ATTACHED:
                        continue

                    val = {'id': str(arr.id), 'display_name': str(arr.display_name), 'vnic_id': str(arr.vnic_id),
                           'vnic_details': self.__load_core_compute_vnic(virtual_network, arr.vnic_id),
                           'instance_id': str(arr.instance_id), 'time_created': str(arr.time_created),
                           'nic_index': str(arr.nic_index), 'subnet_id': str(arr.subnet_id),
                           'compartment_name': str(compartment['name']), 'compartment_id': str(compartment['id']),
                           'region_name': str(self.config['region'])}
                    data.append(val)
                    cnt += 1

            self.__load_print_cnt(cnt, start_time)
            return data

        except oci.exceptions.RequestException as e:

            if self.__check_request_error(e):
                return data

            raise
        except Exception as e:
            self.__print_error("__load_core_compute_vnic_attach", e)
            return data

    ##########################################################################
    # get volume backup policy
    ##########################################################################
    def __load_core_block_volume_backup_policy(self, block_storage, volume_id):

        try:
            backupstr = ""
            backup_policy_assignments = block_storage.get_volume_backup_policy_asset_assignment(volume_id).data

            if backup_policy_assignments:
                for backup_policy_assignment in backup_policy_assignments:
                    bp = block_storage.get_volume_backup_policy(backup_policy_assignment.policy_id).data
                    backupstr += bp.display_name + " "
            return backupstr

        except oci.exceptions.RequestException as e:
            if self.__check_request_error(e):
                return ""
            raise
        except oci.exceptions.ServiceError as e:
            if self.__check_service_error(e.code) or e.code == 'InvalidParameter' or e.code == 'TooManyRequests':
                return ""
            raise
        except Exception as e:
            self.__print_error("__load_core_block_volume_backup_policy", e)

    ##########################################################################
    # data compute read boot volume
    ##########################################################################
    def __load_core_block_boot(self, block_storage, compartments):

        data = []
        cnt = 0
        start_time = time.time()

        try:

            self.__load_print_status("Boot Volumes")

            # reference to volgroups
            volgroups = self.data[self.C_BLOCK][self.C_BLOCK_VOLGRP]

            # loop on all compartments
            for compartment in compartments:
                print(".", end="")

                # loop on all ads
                availability_domains = self.get_availability_domains(self.config['region'])
                for ad in availability_domains:

                    boot_volumes = []
                    try:
                        boot_volumes = oci.pagination.list_call_get_all_results(
                            block_storage.list_boot_volumes,
                            ad['name'],
                            compartment['id'],
                            retry_strategy=oci.retry.DEFAULT_RETRY_STRATEGY
                        ).data

                    except oci.exceptions.ServiceError as e:
                        if self.__check_service_error(e.code):
                            self.__load_print_auth_warning()
                            continue
                        raise

                    # loop on array
                    # arr = oci.core.models.BootVolume.
                    for arr in boot_volumes:

                        val = {'id': str(arr.id), 'display_name': str(arr.display_name),
                               'size_in_gbs': str(arr.size_in_gbs),
                               'time_created': str(arr.time_created),
                               'kms_key_id': str(arr.kms_key_id),
                               'vpus_per_gb': str(arr.vpus_per_gb),
                               'is_hydrated': str(arr.is_hydrated),
                               'volume_group_id': str(arr.volume_group_id),
                               'volume_group_name': "", 'availability_domain': str(arr.availability_domain),
                               'compartment_name': str(compartment['name']), 'compartment_id': str(compartment['id']),
                               'defined_tags': [] if arr.defined_tags is None else arr.defined_tags,
                               'freeform_tags': [] if arr.freeform_tags is None else arr.freeform_tags,
                               'region_name': str(self.config['region']),
                               'backup_policy': self.__load_core_block_volume_backup_policy(block_storage, str(arr.id)),
                               'lifecycle_state': str(arr.lifecycle_state)}

                        # find vol group name
                        for volgrp in volgroups:
                            if str(arr.volume_group_id) == volgrp['id']:
                                val['volume_group_name'] = volgrp['display_name']

                        # check boot volume backup policy
                        data.append(val)
                        cnt += 1

            self.__load_print_cnt(cnt, start_time)
            return data

        except oci.exceptions.RequestException as e:

            if self.__check_request_error(e):
                return data

            raise
        except Exception as e:
            self.__print_error("__load_core_block_boot", e)
            return data

    ##########################################################################
    # data compute read block volume
    ##########################################################################
    def __load_core_block_volume(self, block_storage, compartments):

        data = []
        cnt = 0
        start_time = time.time()

        try:

            self.__load_print_status("Block Volumes")

            # reference to volgroups
            volgroups = self.data[self.C_BLOCK][self.C_BLOCK_VOLGRP]

            # loop on all compartments
            for compartment in compartments:

                arrs = []
                try:
                    arrs = oci.pagination.list_call_get_all_results(
                        block_storage.list_volumes, compartment['id'],
                        sort_by="DISPLAYNAME",
                        retry_strategy=oci.retry.DEFAULT_RETRY_STRATEGY
                    ).data

                except oci.exceptions.ServiceError as e:
                    if self.__check_service_error(e.code):
                        self.__load_print_auth_warning()
                        continue
                    raise

                print(".", end="")

                # loop on array
                # arr = oci.core.models.Volume.
                for arr in arrs:

                    val = {'id': str(arr.id), 'display_name': str(arr.display_name),
                           'size_in_gbs': str(arr.size_in_gbs),
                           'time_created': str(arr.time_created),
                           'kms_key_id': str(arr.kms_key_id),
                           'volume_group_id': str(arr.volume_group_id),
                           'volume_group_name': "", 'availability_domain': str(arr.availability_domain),
                           'compartment_name': str(compartment['name']),
                           'compartment_id': str(compartment['id']),
                           'vpus_per_gb': str(arr.vpus_per_gb),
                           'is_hydrated': str(arr.is_hydrated),
                           'defined_tags': [] if arr.defined_tags is None else arr.defined_tags,
                           'freeform_tags': [] if arr.freeform_tags is None else arr.freeform_tags,
                           'region_name': str(self.config['region']),
                           'backup_policy': self.__load_core_block_volume_backup_policy(block_storage, str(arr.id)),
                           'lifecycle_state': str(arr.lifecycle_state)}

                    # find vol group name
                    for volgrp in volgroups:
                        if str(arr.volume_group_id) == volgrp['id']:
                            val['volume_group_name'] = volgrp['display_name']

                    # check boot volume backup policy
                    data.append(val)
                    cnt += 1

            self.__load_print_cnt(cnt, start_time)
            return data

        except oci.exceptions.RequestException as e:

            if self.__check_request_error(e):
                return data

            raise
        except Exception as e:
            self.__print_error("__load_core_block_volume", e)
            return data

    ##########################################################################
    # data compute read block volume group
    ##########################################################################
    def __load_core_block_volume_group(self, block_storage, compartments):

        data = []
        cnt = 0
        start_time = time.time()

        try:

            self.__load_print_status("Block Volume Groups")

            # loop on all compartments
            for compartment in compartments:

                if self.__if_managed_paas_compartment(compartment['name']):
                    print(".", end="")
                    continue

                # retrieve the data from oci
                arrs = []
                try:
                    arrs = oci.pagination.list_call_get_all_results(
                        block_storage.list_volume_groups,
                        compartment['id'],
                        sort_by="DISPLAYNAME",
                        lifecycle_state=oci.core.models.VolumeGroup.LIFECYCLE_STATE_AVAILABLE,
                        retry_strategy=oci.retry.DEFAULT_RETRY_STRATEGY
                    ).data

                except oci.exceptions.ServiceError as e:
                    if self.__check_service_error(e.code):
                        print(".", end="")
                        # don't cound it as error, it is showing error on old tenancies
                        # self.__load_print_auth_warning()
                        continue
                    raise

                print(".", end="")

                # loop on array
                # arr = oci.core.models.VolumeGroup.
                for arr in arrs:
                    val = {'id': str(arr.id), 'display_name': str(arr.display_name),
                           'size_in_gbs': str(arr.size_in_gbs), 'time_created': str(arr.time_created),
                           'volume_ids': [str(a) for a in arr.volume_ids], 'compartment_name': str(compartment['name']),
                           'defined_tags': [] if arr.defined_tags is None else arr.defined_tags,
                           'freeform_tags': [] if arr.freeform_tags is None else arr.freeform_tags,
                           'compartment_id': str(compartment['id']), 'region_name': str(self.config['region'])}

                    # check boot volume backup policy
                    data.append(val)
                    cnt += 1

            self.__load_print_cnt(cnt, start_time)
            return data

        except oci.exceptions.RequestException as e:

            if self.__check_request_error(e):
                return data

            raise
        except Exception as e:
            self.__print_error("__load_core_block_volume_group", e)
            return data

    ##########################################################################
    # __load_database_main
    ##########################################################################
    #
    # OCI Classes used:
    #
    # class oci.database.DatabaseClient(config, **kwargs)
    # class oci.core.VirtualNetworkClient(config, **kwargs)
    ##########################################################################
    def __load_database_main(self):

        try:
            print("Database...")

            # LoadBalancerClient
            database_client = oci.database.DatabaseClient(self.config, signer=self.signer, timeout=30)
            if self.flags.proxy:
                database_client.base_client.session.proxies = {'https': self.flags.proxy}

            virtual_network = oci.core.VirtualNetworkClient(self.config, signer=self.signer, timeout=15)
            if self.flags.proxy:
                virtual_network.base_client.session.proxies = {'https': self.flags.proxy}

            # reference to compartments
            compartments = self.get_compartment()

            # add the key if not exists
            self.__initialize_data_key(self.C_DATABASE, self.C_DATABASE_DBSYSTEMS)
            self.__initialize_data_key(self.C_DATABASE, self.C_DATABASE_EXADATA)
            self.__initialize_data_key(self.C_DATABASE, self.C_DATABASE_ADB_DATABASE)
            self.__initialize_data_key(self.C_DATABASE, self.C_DATABASE_ADB_D_INFRA)
            self.__initialize_data_key(self.C_DATABASE, self.C_DATABASE_SOFTWARE_IMAGES)

            # reference to orm
            db = self.data[self.C_DATABASE]

            # append the data
            db[self.C_DATABASE_EXADATA] += self.__load_database_exadata_infrastructure(database_client, virtual_network, compartments)
            db[self.C_DATABASE_DBSYSTEMS] += self.__load_database_dbsystems(database_client, virtual_network, compartments)
            db[self.C_DATABASE_ADB_D_INFRA] += self.__load_database_adb_d_infrastructure(database_client, compartments)
            db[self.C_DATABASE_ADB_DATABASE] += self.__load_database_adb_database(database_client, compartments)
            db[self.C_DATABASE_SOFTWARE_IMAGES] += self.__load_database_software_images(database_client, compartments)

            print("")

        except oci.exceptions.RequestException:
            raise
        except oci.exceptions.ServiceError:
            raise
        except Exception as e:
            self.__print_error("__load_database_main", e)

    ##########################################################################
    # __load_database_maintatance
    ##########################################################################
    def __load_database_maintatance(self, database_client, maintenance_run_id, db_system_name):
        try:
            if not maintenance_run_id:
                return {}

            # oci.database.models.MaintenanceRun
            mt = database_client.get_maintenance_run(maintenance_run_id).data
            val = {'id': str(mt.id),
                   'display_name': str(mt.display_name),
                   'description': str(mt.description),
                   'lifecycle_state': str(mt.lifecycle_state),
                   'time_scheduled': str(mt.time_scheduled),
                   'time_started': str(mt.time_started),
                   'time_ended': str(mt.time_ended),
                   'target_resource_type': str(mt.target_resource_type),
                   'target_resource_id': str(mt.target_resource_id),
                   'maintenance_type': str(mt.maintenance_type),
                   'maintenance_subtype': str(mt.maintenance_subtype),
                   'maintenance_display': str(mt.display_name) + " ( " + str(mt.maintenance_type) + ", " + str(mt.maintenance_subtype) + ", " + str(mt.lifecycle_state) + " ), Scheduled: " + str(mt.time_scheduled)[0:16] + ((", Execution: " + str(mt.time_started)[0:16] + " - " + str(mt.time_ended)[0:16]) if str(mt.time_started) != 'None' else ""),
                   'maintenance_alert': ""
                   }

            # If maintenane is less than 14 days
            if mt.time_scheduled:
                delta = mt.time_scheduled.date() - datetime.date.today()
                if delta.days <= 14 and delta.days >= 0 and not mt.time_started:
                    val['maintenance_alert'] = "DBSystem Maintenance is in " + str(delta.days).ljust(2, ' ') + " days, on " + str(mt.time_scheduled)[0:16] + " for " + db_system_name
                    self.dbsystem_maintenance.append(val['maintenance_alert'])
            return val

        except oci.exceptions.ServiceError:
            print("m", end="")
            return ""
        except oci.exceptions.RequestException:
            print("m", end="")
            return ""
        except Exception as e:
            self.__print_error("__load_database_maintatance", e)

    ##########################################################################
    # __load_database_maintatance_windows
    ##########################################################################

    def __load_database_maintatance_windows(self, maintenance_window):
        try:
            if not maintenance_window:
                return {}

            mw = maintenance_window
            value = {
                'preference': str(mw.preference),
                'months': ", ".join([x.name for x in mw.months]) if mw.months else "",
                'weeks_of_month': ", ".join([str(x) for x in mw.weeks_of_month]) if mw.weeks_of_month else "",
                'hours_of_day': ", ".join([str(x) for x in mw.hours_of_day]) if mw.hours_of_day else "",
                'days_of_week': ", ".join([str(x.name) for x in mw.days_of_week]) if mw.days_of_week else "",
                'lead_time_in_weeks': str(mw.lead_time_in_weeks) if mw.lead_time_in_weeks else "",
            }
            value['display'] = str(mw.preference) if str(mw.preference) == "NO_PREFERENCE" else (str(mw.preference) + ": Months: " + value['months'] + ", Weeks: " + value['weeks_of_month'] + ", DOW: " + value['days_of_week'] + ", Hours: " + value['hours_of_day'] + ", Lead Weeks: " + value['lead_time_in_weeks'])
            return value

        except Exception as e:
            self.__print_error("__load_database_maintatance_windows", e)

    ##########################################################################
    # __load_database_exadata_infrastructure
    ##########################################################################

    def __load_database_exadata_infrastructure(self, database_client, virtual_network, compartments):

        data = []
        cnt = 0
        start_time = time.time()

        try:

            self.__load_print_status("Exadata Infrastructure")

            # loop on all compartments
            for compartment in compartments:
                # skip managed paas compartment
                if self.__if_managed_paas_compartment(compartment['name']):
                    print(".", end="")
                    continue

                print(".", end="")

                # list db system
                list_exa = []
                try:
                    list_exa = oci.pagination.list_call_get_all_results(
                        database_client.list_cloud_exadata_infrastructures,
                        compartment['id'],
                        sort_by="DISPLAYNAME",
                        retry_strategy=oci.retry.DEFAULT_RETRY_STRATEGY
                    ).data

                except oci.exceptions.ServiceError as e:
                    if self.__check_service_error(e.code):
                        self.__load_print_auth_warning("a", False)
                        continue
                    else:
                        raise

                # loop on the Exadata infrastructure
                # dbs = oci.database.models.CloudExadataInfrastructureSummary
                for dbs in list_exa:
                    if (dbs.lifecycle_state == oci.database.models.CloudExadataInfrastructureSummary.LIFECYCLE_STATE_TERMINATED or
                            dbs.lifecycle_state == oci.database.models.CloudExadataInfrastructureSummary.LIFECYCLE_STATE_TERMINATING):
                        continue

                    value = {'id': str(dbs.id),
                             'display_name': str(dbs.display_name),
                             'shape': str(dbs.shape),
                             'shape_ocpu': 0,
                             'shape_memory_gb': 0,
                             'shape_storage_tb': 0,
                             'version': 'XP',
                             'lifecycle_state': str(dbs.lifecycle_state),
                             'lifecycle_details': str(dbs.lifecycle_details),
                             'availability_domain': str(dbs.availability_domain),
                             'compute_count': str(dbs.compute_count),
                             'storage_count': str(dbs.storage_count),
                             'total_storage_size_in_gbs': str(dbs.total_storage_size_in_gbs),
                             'available_storage_size_in_gbs': str(dbs.available_storage_size_in_gbs),
                             'compartment_name': str(compartment['name']),
                             'compartment_id': str(compartment['id']),
                             'time_created': str(dbs.time_created),
                             'last_maintenance_run': self.__load_database_maintatance(database_client, dbs.last_maintenance_run_id, str(dbs.display_name) + " - " + str(dbs.shape)),
                             'next_maintenance_run': self.__load_database_maintatance(database_client, dbs.next_maintenance_run_id, str(dbs.display_name) + " - " + str(dbs.shape)),
                             'maintenance_window': self.__load_database_maintatance_windows(dbs.maintenance_window),
                             'defined_tags': [] if dbs.defined_tags is None else dbs.defined_tags,
                             'freeform_tags': [] if dbs.freeform_tags is None else dbs.freeform_tags,
                             'region_name': str(self.config['region']),
                             'vm_clusters': self.__load_database_exadata_vm_clusters(database_client, virtual_network, dbs.id, compartment)
                             }

                    # get shape
                    if dbs.shape:
                        shape_sizes = self.get_shape_details(str(dbs.shape))
                        if shape_sizes:
                            value['shape_ocpu'] = shape_sizes['cpu']
                            value['shape_memory_gb'] = shape_sizes['memory']
                            value['shape_storage_tb'] = shape_sizes['storage']

                        # if x8m calculate ocpu and storage
                        if dbs.shape == "Exadata.X8M":
                            if dbs.compute_count != "2" or dbs.storage_count != "3":
                                value['shape_ocpu'] = dbs.compute_count * 50
                                value['shape_storage_tb'] = dbs.storage_count * 49.5
                                value['shape_memory_gb'] = dbs.compute_count * 720

                    # add the data
                    cnt += 1
                    data.append(value)

            self.__load_print_cnt(cnt, start_time)
            return data

        except oci.exceptions.RequestException as e:
            if self.__check_request_error(e):
                return data
            raise
        except Exception as e:
            self.__print_error("__load_database_exadata_infrastructure", e)
            return data

    ##########################################################################
    # __load_database_exadata_vm_clusters
    ##########################################################################
    def __load_database_exadata_vm_clusters(self, database_client, virtual_network, exa_id, compartment):

        data = []
        try:
            vms = database_client.list_cloud_vm_clusters(
                compartment['id'],
                cloud_exadata_infrastructure_id=exa_id,
                retry_strategy=oci.retry.DEFAULT_RETRY_STRATEGY
            ).data

            # arr = oci.database.models.CloudVmClusterSummary
            for arr in vms:
                if (arr.lifecycle_state == oci.database.models.CloudVmClusterSummary.LIFECYCLE_STATE_TERMINATED or
                        arr.lifecycle_state == oci.database.models.CloudVmClusterSummary.LIFECYCLE_STATE_TERMINATING):
                    continue

                value = {
                    'id': str(arr.id),
                    'cluster_name': str(arr.cluster_name),
                    'hostname': str(arr.hostname),
                    'compartment_id': str(arr.compartment_id),
                    'availability_domain': str(arr.availability_domain),
                    'data_subnet_id': str(arr.subnet_id),
                    'data_subnet': self.get_network_subnet(str(arr.subnet_id), True),
                    'backup_subnet_id': str(arr.backup_subnet_id),
                    'backup_subnet': "" if arr.backup_subnet_id is None else self.get_network_subnet(str(arr.backup_subnet_id), True),
                    'nsg_ids': arr.nsg_ids,
                    'backup_network_nsg_ids': str(arr.backup_network_nsg_ids),
                    'last_update_history_entry_id': str(arr.last_update_history_entry_id),
                    'shape': str(arr.shape),
                    'listener_port': str(arr.listener_port),
                    'lifecycle_state': str(arr.lifecycle_state),
                    'node_count': str(arr.node_count),
                    'storage_size_in_gbs': str(arr.storage_size_in_gbs),
                    'display_name': str(arr.display_name),
                    'time_created': str(arr.time_created),
                    'lifecycle_details': str(arr.lifecycle_details),
                    'time_zone': str(arr.time_zone),
                    'domain': str(arr.domain),
                    'cpu_core_count': str(arr.cpu_core_count),
                    'data_storage_percentage': str(arr.data_storage_percentage),
                    'is_local_backup_enabled': str(arr.is_local_backup_enabled),
                    'is_sparse_diskgroup_enabled': str(arr.is_sparse_diskgroup_enabled),
                    'gi_version': str(arr.gi_version),
                    'system_version': str(arr.system_version),
                    'ssh_public_keys': str(arr.ssh_public_keys),
                    'license_model': str(arr.license_model),
                    'disk_redundancy': str(arr.disk_redundancy),
                    'scan_ip_ids': str(arr.scan_ip_ids),
                    'vip_ids': str(arr.vip_ids),
                    'scan_dns_record_id': str(arr.scan_dns_record_id),
                    'defined_tags': [] if arr.defined_tags is None else arr.defined_tags,
                    'freeform_tags': [] if arr.freeform_tags is None else arr.freeform_tags,
                    'patches': [],
                    'db_homes': self.__load_database_dbsystems_dbhomes(database_client, virtual_network, compartment, arr.id, exa=True),
                    'db_nodes': self.__load_database_dbsystems_dbnodes(database_client, virtual_network, compartment, arr.id, exa=True),
                    'region_name': str(self.config['region']),
                    'scan_ips': [],
                    'vip_ips': [],
                    'scan_dns_name': str(arr.scan_dns_name),
                    'zone_id': str(arr.zone_id)
                }

                # Skip the patches, there is an issue with the api for the vm cluster
                # value['patches'] = self.__load_database_exadata_vm_patches(database_client, arr.id),

                # get shape
                if arr.shape:
                    shape_sizes = self.get_shape_details(str(arr.shape))
                    if shape_sizes:
                        value['shape_ocpu'] = shape_sizes['cpu']
                        value['shape_memory_gb'] = shape_sizes['memory']
                        value['shape_storage_tb'] = shape_sizes['storage']

                # license model
                if arr.license_model == oci.database.models.CloudVmClusterSummary.LICENSE_MODEL_LICENSE_INCLUDED:
                    value['license_model'] = "INCL"
                elif arr.license_model == oci.database.models.CloudVmClusterSummary.LICENSE_MODEL_BRING_YOUR_OWN_LICENSE:
                    value['license_model'] = "BYOL"
                else:
                    value['license_model'] = str(arr.license_model)

                # scan IPs
                if arr.scan_ip_ids is not None:
                    scan_ips = []
                    for scan_ip in arr.scan_ip_ids:
                        scan_ips.append(self.__load_core_network_single_privateip(virtual_network, scan_ip))
                    value['scan_ips'] = scan_ips

                # VIPs
                if arr.vip_ids is not None:
                    vip_ips = []
                    for vipip in arr.vip_ids:
                        vip_ips.append(self.__load_core_network_single_privateip(virtual_network, vipip))
                    value['vip_ips'] = vip_ips

                # add to main data
                data.append(value)

            return data

        except oci.exceptions.ServiceError as e:
            if self.__check_service_error(e.code):
                self.__load_print_auth_warning()
                return data
            else:
                raise
        except oci.exceptions.RequestException as e:
            if self.__check_request_error(e):
                return data
            raise
        except Exception as e:
            self.__print_error("__load_database_exadata_vm_clusters", e)
            return data

    ##########################################################################
    # __load_database_exadata_vm_patches
    ##########################################################################
    def __load_database_exadata_vm_patches(self, database_client, vm_id):

        data = []
        try:
            dbps = oci.pagination.list_call_get_all_results(
                database_client.list_vm_cluster_patches,
                vm_id,
                retry_strategy=oci.retry.DEFAULT_RETRY_STRATEGY
            ).data

            for dbp in dbps:
                data.append({'id': dbp.id, 'description': str(dbp.description),
                             'version': str(dbp.version), 'time_released': str(dbp.time_released),
                             'last_action': str(dbp.last_action)})
            return data

        except oci.exceptions.ServiceError as e:
            if self.__check_service_error(e.code):
                return data
            else:
                raise
        except oci.exceptions.RequestException as e:
            if self.__check_request_error(e):
                return data
            raise
        except Exception as e:
            self.__print_error("__load_database_exadata_vm_patches", e)
            return data

    ##########################################################################
    # __load_database_dbsystems
    ##########################################################################

    def __load_database_dbsystems(self, database_client, virtual_network, compartments):

        data = []
        cnt = 0
        start_time = time.time()

        try:

            self.__load_print_status("DB Systems")

            # loop on all compartments
            for compartment in compartments:
                # skip managed paas compartment
                if self.__if_managed_paas_compartment(compartment['name']):
                    print(".", end="")
                    continue

                print(".", end="")

                # list db system
                list_db_systems = []
                try:
                    list_db_systems = oci.pagination.list_call_get_all_results(
                        database_client.list_db_systems,
                        compartment['id'],
                        sort_by="DISPLAYNAME",
                        retry_strategy=oci.retry.DEFAULT_RETRY_STRATEGY
                    ).data

                except oci.exceptions.ServiceError as e:
                    if self.__check_service_error(e.code):
                        self.__load_print_auth_warning()
                        continue
                    else:
                        raise

                # loop on the db systems
                # dbs = oci.database.models.DbSystemSummary
                for dbs in list_db_systems:
                    if (dbs.lifecycle_state == oci.database.models.DbSystemSummary.LIFECYCLE_STATE_TERMINATED or dbs.lifecycle_state == "MIGRATED"):
                        continue

                    value = {'id': str(dbs.id),
                             'display_name': str(dbs.display_name),
                             'shape': str(dbs.shape),
                             'shape_ocpu': 0,
                             'shape_memory_gb': 0,
                             'shape_storage_tb': 0,
                             'lifecycle_state': str(dbs.lifecycle_state),
                             'data_storage_size_in_gbs': "" if dbs.data_storage_size_in_gbs is None else str(dbs.data_storage_size_in_gbs),
                             'availability_domain': str(dbs.availability_domain),
                             'cpu_core_count': str(dbs.cpu_core_count),
                             'node_count': ("" if dbs.node_count is None else str(dbs.node_count)),
                             'version': str(dbs.version),
                             'hostname': str(dbs.hostname),
                             'domain': str(dbs.domain),
                             'data_storage_percentage': str(dbs.data_storage_percentage),
                             'data_subnet': self.get_network_subnet(str(dbs.subnet_id), True),
                             'data_subnet_id': str(dbs.subnet_id),
                             'backup_subnet': "" if dbs.backup_subnet_id is None else self.get_network_subnet(str(dbs.backup_subnet_id), True),
                             'backup_subnet_id': str(dbs.backup_subnet_id),
                             'scan_dns_record_id': "" if dbs.scan_dns_record_id is None else str(dbs.scan_dns_record_id),
                             'listener_port': str(dbs.listener_port),
                             'cluster_name': "" if dbs.cluster_name is None else str(dbs.cluster_name),
                             'database_edition': str(dbs.database_edition),
                             'compartment_name': str(compartment['name']),
                             'compartment_id': str(compartment['id']),
                             'time_created': str(dbs.time_created),
                             'storage_management': "",
                             'sparse_diskgroup': str(dbs.sparse_diskgroup),
                             'reco_storage_size_in_gb': str(dbs.reco_storage_size_in_gb),
                             'last_maintenance_run': self.__load_database_maintatance(database_client, dbs.last_maintenance_run_id, str(dbs.display_name) + " - " + str(dbs.shape)),
                             'next_maintenance_run': self.__load_database_maintatance(database_client, dbs.next_maintenance_run_id, str(dbs.display_name) + " - " + str(dbs.shape)),
                             'maintenance_window': self.__load_database_maintatance_windows(dbs.maintenance_window),
                             'region_name': str(self.config['region']),
                             'defined_tags': [] if dbs.defined_tags is None else dbs.defined_tags,
                             'freeform_tags': [] if dbs.freeform_tags is None else dbs.freeform_tags,
                             'patches': self.__load_database_dbsystems_patches(database_client, dbs.id),
                             'db_nodes': self.__load_database_dbsystems_dbnodes(database_client, virtual_network, compartment, dbs.id),
                             'db_homes': self.__load_database_dbsystems_dbhomes(database_client, virtual_network, compartment, dbs.id),
                             'scan_dns_name': "" if dbs.scan_dns_name is None else str(dbs.scan_dns_name),
                             'zone_id': str(dbs.zone_id),
                             }

                    # get shape
                    if dbs.shape:
                        shape_sizes = self.get_shape_details(str(dbs.shape))
                        if shape_sizes:
                            value['shape_ocpu'] = shape_sizes['cpu']
                            value['shape_memory_gb'] = shape_sizes['memory']
                            value['shape_storage_tb'] = shape_sizes['storage']

                    # storage_management
                    if dbs.db_system_options:
                        if dbs.db_system_options.storage_management:
                            value['storage_management'] = dbs.db_system_options.storage_management

                    # license model
                    if dbs.license_model == oci.database.models.DbSystem.LICENSE_MODEL_LICENSE_INCLUDED:
                        value['license_model'] = "INCL"
                    elif dbs.license_model == oci.database.models.DbSystem.LICENSE_MODEL_BRING_YOUR_OWN_LICENSE:
                        value['license_model'] = "BYOL"
                    else:
                        value['license_model'] = str(dbs.license_model)

                    # Edition
                    if dbs.database_edition == oci.database.models.DbSystem.DATABASE_EDITION_ENTERPRISE_EDITION:
                        value['database_edition_short'] = "EE"
                    elif dbs.database_edition == oci.database.models.DbSystem.DATABASE_EDITION_ENTERPRISE_EDITION_EXTREME_PERFORMANCE:
                        value['database_edition_short'] = "XP"
                    elif dbs.database_edition == oci.database.models.DbSystem.DATABASE_EDITION_ENTERPRISE_EDITION_HIGH_PERFORMANCE:
                        value['database_edition_short'] = "HP"
                    elif dbs.database_edition == oci.database.models.DbSystem.DATABASE_EDITION_STANDARD_EDITION:
                        value['database_edition_short'] = "SE"
                    else:
                        value['database_edition_short'] = dbs.database_edition

                    # scan IPs
                    value['scan_ips'] = []
                    if dbs.scan_ip_ids is not None:
                        scan_ips = []
                        for scan_ip in dbs.scan_ip_ids:
                            scan_ips.append(self.__load_core_network_single_privateip(virtual_network, scan_ip))
                        value['scan_ips'] = scan_ips

                    # VIPs
                    value['vip_ips'] = []
                    if dbs.vip_ids is not None:
                        vip_ips = []
                        for vipip in dbs.vip_ids:
                            vip_ips.append(self.__load_core_network_single_privateip(virtual_network, vipip))
                        value['vip_ips'] = vip_ips

                    # add the data
                    cnt += 1
                    data.append(value)

            self.__load_print_cnt(cnt, start_time)
            return data

        except oci.exceptions.RequestException as e:
            if self.__check_request_error(e):
                return data
            raise
        except Exception as e:
            self.__print_error("__load_database_dbsystems", e)
            return data

    ##########################################################################
    # __load_database_exadata_infrastructure
    ##########################################################################
    def __load_database_dbsystems_dbnodes(self, database_client, virtual_network, compartment, dbs_id, exa=False):

        data = []
        db_nodes = []
        api_call = ""
        try:
            if not exa:
                api_call = "database_client.list_db_nodes with db_system_id"
                db_nodes = database_client.list_db_nodes(
                    compartment['id'],
                    db_system_id=dbs_id,
                    retry_strategy=oci.retry.DEFAULT_RETRY_STRATEGY
                ).data
            else:
                api_call = "database_client.list_db_nodes with vm_cluster_id"
                db_nodes = database_client.list_db_nodes(
                    compartment['id'],
                    vm_cluster_id=dbs_id,
                    retry_strategy=oci.retry.DEFAULT_RETRY_STRATEGY
                ).data

            # db_node = oci.database.models.DbNodeSummary
            for db_node in db_nodes:
                data.append(
                    {'id': str(db_node.id),
                     'hostname': str(db_node.hostname),
                     'fault_domain': str(db_node.fault_domain),
                     'lifecycle_state': str(db_node.lifecycle_state),
                     'vnic_id': str(db_node.vnic_id),
                     'backup_vnic_id': str(db_node.backup_vnic_id),
                     'maintenance_type': str(db_node.maintenance_type),
                     'time_maintenance_window_start': str(db_node.time_maintenance_window_start),
                     'time_maintenance_window_end': str(db_node.time_maintenance_window_end),
                     'vnic_details': self.__load_core_compute_vnic(virtual_network, str(db_node.vnic_id)),
                     'backup_vnic_details': self.__load_core_compute_vnic(virtual_network, str(db_node.backup_vnic_id)),
                     'software_storage_size_in_gb': str(db_node.software_storage_size_in_gb)})

                # mark reboot migration flag
                if db_node.maintenance_type is not None:
                    self.reboot_migration_counter += 1

            # add to main data
            return data

        except oci.exceptions.ServiceError as e:
            if self.__check_service_error(e.code):
                self.__load_print_auth_warning()
                return data
            else:
                print("Error at API " + api_call)
                raise
        except oci.exceptions.RequestException as e:
            if self.__check_request_error(e):
                return data
            else:
                print("Error at API " + api_call)
                raise
        except Exception as e:
            self.__print_error("__load_database_dbsystems_dbnodes, API=" + api_call, e)
            return data

    ##########################################################################
    # __load_database_dbsystems_dbhomes
    ##########################################################################
    def __load_database_dbsystems_dbhomes(self, database_client, virtual_network, compartment, dbs_id, exa=False):

        data = []
        db_homes = []
        api_call = ""
        try:
            if not exa:
                api_call = "database_client.list_db_homes with db_system_id"
                db_homes = oci.pagination.list_call_get_all_results(
                    database_client.list_db_homes,
                    compartment['id'],
                    db_system_id=dbs_id,
                    retry_strategy=oci.retry.DEFAULT_RETRY_STRATEGY
                ).data
            else:
                api_call = "database_client.list_db_homes with vm_cluster_id"
                db_homes = oci.pagination.list_call_get_all_results(
                    database_client.list_db_homes,
                    compartment['id'],
                    vm_cluster_id=dbs_id,
                    retry_strategy=oci.retry.DEFAULT_RETRY_STRATEGY
                ).data

            # db_home = oci.database.models.DbHomeSummary
            for db_home in db_homes:
                data.append(
                    {'id': str(db_home.id),
                     'display_name': str(db_home.display_name),
                     'compartment_id': str(db_home.compartment_id),
                     'last_patch_history_entry_id': str(db_home.last_patch_history_entry_id),
                     'lifecycle_state': str(db_home.lifecycle_state),
                     'db_system_id': str(db_home.db_system_id),
                     'vm_cluster_id': str(db_home.vm_cluster_id),
                     'db_version': str(db_home.db_version),
                     'time_created': str(db_home.time_created),
                     'databases': self.__load_database_dbsystems_dbhomes_databases(database_client, db_home.id, compartment),
                     'patches': self.__load_database_dbsystems_home_patches(database_client, db_home.id)})

            # add to main data
            return data

        except oci.exceptions.ServiceError as e:
            if self.__check_service_error(e.code):
                self.__load_print_auth_warning("h")
                return data
            else:
                print("Error at API " + api_call)
                raise
        except oci.exceptions.RequestException as e:
            if self.__check_request_error(e):
                return data
            else:
                print("Error at API " + api_call)
                raise
        except Exception as e:
            self.__print_error("__load_database_dbsystems_dbhomess, API=" + api_call, e)
            return data

    ##########################################################################
    # __load_database_dbsystems_dbhomes_databases
    ##########################################################################

    def __load_database_dbsystems_dbhomes_databases(self, database_client, db_home_id, compartment):

        data = []
        try:
            dbs = oci.pagination.list_call_get_all_results(
                database_client.list_databases,
                compartment['id'],
                db_home_id=db_home_id,
                sort_by="DBNAME",
                retry_strategy=oci.retry.DEFAULT_RETRY_STRATEGY
            ).data

            # db = oci.database.models.DatabaseSummary
            for db in dbs:
                if db.lifecycle_state == oci.database.models.DatabaseSummary.LIFECYCLE_STATE_TERMINATED:
                    continue

                value = {'id': str(db.id),
                         'compartment_id': str(db.compartment_id),
                         'character_set': str(db.character_set),
                         'ncharacter_set': str(db.ncharacter_set),
                         'db_home_id': str(db.db_home_id),
                         'db_name': str(db.db_name),
                         'pdb_name': "" if db.pdb_name is None else str(db.pdb_name),
                         'db_workload': str(db.db_workload),
                         'db_unique_name': str(db.db_unique_name),
                         'lifecycle_details': str(db.lifecycle_details),
                         'lifecycle_state': str(db.lifecycle_state),
                         'defined_tags': [] if db.defined_tags is None else db.defined_tags,
                         'freeform_tags': [] if db.freeform_tags is None else db.freeform_tags,
                         'time_created': str(db.time_created),
                         'last_backup_timestamp': str(db.last_backup_timestamp),
                         'kms_key_id': str(db.kms_key_id),
                         'source_database_point_in_time_recovery_timestamp': str(db.source_database_point_in_time_recovery_timestamp),
                         'database_software_image_id': str(db.database_software_image_id),
                         'connection_strings_cdb': "",
                         'auto_backup_enabled': False}

                if db.db_backup_config is not None:
                    if db.db_backup_config.auto_backup_enabled:
                        value['auto_backup_enabled'] = True

                if db.connection_strings is not None:
                    if db.connection_strings.cdb_default:
                        value['connection_strings_cdb'] = db.connection_strings.cdb_default

                value['dataguard'] = self.__load_database_dbsystems_db_dg(database_client, db.id)
                data.append(value)

            # add to main data
            return data

        except oci.exceptions.ServiceError as e:
            if self.__check_service_error(e.code):
                self.__load_print_auth_warning("d")
                return data
            else:
                raise
        except oci.exceptions.RequestException as e:
            if self.__check_request_error(e):
                return data
            raise
        except Exception as e:
            self.__print_error("__load_database_dbsystems_dbhomes_databases", e)
            return data

    ##########################################################################
    # get db system patches
    ##########################################################################
    def __load_database_dbsystems_home_patches(self, database_client, dbhome_id):

        data = []
        try:
            dbps = oci.pagination.list_call_get_all_results(
                database_client.list_db_home_patches,
                dbhome_id,
                retry_strategy=oci.retry.DEFAULT_RETRY_STRATEGY
            ).data

            for dbp in dbps:
                data.append({'id': dbp.id, 'description': str(dbp.description), 'version': str(dbp.version), 'time_released': str(dbp.time_released),
                             'last_action': str(dbp.last_action)})
            return data

        except oci.exceptions.ServiceError as e:
            if self.__check_service_error(e.code):
                return data
            else:
                # Added in order to avoid internal error which happen often here
                if 'InternalError' in str(e.code):
                    print('p', end="")
                    return data
                raise
        except oci.exceptions.RequestException as e:
            if self.__check_request_error(e):
                return data
            raise
        except Exception as e:
            self.__print_error("__load_database_dbsystems_home_patches", e)
            return data

    ##########################################################################
    # get db system patches
    ##########################################################################
    def __load_database_dbsystems_patches(self, database_client, dbs_id):

        data = []
        try:
            dbps = oci.pagination.list_call_get_all_results(
                database_client.list_db_system_patches,
                dbs_id,
                retry_strategy=oci.retry.DEFAULT_RETRY_STRATEGY
            ).data

            for dbp in dbps:
                data.append({'id': dbp.id, 'description': str(dbp.description),
                             'version': str(dbp.version), 'time_released': str(dbp.time_released),
                             'last_action': str(dbp.last_action)})
            return data

        except oci.exceptions.ServiceError as e:
            if self.__check_service_error(e.code):
                return data
            else:
                raise
        except oci.exceptions.RequestException as e:
            if self.__check_request_error(e):
                return data
            raise
        except Exception as e:
            self.__print_error("__load_database_dbsystems_patches", e)
            return data

    ##########################################################################
    # get db system patches
    ##########################################################################
    def __load_database_dbsystems_db_dg(self, database_client, db_id):

        data = []
        try:
            dgs = oci.pagination.list_call_get_all_results(
                database_client.list_data_guard_associations,
                database_id=db_id,
                retry_strategy=oci.retry.DEFAULT_RETRY_STRATEGY
            ).data

            # dg = oci.database.models.DataGuardAssociationSummary
            for dg in dgs:
                if not dg.peer_database_id or dg.lifecycle_state == oci.database.models.DataGuardAssociationSummary.LIFECYCLE_STATE_TERMINATED or dg.lifecycle_state == oci.database.models.DataGuardAssociationSummary.LIFECYCLE_STATE_FAILED:
                    continue

                val = ({'id': str(dg.id),
                        'database_id': str(dg.database_id),
                        'db_name': "",
                        'role': str(dg.role),
                        'peer_role': str(dg.peer_role),
                        'lifecycle_state': str(dg.lifecycle_state),
                        'peer_database_id': str(dg.peer_database_id),
                        'peer_data_guard_association_id': str(dg.peer_data_guard_association_id),
                        'apply_rate': str(dg.apply_rate),
                        'apply_lag': str(dg.apply_lag),
                        'protection_mode': str(dg.protection_mode),
                        'transport_type': str(dg.transport_type),
                        'time_created': str(dg.time_created)})

                # get db name
                try:
                    database = database_client.get_database(dg.peer_database_id).data
                    dbsystem = database_client.get_db_system(dg.peer_db_system_id).data
                    if database and dbsystem:
                        val['db_name'] = str(dbsystem.display_name) + ":" + str(database.db_unique_name)
                except Exception:
                    # incase error use ocid
                    val['db_name'] = str(dg.peer_db_system_id)

                # add the data
                data.append(val)

            return data

        except oci.exceptions.ServiceError as e:
            if self.__check_service_error(e.code):
                self.__load_print_auth_warning()
                return data
            else:
                raise
        except oci.exceptions.RequestException as e:
            if self.__check_request_error(e):
                return data
            raise
        except Exception as e:
            self.__print_error("__load_database_dbsystems_db_dg", e)
            return data

    ##########################################################################
    # __load_database_autonomous_exadata_infrastructure
    ##########################################################################
    def __load_database_adb_d_infrastructure(self, database_client, compartments):

        data = []
        cnt = 0
        start_time = time.time()

        try:

            self.__load_print_status("Autonomous Dedicated")

            # loop on all compartments
            for compartment in compartments:
                # skip managed paas compartment
                if self.__if_managed_paas_compartment(compartment['name']):
                    print(".", end="")
                    continue

                print(".", end="")

                # list_autonomous_exadata_infrastructures
                list_exa = []
                try:
                    list_exa = oci.pagination.list_call_get_all_results(
                        database_client.list_autonomous_exadata_infrastructures,
                        compartment['id'],
                        sort_by="DISPLAYNAME",
                        retry_strategy=oci.retry.DEFAULT_RETRY_STRATEGY
                    ).data

                except oci.exceptions.ServiceError as e:
                    if self.__check_service_error(e.code):
                        self.__load_print_auth_warning("a", False)
                        continue
                    else:
                        raise

                # loop on the Exadata infrastructure
                # dbs = oci.database.models.AutonomousExadataInfrastructureSummary
                for dbs in list_exa:
                    if (dbs.lifecycle_state == oci.database.models.AutonomousExadataInfrastructureSummary.LIFECYCLE_STATE_TERMINATED or
                            dbs.lifecycle_state == oci.database.models.AutonomousExadataInfrastructureSummary.LIFECYCLE_STATE_TERMINATING):
                        continue

                    value = {'id': str(dbs.id),
                             'display_name': str(dbs.display_name),
                             'availability_domain': str(dbs.availability_domain),
                             'subnet_id': str(dbs.subnet_id),
                             'subnet_name': self.get_network_subnet(str(dbs.subnet_id), True),
                             'nsg_ids': dbs.nsg_ids,
                             'shape': str(dbs.shape),
                             'shape_ocpu': 0,
                             'shape_memory_gb': 0,
                             'shape_storage_tb': 0,
                             'hostname': str(dbs.hostname),
                             'domain': str(dbs.domain),
                             'lifecycle_state': str(dbs.lifecycle_state),
                             'lifecycle_details': str(dbs.lifecycle_details),
                             'license_model': str(dbs.license_model),
                             'time_created': str(dbs.time_created),
                             'scan_dns_name': str(dbs.scan_dns_name),
                             'zone_id': str(dbs.zone_id),
                             'maintenance_window': self.__load_database_maintatance_windows(dbs.maintenance_window),
                             'last_maintenance_run': self.__load_database_maintatance(database_client, dbs.last_maintenance_run_id, str(dbs.display_name) + " - " + str(dbs.shape)),
                             'next_maintenance_run': self.__load_database_maintatance(database_client, dbs.next_maintenance_run_id, str(dbs.display_name) + " - " + str(dbs.shape)),
                             'defined_tags': [] if dbs.defined_tags is None else dbs.defined_tags,
                             'freeform_tags': [] if dbs.freeform_tags is None else dbs.freeform_tags,
                             'compartment_name': str(compartment['name']),
                             'compartment_id': str(compartment['id']),
                             'region_name': str(self.config['region']),
                             'containers': self.__load_database_adb_d_containers(database_client, dbs.id, compartment)
                             }

                    # license model
                    if dbs.license_model == oci.database.models.AutonomousExadataInfrastructureSummary.LICENSE_MODEL_LICENSE_INCLUDED:
                        value['license_model'] = "INCL"
                    elif dbs.license_model == oci.database.models.AutonomousExadataInfrastructureSummary.LICENSE_MODEL_BRING_YOUR_OWN_LICENSE:
                        value['license_model'] = "BYOL"
                    else:
                        value['license_model'] = str(dbs.license_model)

                    # get shape
                    if dbs.shape:
                        shape_sizes = self.get_shape_details(str(dbs.shape))
                        if shape_sizes:
                            value['shape_ocpu'] = shape_sizes['cpu']
                            value['shape_memory_gb'] = shape_sizes['memory']
                            value['shape_storage_tb'] = shape_sizes['storage']

                    # add the data
                    cnt += 1
                    data.append(value)

            self.__load_print_cnt(cnt, start_time)
            return data

        except oci.exceptions.RequestException as e:
            if self.__check_request_error(e):
                return data
            raise
        except Exception as e:
            self.__print_error("__load_database_autonomous_exadata_infrastructure", e)
            return data

    ##########################################################################
    # __load_database_autonomous_exadata_infrastructure
    ##########################################################################
    def __load_database_adb_d_containers(self, database_client, exa_id, compartment):

        data = []
        try:
            vms = database_client.list_autonomous_container_databases(
                compartment['id'],
                autonomous_exadata_infrastructure_id=exa_id,
                retry_strategy=oci.retry.DEFAULT_RETRY_STRATEGY
            ).data

            # arr = oci.database.models.AutonomousContainerDatabaseSummary
            for arr in vms:
                if (arr.lifecycle_state == oci.database.models.AutonomousContainerDatabaseSummary.LIFECYCLE_STATE_TERMINATED or
                        arr.lifecycle_state == oci.database.models.AutonomousContainerDatabaseSummary.LIFECYCLE_STATE_TERMINATING):
                    continue

                value = {
                    'id': str(arr.id),
                    'display_name': str(arr.display_name),
                    'db_unique_name': str(arr.db_unique_name),
                    'service_level_agreement_type': str(arr.service_level_agreement_type),
                    'autonomous_exadata_infrastructure_id': str(arr.autonomous_exadata_infrastructure_id),
                    'autonomous_vm_cluster_id': str(arr.autonomous_vm_cluster_id),
                    'infrastructure_type': str(arr.infrastructure_type),
                    'kms_key_id': str(arr.kms_key_id),
                    'vault_id': str(arr.vault_id),
                    'lifecycle_state': str(arr.lifecycle_state),
                    'lifecycle_details': str(arr.lifecycle_details),
                    'time_created': str(arr.time_created),
                    'patch_model': str(arr.patch_model),
                    'patch_id': str(arr.patch_id),
                    'maintenance_window': self.__load_database_maintatance_windows(arr.maintenance_window),
                    'last_maintenance_run': self.__load_database_maintatance(database_client, arr.last_maintenance_run_id, str(arr.display_name)),
                    'next_maintenance_run': self.__load_database_maintatance(database_client, arr.next_maintenance_run_id, str(arr.display_name)),
                    'standby_maintenance_buffer_in_days': str(arr.standby_maintenance_buffer_in_days),
                    'defined_tags': [] if arr.defined_tags is None else arr.defined_tags,
                    'freeform_tags': [] if arr.freeform_tags is None else arr.freeform_tags,
                    'role': str(arr.role),
                    'availability_domain': str(arr.availability_domain),
                    'db_version': str(arr.db_version),
                    'key_store_id': str(arr.key_store_id),
                    'key_store_wallet_name': str(arr.key_store_wallet_name),
                    'region_name': str(self.config['region'])
                }

                # add to main data
                data.append(value)

            return data

        except oci.exceptions.ServiceError as e:
            if self.__check_service_error(e.code):
                self.__load_print_auth_warning()
                return data
            else:
                raise
        except oci.exceptions.RequestException as e:
            if self.__check_request_error(e):
                return data
            raise
        except Exception as e:
            self.__print_error("__load_database_adb_d_containers", e)
            return data

    ##########################################################################
    # __load_database_autonomouns
    ##########################################################################
    def __load_database_adb_database(self, database_client, compartments):

        data = []
        cnt = 0
        start_time = time.time()

        try:

            self.__load_print_status("Autonomous Databases")

            # loop on all compartments
            for compartment in compartments:

                # skip managed paas compartment
                if self.__if_managed_paas_compartment(compartment['name']):
                    print(".", end="")
                    continue

                print(".", end="")

                list_autos = []
                try:
                    list_autos = oci.pagination.list_call_get_all_results(
                        database_client.list_autonomous_databases,
                        compartment['id'],
                        sort_by="DISPLAYNAME",
                        retry_strategy=oci.retry.DEFAULT_RETRY_STRATEGY
                    ).data

                except oci.exceptions.ServiceError as e:
                    if self.__check_service_error(e.code):
                        self.__load_print_auth_warning()
                        continue
                    else:
                        raise

                # loop on auto
                # dbs = oci.database.models.AutonomousDatabaseSummary
                for dbs in list_autos:
                    value = {}
                    if dbs.lifecycle_state == oci.database.models.AutonomousDatabaseSummary.LIFECYCLE_STATE_TERMINATED or dbs.lifecycle_state == oci.database.models.AutonomousDatabaseSummary.LIFECYCLE_STATE_UNAVAILABLE:
                        continue

                    value = {'id': str(dbs.id),
                             'display_name': str(dbs.display_name),
                             'lifecycle_state': str(dbs.lifecycle_state),
                             'data_storage_size_in_tbs': str(dbs.data_storage_size_in_tbs),
                             'db_name': str(dbs.db_name),
                             'cpu_core_count': str(dbs.cpu_core_count),
                             'sum_count': ("0" if dbs.lifecycle_state == oci.database.models.AutonomousDatabaseSummary.LIFECYCLE_STATE_STOPPED else str(dbs.cpu_core_count)),
                             'db_version': str(dbs.db_version),
                             'service_console_url': str(dbs.service_console_url),
                             'connection_strings': str(dbs.connection_strings),
                             'time_created': str(dbs.time_created),
                             'compartment_name': str(compartment['name']),
                             'compartment_id': str(compartment['id']),
                             'defined_tags': [] if dbs.defined_tags is None else dbs.defined_tags,
                             'freeform_tags': [] if dbs.freeform_tags is None else dbs.freeform_tags,
                             'region_name': str(self.config['region']),
                             'whitelisted_ips': "" if dbs.whitelisted_ips is None else str(', '.join(x for x in dbs.whitelisted_ips)),
                             'db_workload': str(dbs.db_workload),
                             'db_type': ("ATP" if str(dbs.db_workload) == "OLTP" else "ADWC"),
                             'is_auto_scaling_enabled': dbs.is_auto_scaling_enabled,
                             'is_dedicated': dbs.is_dedicated,
                             'subnet_id': str(dbs.subnet_id),
                             'data_safe_status': str(dbs.data_safe_status),
                             'time_maintenance_begin': str(dbs.time_maintenance_begin),
                             'time_maintenance_end': str(dbs.time_maintenance_end),
                             'nsg_ids': dbs.nsg_ids,
                             'private_endpoint': str(dbs.private_endpoint),
                             'private_endpoint_label': str(dbs.private_endpoint_label),
                             'backups': [],
                             'autonomous_container_database_id': str(dbs.autonomous_container_database_id),
                             'is_data_guard_enabled': dbs.is_data_guard_enabled,
                             'is_free_tier': dbs.is_free_tier,
                             'is_preview': dbs.is_preview,
                             'infrastructure_type': str(dbs.infrastructure_type),
                             'time_deletion_of_free_autonomous_database': str(dbs.time_deletion_of_free_autonomous_database),
                             'time_reclamation_of_free_autonomous_database': str(dbs.time_reclamation_of_free_autonomous_database),
                             'system_tags': dbs.system_tags,
                             'time_of_last_switchover': str(dbs.time_of_last_switchover),
                             'time_of_last_failover': str(dbs.time_of_last_failover),
                             'failed_data_recovery_in_seconds': str(dbs.failed_data_recovery_in_seconds),
                             'available_upgrade_versions': dbs.available_upgrade_versions,
                             'standby_lag_time_in_seconds': "",
                             'standby_lifecycle_state': ""
                             }

                    # if standby object exist
                    if dbs.standby_db:
                        value['standby_lag_time_in_seconds'] = str(dbs.standby_db.lag_time_in_seconds)
                        value['standby_lifecycle_state'] = str(dbs.standby_db.lifecycle_state)

                    # license model
                    if dbs.license_model == oci.database.models.AutonomousDatabaseSummary.LICENSE_MODEL_LICENSE_INCLUDED:
                        value['license_model'] = "INCL"
                    elif dbs.license_model == oci.database.models.AutonomousDatabaseSummary.LICENSE_MODEL_BRING_YOUR_OWN_LICENSE:
                        value['license_model'] = "BYOL"
                    else:
                        value['license_model'] = str(dbs.license_model)

                    # add the data
                    cnt += 1
                    data.append(value)

            self.__load_print_cnt(cnt, start_time)
            return data

        except oci.exceptions.RequestException as e:
            if self.__check_request_error(e):
                return data
            raise
        except Exception as e:
            self.__print_error("__load_database_autonomouns", e)
            return data

    ##########################################################################
    # __load_database_software_images
    ##########################################################################
    def __load_database_software_images(self, database_client, compartments):

        data = []
        cnt = 0
        start_time = time.time()

        try:

            self.__load_print_status("Database Software Images")

            # loop on all compartments
            for compartment in compartments:

                # skip managed paas compartment
                if self.__if_managed_paas_compartment(compartment['name']):
                    print(".", end="")
                    continue

                print(".", end="")

                db_soft_images = []
                try:
                    db_soft_images = oci.pagination.list_call_get_all_results(
                        database_client.list_database_software_images,
                        compartment['id'],
                        sort_by="DISPLAYNAME",
                        retry_strategy=oci.retry.DEFAULT_RETRY_STRATEGY
                    ).data

                except oci.exceptions.ServiceError as e:
                    if self.__check_service_error(e.code):
                        self.__load_print_auth_warning()
                        continue
                    else:
                        print("e - " + str(e))
                        return data

                # loop on auto
                # array = oci.database.models.DatabaseSoftwareImageSummary
                for array in db_soft_images:
                    if array.lifecycle_state == 'TERMINATED' or array.lifecycle_state == 'FAILED':
                        continue

                    value = {'id': str(array.id),
                             'display_name': str(array.display_name),
                             'database_version': str(array.database_version),
                             'lifecycle_state': str(array.lifecycle_state),
                             'lifecycle_details': str(array.lifecycle_details) if array.lifecycle_details else "",
                             'time_created': str(array.time_created),
                             'image_type': str(array.image_type),
                             'image_shape_family': str(array.image_shape_family),
                             'patch_set': str(array.patch_set),
                             'included_patches_summary': str(array.included_patches_summary),
                             'ls_inventory': str(array.ls_inventory),
                             'is_upgrade_supported': str(array.is_upgrade_supported),
                             'database_software_image_included_patches': array.database_software_image_included_patches,
                             'database_software_image_one_off_patches': array.database_software_image_one_off_patches,
                             'compartment_name': str(compartment['name']),
                             'compartment_id': str(compartment['id']),
                             'defined_tags': [] if array.defined_tags is None else array.defined_tags,
                             'freeform_tags': [] if array.freeform_tags is None else array.freeform_tags,
                             'region_name': str(self.config['region'])
                             }

                    # add the data
                    cnt += 1
                    data.append(value)

            self.__load_print_cnt(cnt, start_time)
            return data

        except oci.exceptions.RequestException as e:
            if self.__check_request_error(e):
                return data
            raise
        except Exception as e:
            self.__print_error("__load_database_software_images", e)
            return data


###########################################################################################################
# ShowOCIData class
# it used the ShowOCIService class and generate JSON structure as output
###########################################################################################################
class ShowOCIData(object):

    ############################################
    # ShowOCIService - Service object to query
    # OCI resources and run searches
    ###########################################
    service = None
    error = 0

    # OCI Processed data
    data = []

    ############################################
    # Init
    ############################################
    def __init__(self, flags):

        # check if not instance fo ShowOCIFlags
        if not isinstance(flags, ShowOCIFlags):
            raise TypeError("flags must be Flags class")

        # initiate service object
        self.service = ShowOCIService(flags)

    ############################################
    # get service data
    ############################################
    def get_service_data(self):

        return self.service.data

    ############################################
    # call service to load data
    ############################################
    def load_service_data(self):

        return self.service.load_service_data()

    ##########################################################################
    # get_oci_main_data
    ##########################################################################
    def process_oci_data(self):

        try:

            # run identity
            identity_data = {'type': "identity", 'data': self.service.get_identity()}
            self.data.append(identity_data)

            # run on compartments
            if self.service.flags.is_loop_on_compartments:

                # pointer to Tenancy in cache
                tenancy = self.service.get_tenancy()

                # run on each subscribed region
                for region_name in tenancy['list_region_subscriptions']:

                    # if filtered by region skip if not cmd.region
                    if self.service.flags.filter_by_region and self.service.flags.filter_by_region not in region_name:
                        continue

                    # execute the region
                    value = self.__get_oci_region_data(region_name)

                    # if data returns, add to the json
                    if value:
                        region_data = ({'type': "region", 'region': region_name, 'data': value})
                        self.data.append(region_data)

            # return the json data
            return self.data

        except Exception as e:
            raise Exception("Error in process_oci_data: " + str(e))

    ##########################################################################
    # Print version
    ##########################################################################
    def get_showoci_config(self, cmdline, start_time):

        data = {
            'program': "showoci.py",
            'author': "Adi Zohar",
            'config_file': self.service.flags.config_file,
            'config_profile': self.service.flags.config_section,
            'use_instance_principals': self.service.flags.use_instance_principals,
            'use_delegation_token': self.service.flags.use_delegation_token,
            'version': self.service.flags.showoci_version,
            'override_tenant_id': self.service.flags.filter_by_tenancy_id,
            'datetime': start_time,
            'machine': self.service.flags.machine,
            'python': self.service.flags.python,
            'cmdline': cmdline,
            'oci_sdk_version': self.service.get_oci_version()
        }

        main_data = {'type': "showoci", 'data': data}

        # add oci config to main data
        self.data.append(main_data)
        return main_data

    ##########################################################################
    # get service error flag
    ##########################################################################
    def get_service_errors(self):
        return self.service.error

    ##########################################################################
    # get service warnings flag
    ##########################################################################
    def get_service_warnings(self):
        return self.service.warning

    ##########################################################################
    # get service reboot migration
    ##########################################################################
    def get_service_reboot_migration(self):

        return self.service.reboot_migration_counter

    ##########################################################################
    # get service reboot migration
    ##########################################################################
    def get_service_dbsystem_maintenance(self):

        return self.service.dbsystem_maintenance

    ##########################################################################
    # print print error
    ##########################################################################
    def __print_error(self, msg, e):
        classname = type(self).__name__

        if isinstance(e, KeyError):
            print("\nError in " + classname + ":" + msg + ": KeyError " + str(e.args))
        else:
            print("\nError in " + classname + ":" + msg + ": " + str(e))

        self.error += 1

    ##########################################################################
    # run on Region
    ##########################################################################
    def __get_oci_region_data(self, region_name):

        ret_var = []
        print("\nProcessing Region " + region_name)

        try:

            # Loop on Compartments and call services
            compartments = self.service.get_compartment()

            # Loop on all relevant compartments
            print("\nProcessing...")
            for compartment in compartments:

                #  check if to skip ManagedCompartmentForPaaS
                if compartment['name'] == "ManagedCompartmentForPaaS" and not self.service.flags.read_ManagedCompartmentForPaaS:
                    continue

                print("    Compartment " + compartment['path'] + "...")
                data = {
                    'compartment_id': compartment['id'],
                    'compartment_name': compartment['name'],
                    'compartment': compartment['name'],
                    'path': compartment['path']
                }
                has_data = False

                # run on network module
                if self.service.flags.read_network:
                    value = self.__get_core_network_main(region_name, compartment)
                    if value:
                        if len(value) > 0:
                            data['network'] = value
                            has_data = True

                # run on compute and block storage
                if self.service.flags.read_compute:
                    value = self.__get_core_compute_main(region_name, compartment)
                    if value:
                        if len(value) > 0:
                            data['compute'] = value
                            has_data = True

                # run on database
                if self.service.flags.read_database:
                    value = self.__get_database_main(region_name, compartment)
                    if value:
                        if len(value) > 0:
                            data['database'] = value
                            has_data = True

                # add the data to main Variable
                if has_data:
                    ret_var.append(data)

            print("")

            # return var
            return ret_var

        except Exception as e:
            self.__print_error("get_oci_region_data", e)

    ##########################################################################
    # Print Network VCN NAT
    ##########################################################################
    def __get_core_network_vcn_nat(self, vcn_id):
        data = []
        try:
            list_nat_gateways = self.service.search_multi_items(self.service.C_NETWORK, self.service.C_NETWORK_NAT, 'vcn_id', vcn_id)
            for arr in list_nat_gateways:
                value = {'id': arr['id'],
                         'name': arr['name'],
                         'display_name': arr['display_name'],
                         'nat_ip': arr['nat_ip'],
                         'compartment_name': arr['compartment_name'],
                         'compartment_id': arr['compartment_id'],
                         'time_created': arr['time_created'],
                         'block_traffic': arr['block_traffic'],
                         'defined_tags': arr['defined_tags'],
                         'freeform_tags': arr['freeform_tags']}

                data.append(value)
            return data

        except Exception as e:
            self.__print_error("__get_core_network_vcn_nat", e)
            return data

    ##########################################################################
    # get Network VCN igw
    ##########################################################################

    def __get_core_network_vcn_igw(self, vcn_id):
        data = []
        try:
            list_igws = self.service.search_multi_items(self.service.C_NETWORK, self.service.C_NETWORK_IGW, 'vcn_id', vcn_id)
            for arr in list_igws:
                value = {'id': arr['id'],
                         'name': arr['name'],
                         'compartment_name': arr['compartment_name'],
                         'compartment_id': arr['compartment_id'],
                         'time_created': arr['time_created']}
                data.append(value)
            return data

        except Exception as e:
            self.__print_error("__get_core_network_vcn_igw", e)
            return data

    ##########################################################################
    # get Network VCN SGW
    ##########################################################################

    def __get_core_network_vcn_sgw(self, vcn_id):
        data = []
        try:

            list_service_gateways = self.service.search_multi_items(self.service.C_NETWORK, self.service.C_NETWORK_SGW, 'vcn_id', vcn_id)
            for arr in list_service_gateways:
                value = {'id': arr['id'],
                         'name': arr['name'],
                         'services': arr['services'],
                         'compartment_name': arr['compartment_name'],
                         'compartment_id': arr['compartment_id'],
                         'route_table_id': arr['route_table_id'],
                         'route_table': "",
                         'transit': "",
                         'time_created': arr['time_created'],
                         'defined_tags': arr['defined_tags'],
                         'freeform_tags': arr['freeform_tags']}

                # check route table
                if value['route_table_id'] != "None":
                    route_table = self.__get_core_network_route(value['route_table_id'])
                    value['route_table'] = route_table
                    value['transit'] = " + Transit Route(" + route_table + ")"

                data.append(value)
            return data

        except Exception as e:
            self.__print_error("__get_core_network_vcn_sgw", e)
            return data

    ##########################################################################
    # get dRG details
    ##########################################################################

    def __get_core_network_vcn_drg_details(self, drg_attachment):
        retStr = ""
        name = ""
        route_table = ""
        try:
            drg_id = drg_attachment['drg_id']

            # get DRG name
            drg = self.service.search_unique_item(self.service.C_NETWORK, self.service.C_NETWORK_DRG, 'id', drg_id)
            if drg:
                name = drg['name']
                retStr = drg['name']

            # check if IPSEC
            list_ip_sec_connections = self.service.search_multi_items(self.service.C_NETWORK, self.service.C_NETWORK_IPS, 'drg_id', drg_id)
            if len(list_ip_sec_connections) > 0:
                retStr += " + IPSEC (" + str(len(list_ip_sec_connections)) + ")"

            # check if Virtual Circuits
            list_virtual_circuits = self.service.search_multi_items(self.service.C_NETWORK, self.service.C_NETWORK_VC, 'drg_id', drg_id)
            if len(list_virtual_circuits) > 0:
                retStr += " + Fastconnect (" + str(len(list_virtual_circuits)) + ")"

            # Check Remote Peering
            rpcs = self.service.search_multi_items(self.service.C_NETWORK, self.service.C_NETWORK_RPC, 'drg_id', drg_id)
            if len(rpcs) > 0:
                retStr += " + Remote Peering (" + str(len(rpcs)) + ")"

            # check transit routing
            if drg_attachment['route_table_id'] != "None" and drg_attachment['route_table_id'] != "":
                route_table = str(self.__get_core_network_route(drg_attachment['route_table_id']))
                retStr += " + Transit Route(" + route_table + ")"

            return retStr, name, route_table

        except Exception as e:
            self.__print_error("__get_core_network_vcn_drg_details", e)
            return retStr, name

    ##########################################################################
    # get Network VCN DRG Attached
    ##########################################################################

    def __get_core_network_vcn_drg_attached(self, vcn_id):
        data = []
        try:

            list_drg_attachments = self.service.search_multi_items(self.service.C_NETWORK, self.service.C_NETWORK_DRG_AT, 'vcn_id', vcn_id)
            for da in list_drg_attachments:
                val, display_name, route_table = self.__get_core_network_vcn_drg_details(da)
                value = {'id': da['id'],
                         'drg_id': da['drg_id'],
                         'display_name': da['display_name'],
                         'route_table_id': da['route_table_id'],
                         'route_table': route_table,
                         'drg_route_table_id': da['drg_route_table_id'],
                         'drg_route_table': self.__get_core_network_drg_route(da['drg_route_table_id']),
                         'export_drg_route_distribution_id': da['export_drg_route_distribution_id'],
                         'name': val,
                         'compartment_name': da['compartment_name'],
                         'compartment_id': da['compartment_id'],
                         'time_created': da['time_created']}
                data.append(value)
            return data

        except Exception as e:
            self.__print_error("__get_core_network_vcn_drg_attached", e)
            return data

    ##########################################################################
    # __get_core_network_vcn_local_peering
    ##########################################################################
    def __get_core_network_vcn_local_peering(self, vcn_id):
        data = []
        try:
            local_peering_gateways = self.service.search_multi_items(self.service.C_NETWORK, self.service.C_NETWORK_LPG, 'vcn_id', vcn_id)
            for lpg in local_peering_gateways:
                routestr = ""
                route_table = ""
                if lpg['route_table_id'] != "None":
                    route_table = str(self.__get_core_network_route(lpg['route_table_id']))
                    routestr = " + Transit Route(" + route_table + ")"

                value = {'id': lpg['id'],
                         'name': (lpg['name'] + routestr),
                         'display_name': (lpg['display_name']),
                         'compartment_id': lpg['compartment_id'],
                         'compartment_name': lpg['compartment_name'],
                         'time_created': lpg['time_created'],
                         'route_table_id': lpg['route_table_id'],
                         'route_table_name': route_table,
                         'route_table': routestr,
                         'vcn_id': lpg['vcn_id'],
                         'peering_status': lpg['peering_status'],
                         'peer_id': lpg['peer_id'],
                         'peer_name': self.__get_core_network_local_peering(lpg['peer_id']),
                         'peer_advertised_cidr': lpg['peer_advertised_cidr'],
                         'peer_advertised_cidr_details': lpg['peer_advertised_cidr_details'],
                         'is_cross_tenancy_peering': lpg['is_cross_tenancy_peering']
                         }
                data.append(value)
            return data

        except Exception as e:
            self.__print_error("__get_core_network_vcn_local_peering", e)
            return data

    ##########################################################################
    # Print Network VCN subnets
    ##########################################################################

    def __get_core_network_vcn_subnets(self, vcn_id):
        data = []
        try:
            subnets = self.service.search_multi_items(self.service.C_NETWORK, self.service.C_NETWORK_SUBNET, 'vcn_id', vcn_id)
            if not subnets:
                return data

            for subnet in subnets:

                # get the list of security lists
                sec_lists = []
                if 'security_list_ids' in subnet:
                    for s in subnet['security_list_ids']:
                        sl = self.service.search_unique_item(self.service.C_NETWORK, self.service.C_NETWORK_SLIST, 'id', s)
                        if sl:
                            sec_lists.append(sl['name'])

                # Get the route and dhcp options
                route_name = ""
                if 'route_table_id' in subnet:
                    route_name_arr = self.service.search_unique_item(self.service.C_NETWORK, self.service.C_NETWORK_ROUTE, 'id', subnet['route_table_id'])
                    if route_name_arr:
                        route_name = route_name_arr['name']

                dhcp_options = ""
                if 'dhcp_options_id' in subnet:
                    dhcp_options_arr = self.service.search_unique_item(self.service.C_NETWORK, self.service.C_NETWORK_DHCP, 'id', subnet['dhcp_options_id'])
                    if dhcp_options_arr:
                        dhcp_options = dhcp_options_arr['name']

                val = ({
                    'id': subnet['id'],
                    'subnet': subnet['subnet'],
                    'name': subnet['name'],
                    'cidr_block': subnet['cidr_block'],
                    'availability_domain': subnet['availability_domain'],
                    'public_private': subnet['public_private'],
                    'dns': subnet['dns_label'],
                    'compartment_name': subnet['compartment_name'],
                    'compartment_id': subnet['compartment_id'],
                    'dhcp_options': dhcp_options,
                    'dhcp_options_id': subnet['dhcp_options_id'],
                    'security_list': sec_lists,
                    'security_list_ids': subnet['security_list_ids'],
                    'route': route_name,
                    'route_table_id': subnet['route_table_id'],
                    'time_created': subnet['time_created'],
                    'defined_tags': subnet['defined_tags'],
                    'freeform_tags': subnet['freeform_tags']
                })
                data.append(val)
            return data

        except Exception as e:
            self.__print_error("__get_core_network_vcn_subnets", e)
            return data
            pass

    ##########################################################################
    # __get_core_network_vcn_vlans
    ##########################################################################
    def __get_core_network_vcn_dns_resolver(self, vcn_id):
        resolvers = self.service.search_multi_items(self.service.C_NETWORK, self.service.C_NETWORK_DNS_RESOLVERS, 'vcn_id', vcn_id)
        return resolvers

    ##########################################################################
    # __get_core_network_vcn_vlans
    ##########################################################################

    def __get_core_network_vcn_vlans(self, vcn_id):
        data = []
        try:
            vlans = self.service.search_multi_items(self.service.C_NETWORK, self.service.C_NETWORK_VLAN, 'vcn_id', vcn_id)
            if not vlans:
                return data

            for vlan in vlans:

                # get the list of NSGs
                nsgs = []
                if 'nsg_ids' in vlan:
                    for nsg in vlan['nsg_ids']:
                        nsg_obj = self.service.search_unique_item(self.service.C_NETWORK, self.service.C_NETWORK_NSG, 'id', nsg)
                        if nsg_obj:
                            nsgs.append(nsg_obj['name'])

                # Get the route and dhcp options
                route_name = ""
                if 'route_table_id' in vlan:
                    route_name_arr = self.service.search_unique_item(self.service.C_NETWORK, self.service.C_NETWORK_ROUTE, 'id', vlan['route_table_id'])
                    if route_name_arr:
                        route_name = route_name_arr['name']

                val = ({
                    'id': vlan['id'],
                    'vlan': vlan['vlan'],
                    'availability_domain': vlan['availability_domain'],
                    'cidr_block': vlan['cidr_block'],
                    'vlan_tag': vlan['vlan_tag'],
                    'display_name': vlan['display_name'],
                    'time_created': vlan['time_created'],
                    'lifecycle_state': vlan['lifecycle_state'],
                    'compartment_name': vlan['compartment_name'],
                    'compartment_id': vlan['compartment_id'],
                    'nsg': nsgs,
                    'nsg_ids': vlan['nsg_ids'],
                    'route': route_name,
                    'route_table_id': vlan['route_table_id'],
                    'defined_tags': vlan['defined_tags'],
                    'freeform_tags': vlan['freeform_tags'],
                    'region_name': vlan['region_name']
                })
                data.append(val)
            return data

        except Exception as e:
            self.__print_error("__get_core_network_vcn_vlans", e)
            return data
            pass

    ##########################################################################
    # Print Network vcn security list
    ##########################################################################

    def __get_core_network_vcn_security_lists(self, vcn_id):
        data = []
        try:
            sec_lists = self.service.search_multi_items(self.service.C_NETWORK, self.service.C_NETWORK_SLIST, 'vcn_id', vcn_id)
            for sl in sec_lists:
                data.append({
                    'id': sl['id'],
                    'name': sl['name'],
                    'compartment_name': sl['compartment_name'],
                    'compartment_id': sl['compartment_id'],
                    'sec_rules': sl['sec_rules'],
                    'time_created': sl['time_created'],
                    'defined_tags': sl['defined_tags'],
                    'freeform_tags': sl['freeform_tags']
                })

            return data

        except Exception as e:
            self.__print_error("__get_core_network_vcn_security_lists", e)
            return data

    ##########################################################################
    # Print Network vcn security groups
    ##########################################################################

    def __get_core_network_vcn_security_groups(self, vcn_id):
        data = []
        try:
            nsgs = self.service.search_multi_items(self.service.C_NETWORK, self.service.C_NETWORK_NSG, 'vcn_id', vcn_id)
            for nsg in nsgs:
                value = {
                    'id': nsg['id'],
                    'name': nsg['name'],
                    'compartment_name': nsg['compartment_name'],
                    'compartment_id': nsg['compartment_id'],
                    'sec_rules': [],
                    'time_created': nsg['time_created'],
                    'defined_tags': nsg['defined_tags'],
                    'freeform_tags': nsg['freeform_tags']
                }

                if 'sec_rules' in nsg:
                    for sec_rule in nsg['sec_rules']:
                        valsec = sec_rule

                        #########################################################################
                        # if need to find NSG OCID and replace the DESC String with value
                        # source
                        #########################################################################
                        if valsec['source_type'] == "NETWORK_SECURITY_GROUP":
                            result = self.service.search_unique_item(self.service.C_NETWORK, self.service.C_NETWORK_NSG, 'id', valsec['source'])
                            if result:
                                valsec['source_name'] = result['name']
                                valsec['desc'] = valsec['desc'].replace(self.service.C_NETWORK_NSG_REPTEXT, result['name'].ljust(17))
                            else:
                                # if not found place the OCID instead of name
                                valsec['source_name'] = "Not Found"
                                valsec['desc'] = valsec['desc'].replace(self.service.C_NETWORK_NSG_REPTEXT, valsec['source'])

                        #########################################################################
                        # if need to find NSG OCID and replace the DESC String with value
                        # Destination
                        #########################################################################
                        if valsec['destination_type'] == "NETWORK_SECURITY_GROUP":
                            result = self.service.search_unique_item(self.service.C_NETWORK, self.service.C_NETWORK_NSG, 'id', valsec['destination'])
                            if result:
                                valsec['destination_name'] = result['name']
                                valsec['desc'] = valsec['desc'].replace(self.service.C_NETWORK_NSG_REPTEXT, result['name'].ljust(17))
                            else:
                                # if not found place the OCID instead of name
                                valsec['destination_name'] = "Not Found"
                                valsec['desc'] = valsec['desc'].replace(self.service.C_NETWORK_NSG_REPTEXT, valsec['destination'])

                        # add to the value sec rules array
                        value['sec_rules'].append(valsec)

                # add to data
                data.append(value)
            return data

        except Exception as e:
            self.__print_error("__get_core_network_vcn_security_lists", e)
            return data

    ###########################################################################
    # get Network vcn rouet table
    ##########################################################################
    def __get_core_network_vcn_route_rule(self, route_rule):

        line = ""
        try:
            if route_rule is None:
                return "None"

            # assign the line for return value
            if route_rule['destination']:
                line = "DST:" + route_rule['destination'].ljust(18)[0:18] + " --> "

            # check network ocid
            network_ocid = route_rule['network_entity_id']
            if network_ocid is None:
                return line + "None"

            # get the name of the component from OCID 2nd id
            network_list = network_ocid.split(".")
            network_dest = ""
            if len(network_list) > 1:
                network_dest = str(network_list[1])

            # if network_dest is empty
            if not network_dest:
                return line + "None"

            # if no ocid
            if network_ocid == "None" or network_ocid == "":
                return line + network_dest

            # if privateip - get the IP
            if network_dest == "privateip":
                network_dest = self.__get_core_network_private_ip(network_ocid)
                if network_dest == "" or network_dest is None:
                    network_dest = "privateip (not exist)"

            # if internetgateway - get the destination name
            if network_dest == "internetgateway":
                network_dest = "IGW"

            # if DRG - get the destination name
            if network_dest == "drg":
                network_dest = self.__get_core_network_drg_name(network_ocid)
                if network_dest == "":
                    network_dest = "DRG (Not Exist)"

            # if natgateway
            if network_dest == "natgateway":
                network_dest = "NATGW"

            # if servicegateway - get the service and sgw name
            if network_dest == "servicegateway":
                network_dest = "SGW"
                result = self.service.search_unique_item(self.service.C_NETWORK, self.service.C_NETWORK_SGW, 'id', network_ocid)
                if result:
                    network_dest = "SGW" + " " + result['name']

            # if localpeeringgateway - get the destination name
            if network_dest == "localpeeringgateway":
                network_dest = self.__get_core_network_local_peering(network_ocid)
                if network_dest == "":
                    network_dest = "LPG (not exist)"

            # return value
            return line + network_dest

        except Exception as e:
            self.__print_error("__get_core_network_vcn_route_rule", e)
            return line

    ########################################################################
    # Print Network vcn Route Tables
    ##########################################################################

    def __get_core_network_vcn_route_tables(self, vcn_id):
        data = []
        try:
            route_tables = self.service.search_multi_items(self.service.C_NETWORK, self.service.C_NETWORK_ROUTE, 'vcn_id', vcn_id)

            for rt in route_tables:
                route_rules = []
                for rl in rt['route_rules']:
                    route_rules.append(
                        {'network_entity_id': rl['network_entity_id'],
                         'destination': rl['destination'],
                         'cidr_block': rl['cidr_block'],
                         'destination_type': rl['destination_type'],
                         'description': rl['description'],
                         'desc': self.__get_core_network_vcn_route_rule(rl)
                         })

                # add route
                val = {'id': rt['id'],
                       'name': rt['name'],
                       'compartment_name': rt['compartment_name'],
                       'compartment_id': rt['compartment_id'],
                       'time_created': rt['time_created'],
                       'route_rules': route_rules}
                data.append(val)
            return data

        except Exception as e:
            self.__print_error("__get_core_network_vcn_route_tables", e)
            return data

    ##########################################################################
    # get DHCP options for DHCP_ID
    ##########################################################################
    def __get_core_network_vcn_dhcp_options(self, vcn_id):

        data = []
        try:
            dhcp_options = self.service.search_multi_items(self.service.C_NETWORK, self.service.C_NETWORK_DHCP, 'vcn_id', vcn_id)

            for dhcp in dhcp_options:
                data.append({
                    'id': dhcp['id'],
                    'name': dhcp['name'],
                    'compartment_name': dhcp['compartment_name'],
                    'compartment_id': dhcp['compartment_id'],
                    'time_created': dhcp['time_created'],
                    'opt': dhcp['options']
                })
            return data

        except Exception as e:
            self.__print_error("__get_core_network_vcn_dhcp_options", e)
            return data

    ##########################################################################
    # print network vcn
    # loop on other compartments for vcn properties
    ##########################################################################
    def __get_core_network_vcn(self, region_name, compartment):

        vcn_data = []
        try:
            vcns = self.service.search_multi_items(self.service.C_NETWORK, self.service.C_NETWORK_VCN, 'region_name', region_name, 'compartment_id', compartment['id'])

            for vcn in vcns:

                # get details for all components
                val = {'igw': self.__get_core_network_vcn_igw(vcn['id']),
                       'sgw': self.__get_core_network_vcn_sgw(vcn['id']),
                       'nat': self.__get_core_network_vcn_nat(vcn['id']),
                       'drg_attached': self.__get_core_network_vcn_drg_attached(vcn['id']),
                       'local_peering': self.__get_core_network_vcn_local_peering(vcn['id']),
                       'subnets': self.__get_core_network_vcn_subnets(vcn['id']),
                       'vlans': self.__get_core_network_vcn_vlans(vcn['id']),
                       'dns_resolvers': self.__get_core_network_vcn_dns_resolver(vcn['id']),
                       'security_lists': self.__get_core_network_vcn_security_lists(vcn['id']),
                       'security_groups': self.__get_core_network_vcn_security_groups(vcn['id']),
                       'route_tables': self.__get_core_network_vcn_route_tables(vcn['id']),
                       'dhcp_options': self.__get_core_network_vcn_dhcp_options(vcn['id'])}

                # assign the data to the vcn
                main_data = {
                    'id': vcn['id'],
                    'name': vcn['name'],
                    'display_name': vcn['display_name'],
                    'cidr_block': vcn['cidr_block'],
                    'cidr_blocks': vcn['cidr_blocks'],
                    'compartment_name': str(compartment['name']),
                    'compartment_id': str(compartment['id']),
                    'drg_route_table_id': "",
                    'drg_route_name': "",
                    'route_table_id': "",
                    'route_table': "",
                    'data': val
                }

                if val['drg_attached']:
                    da = val['drg_attached'][0]
                    main_data['drg_route_table_id'] = da['drg_route_table_id']
                    main_data['drg_route_name'] = da['drg_route_table']
                    main_data['route_table_id'] = da['route_table_id']
                    main_data['route_table'] = da['route_table']

                vcn_data.append(main_data)
            return vcn_data

        except BaseException as e:
            self.__print_error("__get_core_network_vcn", e)
            return vcn_data

    ##########################################################################
    # print network cpe
    ##########################################################################
    def __get_core_network_cpe(self, region_name, compartment):
        data = []
        try:
            cpes = self.service.search_multi_items(self.service.C_NETWORK, self.service.C_NETWORK_CPE, 'region_name', region_name, 'compartment_id', compartment['id'])
            return cpes

        except Exception as e:
            self.__print_error("__get_core_network_cpe", e)
            return data

    ##########################################################################
    # print network drg
    ##########################################################################
    def __get_core_network_drg(self, region_name, compartment):

        data = []
        try:
            drgs = self.service.search_multi_items(self.service.C_NETWORK, self.service.C_NETWORK_DRG, 'region_name', region_name, 'compartment_id', compartment['id'])
            for drg in drgs:
                drg_id = drg['id']
                val = {
                    'id': drg['id'],
                    'name': drg['name'],
                    'time_created': drg['time_created'],
                    'redundancy': drg['redundancy'],
                    'compartment_name': drg['compartment_name'],
                    'compartment_id': drg['compartment_id'],
                    'defined_tags': drg['defined_tags'],
                    'freeform_tags': drg['freeform_tags'],
                    'region_name': drg['region_name'],
                    'drg_route_tables': drg['drg_route_tables'],
                    'ip_sec_connections': self.service.search_multi_items(self.service.C_NETWORK, self.service.C_NETWORK_IPS, 'drg_id', drg_id),
                    'virtual_circuits': self.service.search_multi_items(self.service.C_NETWORK, self.service.C_NETWORK_VC, 'drg_id', drg_id),
                    'remote_peerings': self.service.search_multi_items(self.service.C_NETWORK, self.service.C_NETWORK_RPC, 'drg_id', drg_id),
                    'vcns': []
                }

                # Add VCNs
                drg_attachments = self.service.search_multi_items(self.service.C_NETWORK, self.service.C_NETWORK_DRG_AT, 'drg_id', drg_id)
                for da in drg_attachments:
                    if da['vcn_id']:
                        vcn = self.service.search_unique_item(self.service.C_NETWORK, self.service.C_NETWORK_VCN, 'id', da['vcn_id'])
                        if vcn:
                            vcn['drg_route_table_id'] = da['drg_route_table_id']
                            vcn['drg_route_table'] = self.__get_core_network_drg_route(da['drg_route_table_id'])
                            vcn['route_table_id'] = da['route_table_id']
                            vcn['route_table'] = self.__get_core_network_route(da['route_table_id'])
                            val['vcns'].append(vcn)

                data.append(val)

            return data

        except Exception as e:
            self.__print_error("__get_core_network_drg", e)
            return data

    ##########################################################################
    # get drg route
    ##########################################################################
    def __get_core_network_drg_route(self, drg_route_table_id):
        try:
            route = self.service.search_unique_item(self.service.C_NETWORK, self.service.C_NETWORK_DRG_RT, 'id', drg_route_table_id)
            if route:
                if 'display_name' in route:
                    return route['display_name']
            return ""

        except Exception as e:
            self.__print_error("__get_core_network_drg_route", e)

    ##########################################################################
    # get dRG details
    ##########################################################################

    def __get_core_network_drg_name(self, drg_id):
        try:
            # get DRG name
            drg = self.service.search_unique_item(self.service.C_NETWORK, self.service.C_NETWORK_DRG, 'id', drg_id)
            if drg:
                return "DRG - " + drg['name'] + " (" + drg['redundancy'] + ")"
            return ""

        except Exception as e:
            self.__print_error("__get_core_network_drg_name", e)

    ##########################################################################
    # get cpe name
    ##########################################################################

    def __get_core_network_cpe_name(self, cpe_id):
        try:
            # get DRG name
            cpe = self.service.search_unique_item(self.service.C_NETWORK, self.service.C_NETWORK_CPE, 'id', cpe_id)
            if cpe:
                return "CPE - " + cpe['name']

        except Exception as e:
            self.__print_error("__get_core_network_cpe_name", e)

    ##########################################################################
    # get vcn name
    ##########################################################################
    def __get_core_network_vcn_name(self, vcn_id):
        try:
            # get DRG name
            vcn = self.service.search_unique_item(self.service.C_NETWORK, self.service.C_NETWORK_VCN, 'id', vcn_id)
            if vcn:
                return vcn['name']

        except Exception as e:
            self.__print_error("__get_core_network_vcn_name", e)

    ##########################################################################
    # get rfc name
    ##########################################################################
    def __get_core_network_rpc_name(self, rpc_id):
        try:
            # get DRG name
            rpc = self.service.search_unique_item(self.service.C_NETWORK, self.service.C_NETWORK_RPC, 'id', rpc_id)
            if rpc:
                if 'name' in rpc:
                    return rpc['name']
            return ""

        except Exception as e:
            self.__print_error("__get_core_network_rpc_name", e)

    ##########################################################################
    # get Subnet Name
    ##########################################################################
    def __get_core_network_subnet_name(self, subnet_id):
        try:

            subnet = self.service.search_unique_item(self.service.C_NETWORK, self.service.C_NETWORK_SUBNET, 'id', subnet_id)
            if subnet:
                return (subnet['name'] + " " + subnet['cidr_block'] + ", VCN (" + subnet['vcn_name'] + ")")
            else:
                return ""

        except Exception as e:
            self.__print_error("__get_core_network_subnet_name", e)

    ##########################################################################
    # print network remote peering
    ##########################################################################
    def __get_core_network_remote_peering(self, region_name, compartment):

        data = []
        try:
            rpcs = self.service.search_multi_items(self.service.C_NETWORK, self.service.C_NETWORK_RPC, 'region_name', region_name, 'compartment_id', compartment['id'])
            for rpc in rpcs:
                drg_name = self.__get_core_network_drg_name(rpc['drg_id'])
                main_data = {
                    'id': str(rpc['id']),
                    'peer_id': str(rpc['peer_id']),
                    'name': str(rpc['name']),
                    'drg': drg_name,
                    'drg_id': rpc['drg_id'],
                    'is_cross_tenancy_peering': str(rpc['is_cross_tenancy_peering']),
                    'peer_region_name': str(rpc['peer_region_name']),
                    'peer_rfc_name': self.__get_core_network_rpc_name(rpc['peer_id']),
                    'peer_tenancy_id': rpc['peer_tenancy_id'],
                    'peering_status': rpc['peering_status'],
                    'compartment_id': rpc['compartment_id'],
                    'compartment_name': rpc['compartment_name'],
                    'region_name': rpc['region_name'],
                    'drg_route_table_id': rpc['drg_route_table_id'],
                    'drg_route_table': rpc['drg_route_table']
                }

                data.append(main_data)
            return data

        except Exception as e:
            self.__print_error("__get_core_network_remote_peering", e)
            return data

    ##########################################################################
    # get network ipsec
    ##########################################################################
    def __get_core_network_ipsec(self, region_name, compartment):

        data = []
        try:
            list_ip_sec_connections = self.service.search_multi_items(self.service.C_NETWORK, self.service.C_NETWORK_IPS, 'region_name', region_name, 'compartment_id', compartment['id'])

            for ips in list_ip_sec_connections:
                drg = self.__get_core_network_drg_name(ips['drg_id'])
                cpe = self.__get_core_network_cpe_name(ips['cpe_id'])
                main_data = {
                    'id': ips['id'],
                    'name': ips['name'],
                    'drg': drg,
                    'drg_id': ips['drg_id'],
                    'cpe': cpe,
                    'cpe_id': ips['cpe_id'],
                    'routes': ips['static_routes'],
                    'tunnels': ips['tunnels'],
                    'defined_tags': ips['defined_tags'],
                    'time_created': ips['time_created'],
                    'freeform_tags': ips['freeform_tags'],
                    'compartment_id': ips['compartment_id'],
                    'compartment_name': ips['compartment_name'],
                    'region_name': ips['region_name'],
                    'drg_route_table_id': ips['drg_route_table_id'],
                    'drg_route_table': ips['drg_route_table']
                }

                data.append(main_data)

            return data

        except Exception as e:
            self.__print_error("__get_core_network_ipsec", e)
            return data

    ##########################################################################
    # get network virtual_circuit
    ##########################################################################
    def __get_core_network_virtual_circuit(self, region_name, compartment):

        data = []
        try:
            list_virtual_circuits = self.service.search_multi_items(self.service.C_NETWORK, self.service.C_NETWORK_VC, 'region_name', region_name, 'compartment_id', compartment['id'])

            for vc in list_virtual_circuits:
                drg = self.__get_core_network_drg_name(vc['drg_id'])
                main_data = {
                    'id': str(vc['id']),
                    'name': str(vc['name']),
                    'bandwidth_shape_name': str(vc['bandwidth_shape_name']),
                    'bgp_management': str(vc['bgp_management']),
                    'bgp_session_state': str(vc['bgp_session_state']),
                    'customer_bgp_asn': str(vc['customer_bgp_asn']),
                    'drg': drg,
                    'drg_id': vc['drg_id'],
                    'lifecycle_state': str(vc['lifecycle_state']),
                    'oracle_bgp_asn': str(vc['oracle_bgp_asn']),
                    'provider_name': str(vc['provider_name']),
                    'provider_service_name': str(vc['provider_service_name']),
                    'provider_state': str(vc['provider_state']),
                    'reference_comment': str(vc['reference_comment']),
                    'service_type': str(vc['service_type']),
                    'time_created': str(vc['time_created']),
                    'cross_connect_mappings': vc['cross_connect_mappings'],
                    'type': str(vc['type']),
                    'compartment_id': vc['compartment_id'],
                    'compartment_name': vc['compartment_name'],
                    'region_name': vc['region_name'],
                    'drg_route_table_id': vc['drg_route_table_id'],
                    'drg_route_table': vc['drg_route_table']
                }

                # find Attachment for the Virtual Circuit
                drg_attachment = self.service.search_unique_item(self.service.C_NETWORK, self.service.C_NETWORK_DRG_AT, 'virtual_cirtcuit_id', vc['id'])
                if drg_attachment:
                    main_data['drg_route_table_id'] = drg_attachment['drg_route_table_id']
                    main_data['drg_route_table'] = self.__get_core_network_drg_route(drg_attachment['drg_route_table_id'])

                data.append(main_data)
            return data

        except Exception as e:
            self.__print_error("__get_core_network_virtual_circuit", e)
            return data

    ##########################################################################
    # Print Network VCN Local Peering
    ##########################################################################

    def __get_core_network_local_peering(self, local_peering_id):
        try:
            result = self.service.search_unique_item(self.service.C_NETWORK, self.service.C_NETWORK_LPG, 'id', local_peering_id)
            if result:
                if 'name' in result:
                    return result['name']
            return ""

        except Exception as e:
            self.__print_error("__get_core_network_local_peering", e)

    ##########################################################################
    # get Network route
    ##########################################################################
    def __get_core_network_route(self, route_table_id):
        try:
            route = self.service.search_unique_item(self.service.C_NETWORK, self.service.C_NETWORK_ROUTE, 'id', route_table_id)
            if route:
                if 'name' in route:
                    return route['name']
            return ""

        except Exception as e:
            self.__print_error("__get_core_network_route", e)

    ##########################################################################
    # self.__get_core_network_private_ip
    ##########################################################################
    def __get_core_network_private_ip(self, private_ip_id):

        try:
            result = self.service.search_unique_item(self.service.C_NETWORK, self.service.C_NETWORK_PRIVATEIP, 'id', private_ip_id)
            if result:
                if 'name' in result:
                    return result['name']
            return " Not Exist"

        except Exception as e:
            self.__print_error("__get_core_network_private_ip", e)

    ##########################################################################
    # Network Main
    ##########################################################################
    def __get_core_network_main(self, region_name, compartment):

        return_data = {}
        try:

            data = self.__get_core_network_vcn(region_name, compartment)
            if len(data) > 0:
                return_data['vcn'] = data

            data = self.__get_core_network_drg(region_name, compartment)
            if len(data) > 0:
                return_data['drg'] = data

            data = self.__get_core_network_cpe(region_name, compartment)
            if len(data) > 0:
                return_data['cpe'] = data

            data = self.__get_core_network_ipsec(region_name, compartment)
            if len(data) > 0:
                return_data['ipsec'] = data

            data = self.__get_core_network_remote_peering(region_name, compartment)
            if len(data) > 0:
                return_data['remote_peering'] = data

            data = self.__get_core_network_virtual_circuit(region_name, compartment)
            if len(data) > 0:
                return_data['virtual_circuit'] = data

            return return_data

        except Exception as e:
            self.__print_error("__get_core_network_main", e)
            return return_data

    ##########################################################################
    # get Core Block boot volume
    ##########################################################################

    def __get_core_block_volume_boot(self, boot_volume_id, compartment_name):
        try:
            value = {}
            comp_text = ""
            volume_group = ""

            # get block volume
            bv = self.service.search_unique_item(self.service.C_BLOCK, self.service.C_BLOCK_BOOT, 'id', boot_volume_id)
            if bv:

                # check if different compartment
                if bv['compartment_name'] != compartment_name:
                    comp_text = " (Compartment=" + bv['compartment_name'] + ")"

                if bv['volume_group_name']:
                    volume_group = " - Group " + bv['volume_group_name']

                value = {
                    'id': bv['id'],
                    'sum_info': 'Compute - Block Storage (GB)',
                    'sum_size_gb': bv['size_in_gbs'],
                    'size': bv['size_in_gbs'],
                    'desc': (str(bv['size_in_gbs']) + "GB - " + str(bv['display_name']) + " (" + bv['vpus_per_gb'] + " vpus) " + bv['backup_policy'] + volume_group + comp_text),
                    'backup_policy': "None" if bv['backup_policy'] == "" else bv['backup_policy'],
                    'vpus_per_gb': bv['vpus_per_gb'],
                    'volume_group_name': bv['volume_group_name'],
                    'compartment_name': bv['compartment_name'],
                    'is_hydrated': bv['is_hydrated'],
                    'time_created': bv['time_created'],
                    'display_name': bv['display_name'],
                    'defined_tags': bv['defined_tags'],
                    'freeform_tags': bv['freeform_tags']
                }
            return value

        except Exception as e:
            self.__print_error("__get_core_block_volume_boot", e)

    ##########################################################################
    # get Core Block boot volume
    ##########################################################################

    def __get_core_block_volume(self, volume_id, compartment_name):
        try:
            value = {}
            comp_text = ""
            volume_group = ""

            # get block volume
            bv = self.service.search_unique_item(self.service.C_BLOCK, self.service.C_BLOCK_VOL, 'id', volume_id)
            if bv:

                # check if different compartment
                if bv['compartment_name'] != compartment_name:
                    comp_text = " (Compartment=" + bv['compartment_name'] + ")"

                if bv['volume_group_name']:
                    volume_group = " - Group " + bv['volume_group_name']

                value = {
                    'id': bv['id'],
                    'sum_info': 'Compute - Block Storage (GB)',
                    'sum_size_gb': bv['size_in_gbs'],
                    'desc': (str(bv['size_in_gbs']) + "GB - " + str(bv['display_name']) + " (" + bv['vpus_per_gb'] + " vpus) " + bv['backup_policy'] + volume_group + comp_text),
                    'time_created': bv['time_created'],
                    'compartment_name': bv['compartment_name'],
                    'compartment_id': bv['compartment_id'],
                    'backup_policy': "None" if bv['backup_policy'] == "" else bv['backup_policy'],
                    'display_name': bv['display_name'],
                    'vpus_per_gb': bv['vpus_per_gb'],
                    'volume_group_name': bv['volume_group_name'],
                    'is_hydrated': bv['is_hydrated'],
                    'size': str(bv['size_in_gbs']),
                    'defined_tags': bv['defined_tags'],
                    'freeform_tags': bv['freeform_tags']
                }
            return value

        except Exception as e:
            self.__print_error("__get_core_block_volume", e)

    ##########################################################################
    # get block volume which not attached
    ##########################################################################

    def __get_core_block_volume_not_attached(self, region_name, compartment):

        data = []
        try:
            volumes = self.service.search_multi_items(self.service.C_BLOCK, self.service.C_BLOCK_VOL, 'region_name', region_name, 'compartment_id', compartment['id'])
            volattc = self.service.search_multi_items(self.service.C_COMPUTE, self.service.C_COMPUTE_VOLUME_ATTACH, 'region_name', region_name)

            # loop on volumes
            for vol in volumes:
                found = False

                # loop on vol attached to check if exist
                for att in volattc:
                    if att['volume_id'] == vol['id'] and att['lifecycle_state'] == 'ATTACHED':
                        found = True
                        break

                # if not found, add
                if not found:

                    # append to the list
                    volume_group = ""
                    if vol['volume_group_name']:
                        volume_group = " - Group " + vol['volume_group_name']

                    value = {
                        'id': vol['id'],
                        'display_name': vol['display_name'],
                        'availability_domain': vol['availability_domain'],
                        'size': vol['size_in_gbs'],
                        'backup_policy': vol['backup_policy'],
                        'compartment_name': compartment['name'],
                        'volume_group_name': vol['volume_group_name'],
                        'vpus_per_gb': vol['vpus_per_gb'],
                        'sum_info': 'Compute - Block Storage (GB)',
                        'sum_size_gb': vol['size_in_gbs'],
                        'desc': ((str(vol['size_in_gbs']) + "GB").ljust(7) + " - " + str(vol['display_name']).ljust(20)[0:19] + " - " + vol['availability_domain'] + " - " + vol['time_created'][0:16] + volume_group)
                    }

                    data.append(value)
            return data

        except Exception as e:
            self.__print_error("__get_core_block_volume_not_attached", e)
            return data

    ##########################################################################
    # get block boot which not attached
    ##########################################################################
    def __get_core_block_boot_not_attached(self, region_name, compartment):

        data = []
        try:
            volumes = self.service.search_multi_items(self.service.C_BLOCK, self.service.C_BLOCK_BOOT, 'region_name', region_name, 'compartment_id', compartment['id'])
            volattc = self.service.search_multi_items(self.service.C_COMPUTE, self.service.C_COMPUTE_BOOT_VOL_ATTACH, 'region_name', region_name)

            # loop on volumes
            for vol in volumes:
                found = False

                # loop on vol attached to check if exist
                for att in volattc:
                    if att['boot_volume_id'] == vol['id']:
                        found = True
                        break

                # if not found, add
                if not found:

                    # append to the list
                    volume_group = ""
                    if vol['volume_group_name']:
                        volume_group = " - Group " + vol['volume_group_name']

                    value = {
                        'id': vol['id'],
                        'display_name': vol['display_name'],
                        'availability_domain': vol['availability_domain'],
                        'size': vol['size_in_gbs'],
                        'backup_policy': vol['backup_policy'],
                        'vpus_per_gb': vol['vpus_per_gb'],
                        'compartment_name': compartment['name'],
                        'volume_group_name': vol['volume_group_name'],
                        'sum_info': 'Compute - Block Storage (GB)',
                        'sum_size_gb': vol['size_in_gbs'],
                        'desc': ((str(vol['size_in_gbs']) + "GB").ljust(7) + " - " + str(vol['display_name']).ljust(26)[0:25] + " - " + vol['availability_domain'] + " - " + vol['time_created'][0:16] + volume_group)
                    }

                    data.append(value)

            return data

        except Exception as e:
            self.__print_error("__get_core_block_boot_not_attached", e)
            return data

    ##########################################################################
    # get compute boot volume
    ##########################################################################
    def __get_core_block_volume_groups(self, region_name, compartment):

        data = []
        try:
            volgroups = self.service.search_multi_items(self.service.C_BLOCK, self.service.C_BLOCK_VOLGRP, 'region_name', region_name, 'compartment_id', compartment['id'])

            for vplgrp in volgroups:
                value = {'id': vplgrp['id'], 'name': vplgrp['display_name'], 'size_in_gbs': vplgrp['size_in_gbs'],
                         'compartment_name': str(vplgrp['compartment_name']), 'volumes': [],
                         'time_created': vplgrp['time_created'],
                         'defined_tags': vplgrp['defined_tags'],
                         'freeform_tags': vplgrp['freeform_tags']}

                # check volumes
                for vol_id in vplgrp['volume_ids']:
                    vol = self.service.search_unique_item(self.service.C_BLOCK, self.service.C_BLOCK_VOL, 'id', vol_id)
                    if vol:
                        value['volumes'].append(vol['display_name'] + " - " + vol['size_in_gbs'] + "GB")

                # check boot vol
                for vol_id in vplgrp['volume_ids']:
                    vol = self.service.search_unique_item(self.service.C_BLOCK, self.service.C_BLOCK_BOOT, 'id', vol_id)
                    if vol:
                        value['volumes'].append(vol['display_name'] + " - " + vol['size_in_gbs'] + "GB")

                data.append(value)

            if len(data) > 0:
                return sorted(data, key=lambda k: k['name'])
            return data

        except Exception as e:
            self.__print_error("__get_core_block_volume_groups", e)
            return data

    ##########################################################################
    # print compute instances
    ##########################################################################
    def __get_core_compute_instances(self, region_name, compartment):

        data = []
        try:
            instances = self.service.search_multi_items(self.service.C_COMPUTE, self.service.C_COMPUTE_INST, 'region_name', region_name, 'compartment_id', compartment['id'])

            for instance in instances:

                # fix the shape image for the summary
                sum_shape = ""
                sum_flex = ""
                if instance['image'] == "Not Found" or instance['image'] == "Custom" or "Oracle-Linux" in instance['image']:
                    sum_shape = instance['image_os'][0:35]
                elif 'Windows-Server' in instance['image']:
                    sum_shape = instance['image'][0:19]
                elif instance['image_os'] == "PaaS Image":
                    sum_shape = "PaaS Image - " + instance['display_name'].split("|", 2)[1] if len(instance['display_name'].split("|", 2)) >= 2 else instance['image_os']
                elif instance['image_os'] == "Windows":
                    sum_shape = "Windows-" + instance['image'][0:25]
                else:
                    sum_shape = instance['image'][0:35]

                if 'Flex' in instance['shape']:
                    sum_flex = "." + str(int(instance['shape_ocpu']))

                inst = {'id': instance['id'], 'name': instance['shape'] + " - " + instance['display_name'] + " - " + instance['lifecycle_state'],
                        'sum_info': 'Compute',
                        'sum_shape': str(instance['shape'].replace("Flex", "F") + sum_flex).ljust(22, ' ')[0:21] + " - " + sum_shape,
                        'availability_domain': instance['availability_domain'],
                        'fault_domain': instance['fault_domain'],
                        'time_maintenance_reboot_due': str(instance['time_maintenance_reboot_due']),
                        'image': instance['image'], 'image_id': instance['image_id'],
                        'image_os': instance['image_os'],
                        'shape': instance['shape'],
                        'shape_ocpu': instance['shape_ocpu'],
                        'shape_memory_gb': instance['shape_memory_gb'],
                        'shape_storage_tb': instance['shape_storage_tb'],
                        'shape_gpu_description': instance['shape_gpu_description'],
                        'shape_gpus': instance['shape_gpus'],
                        'shape_local_disk_description': instance['shape_local_disk_description'],
                        'shape_local_disks': instance['shape_local_disks'],
                        'shape_max_vnic_attachments': instance['shape_max_vnic_attachments'],
                        'shape_networking_bandwidth_in_gbps': instance['shape_networking_bandwidth_in_gbps'],
                        'shape_processor_description': instance['shape_processor_description'],
                        'display_name': instance['display_name'],
                        'compartment_name': instance['compartment_name'],
                        'compartment_id': instance['compartment_id'],
                        'lifecycle_state': instance['lifecycle_state'],
                        'console_id': instance['console_id'], 'console': instance['console'],
                        'time_created': instance['time_created'],
                        'agent_is_management_disabled': instance['agent_is_management_disabled'],
                        'agent_is_monitoring_disabled': instance['agent_is_monitoring_disabled'],
                        'defined_tags': instance['defined_tags'],
                        'freeform_tags': instance['freeform_tags'],
                        'metadata': instance['metadata'],
                        'extended_metadata': instance['extended_metadata']
                        }

                # boot volumes attachments
                boot_vol_attachement = self.service.search_multi_items(self.service.C_COMPUTE, self.service.C_COMPUTE_BOOT_VOL_ATTACH, 'instance_id', instance['id'])

                bv = []
                for bva in boot_vol_attachement:
                    bvval = {'id': bva['boot_volume_id']}
                    bvval = self.__get_core_block_volume_boot(bva['boot_volume_id'], instance['compartment_name'])
                    if 'display_name' in bvval:
                        bv.append(bvval)

                inst['boot_volume'] = bv

                # Volumes attachements
                block_vol_attaches = self.service.search_multi_items(self.service.C_COMPUTE, self.service.C_COMPUTE_VOLUME_ATTACH, 'instance_id', instance['id'])

                bvol = []
                for bvola in block_vol_attaches:
                    if bvola['lifecycle_state'] == "ATTACHED":
                        bvval = {'id': bvola['volume_id']}
                        bvval = self.__get_core_block_volume(bvola['volume_id'], instance['compartment_name'])
                        if 'display_name' in bvval:
                            bvol.append(bvval)

                inst['block_volume'] = bvol

                # vnic attachements
                vnicas = self.service.search_multi_items(self.service.C_COMPUTE, self.service.C_COMPUTE_VNIC_ATTACH, 'instance_id', instance['id'])

                vnicdata = []
                for vnic in vnicas:

                    # handle compartment
                    comp_text = ""
                    if vnic['compartment_name'] != compartment['name']:
                        comp_text = " (Compartment=" + vnic['compartment_name'] + ")"

                    if 'vnic_details' in vnic:
                        if 'display_name' in vnic['vnic_details']:
                            val = {
                                'id': vnic['vnic_id'],
                                'desc': vnic['vnic_details']['display_name'] + str(comp_text),
                                'details': vnic['vnic_details']
                            }
                            if 'ip_addresses' in vnic['vnic_details']:
                                val['ip_addresses'] = vnic['vnic_details']['ip_addresses']
                            vnicdata.append(val)

                inst['vnic'] = vnicdata

                # add instance to data
                data.append(inst)

            # return data
            return data

        except BaseException as e:
            self.__print_error("__get_core_compute_instances", e)
            return data

    ##########################################################################
    # print compute images
    ##########################################################################
    def __get_core_compute_images(self, region_name, compartment):

        data = []
        try:
            images = self.service.search_multi_items(self.service.C_COMPUTE, self.service.C_COMPUTE_IMAGES, 'region_name', region_name, 'compartment_id', compartment['id'])

            for image in images:
                value = {'id': image['id'],
                         'desc': image['display_name'].ljust(24) + " - " + image['operating_system'] + " - " + image[
                             'size_in_gbs'].rjust(3) + "GB - Base:  " + image['base_image_name'],
                         'sum_info': 'Object Storage - Images (GB)',
                         'sum_size_gb': image['size_in_gbs'],
                         'sum_count_info': "Compute - Images (Count)",
                         'sum_count_size': "1",
                         'time_created': image['time_created'],
                         'defined_tags': image['defined_tags'],
                         'freeform_tags': image['freeform_tags'],
                         'compartment_name': image['compartment_name'],
                         'compartment_id': image['compartment_id']
                         }
                data.append(value)
            return data

        except Exception as e:
            self.__print_error("__get_core_compute_images", e)
            return data

    ##########################################################################
    # Compute
    ##########################################################################

    def __get_core_compute_main(self, region_name, compartment):
        return_data = {}

        try:

            data = self.__get_core_compute_instances(region_name, compartment)
            if len(data) > 0:
                return_data['instances'] = data

            data = self.__get_core_compute_images(region_name, compartment)
            if len(data) > 0:
                return_data['images'] = data

            data = self.__get_core_block_volume_groups(region_name, compartment)
            if len(data) > 0:
                return_data['volume_groups'] = data

            data = self.__get_core_block_boot_not_attached(region_name, compartment)
            if len(data) > 0:
                return_data['boot_not_attached'] = data

            data = self.__get_core_block_volume_not_attached(region_name, compartment)
            if len(data) > 0:
                return_data['volume_not_attached'] = data

            return return_data

        except Exception as e:
            self.__print_error("__get_core_compute_main", e)
            return return_data

    ##########################################################################
    # print database db nodes
    ##########################################################################
    def __get_database_db_nodes(self, db_nodes):

        data = []
        try:
            nodeidstr = " "
            nodeid = 0
            for db_node in db_nodes:
                nodeid += 1

                if len(db_nodes) > 1:
                    nodeidstr = str(nodeid)

                vnic_desc = ""
                nsg_names = ""
                nsg_ids = ""
                if 'vnic_details' in db_node:
                    if 'dbdesc' in db_node['vnic_details']:
                        vnic_desc = db_node['vnic_details']['dbdesc']

                    if 'nsg_names' in db_node['vnic_details']:
                        nsg_names = db_node['vnic_details']['nsg_names']

                    if 'nsg_ids' in db_node['vnic_details']:
                        nsg_ids = db_node['vnic_details']['nsg_ids']

                value = {'desc': "Node " + str(nodeidstr) + "  : " + str(db_node['hostname']) + " - " + str(db_node['lifecycle_state']) + " - " + str(vnic_desc + ("" if db_node['fault_domain'] == "None" else " - " + str(db_node['fault_domain']))),
                         'software_storage_size_in_gb': db_node['software_storage_size_in_gb'],
                         'lifecycle_state': db_node['lifecycle_state'],
                         'hostname': db_node['hostname'],
                         'nsg_names': nsg_names,
                         'nsg_ids': nsg_ids,
                         'vnic_id': db_node['vnic_id'],
                         'backup_vnic_id': ("" if db_node['backup_vnic_id'] == "None" else db_node['backup_vnic_id']),
                         'vnic_details': db_node['vnic_details'],
                         'backup_vnic_details': db_node['backup_vnic_details'],
                         'maintenance_type': db_node['maintenance_type'],
                         'time_maintenance_window_start': db_node['time_maintenance_window_start'],
                         'time_maintenance_window_end': db_node['time_maintenance_window_end'],
                         'fault_domain': ("" if db_node['fault_domain'] == "None" else db_node['fault_domain'])
                         }

                data.append(value)

            return data

        except Exception as e:
            self.__print_error("__get_database_db_nodes", e)
            return data

    ##########################################################################
    # print database Databases
    ##########################################################################
    def __get_database_db_databases(self, dbs):

        data = []
        try:

            for db in dbs:

                backupstr = (" - AutoBck=N" if db['auto_backup_enabled'] else " - AutoBck=Y")
                pdb_name = db['pdb_name'] + " - " if db['pdb_name'] else ""
                value = {'name': (str(db['db_name']) + " - " + str(db['db_unique_name']) + " - " +
                                  pdb_name +
                                  str(db['db_workload']) + " - " +
                                  str(db['character_set']) + " - " +
                                  str(db['ncharacter_set']) + " - " +
                                  str(db['lifecycle_state']) + backupstr),
                         'backups': self.__get_database_db_backups(db['backups']) if 'backups' in db else [],
                         'time_created': db['time_created'],
                         'defined_tags': db['defined_tags'],
                         'dataguard': self.__get_database_db_dataguard(db['dataguard']),
                         'freeform_tags': db['freeform_tags'],
                         'db_name': db['db_name'],
                         'pdb_name': pdb_name,
                         'db_workload': db['db_workload'],
                         'character_set': db['character_set'],
                         'ncharacter_set': db['ncharacter_set'],
                         'db_unique_name': db['db_unique_name'],
                         'lifecycle_state': db['lifecycle_state'],
                         'auto_backup_enabled': db['auto_backup_enabled'],
                         'connection_strings_cdb': db['connection_strings_cdb'],
                         'source_database_point_in_time_recovery_timestamp': db['source_database_point_in_time_recovery_timestamp'],
                         'kms_key_id': db['kms_key_id'],
                         'last_backup_timestamp': db['last_backup_timestamp'],
                         'id': db['id']
                         }

                data.append(value)
            return data

        except Exception as e:
            self.__print_error("__get_database_db_databases", e)
            return data

    ##########################################################################
    # get db system patches
    ##########################################################################
    def __get_database_db_patches(self, patches):

        data = []
        try:
            for dbp in patches:
                data.append(str(dbp['description']) + " - " + str(dbp['version']) + " - " + str(dbp['time_released'])[0:10] + " - Last Action: " + str(dbp['last_action']))
            return data

        except Exception as e:
            self.__print_error("__get_database_db_patches", e)
            return data

    ##########################################################################
    # __load_database_dbsystems_dbnodes
    ##########################################################################
    def __get_database_db_homes(self, db_homes):

        data = []
        try:
            for db_home in db_homes:
                data.append(
                    {'id': str(db_home['id']),
                     'home': str(db_home['display_name']) + " - " + str(db_home['db_version']),
                     'databases': self.__get_database_db_databases(db_home['databases']),
                     'patches': self.__get_database_db_patches(db_home['patches'])
                     })

            # add to main data
            return data

        except Exception as e:
            self.__print_error("__get_database_db_homes", e)
            return data

    ##########################################################################
    # __load_database_dbsystems_dbnodes
    ##########################################################################
    def __get_database_db_dataguard(self, dataguards):

        data = []
        try:
            for dg in dataguards:

                # add data
                data.append(
                    {'id': str(dg['id']),
                     'database_id': str(dg['database_id']),
                     'peer_name': str(dg['db_name']),
                     'lifecycle_state': str(dg['lifecycle_state']),
                     'peer_data_guard_association_id': str(dg['peer_data_guard_association_id']),
                     'name': "Dataguard: " + dg['role'] + ", " + dg['protection_mode'] + " (" + dg['transport_type'] + "), Peer DB: " + dg['db_name'],
                     'apply_rate': str(dg['apply_rate']),
                     'apply_lag': str(dg['apply_lag']),
                     'peer_role': str(dg['peer_role']),
                     'protection_mode': str(dg['protection_mode']),
                     'transport_type': str(dg['transport_type']),
                     'time_created': str(dg['time_created']),
                     })

            # add to main data
            return data

        except Exception as e:
            self.__print_error("__get_database_db_dataguard", e)
            return data

    ##########################################################################
    # Exadata Infra
    ##########################################################################
    def __get_database_db_exadata(self, region_name, compartment):

        data = []
        try:
            list_exas = self.service.search_multi_items(self.service.C_DATABASE, self.service.C_DATABASE_EXADATA, 'region_name', region_name, 'compartment_id', compartment['id'])

            for dbs in list_exas:
                value = {
                    'id': dbs['id'],
                    'display_name': dbs['display_name'],
                    'shape': dbs['shape'],
                    'shape_ocpu': dbs['shape_ocpu'],
                    'shape_memory_gb': dbs['shape_memory_gb'],
                    'shape_storage_tb': dbs['shape_storage_tb'],
                    'version': dbs['version'],
                    'lifecycle_state': dbs['lifecycle_state'],
                    'lifecycle_details': dbs['lifecycle_details'],
                    'availability_domain': dbs['availability_domain'],
                    'compute_count': dbs['compute_count'],
                    'storage_count': dbs['storage_count'],
                    'total_storage_size_in_gbs': dbs['total_storage_size_in_gbs'],
                    'available_storage_size_in_gbs': dbs['available_storage_size_in_gbs'],
                    'compartment_name': dbs['compartment_name'],
                    'compartment_id': dbs['compartment_id'],
                    'time_created': dbs['time_created'],
                    'last_maintenance_run': dbs['last_maintenance_run'],
                    'next_maintenance_run': dbs['next_maintenance_run'],
                    'maintenance_window': dbs['maintenance_window'],
                    'defined_tags': dbs['defined_tags'],
                    'freeform_tags': dbs['freeform_tags'],
                    'region_name': dbs['region_name'],
                    'name': dbs['display_name'] + " - " + dbs['shape'] + " - " + dbs['lifecycle_state'],
                    'sum_info': 'Database XP - ' + dbs['shape'],
                    'sum_info_storage': 'Database - Storage (GB)',
                    'sum_size_gb': dbs['total_storage_size_in_gbs'],
                    'data': str(dbs['available_storage_size_in_gbs']) + "GB",
                    'vm_clusters': []
                }

                for vm in dbs['vm_clusters']:
                    valvm = {
                        'id': vm['id'],
                        'cluster_name': vm['cluster_name'],
                        'hostname': vm['hostname'],
                        'compartment_id': vm['compartment_id'],
                        'availability_domain': vm['availability_domain'],
                        'data_subnet_id': vm['data_subnet_id'],
                        'data_subnet': vm['data_subnet'],
                        'backup_subnet_id': vm['backup_subnet_id'],
                        'backup_subnet': vm['backup_subnet'],
                        'nsg_ids': vm['nsg_ids'],
                        'backup_network_nsg_ids': vm['backup_network_nsg_ids'],
                        'last_update_history_entry_id': vm['last_update_history_entry_id'],
                        'shape': vm['shape'],
                        'listener_port': vm['listener_port'],
                        'lifecycle_state': vm['lifecycle_state'],
                        'node_count': vm['node_count'],
                        'storage_size_in_gbs': vm['storage_size_in_gbs'],
                        'display_name': vm['display_name'],
                        'time_created': vm['time_created'],
                        'lifecycle_details': vm['lifecycle_details'],
                        'time_zone': vm['time_zone'],
                        'domain': vm['domain'],
                        'cpu_core_count': vm['cpu_core_count'],
                        'data_storage_percentage': vm['data_storage_percentage'],
                        'is_local_backup_enabled': vm['is_local_backup_enabled'],
                        'is_sparse_diskgroup_enabled': vm['is_sparse_diskgroup_enabled'],
                        'gi_version': vm['gi_version'],
                        'system_version': vm['system_version'],
                        'ssh_public_keys': vm['ssh_public_keys'],
                        'license_model': vm['license_model'],
                        'disk_redundancy': vm['disk_redundancy'],
                        'scan_ip_ids': vm['scan_ip_ids'],
                        'scan_ips': vm['scan_ips'],
                        'vip_ids': vm['vip_ids'],
                        'vip_ips': vm['vip_ips'],
                        'scan_dns_record_id': vm['scan_dns_record_id'],
                        'defined_tags': vm['defined_tags'],
                        'freeform_tags': vm['freeform_tags'],
                        'region_name': vm['region_name'],
                        'sum_info': 'Database XP - ' + dbs['shape'] + " - " + vm['license_model'],
                        'sum_info_storage': 'Database - Storage (GB)',
                        'sum_size_gb': vm['storage_size_in_gbs'],
                        'patches': self.__get_database_db_patches(vm['patches']),
                        'db_homes': self.__get_database_db_homes(vm['db_homes']),
                        'db_nodes': self.__get_database_db_nodes(vm['db_nodes']),
                        'zone_id': vm['zone_id'],
                        'scan_dns_name': vm['scan_dns_name']
                    }
                    value['vm_clusters'].append(valvm)

                data.append(value)
            return data

        except Exception as e:
            self.__print_error("__get_database_db_exadata", e)
            return data

    ##########################################################################
    # Database Systems
    ##########################################################################
    def __get_database_db_systems(self, region_name, compartment):

        data = []
        try:
            list_db_systems = self.service.search_multi_items(self.service.C_DATABASE, self.service.C_DATABASE_DBSYSTEMS, 'region_name', region_name, 'compartment_id', compartment['id'])

            for dbs in list_db_systems:
                value = {'id': dbs['id'],
                         'name': dbs['display_name'] + " - " + dbs['shape'] + " - " + dbs['lifecycle_state'],
                         'shape': dbs['shape'],
                         'shape_ocpu': dbs['shape_ocpu'],
                         'shape_memory_gb': dbs['shape_memory_gb'],
                         'shape_storage_tb': dbs['shape_storage_tb'],
                         'display_name': dbs['display_name'],
                         'lifecycle_state': dbs['lifecycle_state'],
                         'sum_info': 'Database ' + dbs['database_edition_short'] + " - " + dbs['shape'] + " - " + dbs['license_model'],
                         'sum_info_storage': 'Database - Storage (GB)',
                         'sum_size_gb': dbs['data_storage_size_in_gbs'],
                         'database_edition': dbs['database_edition'],
                         'database_edition_short': dbs['database_edition_short'],
                         'license_model': dbs['license_model'],
                         'database_version': dbs['version'],
                         'availability_domain': dbs['availability_domain'],
                         'cpu_core_count': dbs['cpu_core_count'],
                         'node_count': dbs['node_count'],
                         'version': (dbs['version'] + " - ") if dbs['version'] != "None" else "" + ((dbs['database_edition'] + " - ") if dbs['database_edition'] != "None" else "") + dbs['license_model'],
                         'host': dbs['hostname'],
                         'domain': dbs['domain'],
                         'data_subnet': dbs['data_subnet'],
                         'data_subnet_id': dbs['data_subnet_id'],
                         'backup_subnet': dbs['backup_subnet'],
                         'backup_subnet_id': dbs['backup_subnet_id'],
                         'scan_dns': dbs['scan_dns_record_id'],
                         'scan_ips': dbs['scan_ips'],
                         'data_storage_size_in_gbs': dbs['data_storage_size_in_gbs'],
                         'reco_storage_size_in_gb': dbs['reco_storage_size_in_gb'],
                         'sparse_diskgroup': dbs['sparse_diskgroup'],
                         'storage_management': dbs['storage_management'],
                         'vip_ips': dbs['vip_ips'],
                         'zone_id': dbs['zone_id'],
                         'scan_dns_name': dbs['scan_dns_name'],
                         'compartment_name': dbs['compartment_name'],
                         'compartment_id': dbs['compartment_id'],
                         'cluster_name': dbs['cluster_name'],
                         'time_created': dbs['time_created'],
                         'defined_tags': dbs['defined_tags'],
                         'freeform_tags': dbs['freeform_tags'],
                         'listener_port': dbs['listener_port'],
                         'last_maintenance_run': dbs['last_maintenance_run'],
                         'next_maintenance_run': dbs['next_maintenance_run'],
                         'maintenance_window': dbs['maintenance_window'],
                         'patches': self.__get_database_db_patches(dbs['patches']),
                         'db_homes': self.__get_database_db_homes(dbs['db_homes']),
                         'db_nodes': self.__get_database_db_nodes(dbs['db_nodes'])
                         }

                if dbs['data_storage_size_in_gbs']:
                    value['data'] = str(dbs['data_storage_size_in_gbs']) + "GB - " + str(dbs['data_storage_percentage']) + "%" + (" - " + dbs['storage_management'] if dbs['storage_management'] else "")
                else:
                    value['data'] = str(dbs['data_storage_percentage']) + "%" + (" - " + dbs['storage_management'] if dbs['storage_management'] else "")

                data.append(value)
            return data

        except Exception as e:
            self.__print_error("__get_database_db_systems", e)
            return data

    ##########################################################################
    # print database db backups
    ##########################################################################
    def __get_database_adb_databases_backups(self, backups):

        data = []
        try:

            for backup in backups:
                backup_type = "Automatic Backup, " if backup['is_automatic'] else "Manual Backup   , "
                data.append(
                    {'name': backup_type + str(backup['display_name']) + " - " + str(backup['type']) + " - " + str(backup['lifecycle_state']),
                     'time': str(backup['time_started'])[0:16] + " - " + str(backup['time_ended'])[0:16]})
            return data

        except Exception as e:
            self.__print_error("__get_database_autonomous_backups", e)
            return data

    ##########################################################################
    # Autonomous db info
    ##########################################################################
    def __get_database_adb_database_info(self, dbs):

        try:
            freemsg = ",  FreeTier" if dbs['is_free_tier'] else ""
            freesum = "Free " if dbs['is_free_tier'] else ""
            value = {
                'id': str(dbs['id']),
                'name': str(dbs['db_name']) + " (" + (str(dbs['display_name']) + ") - " + str(dbs['license_model']) + " - " + str(dbs['lifecycle_state']) + " (" + str(dbs['sum_count']) + " OCPUs" + (" AutoScale" if dbs['is_auto_scaling_enabled'] else "") + ") - " + dbs['db_workload'] + " - " + dbs['db_type'] + freemsg),
                'display_name': dbs['display_name'],
                'license_model': dbs['license_model'],
                'lifecycle_state': dbs['lifecycle_state'],
                'cpu_core_count': str(dbs['cpu_core_count']),
                'data_storage_size_in_tbs': str(dbs['data_storage_size_in_tbs']),
                'db_name': str(dbs['db_name']),
                'compartment_name': str(dbs['compartment_name']),
                'compartment_id': str(dbs['compartment_id']),
                'service_console_url': str(dbs['service_console_url']),
                'time_created': str(dbs['time_created'])[0:16],
                'connection_strings': str(dbs['connection_strings']),
                'sum_info': "Autonomous Database " + freesum + str(dbs['db_workload']) + " (OCPUs) - " + dbs['license_model'],
                'sum_info_stopped': "Stopped Autonomous Database " + freesum + str(dbs['db_workload']) + " (Count) - " + dbs['license_model'],
                'sum_info_count': "Autonomous Database " + freesum + str(dbs['db_workload']) + " (Count) - " + dbs['license_model'],
                'sum_count': str(dbs['sum_count']),
                'sum_info_storage': "Autonomous Database " + freesum + "(TB)",
                'sum_size_tb': str(dbs['data_storage_size_in_tbs']),
                'backups': self.__get_database_adb_databases_backups(dbs['backups']),
                'whitelisted_ips': dbs['whitelisted_ips'],
                'is_auto_scaling_enabled': dbs['is_auto_scaling_enabled'],
                'db_workload': dbs['db_workload'],
                'is_dedicated': dbs['is_dedicated'],
                'db_version': dbs['db_version'],
                'subnet_id': dbs['subnet_id'],
                'subnet_name': "",
                'data_safe_status': dbs['data_safe_status'],
                'time_maintenance_begin': dbs['time_maintenance_begin'],
                'time_maintenance_end': dbs['time_maintenance_end'],
                'nsg_ids': dbs['nsg_ids'],
                'nsg_names': [],
                'private_endpoint': dbs['private_endpoint'],
                'private_endpoint_label': dbs['private_endpoint_label'],
                'defined_tags': dbs['defined_tags'],
                'freeform_tags': dbs['freeform_tags'],
                'is_free_tier': dbs['is_free_tier'],
                'is_preview': dbs['is_preview'],
                'infrastructure_type': dbs['infrastructure_type'],
                'time_deletion_of_free_autonomous_database': dbs['time_deletion_of_free_autonomous_database'],
                'time_reclamation_of_free_autonomous_database': dbs['time_reclamation_of_free_autonomous_database'],
                'system_tags': dbs['system_tags'],
                'time_of_last_switchover': dbs['time_of_last_switchover'],
                'time_of_last_failover': dbs['time_of_last_failover'],
                'failed_data_recovery_in_seconds': dbs['failed_data_recovery_in_seconds'],
                'available_upgrade_versions': dbs['available_upgrade_versions'],
                'standby_lag_time_in_seconds': dbs['standby_lag_time_in_seconds'],
                'standby_lifecycle_state': dbs['standby_lifecycle_state'],
                'autonomous_container_database_id': dbs['autonomous_container_database_id'],
                'is_data_guard_enabled': dbs['is_data_guard_enabled']
            }

            # subnet
            if dbs['subnet_id'] != 'None':
                value['subnet_name'] = self.__get_core_network_subnet_name(dbs['subnet_id'])

            # get the nsg names
            if dbs['nsg_ids']:
                for nsg in dbs['nsg_ids']:
                    nsg_obj = self.service.search_unique_item(self.service.C_NETWORK, self.service.C_NETWORK_NSG, 'id', nsg)
                    if nsg_obj:
                        value['nsg_names'].append(nsg_obj['name'])

            return value

        except Exception as e:
            self.__print_error("__get_database_adb_database_info", e)
            return {}

    ##########################################################################
    # Autonomous
    ##########################################################################
    def __get_database_adb_databases(self, region_name, compartment):

        data = []
        try:
            list_autos = self.service.search_multi_items(self.service.C_DATABASE, self.service.C_DATABASE_ADB_DATABASE, 'region_name', region_name, 'compartment_id', compartment['id'])

            for dbs in list_autos:

                # if dedicated skip, it will be under containers
                if dbs['is_dedicated']:
                    continue

                data.append(self.__get_database_adb_database_info(dbs))
            return data

        except Exception as e:
            self.__print_error("__get_database_autonomous_databases", e)
            return data

    ##########################################################################
    # Autonomous Dedicated Infra
    ##########################################################################
    def __get_database_adb_dedicated(self, region_name, compartment):

        data = []
        try:
            infrastructures = self.service.search_multi_items(self.service.C_DATABASE, self.service.C_DATABASE_ADB_D_INFRA, 'region_name', region_name, 'compartment_id', compartment['id'])

            for infra in infrastructures:
                value = {'id': str(infra['id']),
                         'name': str(infra['display_name']) + " - " + str(infra['license_model']) + " - " + infra['shape'] + " - " + str(infra['lifecycle_state']),
                         'availability_domain': infra['availability_domain'],
                         'subnet_id': infra['subnet_id'],
                         'subnet_name': infra['subnet_name'],
                         'nsg_ids': infra['nsg_ids'],
                         'shape': infra['shape'],
                         'shape_ocpu': infra['shape_ocpu'],
                         'shape_memory_gb': infra['shape_memory_gb'],
                         'shape_storage_tb': infra['shape_storage_tb'],
                         'hostname': infra['hostname'],
                         'domain': str(infra['domain']),
                         'lifecycle_state': str(infra['lifecycle_state']),
                         'lifecycle_details': str(infra['lifecycle_details']),
                         'license_model': str(infra['license_model']),
                         'time_created': str(infra['time_created']),
                         'scan_dns_name': str(infra['scan_dns_name']),
                         'zone_id': infra['zone_id'],
                         'maintenance_window': infra['maintenance_window'],
                         'last_maintenance_run': infra['last_maintenance_run'],
                         'next_maintenance_run': infra['next_maintenance_run'],
                         'defined_tags': infra['defined_tags'],
                         'freeform_tags': infra['freeform_tags'],
                         'compartment_name': infra['compartment_name'],
                         'compartment_id': infra['compartment_id'],
                         'region_name': infra['region_name'],
                         'containers': [],
                         'sum_info': "Autonomous Dedicated " + infra['shape'] + " - " + infra['license_model'],
                         'sum_info_stopped': "Stopped Autonomous Dedicated " + infra['shape'] + " - " + infra['license_model'],
                         'sum_info_count': "Autonomous Dedicated " + infra['shape'] + " - " + infra['license_model'],
                         'sum_count': 1,
                         'sum_info_storage': "",
                         'sum_size_tb': ""
                         }

                for ct in infra['containers']:
                    ct['name'] = ct['display_name'] + " (" + ct['lifecycle_state'] + "), " + ct['db_version'] + ", Patch Model : " + ct['patch_model']
                    ct['databases'] = []

                    # Add Databases
                    databases = self.service.search_multi_items(self.service.C_DATABASE, self.service.C_DATABASE_ADB_DATABASE, 'autonomous_container_database_id', ct['id'])
                    for arr in databases:
                        db = self.__get_database_adb_database_info(arr)
                        db['name'] = str(db['db_name'] + " (" + db['display_name'] + ") - " + infra['license_model'] + " - " + db['lifecycle_state'] + " (" + str(db['sum_count']) + " OCPUs" + (" AutoScale" if db['is_auto_scaling_enabled'] else "") + ") - " + db['db_workload'])
                        db['sum_info'] = "Autonomous Database Dedicated " + str(db['db_workload']) + " (OCPUs) - " + infra['license_model']
                        db['sum_info_stopped'] = "Stopped Autonomous Database Dedicated " + str(db['db_workload']) + " (Count) - " + infra['license_model']
                        db['sum_info_count'] = "Autonomous Database Dedicated " + str(db['db_workload']) + " (Count) - " + infra['license_model']
                        db['sum_info_storage'] = "Autonomous Database Dedicated (TB)"
                        ct['databases'].append(db)

                    # Add containers
                    value['containers'].append(ct)

                # get the nsg names
                if infra['nsg_ids']:
                    for nsg in infra['nsg_ids']:
                        nsg_obj = self.service.search_unique_item(self.service.C_NETWORK, self.service.C_NETWORK_NSG, 'id', nsg)
                        if nsg_obj:
                            value['nsg_names'].append(nsg_obj['name'])

                data.append(value)
            return data

        except Exception as e:
            self.__print_error("__get_database_adb_d_infrastructure", e)
            return data

    ##########################################################################
    # __get_database_software_images
    ##########################################################################
    def __get_database_software_images(self, region_name, compartment):

        data = []
        try:
            database_software_images = self.service.search_multi_items(self.service.C_DATABASE, self.service.C_DATABASE_SOFTWARE_IMAGES, 'region_name', region_name, 'compartment_id', compartment['id'])
            return database_software_images

        except Exception as e:
            self.__print_error("__get_database_software_images", e)
            return data

    ##########################################################################
    # __get_database_goldengate
    ##########################################################################
    def __get_database_goldengate(self, region_name, compartment):

        return_data = {}
        data = []
        try:
            data = self.__get_database_goldengate_deployments(region_name, compartment)
            if data:
                if len(data) > 0:
                    return_data['gg_deployments'] = data

            data = self.__get_database_goldengate_db_registration(region_name, compartment)
            if data:
                if len(data) > 0:
                    return_data['gg_db_registration'] = data

            return return_data

        except Exception as e:
            self.__print_error("__get_database_goldengate", e)
            return return_data

    ##########################################################################
    # __get_database_gg_deployments
    ##########################################################################
    def __get_database_goldengate_deployments(self, region_name, compartment):

        data = []
        try:
            database_gg_deployments = self.service.search_multi_items(self.service.C_DATABASE, self.service.C_DATABASE_GG_DEPLOYMENTS, 'region_name', region_name, 'compartment_id', compartment['id'])
            return database_gg_deployments

        except Exception as e:
            self.__print_error("__get_database_goldengate_deployments", e)
            return data

    ##########################################################################
    # __get_database_gg_db_registration
    ##########################################################################
    def __get_database_goldengate_db_registration(self, region_name, compartment):

        data = []
        try:
            database_gg_db_registrations = self.service.search_multi_items(self.service.C_DATABASE, self.service.C_DATABASE_GG_DB_REGISTRATION, 'region_name', region_name, 'compartment_id', compartment['id'])
            return database_gg_db_registrations

        except Exception as e:
            self.__print_error("__get_database_goldengate_db_registration", e)
            return data

    ##########################################################################
    # Database
    ##########################################################################
    def __get_database_main(self, region_name, compartment):

        return_data = {}
        try:

            # DB System
            data = self.__get_database_db_systems(region_name, compartment)
            if data:
                if len(data) > 0:
                    return_data['db_system'] = data

            data = self.__get_database_db_exadata(region_name, compartment)
            if data:
                if len(data) > 0:
                    return_data['exadata_infrustructure'] = data

            data = self.__get_database_adb_dedicated(region_name, compartment)
            if data:
                if len(data) > 0:
                    return_data['autonomous_dedicated'] = data

            data = self.__get_database_adb_databases(region_name, compartment)
            if data:
                if len(data) > 0:
                    return_data['autonomous'] = data

            data = self.__get_database_software_images(region_name, compartment)
            if data:
                if len(data) > 0:
                    return_data['software_images'] = data

            return return_data

        except Exception as e:
            self.__print_error("__get_database_main", e)
            return return_data


###########################################################################################################
# ShowOCIOutput class
# accept data as JSON format and print nice output
###########################################################################################################
class ShowOCIOutput(object):

    ##########################################################################
    # spaces for align
    ##########################################################################
    tabs = ' ' * 4
    taba = '--> '
    tabs2 = tabs + tabs
    error = 0

    ############################################
    # Init
    ############################################
    def __init__(self):
        pass

    ##########################################################################
    # Print header centered
    ##########################################################################
    def print_header(self, name, category, topBorder=True, bottomBorder=True, printText=True):
        options = {0: 95, 1: 60, 2: 40, 3: 85}
        chars = int(options[category])
        if topBorder:
            print("")
            print('#' * chars)
        if printText:
            print("#" + name.center(chars - 2, " ") + "#")
        if bottomBorder:
            print('#' * chars)

    ##########################################################################
    # print_oci_main
    ##########################################################################

    def print_data(self, data, print_version=False):
        try:
            has_data = False
            for d in data:
                if 'type' in d:
                    if d['type'] == "showoci":
                        if print_version:
                            self.print_showoci_config(d['data'])

                    elif d['type'] == "identity":
                        self.__print_identity_main(d['data'])
                        has_data = True

                    elif d['type'] == "region":

                        if d['data']:
                            self.print_header(d['region'], 0)
                            has_data = True

                        self.__print_region_data(d['region'], d['data'])

                    else:
                        print("Error Unknown Type in JSON file...")

            # if no data - print message
            if not has_data:
                print("")
                print("*** Data not found, please check your execution flags ***")

        except Exception as e:
            raise Exception("Error in self.__print_main: " + str(e.args))

    ##########################################################################
    # Print showoci data
    ##########################################################################
    def print_showoci_config(self, data):
        try:
            self.print_header(data['program'], 1)
            print("Author          : " + data['author'])
            print("Machine         : " + data['machine'])
            print("Python Version  : " + data['python'])
            if data['use_instance_principals']:
                print("Authentication  : Instance Principals")
            elif data['use_delegation_token']:
                print("Authentication  : Instance Principals With Delegation Token")
                print("Config File     : " + data['config_file'])
                print("Config Profile  : " + data['config_profile'])
            else:
                print("Authentication  : Config File")
                print("Config File     : " + data['config_file'])
                print("Config Profile  : " + data['config_profile'])
            print("Date/Time       : " + data['datetime'])
            print("Comand Line     : " + data['cmdline'])
            print("Showoci Version : " + data['version'])
            print("OCI SDK Version : " + data['oci_sdk_version'])
            if 'proxy' in data:
                print("Proxy           : " + data['proxy'])
            if 'override_tenant_id' in data:
                if data['override_tenant_id']:
                    print("Override id     : " + data['override_tenant_id'])
            if 'joutfile' in data:
                print("JSON Out        : " + data['joutfile'])

            print("")

        except Exception as e:
            raise Exception("Error in print_showoci_config: " + str(e.args))

    ##########################################################################
    # get errors
    ##########################################################################
    def get_errors(self):
        return self.error

    ##########################################################################
    # print print error
    ##########################################################################
    def __print_error(self, msg, e):
        classname = type(self).__name__

        if isinstance(e, KeyError):
            print("\nError in " + classname + ":" + msg + ": KeyError " + str(e.args))
        else:
            print("\nError in " + classname + ":" + msg + ": " + str(e))

        self.error += 1

    ##########################################################################
    # Print Tenancy
    ##########################################################################
    def __print_identity_tenancy(self, tenancy):
        try:

            self.print_header("Tenancy", 0)
            print("Name        : " + tenancy['name'])
            print("Tenant Id   : " + tenancy['id'])
            print("Home Region : " + tenancy['home_region_key'])
            print("Subs Region : " + tenancy['subscribe_regions'])
            print("")

        except Exception as e:
            self.__print_error("__print_identity_tenancy", e)

    ##########################################################################
    # Print Identity Users
    ##########################################################################

    def __print_identity_users(self, users):
        try:
            self.print_header("Users", 2)

            for user in users:
                last_login = "" if user['last_successful_login_time'] == "None" else ", Last Login = " + user['last_successful_login_time'][0:10]
                mfa_enabled = "" if user['is_mfa_activated'] == "False" else ", MFA Enabled"
                print(self.taba + user['name'] + mfa_enabled + last_login)
                print(self.tabs + "Groups     : " + user['groups'])
                print("")

        except Exception as e:
            self.__print_error("__print_identity_users", e)

    ##########################################################################
    # Print Identity Groups
    ##########################################################################

    def __print_identity_groups(self, groups):
        try:
            self.print_header("Groups", 2)

            for group in groups:
                print(self.taba + group['name'].ljust(18, " ") + " : " + group['users'])

        except Exception as e:
            self.__print_error("__print_identity_groups", e)

    ##########################################################################
    # Print Identity Policies
    ##########################################################################
    def __print_identity_policies(self, policies_data):
        try:
            if not policies_data:
                return

            self.print_header("Policies", 2)

            for c in policies_data:
                policies = c['policies']
                if not policies:
                    continue

                print("\nCompartment " + c['compartment_path'] + ":")
                for policy in policies:
                    print("")
                    print(self.taba + policy['name'] + ":")
                    print(self.tabs + "\n    ".join(policy['statements']))

        except Exception as e:
            self.__print_error("__print_identity_policies", e)

    ##########################################################################
    # Print Identity Providers
    ##########################################################################
    def __print_identity_providers(self, identity_providers):

        try:

            if not identity_providers:
                return

            self.print_header("identity providers", 2)

            for ip in identity_providers:
                print(self.taba + ip['name'])
                print(self.tabs + "Desc      : " + ip['description'])
                print(self.tabs + "Type      : " + ip['product_type'])
                print(self.tabs + "Protocol  : " + ip['protocol'])
                print(self.tabs + "Redirect  : " + ip['redirect_url'])
                print(self.tabs + "Metadata  : " + ip['metadata_url'])
                for ig in ip['group_map']:
                    print(self.tabs + "Group Map : " + ig)
                print("")
            print("")

        except Exception as e:
            self.__print_error("__print_identity_providers", e)

    ##########################################################################
    # Print Dynamic Groups
    ##########################################################################
    def __print_identity_dynamic_groups(self, dynamic_groups):
        try:
            if not dynamic_groups:
                return
            self.print_header("Dynamic Groups", 2)

            for dg in dynamic_groups:
                print(self.taba + dg['name'])
                print(self.tabs + "Desc      :" + dg['description'])
                print(self.tabs + "Rules     :" + dg['matching_rule'])
            print("")

        except Exception as e:
            self.__print_error("__print_identity_dynamic_groups", e)

    ##########################################################################
    # Print network sources
    ##########################################################################
    def __print_network_sources(self, network_sources):
        try:
            if not network_sources:
                return
            self.print_header("Network Sources", 2)

            for ns in network_sources:
                print(self.taba + ns['name'])
                print(self.tabs + "Desc      : " + ns['description'])
                print(self.tabs + "Services  : " + ", ".join(ns['services']))
                print(self.tabs + "Public IPs: " + ", ".join(ns['public_source_list']))
                print(self.tabs + "VCN IPs   : " + ", ".join(x['ip_ranges'] for x in ns['virtual_source_list']))

            print("")

        except Exception as e:
            self.__print_error("__print_network_sources", e)

    ##########################################################################
    # Print Cost Tracking Tags
    ##########################################################################
    def __print_identity_cost_tracking_tags(self, tags):
        try:
            if not tags:
                return
            self.print_header("Cost Tracking Tags", 2)

            for tag in tags:
                print(self.taba + tag['tag_namespace_name'] + "." + tag['name'])
                print(self.tabs + "Desc      :" + tag['description'])
                print(self.tabs + "Created   :" + tag['time_created'][0:16])
                print("")

        except Exception as e:
            self.__print_error("__print_identity_cost_tracking_tags", e)

    ##########################################################################
    # Identity Module
    ##########################################################################

    def __print_identity_main(self, data):
        try:
            if 'tenancy' in data:
                self.__print_identity_tenancy(data['tenancy'])
            if 'users' in data:
                self.__print_identity_users(data['users'])
            if 'groups' in data:
                self.__print_identity_groups(data['groups'])
            if 'dynamic_groups' in data:
                self.__print_identity_dynamic_groups(data['dynamic_groups'])
            if 'network_sources' in data:
                self.__print_network_sources(data['network_sources'])
            if 'policies' in data:
                self.__print_identity_policies(data['policies'])
            if 'providers' in data:
                self.__print_identity_providers(data['providers'])

        except Exception as e:
            self.__print_error("__print_identity_data", e)

    ##########################################################################
    # return compartment name
    ##########################################################################

    def __print_core_network_vcn_compartment(self, vcn_compartment, data_compartment):
        if vcn_compartment == data_compartment:
            return ""
        val = "  (Compartment=" + data_compartment + ")"
        return val

    ##########################################################################
    # Print Network VCN subnets
    ##########################################################################

    def __print_core_network_vcn_subnet(self, subnets, vcn_compartment):
        try:
            for subnet in subnets:
                print("")
                print(self.tabs + "Subnet " + subnet['subnet'] + self.__print_core_network_vcn_compartment(vcn_compartment, subnet['compartment_name']))
                print(self.tabs + self.tabs + "Name    : " + subnet['name'])
                print(self.tabs + self.tabs + "DNS     : " + subnet['dns'])
                print(self.tabs + self.tabs + "DHCP    : " + subnet['dhcp_options'])
                print(self.tabs + self.tabs + "Route   : " + subnet['route'])
                for s in subnet['security_list']:
                    print(self.tabs + self.tabs + "Sec List: " + s)

        except Exception as e:
            self.__print_error("__print_core_network_vcn_subnet", e)

    ##########################################################################
    # Print Network VCN VLAN
    ##########################################################################

    def __print_core_network_vcn_vlan(self, vlans, vcn_compartment):
        try:
            for vlan in vlans:
                print("")
                print(self.tabs + "VLAN " + vlan['vlan'] + self.__print_core_network_vcn_compartment(vcn_compartment,
                                                                                                     vlan[
                                                                                                         'compartment_name']))
                print(self.tabs + self.tabs + "Route   : " + vlan['route'])
                for s in vlan['nsg']:
                    print(self.tabs + self.tabs + "NSG     : " + s)

        except Exception as e:
            self.__print_error("__print_core_network_vcn_vlan", e)

    ##########################################################################
    # get DHCP options for DHCP_ID
    ##########################################################################

    def __print_core_network_vcn_dhcp_options(self, dhcp_options, vcn_compartment):
        try:
            for dhcp in dhcp_options:
                print("")
                print(self.tabs + "DHCP Options: " + dhcp['name'] + self.__print_core_network_vcn_compartment(vcn_compartment, dhcp['compartment_name']))

                for opt in dhcp['opt']:
                    print(self.tabs + self.tabs + opt)

        except Exception as e:
            self.__print_error("__print_core_network_vcn_dhcp_options", e)

    ##########################################################################
    # Print Network vcn security list
    ##########################################################################

    def __print_core_network_vcn_security_lists(self, sec_lists, vcn_compartment):
        try:
            if not sec_lists:
                return
            for sl in sec_lists:
                print("")
                print(self.tabs + "Sec List    : " + str(sl['name']) + self.__print_core_network_vcn_compartment(vcn_compartment, sl['compartment_name']))
                if len(sl['sec_rules']) == 0:
                    print(self.tabs + "            : Empty.")

                for slr in sl['sec_rules']:
                    print(self.tabs + self.tabs + slr['desc'])

        except Exception as e:
            self.__print_error("__print_core_network_vcn_security_lists", e)

    ##########################################################################
    # Print Network vcn security groups
    ##########################################################################

    def __print_core_network_vcn_security_groups(self, sec_groups, vcn_compartment):
        try:
            if not sec_groups:
                return
            for sl in sec_groups:
                print("")
                print(self.tabs + "Sec Group   : " + str(sl['name']) + self.__print_core_network_vcn_compartment(vcn_compartment, sl['compartment_name']))
                if len(sl['sec_rules']) == 0:
                    print(self.tabs + "            : Empty or no Permission.")

                for slr in sl['sec_rules']:
                    print(self.tabs + self.tabs + slr['desc'])

        except Exception as e:
            self.__print_error("__print_core_network_vcn_security_groups", e)

    ########################################################################
    # Print Network vcn Route Tables
    ##########################################################################

    def __print_core_network_vcn_route_tables(self, route_tables, vcn_compartment):
        try:
            if not route_tables:
                return

            for rt in route_tables:
                print("")
                print(self.tabs + "Route Table : " + rt['name'] + self.__print_core_network_vcn_compartment(vcn_compartment, rt['compartment_name']))

                if 'route_rules' not in rt:
                    print(self.tabs + self.tabs + "Route   : Empty.")
                else:
                    if len(rt['route_rules']) == 0:
                        print(self.tabs + self.tabs + "Route   : Empty.")
                    else:
                        for rl in rt['route_rules']:
                            print(self.tabs + self.tabs + "Route   : " + str(rl['desc']))

        except Exception as e:
            self.__print_error("__print_core_network_vcn_route_tables", e)

    ##########################################################################
    # print network vcn
    ##########################################################################
    def __print_core_network_vcn(self, vcns):

        try:
            if len(vcns) == 0:
                return

            self.print_header("VCNs", 2)
            for vcn in vcns:
                print(self.taba + "VCN    " + vcn['name'])
                vcn_compartment = vcn['compartment_name']

                if 'igw' in vcn['data']:
                    for igwloop in vcn['data']['igw']:
                        print(self.tabs + "Internet GW : " + igwloop['name'] + self.__print_core_network_vcn_compartment(vcn_compartment, igwloop['compartment_name']))

                if 'sgw' in vcn['data']:
                    for sgwloop in vcn['data']['sgw']:
                        print(self.tabs + "Service GW  : " + sgwloop['name'] + sgwloop['transit'] + " - " + sgwloop['services'] + self.__print_core_network_vcn_compartment(vcn_compartment, sgwloop['compartment_name']))

                if 'nat' in vcn['data']:
                    for natloop in vcn['data']['nat']:
                        print(self.tabs + "NAT GW      : " + natloop['name'] + self.__print_core_network_vcn_compartment(vcn_compartment, natloop['compartment_name']))

                if 'drg_attached' in vcn['data']:
                    for drgloop in vcn['data']['drg_attached']:
                        print(self.tabs + "DRG Attached: " + drgloop['name'] + self.__print_core_network_vcn_compartment(vcn_compartment, drgloop['compartment_name']))

                if 'local_peering' in vcn['data']:
                    for lpeer in vcn['data']['local_peering']:
                        print(self.tabs + "Local Peer  : " + lpeer['name'] + " ---> " + lpeer['peer_name'] + self.__print_core_network_vcn_compartment(vcn_compartment, lpeer['compartment_name']))

                if 'subnets' in vcn['data']:
                    self.__print_core_network_vcn_subnet(vcn['data']['subnets'], vcn_compartment)

                if 'vlans' in vcn['data']:
                    self.__print_core_network_vcn_vlan(vcn['data']['vlans'], vcn_compartment)

                if 'security_lists' in vcn['data']:
                    self.__print_core_network_vcn_security_lists(vcn['data']['security_lists'], vcn_compartment)

                if 'security_groups' in vcn['data']:
                    self.__print_core_network_vcn_security_groups(vcn['data']['security_groups'], vcn_compartment)

                if 'route_tables' in vcn['data']:
                    self.__print_core_network_vcn_route_tables(vcn['data']['route_tables'], vcn_compartment)

                if 'dhcp_options' in vcn['data']:
                    self.__print_core_network_vcn_dhcp_options(vcn['data']['dhcp_options'], vcn_compartment)

                print("")

        except BaseException as e:
            self.__print_error("__print_core_network_vcn", e)

    ##########################################################################
    # print network drg
    ##########################################################################
    def __print_core_network_drg(self, drgs):

        try:
            if len(drgs) == 0:
                return

            self.print_header("DRGs", 2)
            for drg in drgs:
                print(self.taba + "DRG   Name      : " + drg['name'] + ", Redundant: " + drg['redundancy'])

                for index, arr in enumerate(drg['ip_sec_connections'], start=1):
                    drg_route_table = ", DRG Route: " + arr['drg_route_table'] if arr['drg_route_table'] else ""
                    print(self.tabs + "      IPSEC " + str(index) + "   : " + arr['name'] + " (" + arr['tunnels_status'] + ")" + drg_route_table)

                for index, arr in enumerate(drg['virtual_circuits'], start=1):
                    drg_route_table = ", DRG Route: " + arr['drg_route_table'] if arr['drg_route_table'] else ""
                    print(self.tabs + "      VC " + str(index) + "      : " + arr['name'] + " (" + arr['bgp_session_state'] + ")" + drg_route_table)

                for index, arr in enumerate(drg['remote_peerings'], start=1):
                    drg_route_table = ", DRG Route: " + arr['drg_route_table'] if arr['drg_route_table'] else ""
                    print(self.tabs + "      RPC " + str(index) + "     : " + arr['name'] + " (" + arr['peering_status'] + ")" + drg_route_table)

                for index, arr in enumerate(drg['vcns'], start=1):
                    drg_route_table = ", DRG Route: " + arr['drg_route_table'] if arr['drg_route_table'] else ""
                    route_table = ", Route Table: " + arr['route_table'] if arr['route_table'] else ""
                    print(self.tabs + "      VCN " + str(index) + "     : " + arr['name'] + drg_route_table + route_table)

                for rt in drg['drg_route_tables']:
                    print("")
                    print(self.tabs + "      DRG Route : " + rt['display_name'] + ", is_ecmp_enabled: " + rt['is_ecmp_enabled'])
                    for index, arr in enumerate(rt['route_rules'], start=1):
                        print(self.tabs + "         Rule " + str(index) + " : " + arr['name'])
                print("")

        except Exception as e:
            self.__print_error("__print_core_network_drg", e)

    ##########################################################################
    # print network remote peering
    ##########################################################################
    def __print_core_network_remote_peering(self, rpcs):

        try:
            if len(rpcs) == 0:
                return

            self.print_header("Remote Peering", 2)
            for rpc in rpcs:
                print(self.taba + "RPC   Name   : " + rpc['name'])
                print(self.tabs + "      DRG    : " + rpc['drg'])

                # if peer has name if not id
                if rpc['peer_rfc_name']:
                    print(self.tabs + "      Peer   : " + rpc['peer_rfc_name'] + " - " + rpc['peer_region_name'])
                else:
                    print(self.tabs + "      PeerId : " + rpc['peer_id'])
                    print(self.tabs + "      Region : " + rpc['peer_region_name'])

                print(self.tabs + "      Status : " + rpc['peering_status'])
                if rpc['is_cross_tenancy_peering'] == "True":
                    print(self.tabs + "       Tenant: Cross Tenant: " + rpc['peer_tenancy_id'])

        except Exception as e:
            self.__print_error("__print_core_network_vcn", e)

    ##########################################################################
    # print network cpe
    ##########################################################################
    def __print_core_network_cpe(self, cpes):

        try:

            if len(cpes) == 0:
                return

            self.print_header("CPEs", 2)
            for cpe in cpes:
                print(self.taba + "CPE    " + cpe['name'])

        except Exception as e:
            self.__print_error("__print_core_network_cpe", e)

    ##########################################################################
    # print network ipsec
    ##########################################################################
    def __print_core_network_ipsec(self, ipsecs):

        try:
            if len(ipsecs) == 0:
                return

            self.print_header("IPSec", 2)
            for ips in ipsecs:

                print(self.taba + "IPSEC  : " + ips['name'])
                print(self.tabs + "DRG    : " + ips['drg'])
                print(self.tabs + "CPE    : " + ips['cpe'])
                # get tunnel status
                for t in ips['tunnels']:
                    print(self.tabs + "Tunnel : " + t['display_name'].ljust(12) + " - " + t['status'] + ", " + t['routing'] + ", VPN: " + t['vpn_ip'] + ", CPE: " + t['cpe_ip'] + ", " + t['status_date'])
                    if t['bgp_info']:
                        print(self.tabs + "       : " + t['bgp_info'])

                if ips['routes']:
                    print(self.tabs + "Routes : " + "\n    Static : ".join(ips['routes']))
                print("")

        except Exception as e:
            self.__print_error("__print_core_network_ipsec", e)

    ##########################################################################
    # print virtual cirtuicts
    ##########################################################################
    def __print_core_network_virtual_circuit(self, virtual_circuit):

        try:
            if len(virtual_circuit) == 0:
                return

            self.print_header("Virtual Circuits (FC)", 2)
            for vc in virtual_circuit:

                print(self.taba + "VC      : " + vc['name'] + " - " + vc['bandwidth_shape_name'] + " - " + vc['lifecycle_state'])
                print(self.tabs + "DRG     : " + vc['drg'])
                print(self.tabs + "BGP     : " + vc['bgp_management'] + " - " + vc['bgp_session_state'] + " - Cust ASN:" + vc['customer_bgp_asn'] + " - Ora ASN:" + vc['oracle_bgp_asn'])
                print(self.tabs + "PROVIDER: " + vc['provider_name'] + " - " + vc['provider_service_name'] + " - " + vc['provider_state'] + " - " + vc['service_type'])
                # get tunnel status
                for t in vc['cross_connect_mappings']:
                    print(self.tabs + "CCMAP   : Cust : " + str(t['customer_bgp_peering_ip']) + " - Ora : " + str(t['oracle_bgp_peering_ip']) + " - VLAN " + str(t['vlan']))
                print("")

        except Exception as e:
            self.__print_error("__print_core_network_virtual_circuit", e)

    ##########################################################################
    # print network Main
    ##########################################################################

    def __print_core_network_main(self, data):
        try:
            if 'vcn' in data:
                self.__print_core_network_vcn(data['vcn'])
            if 'drg' in data:
                self.__print_core_network_drg(data['drg'])
            if 'cpe' in data:
                self.__print_core_network_cpe(data['cpe'])
            if 'ipsec' in data:
                self.__print_core_network_ipsec(data['ipsec'])
            if 'remote_peering' in data:
                self.__print_core_network_remote_peering(data['remote_peering'])
            if 'virtual_circuit' in data:
                self.__print_core_network_virtual_circuit(data['virtual_circuit'])

        except Exception as e:
            self.__print_error("__print_core_network", e)

    ##########################################################################
    # database exadata
    ##########################################################################
    def __print_database_db_exadata_infra(self, list_exadata):

        try:
            for dbs in list_exadata:
                print("")

                print(self.taba + "ExaCS   : " + dbs['name'])
                print(self.tabs + "Created : " + dbs['time_created'][0:16])
                print(self.tabs + "AD      : " + dbs['availability_domain'])

                if 'compute_count' in dbs:
                    if dbs['compute_count'] != "None":
                        print(self.tabs + "VM Hosts: " + str(dbs['compute_count']))

                if 'storage_count' in dbs:
                    if dbs['storage_count'] != "None" and dbs['total_storage_size_in_gbs'] != "None":
                        print(self.tabs + "Storage : Hosts = " + str(dbs['storage_count']) + ", Total = " + str(dbs['total_storage_size_in_gbs']) + "GB")

                if 'maintenance_window' in dbs:
                    if dbs['maintenance_window']:
                        print(self.tabs + "Maint   : Window : " + dbs['maintenance_window']['display'])

                if 'last_maintenance_run' in dbs:
                    if dbs['last_maintenance_run']:
                        print(self.tabs + "Maint   : Last   : " + dbs['last_maintenance_run']['description'])
                        print(self.tabs + "                 : " + dbs['last_maintenance_run']['maintenance_display'])

                if 'next_maintenance_run' in dbs:
                    if dbs['next_maintenance_run']:
                        print(self.tabs + "Maint   : Next   : " + dbs['next_maintenance_run']['description'])
                        print(self.tabs + "                 : " + dbs['next_maintenance_run']['maintenance_display'])
                        if dbs['next_maintenance_run']['maintenance_alert']:
                            print(self.tabs + "          Alert  : " + dbs['next_maintenance_run']['maintenance_alert'])

                print("")

                # clusters
                for vm in dbs['vm_clusters']:

                    if 'display_name' in vm:
                        print(self.tabs + "VMCLSTR : " + str(vm['display_name']) + " (" + vm['lifecycle_state'] + ")")

                    if 'cluster_name' in vm:
                        if vm['cluster_name']:
                            print(self.tabs + "Cluster : " + vm['cluster_name'])

                    if 'cpu_core_count' in vm:
                        print(self.tabs + "Cores   : " + str(vm['cpu_core_count']))

                    if 'node_count' in vm:
                        if vm['node_count']:
                            print(self.tabs + "Nodes   : " + str(vm['node_count']))

                    if 'domain' in vm:
                        if vm['domain']:
                            print(self.tabs + "Domain  : " + vm['domain'])

                    if 'data_subnet' in vm:
                        if vm['data_subnet']:
                            print(self.tabs + "DataSub : " + vm['data_subnet'])

                    if 'backup_subnet' in vm:
                        if vm['backup_subnet']:
                            print(self.tabs + "BackSub : " + vm['backup_subnet'])

                    if 'scan_dns' in vm:
                        if vm['scan_dns']:
                            print(self.tabs + "Scan    : " + vm['scan_dns_name'])

                    if 'scan_ips' in vm:
                        for ip in vm['scan_ips']:
                            print(self.tabs + "Scan Ips: " + ip)

                    if 'vip_ips' in vm:
                        for ip in vm['vip_ips']:
                            print(self.tabs + "VIP Ips : " + ip)

                    if 'listener_port' in vm:
                        print(self.tabs + "Port    : " + vm['listener_port'])

                    if 'gi_version' in vm:
                        print(self.tabs + "GI      : " + vm['gi_version'])

                    if 'data_storage_percentage' in vm:
                        print(self.tabs + "Data    : " + vm['data_storage_percentage'] + "%, Sparse: " + vm['is_sparse_diskgroup_enabled'] + ", Local Backup: " + vm['is_local_backup_enabled'])

                    if 'patches' in vm:
                        for p in vm['patches']:
                            print(self.tabs + "Patches : " + p)

                    # db nodes
                    for db_node in vm['db_nodes']:
                        print(self.tabs + db_node['desc'])
                        if 'nsg_names' in db_node:
                            if db_node['nsg_names']:
                                print(self.tabs + "        : SecGrp : " + db_node['nsg_names'])

                        if 'time_maintenance_window_start' in db_node:
                            if db_node['maintenance_type'] != "None":
                                print(self.tabs + self.tabs + "     Maintenance: " + db_node['maintenance_type'] + "  " + db_node['time_maintenance_window_start'][0:16] + " - " + db_node['time_maintenance_window_end'][0:16])

                    # db homes
                    for db_home in vm['db_homes']:
                        print(self.tabs + "Home    : " + db_home['home'])

                        # patches
                        for p in db_home['patches']:
                            print(self.tabs + self.tabs + " PT : " + p)

                        # databases
                        for db in db_home['databases']:
                            print(self.tabs + self.tabs + " DB : " + db['name'])

                            # print data guard
                            for dg in db['dataguard']:
                                print(self.tabs + self.tabs + "      " + dg['name'])

                            # print backups
                            for backup in db['backups']:
                                print(self.tabs + self.tabs + "      " + backup['name'] + " - " + backup['time'] + " - " + backup['size'])

                        print(self.tabs + "        : " + '-' * 90)

        except Exception as e:
            self.__print_error("__print_database_db_exadata_infra", e)

    ##########################################################################
    # print database db system
    ##########################################################################

    def __print_database_db_system_details(self, dbs):
        try:
            print(self.taba + "DBaaS   : " + dbs['name'] + " - " + dbs['version'])
            print(self.tabs + "Created : " + dbs['time_created'][0:16])
            print(self.tabs + "AD      : " + dbs['availability_domain'])

            if 'cpu_core_count' in dbs:
                print(self.tabs + "Cores   : " + str(dbs['cpu_core_count']))

            if 'node_count' in dbs:
                if dbs['node_count']:
                    print(self.tabs + "Nodes   : " + str(dbs['node_count']))

            if 'host' in dbs:
                print(self.tabs + "Host    : " + dbs['host'])

            if 'domain' in dbs:
                if dbs['domain']:
                    print(self.tabs + "Domain  : " + dbs['domain'])

            if 'cluster_name' in dbs:
                if dbs['cluster_name']:
                    print(self.tabs + "Cluster : " + dbs['cluster_name'])

            if 'data' in dbs:
                if dbs['data']:
                    print(self.tabs + "Data    : " + dbs['data'])

            if 'data_subnet' in dbs:
                print(self.tabs + "DataSub : " + dbs['data_subnet'])

            if 'backup_subnet' in dbs:
                if dbs['backup_subnet']:
                    print(self.tabs + "BackSub : " + dbs['backup_subnet'])

            if 'scan_dns' in dbs:
                if dbs['scan_dns']:
                    print(self.tabs + "Scan    : " + dbs['scan_dns_name'])

            if 'scan_ips' in dbs:
                for ip in dbs['scan_ips']:
                    print(self.tabs + "Scan Ips: " + ip)

            if 'vip_ips' in dbs:
                for ip in dbs['vip_ips']:
                    print(self.tabs + "VIP Ips : " + ip)

            if 'listener_port' in dbs:
                print(self.tabs + "Port    : " + dbs['listener_port'])

            if 'patches' in dbs:
                for p in dbs['patches']:
                    print(self.tabs + "Patches : " + p)

            if 'maintenance_window' in dbs:
                if dbs['maintenance_window']:
                    print(self.tabs + "Maint   : Window : " + dbs['maintenance_window']['display'])

            if 'last_maintenance_run' in dbs:
                if dbs['last_maintenance_run']:
                    print(self.tabs + "Maint   : Last   : " + dbs['last_maintenance_run']['description'])
                    print(self.tabs + "                 : " + dbs['last_maintenance_run']['maintenance_display'])

            if 'next_maintenance_run' in dbs:
                if dbs['next_maintenance_run']:
                    print(self.tabs + "Maint   : Next   : " + dbs['next_maintenance_run']['description'])
                    print(self.tabs + "                 : " + dbs['next_maintenance_run']['maintenance_display'])
                    if dbs['next_maintenance_run']['maintenance_alert']:
                        print(self.tabs + "          Alert  : " + dbs['next_maintenance_run']['maintenance_alert'])

            print(self.tabs + "        : " + '-' * 90)

        except Exception as e:
            self.__print_error("__print_database_db_system_details", e)

    ##########################################################################
    # database db systems
    ##########################################################################
    def __print_database_db_system(self, list_db_systems):

        try:
            for dbs in list_db_systems:
                print("")

                # db systems
                self.__print_database_db_system_details(dbs)

                # db nodes
                for db_node in dbs['db_nodes']:
                    print(self.tabs + db_node['desc'])
                    if 'nsg_names' in db_node:
                        if db_node['nsg_names']:
                            print(self.tabs + "        : SecGrp : " + db_node['nsg_names'])

                    if 'time_maintenance_window_start' in db_node:
                        if db_node['maintenance_type'] != "None":
                            print(self.tabs + self.tabs + "     Maintenance: " + db_node['maintenance_type'] + "  " + db_node['time_maintenance_window_start'][0:16] + " - " + db_node['time_maintenance_window_end'][0:16])

                # db homes
                for db_home in dbs['db_homes']:
                    print(self.tabs + "Home    : " + db_home['home'])

                    # patches
                    for p in db_home['patches']:
                        print(self.tabs + self.tabs + " PT : " + p)

                    # databases
                    for db in db_home['databases']:
                        print(self.tabs + self.tabs + " DB : " + db['name'])

                        # print data guard
                        for dg in db['dataguard']:
                            print(self.tabs + self.tabs + "      " + dg['name'])

                        # print backups
                        for backup in db['backups']:
                            print(self.tabs + self.tabs + "      " + backup['name'] + " - " + backup['time'] + " - " + backup['size'])

        except Exception as e:
            self.__print_error("__print_database_db_system", e)

    ##########################################################################
    # print database Autonomous Shared
    ##########################################################################

    def __print_database_db_autonomous(self, dbs):
        try:
            for db in dbs:
                print(self.taba + "ADB-S      : " + db['name'])
                if 'cpu_core_count' in db:
                    print(self.tabs + "Size       : " + str(db['cpu_core_count']) + " OCPUs, " + str(db['data_storage_size_in_tbs']) + "TB Storage")
                if 'time_created' in db:
                    print(self.tabs + "Created    : " + db['time_created'])
                if 'whitelisted_ips' in db:
                    if db['whitelisted_ips']:
                        print(self.tabs + "Allowed IPs: " + db['whitelisted_ips'])
                if 'private_endpoint' in db:
                    if db['private_endpoint'] != 'None':
                        print(self.tabs + "Private EP : " + db['private_endpoint'] + ", Subnet: " + db['subnet_name'])
                if 'nsg_names' in db:
                    for nsg in db['nsg_names']:
                        print(self.tabs + "           : Network Security Group: " + nsg)
                if 'data_safe_status' in db:
                    print(self.tabs + "DataSafe   : " + db['data_safe_status'])
                if 'time_maintenance_begin' in db:
                    print(self.tabs + "Maintenance: " + db['time_maintenance_begin'][0:16] + " - " + db['time_maintenance_end'][0:16])
                if db['is_data_guard_enabled']:
                    print(self.tabs + "Data Guard : Lag In Second: " + db['standby_lag_time_in_seconds'] + ", lifecycle: " + db['standby_lifecycle_state'] + ",  Last Switch: " + db['time_of_last_switchover'][0:16] + ",  Last Failover: " + db['time_of_last_switchover'][0:16])

                # print backups
                if db['backups']:
                    for backup in db['backups']:
                        print(self.tabs + self.tabs + "         " + backup['name'] + " - " + backup['time'])
                print("")

        except Exception as e:
            self.__print_error("__print_database_db_autonomous", e)

    ##########################################################################
    # ADB-D
    ##########################################################################
    def __print_database_db_autonomous_dedicated(self, list_exadata):

        try:
            for dbs in list_exadata:
                print("")

                print(self.taba + "ADB-D    : " + dbs['name'])
                print(self.tabs + "Created  : " + dbs['time_created'][0:16])
                print(self.tabs + "AD       : " + dbs['availability_domain'])
                print(self.tabs + "Hostname : " + dbs['hostname'])
                print(self.tabs + "Domain   : " + dbs['domain'])
                print(self.tabs + "ScanDNS  : " + dbs['scan_dns_name'])

                if 'subnet_name' in dbs:
                    if dbs['subnet_name'] != "None" and dbs['subnet_name']:
                        print(self.tabs + "Subnet   : " + str(dbs['subnet_name']))

                if 'maintenance_window' in dbs:
                    if dbs['maintenance_window']:
                        print(self.tabs + "Maint    : Window : " + dbs['maintenance_window']['display'])

                if 'last_maintenance_run' in dbs:
                    if dbs['last_maintenance_run']:
                        print(self.tabs + "Maint    : Last   : " + dbs['last_maintenance_run']['description'])
                        print(self.tabs + "                 : " + dbs['last_maintenance_run']['maintenance_display'])

                if 'next_maintenance_run' in dbs:
                    if dbs['next_maintenance_run']:
                        print(self.tabs + "Maint    : Next   : " + dbs['next_maintenance_run']['description'])
                        print(self.tabs + "                 : " + dbs['next_maintenance_run']['maintenance_display'])
                        if dbs['next_maintenance_run']['maintenance_alert']:
                            print(self.tabs + "           Alert  : " + dbs['next_maintenance_run']['maintenance_alert'])

                print("")

                # containers
                for vm in dbs['containers']:

                    print(self.tabs + "Container: " + vm['name'])

                    # databases
                    for db in vm['databases']:
                        print(self.tabs + self.taba + "ADB-S      : " + db['name'])
                        if 'cpu_core_count' in db:
                            print(self.tabs + self.tabs + "Size       : " + str(db['cpu_core_count']) + " OCPUs, " + str(db['data_storage_size_in_tbs']) + "TB Storage")
                        if 'time_created' in db:
                            print(self.tabs + self.tabs + "Created    : " + db['time_created'])
                        if 'data_safe_status' in db:
                            print(self.tabs + self.tabs + "DataSafe   : " + db['data_safe_status'])
                        if 'time_maintenance_begin' in db:
                            print(self.tabs + self.tabs + "Maintenance: " + db['time_maintenance_begin'][0:16] + " - " + db['time_maintenance_end'][0:16])
                        if db['is_data_guard_enabled']:
                            print(self.tabs + self.tabs + "Data Guard : Lag In Second: " + db['standby_lag_time_in_seconds'] + ", lifecycle: " + db['standby_lifecycle_state'] + ",  Last Switch: " + db['time_of_last_switchover'][0:16] + ",  Last Failover: " + db['time_of_last_switchover'][0:16])

                        # print backups
                        if db['backups']:
                            for backup in db['backups']:
                                print(self.tabs + self.tabs + "         " + backup['name'] + " - " + backup['time'])
                        print("")

        except Exception as e:
            self.__print_error("__print_database_db_exadata_infra", e)

    ##########################################################################
    # print database nosql
    ##########################################################################

    def __print_database_software_images(self, dbs):
        try:
            for db in dbs:
                print(self.taba + "Name    : " + db['display_name'] + " - " + db['patch_set'] + " - " + db['image_shape_family'] + " - " + db['image_type'])
                print(self.tabs + "Created : " + db['time_created'][0:16] + " (" + db['lifecycle_state'] + ")")
                print("")

        except Exception as e:
            self.__print_error("__print_database_software_images", e)

    ##########################################################################
    # database
    ##########################################################################

    def __print_database_main(self, list_databases):
        try:

            if len(list_databases) == 0:
                return

            if 'exadata_infrustructure' in list_databases:
                self.print_header("Exadata Infrastructure", 2)
                self.__print_database_db_exadata_infra(list_databases['exadata_infrustructure'])
                print("")

            if 'db_system' in list_databases:
                self.print_header("databases DB Systems", 2)
                self.__print_database_db_system(list_databases['db_system'])
                print("")

            if 'autonomous_dedicated' in list_databases:
                self.print_header("Autonomous Dedicated", 2)
                self.__print_database_db_autonomous_dedicated(list_databases['autonomous_dedicated'])
                print("")

            if 'autonomous' in list_databases:
                self.print_header("Autonomous databases", 2)
                self.__print_database_db_autonomous(list_databases['autonomous'])
                print("")

            if 'software_images' in list_databases:
                self.print_header("Database Software Images", 2)
                self.__print_database_software_images(list_databases['software_images'])

        except Exception as e:
            self.__print_error("__print_database_main", e)

    ##########################################################################
    # print compute instances
    ##########################################################################

    def __print_core_compute_instances(self, instances):

        try:

            if len(instances) == 0:
                return

            self.print_header("Compute Instances", 2)
            for instance in instances:
                if 'name' in instance:
                    print(self.taba + instance['name'])

                if instance['shape_ocpu'] > 0:
                    print(self.tabs2 + "Shape: Ocpus: " + str(instance['shape_ocpu']) + ", Memory: " + str(instance['shape_memory_gb']) + "GB, Local Storage: " + str(instance['shape_storage_tb']) + "TB, Processor: " + str(instance['shape_processor_description']))

                if 'availability_domain' in instance and 'fault_domain' in instance:
                    print(self.tabs2 + "AD   : " + instance['availability_domain'] + " - " + instance['fault_domain'])

                if 'time_maintenance_reboot_due' in instance:
                    if instance['time_maintenance_reboot_due'] != "None":
                        print(self.tabs2 + "MRB  : Maintenance Reboot Due " + instance['time_maintenance_reboot_due'])

                if 'image' in instance:
                    print(self.tabs2 + "Img  : " + instance['image'] + " (" + instance['image_os'] + ")")

                if 'boot_volume' in instance:
                    for bv in instance['boot_volume']:
                        if 'desc' in bv:
                            print(self.tabs2 + "Boot : " + bv['desc'])

                if 'block_volume' in instance:
                    for bv in instance['block_volume']:
                        if 'desc' in bv:
                            print(self.tabs2 + "Vol  : " + bv['desc'])

                if 'vnic' in instance:
                    for vnic in instance['vnic']:
                        if 'desc' in vnic:
                            print(self.tabs2 + "VNIC : " + vnic['desc'])
                        if 'nsg_names' in vnic['details']:
                            if vnic['details']['nsg_names']:
                                print(self.tabs2 + "     : SecGrp: " + vnic['details']['nsg_names'])
                        if 'internal_fqdn' in vnic['details']:
                            if vnic['details']['internal_fqdn']:
                                print(self.tabs2 + "     : Int FQDN     : " + vnic['details']['internal_fqdn'])
                        if 'ip_addresses' in vnic:
                            print(self.tabs2 + "     : IP Addresses : " + str(', '.join(x['ip_address'] for x in vnic['ip_addresses'])))

                if 'console' in instance:
                    if instance['console']:
                        print(self.tabs2 + instance['console'])

                if 'agent_is_management_disabled' in instance:
                    print(self.tabs2 + "Agent: Is Management Disabled = " + instance['agent_is_management_disabled'] + ", Is Monitoring Disabled = " + instance['agent_is_monitoring_disabled'])

                print("")

        except Exception as e:
            self.__print_error("__print_core_compute_instances", e)

    ##########################################################################
    # print compute images
    ##########################################################################
    def __print_core_compute_images(self, images):

        try:
            if len(images) == 0:
                return

            self.print_header("Compute Custom Images", 2)
            for image in images:
                print(self.taba + image['desc'])

        except Exception as e:
            self.__print_error("__print_core_compute_images", e)

    ##########################################################################
    # print compute block volume Groups
    ##########################################################################
    def __print_core_compute_volume_groups(self, volgroups):

        try:
            if len(volgroups) == 0:
                return

            self.print_header("Block Volume Groups", 2)
            for volgrp in volgroups:
                print(self.taba + volgrp['name'] + " - " + volgrp['size_in_gbs'] + "GB")
                for vol in volgrp['volumes']:
                    print(self.tabs + self.tabs + " Vol : " + vol)

        except Exception as e:
            self.__print_error("__print_core_compute_volume_groups", e)

    ##########################################################################
    # print compute block volume not attached
    ##########################################################################
    def __print_core_compute_volume_not_attached(self, vols):

        try:
            if len(vols) == 0:
                return

            self.print_header("Block Volume Not Attached", 2)
            for vol in vols:
                print(self.taba + vol['desc'])

        except Exception as e:
            self.__print_error("__print_core_compute_volume_groups", e)

    ##########################################################################
    # print compute boot volume not attached
    ##########################################################################
    def __print_core_compute_boot_vol_not_attached(self, vols):

        try:
            if len(vols) == 0:
                return

            self.print_header("Block Boot Not Attached", 2)
            for vol in vols:
                print(self.taba + vol['desc'])

        except Exception as e:
            self.__print_error("__print_core_compute_boot_vol_not_attached", e)

    ##########################################################################
    # print Compute
    ##########################################################################
    def __print_core_compute_main(self, data):

        try:
            if len(data) == 0:
                return

            if 'instances' in data:
                self.__print_core_compute_instances(data['instances'])

            if 'images' in data:
                self.__print_core_compute_images(data['images'])

            if 'boot_not_attached' in data:
                self.__print_core_compute_boot_vol_not_attached(data['boot_not_attached'])

            if 'volume_not_attached' in data:
                self.__print_core_compute_volume_not_attached(data['volume_not_attached'])

            if 'volume_group' in data:
                self.__print_core_compute_volume_groups(data['volume_group'])

        except Exception as e:
            self.__print_error("__print_core_compute_main", e)

    ##########################################################################
    # Print Identity data
    ##########################################################################
    def __print_region_data(self, region_name, data):

        try:
            if not data:
                return

            for cdata in data:
                if 'path' in cdata:
                    self.print_header("Compartment " + cdata['path'], 1)
                if 'network' in cdata:
                    self.__print_core_network_main(cdata['network'])
                if 'compute' in cdata:
                    self.__print_core_compute_main(cdata['compute'])
                if 'database' in cdata:
                    self.__print_database_main(cdata['database'])

        except Exception as e:
            self.__print_error("__print_region_data", e)
            raise


##########################################################################
# check OCI version
##########################################################################
if sys.version_info.major < 3:
    python_version = str(sys.version_info.major) + "." + str(sys.version_info.minor)
    print("******************************************************")
    print("***    Showoci only supports Python 3 or Above     ***")
    print("***             Current Version = " + python_version.ljust(16) + " ***")
    print("******************************************************")
    sys.exit()


##########################################################################
# execute_extract
##########################################################################
def execute_extract():

    # get parset cmd
    cmd = set_parser_arguments()
    if cmd is None:
        return

    # Start time
    start_time = str(datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

    # get flags object for calling cache
    flags = set_service_extract_flags(cmd)

    ############################################
    # create data instance
    ############################################
    data = ShowOCIData(flags)

    ############################################
    # output and summary instances
    ############################################
    output = ShowOCIOutput()

    ############################################
    # print showoci config
    ############################################
    cmdline = ' '.join(x for x in sys.argv[1:])
    showoci_config = data.get_showoci_config(cmdline, start_time)
    output.print_showoci_config(showoci_config['data'])

    ############################################
    # load oci data to cache
    ############################################
    output.print_header('Load OCI data to Memory', 1)

    if not data.load_service_data():
        return

    ############################################
    # if print service data to file or screen
    ############################################
    if cmd.servicefile or cmd.servicescr:
        if cmd.servicefile:
            if cmd.servicefile.name:
                print_to_json_file(cmd.servicefile.name, data.get_service_data(), "Service Data")

        elif cmd.servicescr:
            print(json.dumps(data.get_service_data(), indent=4, sort_keys=False))

    else:
        ############################################
        # process the data into data json
        ############################################
        output.print_header("Start Processing Data", 1)
        extracted_data = data.process_oci_data()

        ############################################
        # if JSON and screen
        ############################################
        if cmd.sjoutfile:
            # print nice
            output.print_data(extracted_data)

            # Add summary to JSON and print to JSON file
            if cmd.sjoutfile.name:
                print_to_json_file(output, cmd.sjoutfile.name, extracted_data, "JSON Data")

        ############################################
        # JSON File only
        ############################################
        elif cmd.joutfile:
            if cmd.joutfile.name:
                print_to_json_file(output, cmd.joutfile.name, extracted_data, "JSON Data")

        ############################################
        # JSON to screen only
        ############################################
        elif cmd.joutscr:
            print(json.dumps(extracted_data, indent=4, sort_keys=False))

        ############################################
        # print nice output as default to screen
        # and summary
        ############################################
        else:
            output.print_data(extracted_data)

    ############################################
    # print completion
    ############################################
    service_errors = data.get_service_errors()
    service_warnings = data.get_service_warnings()
    output_errors = output.get_errors()
    complete_message = return_error_message(service_errors, service_warnings, data.error, output_errors)

    # if reboot migration
    if data.get_service_reboot_migration() > 0:
        output.print_header(str(data.get_service_reboot_migration()) + " Reboot Migration Alert for Compute or DB Node", 0)

    # if dbsystem maintenance
    if data.get_service_dbsystem_maintenance():
        output.print_header("DB System Maintenance", 0)
        for alert in data.get_service_dbsystem_maintenance():
            print(alert)

    # print completion
    output.print_header("Completed " + complete_message + " at " + str(datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")), 0)


##########################################################################
# compile the error message
##########################################################################
def return_error_message(service_error, service_warning, data_error, output_error):

    complete_message = "Successfully"

    if service_error > 0 or service_warning > 0 or data_error > 0 or output_error > 0:
        complete_message = "With "

        if service_error > 0:
            complete_message += str(service_error) + "x(Service Errors) "

        if service_warning > 0:
            complete_message += str(service_warning) + "x(Service Warnings) "

        if data_error > 0:
            complete_message += str(data_error) + " (Processing Errors) "

        if output_error > 0:
            complete_message += str(output_error) + "x(Output Errors) "

    return complete_message


##########################################################################
# set parser
##########################################################################
def set_parser_arguments():
    parser = argparse.ArgumentParser()
    parser.add_argument('-a', action='store_true', default=False, dest='all', help='Print All Resources')
    parser.add_argument('-ani', action='store_true', default=False, dest='allnoiam', help='Print All Resources but identity')
    parser.add_argument('-c', action='store_true', default=False, dest='compute', help='Print Compute')
    parser.add_argument('-d', action='store_true', default=False, dest='database', help='Print Database')
    parser.add_argument('-i', action='store_true', default=False, dest='identity', help='Print Identity')
    parser.add_argument('-ic', action='store_true', default=False, dest='identity_compartments', help='Print Identity Compartments only')
    parser.add_argument('-n', action='store_true', default=False, dest='network', help='Print Network')
    parser.add_argument('-mc', action='store_true', default=False, dest='mgdcompart', help='exclude ManagedCompartmentForPaaS')

    parser.add_argument('-ip', action='store_true', default=False, dest='instance_principals', help='Use Instance Principals for Authentication')
    parser.add_argument('-dt', action='store_true', default=False, dest='delegation_token', help='Use Delegation Token (Cloud shell)')
    parser.add_argument('-t', default="", dest='profile', help='Config file section to use (tenancy profile)')
    parser.add_argument('-p', default="", dest='proxy', help='Set Proxy (i.e. www-proxy-server.com:80) ')
    parser.add_argument('-rg', default="", dest='region', help='Filter by Region')
    parser.add_argument('-cp', default="", dest='compart', help='Filter by Compartment Name or OCID')
    parser.add_argument('-cpr', default="", dest='compart_recur', help='Filter by Comp Name Recursive')
    parser.add_argument('-cpath', default="", dest='compartpath', help='Filter by Compartment path ,(i.e. -cpath "Adi / Sub"')
    parser.add_argument('-tenantid', default="", dest='tenantid', help='Override confile file tenancy_id')
    parser.add_argument('-cf', default="", dest='config', help="Config File (~/.oci/config)")
    parser.add_argument('-jf', type=argparse.FileType('w'), dest='joutfile', help="Output to file   (JSON format)")
    parser.add_argument('-js', action='store_true', default=False, dest='joutscr', help="Output to screen (JSON format)")
    parser.add_argument('-sjf', type=argparse.FileType('w'), dest='sjoutfile', help="Output to screen (nice format) and JSON File")
    parser.add_argument('-cachef', type=argparse.FileType('w'), dest='servicefile', help="Output Cache to file   (JSON format)")
    parser.add_argument('-caches', action='store_true', default=False, dest='servicescr', help="Output Cache to screen (JSON format)")
    parser.add_argument('--version', action='version', version='%(prog)s ' + version)

    result = parser.parse_args()

    if len(sys.argv) < 2:
        parser.print_help()
        return None

    if not (result.all or result.allnoiam or result.network or result.identity or result.identity_compartments or
            result.compute or result.database):

        parser.print_help()

        print("******************************************************")
        print("***    You must choose at least one parameter!!    ***")
        print("******************************************************")
        return None

    return result


##########################################################################
# set cache flags for extract
##########################################################################
def set_service_extract_flags(cmd):

    prm = ShowOCIFlags()

    prm.showoci_version = version

    if cmd.proxy:
        prm.proxy = cmd.proxy

    if cmd.mgdcompart:
        prm.read_ManagedCompartmentForPaaS = False

    if cmd.all or cmd.identity:
        prm.read_identity = True

    if cmd.all or cmd.allnoiam or cmd.network:
        prm.read_network = True

    if cmd.all or cmd.allnoiam or cmd.compute:
        prm.read_compute = True

    if cmd.all or cmd.allnoiam or cmd.database:
        prm.read_database = True

    if cmd.config:
        if cmd.config.name:
            prm.config_file = cmd.config.name

    if cmd.profile:
        prm.config_section = cmd.profile

    if cmd.region:
        prm.filter_by_region = str(cmd.region)

    if cmd.compart:
        prm.filter_by_compartment = str(cmd.compart)

    if cmd.compart_recur:
        prm.filter_by_compartment_recursive = str(cmd.compart_recur)

    if cmd.compartpath:
        prm.filter_by_compartment_path = str(cmd.compartpath)

    if cmd.instance_principals:
        prm.use_instance_principals = True

    if cmd.delegation_token:
        prm.use_delegation_token = True

    if cmd.tenantid:
        prm.filter_by_tenancy_id = cmd.tenantid

    return prm


############################################
# print data to json file
############################################
def print_to_json_file(output, file_name, data, header):

    with open(file_name, 'w') as outfile:
        json.dump(data, outfile, indent=4, sort_keys=False)

    output.print_header(header + " exported to " + file_name, 0)


##########################################################################
# Main
##########################################################################
execute_extract()
