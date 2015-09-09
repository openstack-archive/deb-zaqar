# Copyright 2015 Red Hat, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or
# implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import datetime

import falcon
from oslo_serialization import jsonutils
from oslo_utils import timeutils

from zaqar.common import urls
from zaqar.tests.unit.transport.wsgi import base


class TestURL(base.V2Base):

    config_file = 'wsgi_mongodb.conf'

    def setUp(self):
        super(TestURL, self).setUp()

        self.signed_url_prefix = self.url_prefix + '/queues/shared_queue/share'

    def test_url_generation(self):
        timeutils.set_time_override()
        self.addCleanup(timeutils.clear_time_override)

        data = {'methods': ['GET', 'POST']}
        response = self.simulate_post(self.signed_url_prefix,
                                      body=jsonutils.dumps(data))

        self.assertEqual(self.srmock.status, falcon.HTTP_200)
        content = jsonutils.loads(response[0])

        expires = timeutils.utcnow(True) + datetime.timedelta(days=1)
        expires_str = expires.strftime(urls._DATE_FORMAT)

        for field in ['signature', 'project', 'methods', 'path', 'expires']:
            self.assertIn(field, content)

        self.assertEqual(expires_str, content['expires'])
        self.assertEqual(data['methods'], content['methods'])

    def test_url_bad_request(self):
        self.simulate_post(self.signed_url_prefix, body='not json')
        self.assertEqual(self.srmock.status, falcon.HTTP_400)

        data = {'dummy': 'meh'}
        self.simulate_post(self.signed_url_prefix, body=jsonutils.dumps(data))
        self.assertEqual(self.srmock.status, falcon.HTTP_400)

        data = {'expires': 'wrong date format'}
        self.simulate_post(self.signed_url_prefix, body=jsonutils.dumps(data))
        self.assertEqual(self.srmock.status, falcon.HTTP_400)

        data = {'methods': 'methods not list'}
        self.simulate_post(self.signed_url_prefix, body=jsonutils.dumps(data))
        self.assertEqual(self.srmock.status, falcon.HTTP_400)

    def test_url_verification_success(self):
        data = {'methods': ['GET', 'POST']}
        response = self.simulate_post(self.signed_url_prefix,
                                      body=jsonutils.dumps(data))

        self.assertEqual(self.srmock.status, falcon.HTTP_200)
        content = jsonutils.loads(response[0])

        headers = {
            'URL-Signature': content['signature'],
            'URL-Expires': content['expires'],
            'URL-Methods': ','.join(content['methods'])
        }
        headers.update(self.headers)
        response = self.simulate_get(content['path'], headers=headers)
        self.assertEqual(self.srmock.status, falcon.HTTP_200)

    def test_url_verification_bad_request(self):
        path = self.url_prefix + '/queues/shared_queue/messages'
        expires = timeutils.utcnow() + datetime.timedelta(days=1)
        expires_str = expires.strftime(urls._DATE_FORMAT)

        headers = {
            'URL-Signature': 'dummy',
            'URL-Expires': 'not a real date',
            'URL-Methods': 'GET,POST'
        }
        headers.update(self.headers)
        self.simulate_get(path, headers=headers)
        self.assertEqual(self.srmock.status, falcon.HTTP_404)

        headers = {
            'URL-Signature': 'dummy',
            'URL-Expires': expires_str,
            'URL-Methods': ''
        }
        headers.update(self.headers)
        self.simulate_get(path, headers=headers)
        self.assertEqual(self.srmock.status, falcon.HTTP_404)

        headers = {
            'URL-Signature': 'dummy',
            'URL-Expires': expires_str,
            'URL-Methods': 'nothing here'
        }
        headers.update(self.headers)
        self.simulate_get(path, headers=headers)
        self.assertEqual(self.srmock.status, falcon.HTTP_404)

        headers = {
            'URL-Signature': 'dummy',
            'URL-Expires': expires_str,
            'URL-Methods': 'POST,PUT'
        }
        headers.update(self.headers)
        self.simulate_get(path, headers=headers)
        self.assertEqual(self.srmock.status, falcon.HTTP_404)

        headers = {
            'URL-Signature': 'wrong signature',
            'URL-Expires': expires_str,
            'URL-Methods': 'GET,POST'
        }
        headers.update(self.headers)
        self.simulate_get(path, headers=headers)
        self.assertEqual(self.srmock.status, falcon.HTTP_404)

        headers = {
            'URL-Signature': 'will fail because of the old date',
            'URL-Expires': '2015-01-01T00:00:00',
            'URL-Methods': 'GET,POST'
        }
        headers.update(self.headers)
        self.simulate_get(path, headers=headers)
        self.assertEqual(self.srmock.status, falcon.HTTP_404)
