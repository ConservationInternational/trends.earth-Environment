"""API """

import os

import requests

API_URL = os.getenv('API_URL', None)
EMAIL = os.getenv('API_USER', None)
PASSWORD = os.getenv('API_PASSWORD', None)
EXECUTION_ID = os.getenv('EXECUTION_ID', None)


def login():
    response = requests.post(API_URL + '/auth',
                             json={
                                 "email": EMAIL,
                                 "password": PASSWORD
                             })

    if response.status_code != 200:
        print('Error login.')
        print(response)
        raise Exception('Error logging in')

    return response.json()['access_token']


def get_params():
    jwt = login()
    response = requests.get(API_URL + '/api/v1/execution/' + EXECUTION_ID,
                            headers={'Authorization': 'Bearer ' + jwt})

    if response.status_code != 200:
        print('Error getting parameters')
        return None
    else:
        return response.json()['data']['params']


def patch_execution(json):
    jwt = login()
    response = requests.patch(API_URL + '/api/v1/execution/' + EXECUTION_ID,
                              json=json,
                              headers={'Authorization': 'Bearer ' + jwt})

    if response.status_code != 200:
        print('Error patching execution')
        print(response)


def save_log(json):
    jwt = login()
    response = requests.post(API_URL + '/api/v1/execution/' + EXECUTION_ID +
                             '/log',
                             json=json,
                             headers={'Authorization': 'Bearer ' + jwt})

    if response.status_code != 200:
        print('Error doing request.')
        print(response)
