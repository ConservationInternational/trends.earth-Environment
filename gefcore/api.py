"""API """

import os
import tempfile
import json
import gzip
from pathlib import Path

import rollbar

rollbar.init(os.getenv('ROLLBAR_SCRIPT_TOKEN'), os.getenv('ENV'))

import boto3

import requests

API_URL = os.getenv('API_URL', None)
EMAIL = os.getenv('API_USER', None)
PASSWORD = os.getenv('API_PASSWORD', None)
EXECUTION_ID = os.getenv('EXECUTION_ID', None)
PARAMS_S3_PREFIX = os.getenv('PARAMS_S3_PREFIX', None)
PARAMS_S3_BUCKET = os.getenv('PARAMS_S3_BUCKET', None)


def login():
    response = requests.post(API_URL + '/auth',
                             json={
                                 "email": EMAIL,
                                 "password": PASSWORD
                             })

    if response.status_code != 200:
        print('Error login.')
        print(response)
        rollbar.report_message('Error logging in',
                               extra_data={'response': response.json()})
        raise Exception('Error logging in')

    return response.json()['access_token']


def _get_params_from_s3(out_path):
    object_name = PARAMS_S3_PREFIX + '/' + EXECUTION_ID + '.json.gz'
    s3 = boto3.client('s3')
    s3.download_file(PARAMS_S3_BUCKET, object_name, str(out_path))


def get_params():
    with tempfile.TemporaryDirectory() as temp_dir:
        params_gz_file = Path(temp_dir) / (str(EXECUTION_ID) + '.json.gz')
        _get_params_from_s3(params_gz_file)
        with gzip.open(params_gz_file, 'r') as fin:
            json_bytes = fin.read() 
            json_str = json_bytes.decode('utf-8')
            params = json.loads(json_str)    

    if params is None:
        print('Error getting parameters')
        rollbar.report_message('Error getting parameters')
        return None
    else:
        return params


def patch_execution(json):
    jwt = login()
    response = requests.patch(API_URL + '/api/v1/execution/' + EXECUTION_ID,
                              json=json,
                              headers={'Authorization': 'Bearer ' + jwt})

    if response.status_code != 200:
        print('Error patching execution')
        rollbar.report_message('Error patching execution',
                               extra_data={'response': response.json()})
        print(response)


def save_log(json):
    jwt = login()
    response = requests.post(API_URL + '/api/v1/execution/' + EXECUTION_ID +
                             '/log',
                             json=json,
                             headers={'Authorization': 'Bearer ' + jwt})

    if response.status_code != 200:
        print('Error saving log')
        rollbar.report_message('Error saving log',
                               extra_data={'response': response.json()})
        print(response)
