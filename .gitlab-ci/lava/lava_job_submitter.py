#!/usr/bin/env python3
#
# Copyright (C) 2020, 2021 Collabora Limited
# Author: Gustavo Padovan <gustavo.padovan@collabora.com>
#
# Permission is hereby granted, free of charge, to any person obtaining a
# copy of this software and associated documentation files (the "Software"),
# to deal in the Software without restriction, including without limitation
# the rights to use, copy, modify, merge, publish, distribute, sublicense,
# and/or sell copies of the Software, and to permit persons to whom the
# Software is furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice (including the next
# paragraph) shall be included in all copies or substantial portions of the
# Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.  IN NO EVENT SHALL
# THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

"""Send a job to LAVA, track it and collect log back"""

import argparse
import jinja2
import lavacli
import os
import sys
import time
import traceback
import urllib.parse
import xmlrpc
import yaml

from datetime import datetime
from lavacli.utils import loader


def print_log(msg):
    print("{}: {}".format(datetime.now(), msg))

def fatal_err(msg):
    print_log(msg)
    sys.exit(1)

def generate_lava_yaml(args):
    env = jinja2.Environment(loader = jinja2.FileSystemLoader(os.path.dirname(args.template)), trim_blocks=True, lstrip_blocks=True)
    template = env.get_template(os.path.basename(args.template))

    values = {}
    values['pipeline_info'] = args.pipeline_info
    values['base_system_url_prefix'] = args.base_system_url_prefix
    values['mesa_build_url'] = args.mesa_build_url
    values['job_rootfs_overlay_url'] = args.job_rootfs_overlay_url
    values['job_artifacts_base'] = args.job_artifacts_base
    values['device_type'] = args.device_type
    values['dtb'] = args.dtb
    values['kernel_image_name'] = args.kernel_image_name
    values['kernel_image_type'] = args.kernel_image_type
    values['boot_method'] = args.boot_method
    values['tags'] = args.lava_tags

    if args.dump_yaml:
        dump_values = values
        dump_values['jwt'] = 'xxx'
        print(template.render(dump_values))

    values['jwt'] = args.jwt
    yaml = template.render(values)

    return yaml


def setup_lava_proxy():
    config = lavacli.load_config("default")
    uri, usr, tok = (config.get(key) for key in ("uri", "username", "token"))
    uri_obj = urllib.parse.urlparse(uri)
    uri_str = "{}://{}:{}@{}{}".format(uri_obj.scheme, usr, tok, uri_obj.netloc, uri_obj.path)
    transport = lavacli.RequestsTransport(
        uri_obj.scheme,
        config.get("proxy"),
        config.get("timeout", 120.0),
        config.get("verify_ssl_cert", True),
    )
    proxy = xmlrpc.client.ServerProxy(
        uri_str, allow_none=True, transport=transport)

    print_log("Proxy for {} created.".format(config['uri']))

    return proxy


def _call_proxy(fn, *args):
    retries = 60
    for n in range(1, retries + 1):
        try:
            return fn(*args)
        except xmlrpc.client.ProtocolError as err:
            if n == retries:
                traceback.print_exc()
                fatal_err("A protocol error occurred (Err {} {})".format(err.errcode, err.errmsg))
            else:
                time.sleep(15)
                pass
        except xmlrpc.client.Fault as err:
            traceback.print_exc()
            fatal_err("FATAL: Fault: {} (code: {})".format(err.faultString, err.faultCode))


def get_job_results(proxy, job_id, test_suite, test_case):
    # Look for infrastructure errors and retry if we see them.
    results_yaml = _call_proxy(proxy.results.get_testjob_results_yaml, job_id)
    results = yaml.load(results_yaml, Loader=loader(False))
    for res in results:
        metadata = res['metadata']
        if not 'result' in metadata or metadata['result'] != 'fail':
            continue
        if 'error_type' in metadata and metadata['error_type'] == "Infrastructure":
            print_log("LAVA job {} failed with Infrastructure Error. Retry.".format(job_id))
            return False
        if 'case' in metadata and metadata['case'] == "validate":
            print_log("LAVA job {} failed validation (possible download error). Retry.".format(job_id))
            return False

    results_yaml = _call_proxy(proxy.results.get_testcase_results_yaml, job_id, test_suite, test_case)
    results = yaml.load(results_yaml, Loader=loader(False))
    if not results:
        fatal_err("LAVA: no result for test_suite '{}', test_case '{}'".format(test_suite, test_case))

    print_log("LAVA: result for test_suite '{}', test_case '{}': {}".format(test_suite, test_case, results[0]['result']))
    if results[0]['result'] != 'pass':
        fatal_err("FAIL")

    return True


def follow_job_execution(proxy, job_id):
    line_count = 0
    finished = False
    while not finished:
        (finished, data) = _call_proxy(proxy.scheduler.jobs.logs, job_id, line_count)
        logs = yaml.load(str(data), Loader=loader(False))
        if logs:
            for line in logs:
                print("{} {}".format(line["dt"], line["msg"]))

            line_count += len(logs)


def show_job_data(proxy, job_id):
    show = _call_proxy(proxy.scheduler.jobs.show, job_id)
    for field, value in show.items():
        print("{}\t: {}".format(field, value))


def validate_job(proxy, job_file):
    try:
        return _call_proxy(proxy.scheduler.jobs.validate, job_file, True)
    except:
        return False

def submit_job(proxy, job_file):
    return _call_proxy(proxy.scheduler.jobs.submit, job_file)


def main(args):
    proxy = setup_lava_proxy()

    yaml_file = generate_lava_yaml(args)

    if args.validate_only:
        ret = validate_job(proxy, yaml_file)
        if not ret:
            fatal_err("Error in LAVA job definition")
        print("LAVA job definition validated successfully")
        return


    while True:
        job_id = submit_job(proxy, yaml_file)

        print_log("LAVA job id: {}".format(job_id))

        follow_job_execution(proxy, job_id)

        show_job_data(proxy, job_id)

        if get_job_results(proxy,  job_id, "0_mesa", "mesa") == True:
             break


if __name__ == '__main__':
    # given that we proxy from DUT -> LAVA dispatcher -> LAVA primary -> us ->
    # GitLab runner -> GitLab primary -> user, safe to say we don't need any
    # more buffering
    sys.stdout.reconfigure(line_buffering=True)
    sys.stderr.reconfigure(line_buffering=True)
    parser = argparse.ArgumentParser("LAVA job submitter")

    parser.add_argument("--template")
    parser.add_argument("--pipeline-info")
    parser.add_argument("--base-system-url-prefix")
    parser.add_argument("--mesa-build-url")
    parser.add_argument("--job-rootfs-overlay-url")
    parser.add_argument("--job-artifacts-base")
    parser.add_argument("--device-type")
    parser.add_argument("--dtb", nargs='?', default="")
    parser.add_argument("--kernel-image-name")
    parser.add_argument("--kernel-image-type", nargs='?', default="")
    parser.add_argument("--boot-method")
    parser.add_argument("--lava-tags", nargs='?', default="")
    parser.add_argument("--jwt")
    parser.add_argument("--validate-only", action='store_true')
    parser.add_argument("--dump-yaml", action='store_true')

    parser.set_defaults(func=main)
    args = parser.parse_args()
    args.func(args)