# Copyright (c) 2013 Rackspace, Inc.
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

import falcon
from oslo_log import log as logging
import six

from zaqar.i18n import _
from zaqar.storage import errors as storage_errors
from zaqar.transport import acl
from zaqar.transport import utils
from zaqar.transport import validation
from zaqar.transport.wsgi import errors as wsgi_errors
from zaqar.transport.wsgi import utils as wsgi_utils

LOG = logging.getLogger(__name__)


class ItemResource(object):

    __slots__ = ('_validate', '_queue_controller', '_message_controller')

    def __init__(self, validate, queue_controller, message_controller):
        self._validate = validate
        self._queue_controller = queue_controller
        self._message_controller = message_controller

    @acl.enforce("queues:get")
    def on_get(self, req, resp, project_id, queue_name):
        LOG.debug(u'Queue metadata GET - queue: %(queue)s, '
                  u'project: %(project)s',
                  {'queue': queue_name, 'project': project_id})

        try:
            resp_dict = self._queue_controller.get(queue_name,
                                                   project=project_id)

        except storage_errors.DoesNotExist as ex:
            LOG.debug(ex)
            raise falcon.HTTPNotFound()

        except Exception as ex:
            LOG.exception(ex)
            description = _(u'Queue metadata could not be retrieved.')
            raise wsgi_errors.HTTPServiceUnavailable(description)

        resp.body = utils.to_json(resp_dict)
        # status defaults to 200

    @acl.enforce("queues:create")
    def on_put(self, req, resp, project_id, queue_name):
        LOG.debug(u'Queue item PUT - queue: %(queue)s, '
                  u'project: %(project)s',
                  {'queue': queue_name, 'project': project_id})

        try:
            # Place JSON size restriction before parsing
            self._validate.queue_metadata_length(req.content_length)
        except validation.ValidationFailed as ex:
            LOG.debug(ex)
            raise wsgi_errors.HTTPBadRequestAPI(six.text_type(ex))

        # Deserialize queue metadata
        metadata = None
        if req.content_length:
            document = wsgi_utils.deserialize(req.stream, req.content_length)
            metadata = wsgi_utils.sanitize(document, spec=None)

        try:
            created = self._queue_controller.create(queue_name,
                                                    metadata=metadata,
                                                    project=project_id)

        except storage_errors.FlavorDoesNotExist as ex:
            LOG.exception(ex)
            raise wsgi_errors.HTTPBadRequestAPI(six.text_type(ex))

        except Exception as ex:
            LOG.exception(ex)
            description = _(u'Queue could not be created.')
            raise wsgi_errors.HTTPServiceUnavailable(description)

        resp.status = falcon.HTTP_201 if created else falcon.HTTP_204
        resp.location = req.path

    @acl.enforce("queues:delete")
    def on_delete(self, req, resp, project_id, queue_name):
        LOG.debug(u'Queue item DELETE - queue: %(queue)s, '
                  u'project: %(project)s',
                  {'queue': queue_name, 'project': project_id})
        try:
            self._queue_controller.delete(queue_name, project=project_id)

        except Exception as ex:
            LOG.exception(ex)
            description = _(u'Queue could not be deleted.')
            raise wsgi_errors.HTTPServiceUnavailable(description)

        resp.status = falcon.HTTP_204


class CollectionResource(object):

    __slots__ = ('_queue_controller', '_validate')

    def __init__(self, validate, queue_controller):
        self._queue_controller = queue_controller
        self._validate = validate

    @acl.enforce("queues:get_all")
    def on_get(self, req, resp, project_id):
        LOG.debug(u'Queue collection GET - project: %(project)s',
                  {'project': project_id})

        kwargs = {}

        # NOTE(kgriffs): This syntax ensures that
        # we don't clobber default values with None.
        req.get_param('marker', store=kwargs)
        req.get_param_as_int('limit', store=kwargs)
        req.get_param_as_bool('detailed', store=kwargs)

        try:
            self._validate.queue_listing(**kwargs)
            results = self._queue_controller.list(project=project_id, **kwargs)

        except validation.ValidationFailed as ex:
            LOG.debug(ex)
            raise wsgi_errors.HTTPBadRequestAPI(six.text_type(ex))

        except Exception as ex:
            LOG.exception(ex)
            description = _(u'Queues could not be listed.')
            raise wsgi_errors.HTTPServiceUnavailable(description)

        # Buffer list of queues
        queues = list(next(results))

        # Got some. Prepare the response.
        kwargs['marker'] = next(results) or kwargs.get('marker', '')
        for each_queue in queues:
            each_queue['href'] = req.path + '/' + each_queue['name']

        links = []
        if queues:
            links = [
                {
                    'rel': 'next',
                    'href': req.path + falcon.to_query_str(kwargs)
                }
            ]

        response_body = {
            'queues': queues,
            'links': links
        }

        resp.body = utils.to_json(response_body)
        # status defaults to 200
