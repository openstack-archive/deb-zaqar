# Copyright (c) 2015 Red Hat, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may not
# use this file except in compliance with the License.  You may obtain a copy
# of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations under
# the License.

from zaqar.api.v1_1 import endpoints
from zaqar.api.v1_1 import request as schema_validator

from zaqar.common.api import request
from zaqar.common.api import response
from zaqar.common import errors


class Handler(object):
    """Defines API handler

    The handler validates and process the requests
    """

    def __init__(self, storage, control, validate, defaults):
        self.v1_1_endpoints = endpoints.Endpoints(storage, control,
                                                  validate, defaults)

    def process_request(self, req):
        # FIXME(vkmc): Control API version
        return getattr(self.v1_1_endpoints, req._action)(req)

    @staticmethod
    def validate_request(payload, req):
        """Validate a request and its payload against a schema.

        :return: a Response object if validation failed, None otherwise.
        """
        try:
            action = payload.get('action')
            validator = schema_validator.RequestSchema()
            is_valid = validator.validate(action=action, body=payload)
        except errors.InvalidAction as ex:
            body = {'error': str(ex)}
            headers = {'status': 400}
            return response.Response(req, body, headers)
        else:
            if not is_valid:
                body = {'error': 'Schema validation failed.'}
                headers = {'status': 400}
                return response.Response(req, body, headers)

    def create_response(self, code, body, req=None):
        if req is None:
            req = self.create_request()
        headers = {'status': code}
        return response.Response(req, body, headers)

    @staticmethod
    def create_request(payload=None):
        if payload is None:
            payload = {}
        action = payload.get('action')
        body = payload.get('body', {})
        headers = payload.get('headers')

        return request.Request(action=action, body=body,
                               headers=headers, api="v1.1")
